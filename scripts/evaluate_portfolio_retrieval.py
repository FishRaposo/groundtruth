#!/usr/bin/env python3
"""Evaluate frozen synthetic cases through the real local application HTTP API."""

import argparse
import hashlib
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

from app.evidence_policy import (
    ProcedureVerificationProfile,
    ProposalProfile,
    RoleScopePolicy,
    SourceContextPolicy,
)
from app.portfolio import load_corpus
from app.portfolio.comparison import (
    bind_record,
    check_response_configuration,
    read_selection,
    report_binding,
    selection_identity,
    validate_runtime_settings,
)
from app.portfolio.comparison import (
    check_measured_settings as check_measured_settings,
)
from app.portfolio.comparison import (
    evidence_profile_matches as evidence_profile_matches,
)
from app.portfolio.comparison import (
    read_coverage_selection as read_coverage_selection,
)
from app.portfolio.comparison import (
    support_configuration_matches as support_configuration_matches,
)
from app.portfolio.coverage import bind_source_observations, source_manifest_hash
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


def public_source_manifest(documents):
    """Only sanitized immutable-read observations; no private seed principals/keys."""
    return {
        "contract": "canonical-source-observations-v1",
        "documents": {
            logical: [
                {key: value for key, value in snapshot.items() if key != "body"}
                for snapshot in document.get("source_snapshots", {}).values()
            ]
            for logical, document in documents.items()
        },
    }


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
        docs[logical] = {"document_id": mapped["document_id"], "versions": versions}
        if corpus["manifest"]["schema_version"] == 2:
            # The authored corpus, never response/seed claims, is authority.
            docs[logical].update(
                visibility=document["visibility"],
                workspace_id=document["workspace_id"],
                owner=document["owner"],
                principals=corpus["manifest"]["principals"],
            )
        bind_source_observations(docs[logical], mapped.get("verified_publications", []))
    return docs


def apply_setting_overrides(args, settings, coverage):
    overrides = {
        "top_k": getattr(args, "expected_top_k", None),
        "refusal_threshold": args.expected_refusal_threshold,
        "reader_null_threshold": args.expected_reader_null_threshold,
        "reader_model_revision": args.expected_reader_model_revision,
        "answer_support_mode": getattr(args, "expected_support_mode", None),
        "support_model_revision": getattr(args, "expected_support_revision", None),
        "support_min_margin": getattr(args, "expected_support_margin", None),
        "selection_contract": getattr(args, "expected_selection_contract", None),
        "answer_proposal_profile": getattr(args, "expected_proposal_profile", None),
        "role_scope_policy": getattr(args, "expected_role_scope_policy", None),
        "source_context_policy": getattr(args, "expected_source_context_policy", None),
        "procedure_verification_profile": getattr(
            args, "expected_procedure_verification_profile", None
        ),
        "answer_selection_mode": getattr(args, "expected_answer_selection_mode", None),
        "generation_mode": getattr(args, "expected_generation_mode", None),
    }
    for key, value in overrides.items():
        if value is None:
            continue
        if args.split != "development" or (key.startswith("reader_") and not coverage):
            raise ValueError("Setting overrides require a matching development corpus")
        if key == "top_k" and (
            type(value) is not int
            or value != 5
            or ("top_k" in settings and settings["top_k"] != value)
        ):
            raise ValueError("Explicit top_k must be 5 and match any frozen setting")
        if key == "support_min_margin" and (
            not math.isfinite(value) or not 0 <= value <= 4
        ):
            raise ValueError("Support margin must be finite in [0, 4]")
        settings[key] = value


def validate_mode_settings(settings):
    for key, allowed in (
        ("answer_proposal_profile", get_args(ProposalProfile)),
        ("role_scope_policy", get_args(RoleScopePolicy)),
        ("source_context_policy", get_args(SourceContextPolicy)),
        ("procedure_verification_profile", get_args(ProcedureVerificationProfile)),
    ):
        if key in settings and settings[key] not in allowed:
            raise ValueError("Expected profile/policy mode is unknown")


def evaluation_settings(args, corpus, seed):
    corpus_hash = corpus["manifest"]["manifest_sha256"]
    coverage = corpus["manifest"]["schema_version"] == 2
    bind_record(seed, corpus, args.execution_arm)
    if coverage:
        if seed.get("corpus_manifest_sha256") != corpus_hash:
            raise ValueError("Seed manifest belongs to a different corpus")
        if args.split not in corpus["manifest"]["expected_counts"]:
            raise ValueError("Requested split is absent from the corpus")
        if args.execution_arm is None:
            raise ValueError("Version-two evaluation requires explicit --execution-arm")
    elif args.require_answer_spans or args.execution_arm:
        raise ValueError("Answer span/arm validation requires a version-two corpus")
    selection = read_selection(args.split, args.selection, selection_identity(corpus))
    settings = dict((selection or {}).get("settings", corpus["profile"]))
    apply_setting_overrides(args, settings, coverage)
    validate_mode_settings(settings)
    validate_runtime_settings(
        settings,
        complete=selection is not None
        and "comparison_representation" in corpus["manifest"],
    )
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
    parser.add_argument("--expected-top-k", type=int, choices=(5,))
    parser.add_argument("--expected-reader-null-threshold", type=float)
    parser.add_argument("--expected-reader-model-revision")
    parser.add_argument("--expected-support-mode", choices=("disabled", "local_nli"))
    parser.add_argument("--expected-support-revision")
    parser.add_argument("--expected-support-margin", type=float)
    parser.add_argument("--expected-selection-contract")
    parser.add_argument(
        "--expected-proposal-profile", choices=get_args(ProposalProfile)
    )
    parser.add_argument(
        "--expected-role-scope-policy", choices=get_args(RoleScopePolicy)
    )
    parser.add_argument(
        "--expected-source-context-policy", choices=get_args(SourceContextPolicy)
    )
    parser.add_argument("--expected-refusal-threshold", type=float)
    parser.add_argument(
        "--expected-procedure-verification-profile",
        choices=get_args(ProcedureVerificationProfile),
    )
    parser.add_argument(
        "--expected-answer-selection-mode", choices=("lexical", "reader")
    )
    parser.add_argument(
        "--expected-generation-mode", choices=("legacy", "extractive", "provider")
    )
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
        report.update(report_binding(corpus))
        if coverage:
            report["score_contract"] = "coverage-v2"
            report["span_integrity_required"] = (
                args.require_answer_spans or args.execution_arm == "candidate"
            )
            report["execution_arm"] = args.execution_arm
            report["source_document_ids"] = public_source_document_ids(docs)
            report["source_manifest"] = public_source_manifest(docs)
            report["source_manifest_sha256"] = source_manifest_hash(
                report["source_manifest"]
            )
            report["source_identity_scope"] = (
                "Frozen corpus establishes content truth; canonical chunk IDs are "
                "historical authenticated server observations. Portable replay checks "
                "internal identity "
                "and content consistency, not independent server attestation."
            )
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
