#!/usr/bin/env python3
"""Evaluate frozen synthetic cases through the real local application HTTP API."""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.portfolio import load_corpus
from app.portfolio.evaluation import (
    METHODS,
    file_hash,
    read_seed,
    request_json,
    score_case,
    summarize,
)


def check_measured_settings(selection, development):
    for key in ("top_k", "refusal_threshold"):
        expected = development.get("settings", {}).get(key)
        if selection.get("settings", {}).get(key) != expected:
            raise ValueError(
                "Selected settings differ from measured development settings"
            )


def read_selection(split, selection_path, corpus_hash):
    selection = None
    if split == "held_out":
        if selection_path is None:
            raise ValueError(
                "Held-out evaluation requires a frozen development-only selection"
            )
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        if selection.get("selection_basis") != "development_only":
            raise ValueError("Selection must declare development_only")
        if selection.get("corpus_manifest_sha256") != corpus_hash:
            raise ValueError("Selection belongs to a different corpus")
        dev_path = Path(selection["development_report_path"])
        if not dev_path.is_absolute():
            dev_path = selection_path.parent / dev_path
        if file_hash(dev_path) != selection["development_report_sha256"]:
            raise ValueError("Development report checksum mismatch")
        dev = json.loads(dev_path.read_text(encoding="utf-8"))
        if (
            dev.get("split") != "development"
            or dev.get("corpus_manifest_sha256") != corpus_hash
        ):
            raise ValueError("Selection must reference matching development evidence")
        if not selection.get("frozen_at"):
            raise ValueError("Selection requires frozen_at")
        check_measured_settings(selection, dev)
    return selection


def map_documents(corpus, seed):
    docs = {}
    for document in corpus["documents"]:
        logical = document["id"]
        if logical not in seed["documents"]:
            raise ValueError(f"Seed manifest missing document {logical}")
        mapped = seed["documents"][logical]
        versions = {str(v["version_number"]): v for v in document["versions"]}
        for version, snapshot in versions.items():
            if (
                mapped.get("versions", {}).get(version, {}).get("content_hash")
                != snapshot["content_hash"]
            ):
                raise ValueError(
                    f"Seed content mismatch for {logical} version {version}"
                )
        docs[logical] = {**mapped, "versions": versions}
    return docs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--split", choices=("development", "held_out"), default="development"
    )
    parser.add_argument("--method", choices=(*METHODS, "all"), default="all")
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--expected-refusal-threshold", type=float)
    args = parser.parse_args()
    try:
        corpus = load_corpus()
        seed = read_seed(args.seed_manifest)
        corpus_hash = corpus["manifest"]["manifest_sha256"]
        selection = read_selection(args.split, args.selection, corpus_hash)
        settings = (selection or {}).get("settings", corpus["profile"])
        settings = dict(settings)
        if args.expected_refusal_threshold is not None:
            if args.split != "development":
                raise ValueError(
                    "Held-out settings come only from the frozen selection"
                )
            settings["refusal_threshold"] = args.expected_refusal_threshold
        if settings.get("top_k") != 5:
            raise ValueError("Frozen evaluation contract uses top_k=5")
        docs = map_documents(corpus, seed)
        methods = METHODS if args.method == "all" else (args.method,)
        results = {}
        for method in methods:
            rows = []
            for case in corpus["cases"]:
                if case["split"] != args.split:
                    continue
                status, response, elapsed = request_json(
                    seed,
                    case["principal"],
                    "/api/queries",
                    {
                        "question": case["question"],
                        "top_k": 5,
                        "document_ids": (
                            [docs[d]["document_id"] for d in case["document_ids"]]
                            if case["document_ids"] is not None
                            else None
                        ),
                        "retrieval_method": method,
                    },
                )
                row = score_case(case, response, status, docs)
                threshold = (response.get("retrieval_trace") or {}).get(
                    "refusal_threshold"
                )
                if status == 200 and threshold != settings.get("refusal_threshold"):
                    row["configuration_error"] = "Actual refusal threshold differs"
                    row["execution_error"] = True
                    row["passed"] = False
                row["http_elapsed_ms"] = elapsed
                row["method"] = method
                row["search_scope"] = (
                    "explicit_document_filter"
                    if case["document_ids"] is not None
                    else "all_authorized_documents"
                )
                rows.append(row)
            results[method] = {"summary": summarize(rows), "cases": rows}
        report = {
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "corpus_revision": corpus["manifest"]["revision"],
            "corpus_manifest_sha256": corpus_hash,
            "split": args.split,
            "selection_sha256": file_hash(args.selection) if args.selection else None,
            "settings": settings,
            "profile": seed["profile"],
            "measurement_scope": (
                "Actual HTTP application; synthetic authored contract; "
                "no human/model-quality validation."
            ),
            "indexed_claim": False,
            "indexed_note": (
                "Indexed query-plan proof belongs to the separate "
                "live PostgreSQL benchmark."
            ),
            "results": results,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        body = (json.dumps(report, indent=2) + "\n").encode()
        args.output.write_bytes(body)
        args.output.with_suffix(args.output.suffix + ".sha256").write_text(
            hashlib.sha256(body).hexdigest() + "\n", encoding="utf-8"
        )
        summaries = {method: value["summary"] for method, value in results.items()}
        print(
            json.dumps(
                {"output": str(args.output), "split": args.split, "results": summaries}
            )
        )
        if any(v["summary"]["execution_errors"] for v in results.values()):
            return 2
        return int(any(v["summary"]["failed"] for v in results.values()))
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"Evaluation unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
