"""Portable historical evidence replay. No HTTP, database or model inference."""
from __future__ import annotations
import argparse
import copy
import gzip
import hashlib
import importlib.abc
import importlib.machinery
import json
import os
import sys
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace
from contextlib import nullcontext

ROOT = Path(__file__).resolve().parent
PINNED_SOURCE_ZIP = "1b1a163a40e4bc7883b204e0ef48b0c4bd40a8d82a8051c6039c40112f53e142"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def hashes():
    sums = ROOT / "SHA256SUMS"
    checked = 0
    listed = set()
    for line in sums.read_text().splitlines():
        digest, name = line.split("  ", 1)
        if name in listed:
            raise ValueError("Duplicate manifest path")
        listed.add(name)
        target = (ROOT / name).resolve()
        if not target.is_relative_to(ROOT) or not target.is_file():
            raise ValueError("Invalid manifest path")
        if sha(target.read_bytes()) != digest:
            raise ValueError("Changed exported artifact: " + name)
        checked += 1
    actual = {path.relative_to(ROOT).as_posix() for path in ROOT.rglob("*") if path.is_file() and path != sums}
    if actual != listed:
        raise ValueError("Export manifest omits or adds a file")
    manifest = read(ROOT / "manifest.json")
    if set(manifest["files"]) != actual - {"manifest.json"}:
        raise ValueError("Export inventory membership differs from checksum manifest")
    for name, record in manifest["files"].items():
        data = (ROOT / name).read_bytes()
        if record != {"sha256": sha(data), "bytes": len(data)}:
            raise ValueError("Export inventory record differs: " + name)
    source = ROOT / "verifier/source27-api.zip"
    if sha(source.read_bytes()) != PINNED_SOURCE_ZIP:
        raise ValueError("Historical verifier source archive differs from pin")
    source_files = read(ROOT / "verifier/source27-manifest.json")["files"]
    with zipfile.ZipFile(source) as archive:
        if set(archive.namelist()) != set(source_files) or len(source_files) != 226:
            raise ValueError("Historical source archive membership differs")
        for name, digest in source_files.items():
            if sha(archive.read(name)) != digest:
                raise ValueError("Changed historical verifier source: " + name)
    assets = read(ROOT / "public-demo-assets/manifest.json")
    bodies = {}
    for entry in assets["files"]:
        data = (ROOT / "public-demo-assets" / entry["file"]).read_bytes()
        assert len(data) == entry["upload_bytes"] and sha(data) == entry["upload_sha256"]
        assert data.endswith(b"\n") and b"\r" not in data
        body = data.decode()[:-1]
        assert sha(body.encode()) == entry["canonical_sha256"]
        bodies[entry["canonical_sha256"]] = body
    return {"export_files_hashed": checked, "historical_source_files_hashed": 226}, bodies


def canonical_replay():
    # Import directly from the sealed ZIP: no extraction, temporary ACL or current checkout.
    with nullcontext((ROOT / "verifier/source27-api.zip").resolve()) as base:
        with zipfile.ZipFile(ROOT / "verifier/source27-api.zip") as archive:
            member_names = set(archive.namelist())
            for member in archive.infolist():
                target = (base / member.filename).resolve()
                if not target.is_relative_to(base):
                    raise ValueError("Unsafe historical source member")
        sys.path.insert(0, str(base / "apps/api"))
        # The frozen archive omits directory entries for implicit namespace packages.
        # Supply only their import locations; every executable source byte remains pinned.
        class HistoricalNamespaces(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if not fullname.startswith("app."):
                    return None
                relative = "apps/api/" + fullname.replace(".", "/")
                if relative + "/__init__.py" in member_names:
                    return None
                if any(name.startswith(relative + "/") for name in member_names):
                    found = importlib.machinery.ModuleSpec(fullname, loader=None, is_package=True)
                    found.submodule_search_locations = [str(base) + "/" + relative]
                    return found
                return None
        sys.meta_path.insert(0, HistoricalNamespaces())
        os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        # Imports are pure verifier/context helpers. No SQL connection or model is used.
        from app.services.procedure_output import verify_output
        from app.services.document.source_context import validated_snapshot_context
        from app.services.requirement_contract import validate_discovery_lineage

        assert Path(sys.modules["app.services.procedure_output"].__file__).resolve().is_relative_to(base)
        assert "torch" not in sys.modules and "transformers" not in sys.modules
        version_data = json.loads(gzip.decompress((ROOT / "public-source-snapshots.json.gz").read_bytes()))["versions"]
        with zipfile.ZipFile(ROOT / "actual-records.zip") as archive:
            records = {name: json.loads(archive.read(name)) for name in archive.namelist()}
        completed = refused = source_checks = tamper_rejections = 0

        def verify_record(record):
            nonlocal completed, tamper_rejections
            assert record["outcome"] == "completed" and record["refused"] is False
            selection = record["provenance"]["answer_selection"]
            captured = record["retrieval_trace"]["provenance"]["answer_selection"]
            metadata = {entry["document_id"]: {key: entry[key] for key in ("condition", "conflict_group")} for entry in captured.get("procedure_read_set", {}).get("sources", [])}
            snapshots = {}
            identities = selection["inspected_sources"] + [row["procedure_completeness"] for row in selection["requirements"]]
            for identity in identities:
                identifier = identity["document_id"]
                key = f"{identifier}:{identity['document_version']}:{identity['content_hash']}"
                version = version_data[key]
                assert sha(version["body"].encode()) == version["content_hash"]
                snapshot = SimpleNamespace(
                    chunks=version["chunks"], normalized_content=version["body"],
                    content_hash=version["content_hash"], document_id=uuid.UUID(identifier),
                    workspace_id=version["workspace_id"], version_number=version["document_version"],
                )
                snapshots[identifier] = {**version, "captured_scope": validated_snapshot_context(snapshot), "metadata": metadata.get(identifier, {})}
            context = {"question": record["question"], "answer": record["answer"], "citations": record["sources"], "source_snapshots": snapshots, "query_context": record["retrieval_trace"]}
            assert validate_discovery_lineage(selection)["valid"] is True
            assert verify_output(selection, **context)
            changed = copy.deepcopy(selection)
            changed["requirements"][0]["procedure_completeness"]["output_certificate"]["answer_sha256"] = "0" * 64
            assert not verify_output(changed, **context)
            assert not verify_output(selection, **{**context, "answer": record["answer"] + " fabricated"})
            completed += 1
            tamper_rejections += 2
            return snapshots

        original = {}
        for name, record in sorted(records.items()):
            if not name.startswith("connected/") or "-source-" in name:
                continue
            original[record["id"]] = record
            if record["outcome"] == "refused":
                assert record["refused"] is True and record["answer"] is None and record["sources"] == []
                refused += 1
                continue
            snapshots = verify_record(record)
            for source in record["sources"]:
                response = records[f"connected/{record['id']}-source-{source['citation_index']}.json"]
                assert all(response[key] == source[key] for key in ("document_id", "chunk_id", "document_version", "content_hash", "quoted_text", "source_status", "answer_spans"))
                assert response["passage"] == source["quoted_text"]
                snapshot = snapshots[source["document_id"]]
                assert any(chunk["id"] == source["chunk_id"] and chunk["content"] == source["quoted_text"] for chunk in snapshot["chunks"])
                for span in source["answer_spans"]:
                    assert source["quoted_text"][span["start"]:span["end"]] == span["text"]
                source_checks += 1
        assert len(original) == 12 and completed == 9 and refused == 3 and source_checks == 9
        history_equal = 0
        for phase in ("missing", "repaired"):
            for identifier, record in original.items():
                assert records[f"restart/{phase}/history-{identifier}.json"] == record
                history_equal += 1
                for source in record["sources"]:
                    suffix = f"{identifier}-source-{source['citation_index']}.json"
                    assert records[f"restart/{phase}/history-{suffix}"] == records["connected/" + suffix]
        missing_normal = records["restart/missing/normal.json"]
        missing_stream = records["restart/missing/stream.json"]
        assert missing_normal["status"] == 503
        assert missing_stream["status"] == 200 and [event["type"] for event in missing_stream["events"]] == ["error"]
        errors = [record for name, record in records.items() if name.startswith("restart/missing/new-error-")]
        assert len(errors) == 2
        for record in errors:
            assert record["outcome"] == "error" and record["refused"] is False and record["answer"] is None and record["sources"] == []
        normal = records["restart/repaired/normal.json"]
        stream = records["restart/repaired/stream.json"]
        assert normal["status"] == stream["status"] == 200
        done = [event for event in stream["events"] if event["type"] == "done"]
        assert len(done) == 1 and not any(event["type"] == "error" for event in stream["events"])
        done = done[0]
        assert "".join(event["content"] for event in stream["events"] if event["type"] == "token") == done["answer"] == normal["body"]["answer"]
        citations = next(event for event in stream["events"] if event["type"] == "citations")
        assert citations["sources"] == done["sources"] and citations["retrieval_trace"] == done["retrieval_trace"]
        cedar = next(record for record in original.values() if record["outcome"] == "completed" and "Cedar" in record["question"])
        for record in (normal["body"], done):
            assert record["answer"] == cedar["answer"] and record["sources"] == cedar["sources"]
            verify_record(record)
        assert "torch" not in sys.modules and "transformers" not in sys.modules
        return {"canonical_completed_records": completed, "original_refusals_checked": refused, "actual_source_responses_checked": source_checks, "modified_certificate_or_answer_rejected": tamper_rejections, "old_history_DTO_equalities": history_equal, "old_source_DTO_equalities": 18, "error_records_checked": len(errors), "restart_repaired_records_verified": 2, "no_models_imported": True, "scope": "Historical captured decisions and literal output replay only; no new inference, live auth or DB observation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", action="store_true", help="Use frozen historical API verifier; needs existing API dependencies, no Torch/model assets")
    args = parser.parse_args()
    result, asset_bodies = hashes()
    versions = json.loads(gzip.decompress((ROOT / "public-source-snapshots.json.gz").read_bytes()))["versions"]
    for version in versions.values():
        assert version["body"] == asset_bodies[version["content_hash"]]
    result["public_demo_versions_bound_to_assets"] = len(versions)
    if args.canonical:
        result.update(canonical_replay())
    result["scope"] = "Portable integrity/captured-evidence replay, not new model/engineering/quality execution"
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
