"""Packaged synthetic portfolio corpus, independent of the working directory."""

import hashlib
import json
from collections import Counter
from importlib.resources import files
from pathlib import Path
from typing import Any


def version_upload_bytes(version: dict[str, Any]) -> bytes:
    """Return frozen experimental input, distinct from arm-canonical evidence.

    Existing corpora upload their canonical content as before. A comparison
    projection may declare shared raw input, but both fields are mandatory and
    checked independently of the published content hash.
    """
    if "input_content" not in version and "input_sha256" not in version:
        return version["content"].encode("utf-8")
    raw, digest = version.get("input_content"), version.get("input_sha256")
    if not isinstance(raw, str) or not isinstance(digest, str):
        raise ValueError("Input content and input hash must both be declared")
    body = raw.encode("utf-8")
    if hashlib.sha256(body).hexdigest() != digest:
        raise ValueError("Input content hash mismatch")
    return body


def load_corpus(
    assets_root: Path | None = None,
    *,
    expected_representation_profile: str | None = None,
    expected_common_manifest_sha256: str | None = None,
) -> dict[str, Any]:
    """Load and verify frozen source snapshots and authored case contracts."""
    root = (
        assets_root
        if assets_root is not None
        else files("app.portfolio").joinpath("assets")
    )
    manifest_body = root.joinpath("manifest.json").read_bytes()
    manifest = json.loads(manifest_body)
    if manifest.get("schema_version") not in (1, 2):
        raise ValueError("Unsupported corpus schema")
    expected_files = {"documents.json", "cases.json", "profile.json"}
    if set(manifest.get("files", {})) != expected_files:
        raise ValueError("Corpus manifest file set is invalid")
    values: dict[str, Any] = {}
    for name in sorted(expected_files):
        body = root.joinpath(name).read_bytes()
        if hashlib.sha256(body).hexdigest() != manifest["files"][name]:
            raise ValueError(f"Corpus checksum mismatch: {name}")
        values[name.removesuffix(".json")] = json.loads(body)
    from app.portfolio.representation import validate_representation

    validate_representation(
        manifest,
        values,
        expected_representation_profile,
        expected_common_manifest_sha256,
    )
    documents, cases = values["documents"], values["cases"]
    if (
        len(documents) != manifest["document_count"]
        or len(cases) != manifest["case_count"]
    ):
        raise ValueError("Corpus record count mismatch")
    by_id = {document["id"]: document for document in documents}
    if len(by_id) != len(documents) or len({case["id"] for case in cases}) != len(
        cases
    ):
        raise ValueError("Duplicate document or case identifier")
    family_splits = _validate_documents(documents)
    _validate_cases(cases, by_id, manifest, family_splits)
    if manifest["schema_version"] == 2:
        from app.portfolio.coverage import validate_coverage

        validate_coverage(documents, cases, manifest)
    manifest["manifest_sha256"] = hashlib.sha256(manifest_body).hexdigest()
    return {"manifest": manifest, **values}


def _validate_documents(documents: list[dict[str, Any]]) -> dict[str, str]:
    family_splits: dict[str, str] = {}
    for document in documents:
        family, split = document["family"], document["split"]
        if family_splits.setdefault(family, split) != split:
            raise ValueError("Source family crosses evaluation splits")
        versions = document["versions"]
        if [v["version_number"] for v in versions] != list(range(1, len(versions) + 1)):
            raise ValueError("Document version sequence is invalid")
        for version in versions:
            version_upload_bytes(version)
            if (
                hashlib.sha256(version["content"].encode()).hexdigest()
                != version["content_hash"]
            ):
                raise ValueError("Document content hash mismatch")
    return family_splits


def _validate_cases(
    cases: list[dict[str, Any]],
    by_id: dict[str, Any],
    manifest: dict[str, Any],
    family_splits: dict[str, str],
) -> None:
    counts = Counter((case["split"], case["category"]) for case in cases)
    required = {
        (split, category): count
        for split, categories in manifest["expected_counts"].items()
        for category, count in categories.items()
    }
    if counts != required:
        raise ValueError("Case category/split counts mismatch")
    for case in cases:
        if family_splits.get(case["family"]) != case["split"]:
            raise ValueError("Case/source family split mismatch")
        if case["principal"] not in manifest["principals"]:
            raise ValueError("Case principal is unknown")
        if case["document_ids"] is not None and any(
            d not in by_id for d in case["document_ids"]
        ):
            raise ValueError("Case scope references unknown document")
        for source in case["expected_sources"] + case["forbidden_sources"]:
            _validate_source(source, by_id, case["split"])


def _validate_source(source: dict[str, Any], by_id: dict[str, Any], split: str) -> None:
    document = by_id.get(source["document_id"])
    if not document or source["version_number"] not in {
        v["version_number"] for v in document["versions"]
    }:
        raise ValueError("Case references unknown source version")
    if document["split"] != split:
        raise ValueError("Case references source from another split")
    if "quoted_text" in source:
        version = document["versions"][source["version_number"] - 1]
        if not source["quoted_text"] or source["quoted_text"] not in version["content"]:
            raise ValueError("Expected quotation is not in frozen source")
