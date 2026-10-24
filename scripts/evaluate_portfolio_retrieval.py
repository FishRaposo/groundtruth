#!/usr/bin/env python3
"""Evaluate frozen synthetic cases through the real local application HTTP API."""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.portfolio import load_corpus
from app.portfolio.evaluation import (
    METHODS,
    file_hash,
    read_seed,
    request_json,
    score_case,
    summarize,
)

OBSERVED_RESPONSE_FIELDS = (
    "id",
    "question",
    "answer",
    "sources",
    "refused",
    "outcome",
    "evidence_access",
    "refusal_reason",
    "provenance",
    "retrieval_trace",
    "execution_mode",
)
PRIVATE_EVIDENCE_FIELDS = {
    "headers",
    "request_headers",
    "response_headers",
    "authorization",
    "api_key",
    "apikey",
    "x_api_key",
    "access_token",
    "refresh_token",
    "credentials",
    "credential",
    "password",
    "secret",
    "exception",
    "raw_exception",
    "traceback",
    "stack_trace",
}


def public_evidence(value: Any) -> Any:
    """Fresh JSON snapshot; structured credentials/exception details never escape."""
    if isinstance(value, dict):
        return {
            key: public_evidence(item)
            for key, item in value.items()
            if key.casefold().replace("-", "_") not in PRIVATE_EVIDENCE_FIELDS
        }
    if isinstance(value, list):
        return [public_evidence(item) for item in value]
    return value


def build_case_row(case, response, status, documents, *, require_answer_spans=False):
    row = score_case(
        case, response, status, documents, require_answer_spans=require_answer_spans
    )
    if case.get("score_contract") == "coverage-v2":
        snapshot = public_evidence(
            {key: response[key] for key in OBSERVED_RESPONSE_FIELDS if key in response}
        )
        row["observed_response"] = snapshot
        row["provenance"] = snapshot.get("provenance")
        row["retrieval_trace"] = snapshot.get("retrieval_trace") or {}
    return row


def public_source_document_ids(documents):
    return {
        logical: str(document["document_id"]) for logical, document in documents.items()
    }


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
        if selection.get("schema_version") == 2:
            return read_coverage_selection(selection, selection_path, corpus_hash)
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


def _validate_binding_times(selection, freeze):
    if not selection.get("frozen_at") or selection["frozen_at"] != freeze.get(
        "frozen_at"
    ):
        raise ValueError("Selection must preserve the candidate freeze timestamp")
    if not selection.get("binding_at"):
        raise ValueError("Validation binding requires binding_at")
    frozen_at = datetime.fromisoformat(selection["frozen_at"].replace("Z", "+00:00"))
    binding_at = datetime.fromisoformat(selection["binding_at"].replace("Z", "+00:00"))
    if frozen_at.tzinfo is None or binding_at.tzinfo is None or binding_at < frozen_at:
        raise ValueError("Binding must occur after the dated candidate freeze")


def read_coverage_selection(selection, selection_path, corpus_hash):
    """Bind later validation sources to an immutable earlier candidate freeze."""
    if selection.get("selection_basis") != "development_only":
        raise ValueError("Selection must declare development_only")
    if selection.get("validation_corpus_manifest_sha256") != corpus_hash:
        raise ValueError("Selection belongs to a different validation corpus")

    def artifact(name):
        path = Path(selection[name + "_path"])
        if not path.is_absolute():
            path = selection_path.parent / path
        if file_hash(path) != selection[name + "_sha256"]:
            raise ValueError(name.replace("_", " ") + " checksum mismatch")
        return json.loads(path.read_text(encoding="utf-8"))

    development = artifact("development_report")
    freeze = artifact("candidate_freeze")
    development_hash = selection.get("development_corpus_manifest_sha256")
    if (
        not development_hash
        or development.get("split") != "development"
        or development.get("corpus_manifest_sha256") != development_hash
        or freeze.get("development_corpus_manifest_sha256") != development_hash
    ):
        raise ValueError("Selection must reference frozen development evidence")
    _validate_binding_times(selection, freeze)
    if selection.get("settings") != development.get("settings") or selection.get(
        "settings"
    ) != freeze.get("settings"):
        raise ValueError("Selected settings differ from measured frozen settings")
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
        if corpus["manifest"]["schema_version"] == 2:
            # The authored corpus, never response/seed claims, is authority.
            docs[logical].update(
                visibility=document["visibility"],
                workspace_id=document["workspace_id"],
                owner=document["owner"],
                principals=corpus["manifest"]["principals"],
            )
    return docs


def apply_setting_overrides(args, settings, coverage):
    overrides = {
        "refusal_threshold": args.expected_refusal_threshold,
        "reader_null_threshold": args.expected_reader_null_threshold,
        "reader_model_revision": args.expected_reader_model_revision,
    }
    for key, value in overrides.items():
        if value is None:
            continue
        if args.split != "development" or (key.startswith("reader_") and not coverage):
            raise ValueError("Setting overrides require a matching development corpus")
        settings[key] = value


def evaluation_settings(args, corpus, seed):
    corpus_hash = corpus["manifest"]["manifest_sha256"]
    coverage = corpus["manifest"]["schema_version"] == 2
    if coverage:
        if seed.get("corpus_manifest_sha256") != corpus_hash:
            raise ValueError("Seed manifest belongs to a different corpus")
        if args.split not in corpus["manifest"]["expected_counts"]:
            raise ValueError("Requested split is absent from the corpus")
        if args.execution_arm is None:
            raise ValueError("Version-two evaluation requires explicit --execution-arm")
    elif args.require_answer_spans or args.execution_arm:
        raise ValueError("Answer span/arm validation requires a version-two corpus")
    selection = read_selection(args.split, args.selection, corpus_hash)
    settings = dict((selection or {}).get("settings", corpus["profile"]))
    apply_setting_overrides(args, settings, coverage)
    if settings.get("top_k") != 5:
        raise ValueError("Frozen evaluation contract uses top_k=5")
    if (
        coverage
        and args.execution_arm == "candidate"
        and any(
            key not in settings
            for key in ("reader_null_threshold", "reader_model_revision")
        )
    ):
        raise ValueError("Candidate requires expected reader threshold and revision")
    return coverage, selection, settings


def check_response_configuration(row, response, status, settings, arm):
    if status != 200:
        return
    threshold = (response.get("retrieval_trace") or {}).get("refusal_threshold")
    error = None
    expected_threshold = (
        None if arm == "candidate" else settings.get("refusal_threshold")
    )
    if threshold != expected_threshold:
        error = "Actual refusal threshold differs"
    selection = (response.get("provenance") or {}).get("answer_selection") or {}
    if arm == "baseline" and selection.get("mode") not in (None, "lexical"):
        error = "Baseline must use the lexical answer selection contract"
    if arm == "candidate" and (
        selection.get("mode") != "reader"
        or selection.get("threshold") != settings["reader_null_threshold"]
        or selection.get("revision") != settings["reader_model_revision"]
    ):
        error = "Actual candidate reader mode, threshold or revision differs"
    if error:
        row["configuration_error"] = error
        row["execution_error"] = True
        row["passed"] = False
        if "answer_quality_passed" in row:
            row["answer_quality_passed"] = False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--split", choices=("development", "held_out"), default="development"
    )
    parser.add_argument("--method", choices=(*METHODS, "all"), default="all")
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--corpus-dir", type=Path)
    parser.add_argument("--execution-arm", choices=("baseline", "candidate"))
    parser.add_argument("--require-answer-spans", action="store_true")
    parser.add_argument("--expected-reader-null-threshold", type=float)
    parser.add_argument("--expected-reader-model-revision")
    parser.add_argument("--expected-refusal-threshold", type=float)
    args = parser.parse_args()
    try:
        corpus = load_corpus(args.corpus_dir)
        seed = read_seed(args.seed_manifest)
        corpus_hash = corpus["manifest"]["manifest_sha256"]
        coverage, selection, settings = evaluation_settings(args, corpus, seed)
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
                row = build_case_row(
                    case,
                    response,
                    status,
                    docs,
                    require_answer_spans=(
                        args.require_answer_spans or args.execution_arm == "candidate"
                    ),
                )
                check_response_configuration(
                    row, response, status, settings, args.execution_arm
                )
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
            "schema_version": 2 if coverage else 1,
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
        if coverage:
            report["score_contract"] = "coverage-v2"
            report["span_integrity_required"] = (
                args.require_answer_spans or args.execution_arm == "candidate"
            )
            report["execution_arm"] = args.execution_arm
            report["source_document_ids"] = public_source_document_ids(docs)
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
