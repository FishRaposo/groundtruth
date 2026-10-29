"""Check blind acceptance and re-score portable API evidence against a corpus.

CLI requires --corpus-dir; projected reports also require both arm directories.
The compare_reports Python interface retains its
arithmetic-only mode when corpus is omitted, for isolated gate-math tests.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from uuid import UUID

METHODS = {"keyword", "vector", "hybrid", "reranked"}
CATEGORIES = {
    "answerable": 120,
    "unanswerable": 40,
    "conflicting_stale": 20,
    "adversarial": 20,
}


def inspect_method(value: dict) -> dict:
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("cases"), list)
        or not isinstance(value.get("summary"), dict)
    ):
        raise ValueError("Method cases and summary shapes are invalid")
    required = {
        "case_id",
        "category",
        "answer_quality_passed",
        "execution_error",
        "unauthorized_source_exposures",
        "citation_integrity_correct",
        "span_integrity_correct",
    }
    if any(
        not isinstance(row, dict)
        or not required.issubset(row)
        or not isinstance(row.get("case_id"), str)
        or not isinstance(row.get("category"), str)
        for row in value["cases"]
    ):
        raise ValueError("Comparison case row shape is invalid")
    rows = value["cases"]
    if Counter(row["category"] for row in rows) != CATEGORIES:
        raise ValueError("Blind case category counts differ from 120/40/20/20")
    identities = {row["case_id"] for row in rows}
    if len(identities) != 200:
        raise ValueError("Blind case IDs must be unique")
    positive = [row for row in rows if row["category"] == "answerable"]
    negative = [row for row in rows if row["category"] != "answerable"]
    observed = {
        "answerable_total": len(positive),
        "answerable_correct": sum(row["answer_quality_passed"] for row in positive),
        "negative_total": len(negative),
        "negative_correct": sum(row["answer_quality_passed"] for row in negative),
        "execution_errors": sum(row["execution_error"] for row in rows),
        "unauthorized_source_exposures": sum(
            row["unauthorized_source_exposures"] for row in rows
        ),
        "citation_integrity_failures": sum(
            not row["citation_integrity_correct"] for row in rows
        ),
        "span_integrity_failures": sum(
            not row["span_integrity_correct"] for row in rows
        ),
    }
    if any(value["summary"].get(key) != actual for key, actual in observed.items()):
        raise ValueError("Published summary disagrees with recorded cases")
    return {
        **observed,
        "identities": {(row["case_id"], row["category"]) for row in rows},
    }


def _validate_report_containers(baseline, candidate):
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        raise ValueError("Baseline and candidate reports must be JSON objects")
    if any(not isinstance(r.get("results"), dict) for r in (baseline, candidate)):
        raise ValueError("Report retrieval methods must be an object")


def validate_headers(baseline: dict, candidate: dict) -> None:
    _validate_report_containers(baseline, candidate)
    if (
        baseline.get("execution_arm") != "baseline"
        or candidate.get("execution_arm") != "candidate"
        or not candidate.get("span_integrity_required")
    ):
        raise ValueError("Comparison arms or candidate span verification are missing")
    for key, expected in (
        ("schema_version", 2),
        ("score_contract", "coverage-v2"),
        ("split", "held_out"),
    ):
        if any(report.get(key) != expected for report in (baseline, candidate)):
            raise ValueError("Only complete version-two blind evaluations qualify")
    for key in ("selection_sha256",):
        if not baseline.get(key) or baseline[key] != candidate.get(key):
            raise ValueError("Comparison dataset or frozen selection differs")
    if any(
        "comparison_representation" in r or "common_corpus_manifest_sha256" in r
        for r in (baseline, candidate)
    ):
        from app.portfolio.comparison import validate_pair

        validate_pair(baseline, candidate)
    elif not baseline.get("corpus_manifest_sha256") or baseline[
        "corpus_manifest_sha256"
    ] != candidate.get("corpus_manifest_sha256"):
        raise ValueError("Comparison dataset differs")
    if any(set(report["results"]) != METHODS for report in (baseline, candidate)):
        raise ValueError("All four retrieval methods must be reported")


def portable_documents(report: dict, corpus: dict) -> dict:
    from app.portfolio.coverage import bind_source_observations, source_manifest_hash

    mapping = report.get("source_document_ids")
    catalog = {document["id"]: document for document in corpus["documents"]}
    if not isinstance(mapping, dict) or set(mapping) != set(catalog):
        raise ValueError("Portable source document mapping differs from corpus")
    values = list(mapping.values())
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("Portable source document IDs must be UUID strings")
    if len(set(values)) != len(values):
        raise ValueError("Portable source document IDs must be unique")
    for value in values:
        UUID(value)
    documents = {
        logical: {
            "document_id": mapping[logical],
            "versions": {
                str(version["version_number"]): version
                for version in document["versions"]
            },
            "owner": document["owner"],
            "workspace_id": document["workspace_id"],
            "visibility": document["visibility"],
            "principals": corpus["manifest"]["principals"],
        }
        for logical, document in catalog.items()
    }
    manifest = report.get("source_manifest")
    if manifest is not None:
        if (
            not isinstance(manifest, dict)
            or manifest.get("contract") != "canonical-source-observations-v1"
            or not isinstance(manifest.get("documents"), dict)
            or set(manifest["documents"]) != set(documents)
            or (
                "source_manifest_sha256" in report
                and report["source_manifest_sha256"] != source_manifest_hash(manifest)
            )
        ):
            raise ValueError("Portable source snapshot manifest differs")
        for logical, document in documents.items():
            bind_source_observations(document, manifest["documents"][logical])
    return documents


def audit_row(
    row: dict,
    case: dict,
    documents: dict,
    require_spans: bool,
    *,
    settings: dict | None = None,
    arm: str | None = None,
    frozen_runtime: bool = False,
) -> dict:
    from app.portfolio.evaluation import score_case

    if not isinstance(row, dict):
        raise ValueError("Portable observed row must be an object")
    response = row.get("observed_response")
    status = row.get("http_status")
    if not isinstance(response, dict) or type(status) is not int:
        raise ValueError("Portable observed evidence requires response and HTTP status")
    if status == 200 and response.get("question") != case["question"]:
        raise ValueError("Portable observed evidence question differs from corpus")
    if settings is not None:
        from app.portfolio.comparison import runtime_configuration_error

        required_reader = frozen_runtime or any(
            k in settings for k in ("reader_null_threshold", "reader_model_revision")
        )
        error = runtime_configuration_error(
            response, status, settings, arm, require_reader=required_reader
        )
        if error:
            raise ValueError("Portable runtime configuration differs: " + error)
    try:
        rescored = score_case(
            case, response, status, documents, require_answer_spans=require_spans
        )
    except (AttributeError, KeyError, IndexError, TypeError) as exc:
        raise ValueError("Invalid portable observed evidence structure") from exc
    differing = [
        key for key, value in rescored.items() if key not in row or row[key] != value
    ]
    if differing:
        raise ValueError(
            f"Case {case['id']} observed evidence disagrees with recorded fields: "
            + ", ".join(differing)
        )
    return rescored


def audit_report(
    report: dict,
    corpus: dict,
    *,
    common_corpus: dict | None = None,
    selection_path: Path | None = None,
) -> dict:
    """Rebuild score context from public IDs plus authoritative frozen sources."""
    if not isinstance(report, dict) or not isinstance(report.get("results"), dict):
        raise ValueError("Portable report shape is invalid")
    manifest = corpus["manifest"]
    if (
        manifest.get("schema_version") != 2
        or manifest.get("score_contract") != "coverage-v2"
    ):
        raise ValueError("Portable audit requires a version-two coverage corpus")
    if report.get("corpus_manifest_sha256") != manifest["manifest_sha256"]:
        raise ValueError("Portable report corpus manifest checksum differs")
    from app.portfolio.comparison import (
        bind_record,
        report_binding,
        validate_common_view,
    )

    descriptor = bind_record(report, corpus, report.get("execution_arm"), report=True)
    if (
        descriptor is not None
        and report.get("split") == "held_out"
        and selection_path is None
    ):
        raise ValueError("Projected blind audit requires the actual selection artifact")
    if descriptor is not None and common_corpus is not None:
        validate_common_view(corpus, common_corpus, report["execution_arm"])
    settings = _audit_runtime_settings(report, corpus, common_corpus, selection_path)
    documents = portable_documents(report, corpus)
    cases = {
        case["id"]: case for case in corpus["cases"] if case["split"] == report["split"]
    }
    if not cases:
        raise ValueError("Portable report split has no canonical cases")
    case_rows = 0
    runtime_rows = 0
    for method, value in report["results"].items():
        count, checked = _audit_method(
            method, value, cases, documents, report, settings, selection_path
        )
        case_rows += count
        runtime_rows += checked
    return {
        "verified": True,
        "runtime_verification": {
            "verified": selection_path is not None,
            "scope": "actual_frozen_selection"
            if selection_path is not None
            else "historical_unrecorded_or_report_claims_only",
            "checked_http_200_rows": runtime_rows,
        },
        "case_rows": case_rows,
        "source_documents": len(documents),
        **report_binding(corpus),
        "corpus_manifest_sha256": manifest["manifest_sha256"],
    }


def _audit_runtime_settings(report, corpus, common_corpus, selection_path):
    from app.portfolio.comparison import (
        selected_runtime_settings,
        selection_identity,
        validate_runtime_settings,
    )

    settings = None
    if selection_path is not None:
        settings = selected_runtime_settings(
            selection_path, report, selection_identity(common_corpus or corpus)
        )
    elif report.get("settings") is not None:
        claimed = report["settings"]
        if not isinstance(claimed, dict):
            raise ValueError(
                "Historical runtime settings must be an object when recorded"
            )
        settings = validate_runtime_settings(
            {key: value for key, value in claimed.items() if value is not None}
        )
    return settings


def _audit_method(method, value, cases, documents, report, settings, selection_path):
    from app.portfolio.evaluation import summarize

    if (
        not isinstance(value, dict)
        or not isinstance(value.get("cases"), list)
        or not isinstance(value.get("summary"), dict)
    ):
        raise ValueError("Portable method shape is invalid")
    rows = value["cases"]
    if len(rows) != len(cases) or {row["case_id"] for row in rows} != set(cases):
        raise ValueError("Portable report case IDs differ from canonical corpus")
    rescored = [
        audit_row(
            row,
            cases[row["case_id"]],
            documents,
            bool(report.get("span_integrity_required")),
            settings=settings,
            arm=report.get("execution_arm"),
            frozen_runtime=selection_path is not None,
        )
        for row in rows
    ]
    for key, expected in summarize(rescored).items():
        if key not in value["summary"] or value["summary"][key] != expected:
            raise ValueError(
                f"Method {method} observed evidence summary differs: {key}"
            )
    case_rows = len(rows)
    runtime_rows = (
        sum(row.get("http_status") == 200 for row in rows)
        if settings is not None
        else 0
    )
    return case_rows, runtime_rows


def _comparison_context(
    baseline, candidate, corpus, baseline_corpus, candidate_corpus, selection_path
):
    projected = "comparison_representation" in baseline
    arm_views = baseline_corpus is not None or candidate_corpus is not None
    if arm_views and (
        corpus is None
        or baseline_corpus is None
        or candidate_corpus is None
        or not projected
    ):
        raise ValueError(
            "Portable projected comparison requires common and both arm source views"
        )
    if projected and corpus is not None and not arm_views:
        raise ValueError(
            "Projected comparison requires both authoritative arm source views"
        )
    if projected and corpus is not None:
        if selection_path is None:
            raise ValueError(
                "Projected comparison requires the actual frozen selection artifact"
            )
        from app.portfolio.comparison import (
            selected_runtime_settings,
            selection_identity,
        )

        for report in (baseline, candidate):
            selected_runtime_settings(
                selection_path, report, selection_identity(corpus)
            )
    elif selection_path is not None:
        raise ValueError(
            "Frozen runtime verification requires portable projected source views"
        )

    return projected


def compare_reports(
    baseline: dict,
    candidate: dict,
    *,
    corpus: dict | None = None,
    baseline_corpus: dict | None = None,
    candidate_corpus: dict | None = None,
    selection_path: Path | None = None,
) -> dict:
    validate_headers(baseline, candidate)
    projected = _comparison_context(
        baseline, candidate, corpus, baseline_corpus, candidate_corpus, selection_path
    )
    measured = {}
    for method in sorted(METHODS):
        before = inspect_method(baseline["results"][method])
        after = inspect_method(candidate["results"][method])
        if before.pop("identities") != after.pop("identities"):
            raise ValueError("Comparison case IDs differ")
        if before["execution_errors"] or after["execution_errors"]:
            raise ValueError("Execution errors prevent a complete comparison")
        if any(
            after[key]
            for key in (
                "unauthorized_source_exposures",
                "citation_integrity_failures",
                "span_integrity_failures",
            )
        ):
            raise ValueError("Candidate evidence or access integrity failed")
        measured[method] = {"baseline": before, "candidate": after}
    default = measured["reranked"]
    passed = (
        default["candidate"]["answerable_correct"] >= 114
        and default["candidate"]["answerable_correct"]
        > default["baseline"]["answerable_correct"]
        and default["candidate"]["negative_correct"] == 80
    )
    result = {
        "gate": "passed" if passed else "failed",
        "methods": measured,
        "frozen_runtime_verified": projected
        and corpus is not None
        and selection_path is not None,
        "comparison_scope": (
            "portable_sources_and_selected_runtime_verified"
            if projected
            else "legacy_sources_only_runtime_unverified"
        )
        if corpus is not None
        else "arithmetic_only_not_portable",
    }
    if corpus is not None:
        if projected:
            assert baseline_corpus is not None and candidate_corpus is not None
            baseline_source, candidate_source = baseline_corpus, candidate_corpus
        else:
            baseline_source = candidate_source = corpus
        result["portable_evidence"] = {
            "baseline": audit_report(
                baseline,
                baseline_source,
                common_corpus=corpus if projected else None,
                selection_path=selection_path if projected else None,
            ),
            "candidate": audit_report(
                candidate,
                candidate_source,
                common_corpus=corpus if projected else None,
                selection_path=selection_path if projected else None,
            ),
        }
    if projected:
        from app.portfolio.comparison import disclosure

        result.update(disclosure(baseline, candidate, verified=corpus is not None))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    parser.add_argument("--baseline-corpus-dir", type=Path)
    parser.add_argument("--candidate-corpus-dir", type=Path)
    parser.add_argument("--selection", type=Path)
    args = parser.parse_args()
    try:
        from app.portfolio.comparison import load_views

        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
        if not isinstance(baseline, dict) or not isinstance(candidate, dict):
            raise ValueError("Baseline and candidate reports must be JSON objects")
        corpus, baseline_view, candidate_view = load_views(
            args.corpus_dir, args.baseline_corpus_dir, args.candidate_corpus_dir
        )
        result = compare_reports(
            baseline,
            candidate,
            corpus=corpus,
            baseline_corpus=baseline_view,
            candidate_corpus=candidate_view,
            selection_path=args.selection,
        )
    except (ImportError, OSError, ValueError, KeyError, TypeError) as exc:
        reason = (
            "Invalid or unavailable evidence artifact"
            if isinstance(
                exc, (ImportError, OSError, KeyError, TypeError, UnicodeError)
            )
            else str(exc)
        )
        print(f"Coverage acceptance unavailable: {reason}")
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["gate"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
