"""Check blind acceptance and re-score portable API evidence against a corpus.

CLI requires --corpus-dir. The compare_reports Python interface retains its
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


def validate_headers(baseline: dict, candidate: dict) -> None:
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
    for key in ("corpus_manifest_sha256", "selection_sha256"):
        if not baseline.get(key) or baseline[key] != candidate.get(key):
            raise ValueError("Comparison dataset or frozen selection differs")
    if any(set(report["results"]) != METHODS for report in (baseline, candidate)):
        raise ValueError("All four retrieval methods must be reported")


def portable_documents(report: dict, corpus: dict) -> dict:
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
    return {
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


def audit_row(row: dict, case: dict, documents: dict, require_spans: bool) -> dict:
    from app.portfolio.evaluation import score_case

    response = row.get("observed_response")
    status = row.get("http_status")
    if not isinstance(response, dict) or type(status) is not int:
        raise ValueError("Portable observed evidence requires response and HTTP status")
    if status == 200 and response.get("question") != case["question"]:
        raise ValueError("Portable observed evidence question differs from corpus")
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


def audit_report(report: dict, corpus: dict) -> dict:
    """Rebuild score context from public IDs plus authoritative frozen sources."""
    from app.portfolio.evaluation import summarize

    manifest = corpus["manifest"]
    if (
        manifest.get("schema_version") != 2
        or manifest.get("score_contract") != "coverage-v2"
    ):
        raise ValueError("Portable audit requires a version-two coverage corpus")
    if report.get("corpus_manifest_sha256") != manifest["manifest_sha256"]:
        raise ValueError("Portable report corpus manifest checksum differs")
    documents = portable_documents(report, corpus)
    cases = {
        case["id"]: case for case in corpus["cases"] if case["split"] == report["split"]
    }
    if not cases:
        raise ValueError("Portable report split has no canonical cases")
    case_rows = 0
    for method, value in report["results"].items():
        rows = value["cases"]
        if len(rows) != len(cases) or {row["case_id"] for row in rows} != set(cases):
            raise ValueError("Portable report case IDs differ from canonical corpus")
        rescored = [
            audit_row(
                row,
                cases[row["case_id"]],
                documents,
                bool(report.get("span_integrity_required")),
            )
            for row in rows
        ]
        for key, expected in summarize(rescored).items():
            if key not in value["summary"] or value["summary"][key] != expected:
                raise ValueError(
                    f"Method {method} observed evidence summary differs: {key}"
                )
        case_rows += len(rows)
    return {
        "verified": True,
        "case_rows": case_rows,
        "source_documents": len(documents),
        "corpus_manifest_sha256": manifest["manifest_sha256"],
    }


def compare_reports(
    baseline: dict, candidate: dict, *, corpus: dict | None = None
) -> dict:
    validate_headers(baseline, candidate)
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
    result = {"gate": "passed" if passed else "failed", "methods": measured}
    if corpus is not None:
        result["portable_evidence"] = {
            "baseline": audit_report(baseline, corpus),
            "candidate": audit_report(candidate, corpus),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--corpus-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        from app.portfolio import load_corpus

        corpus = load_corpus(args.corpus_dir)
        result = compare_reports(
            json.loads(args.baseline.read_text(encoding="utf-8")),
            json.loads(args.candidate.read_text(encoding="utf-8")),
            corpus=corpus,
        )
    except (ImportError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Coverage acceptance unavailable: {exc}")
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["gate"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
