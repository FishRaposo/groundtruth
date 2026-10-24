"""Acceptance is 95% answerable coverage plus all negative contracts, not 100%."""

import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "coverage_delivery", ROOT / "scripts/verify_answer_coverage_delivery.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def observation(arm, positives, *, negative_failure=False):
    rows = []
    for category, total in (
        ("answerable", 120),
        ("unanswerable", 40),
        ("conflicting_stale", 20),
        ("adversarial", 20),
    ):
        for index in range(total):
            correct = index < positives if category == "answerable" else True
            if negative_failure and category == "unanswerable" and index == 0:
                correct = False
            rows.append(
                {
                    "case_id": f"{category}-{index}",
                    "category": category,
                    "answer_quality_passed": correct,
                    "execution_error": False,
                    "unauthorized_source_exposures": 0,
                    "citation_integrity_correct": True,
                    "span_integrity_correct": True,
                }
            )
    value = {
        "cases": rows,
        "summary": {
            "answerable_total": 120,
            "answerable_correct": positives,
            "negative_total": 80,
            "negative_correct": 79 if negative_failure else 80,
            "execution_errors": 0,
            "unauthorized_source_exposures": 0,
            "citation_integrity_failures": 0,
            "span_integrity_failures": 0,
        },
    }
    return {
        "schema_version": 2,
        "score_contract": "coverage-v2",
        "split": "held_out",
        "execution_arm": arm,
        "span_integrity_required": arm == "candidate",
        "corpus_manifest_sha256": "same-corpus",
        "selection_sha256": "same-freeze",
        "results": {method: copy.deepcopy(value) for method in MODULE.METHODS},
    }


def test_exact_95_percent_with_six_false_refusals_can_pass():
    result = MODULE.compare_reports(
        observation("baseline", 30), observation("candidate", 114)
    )
    assert result["gate"] == "passed"


@pytest.mark.parametrize("positive,negative_failure", [(113, False), (120, True)])
def test_missing_coverage_or_one_unsupported_negative_fails(positive, negative_failure):
    candidate = observation("candidate", positive, negative_failure=negative_failure)
    assert (
        MODULE.compare_reports(observation("baseline", 30), candidate)["gate"]
        == "failed"
    )


def test_equal_baseline_is_not_an_improvement():
    assert (
        MODULE.compare_reports(
            observation("baseline", 120), observation("candidate", 120)
        )["gate"]
        == "failed"
    )


def test_fabricated_summary_and_misaligned_case_ids_are_rejected():
    candidate = observation("candidate", 113)
    candidate["results"]["reranked"]["summary"]["answerable_correct"] = 120
    with pytest.raises(ValueError, match="summary"):
        MODULE.compare_reports(observation("baseline", 30), candidate)
    candidate = observation("candidate", 120)
    candidate["results"]["reranked"]["cases"][0]["case_id"] = "different-question"
    with pytest.raises(ValueError, match="IDs differ"):
        MODULE.compare_reports(observation("baseline", 30), candidate)


def portable_fixture(arm, positives):
    # Mechanical gate fixture, not an authored development/blind quality corpus.
    from app.portfolio.evaluation import score_case, summarize

    passages = [
        "Relay maintenance lasts 11 minutes.",
        "The route marshal owns the handover.",
    ]
    documents = []
    mapped = {}
    mapping = {}
    import hashlib

    for index, passage in enumerate(passages, 1):
        logical = f"unit-source-{index}"
        identifier = f"00000000-0000-0000-0000-{index:012d}"
        snapshot = {
            "version_number": 1,
            "content": passage,
            "content_hash": hashlib.sha256(passage.encode()).hexdigest(),
        }
        document = {
            "id": logical,
            "owner": "unit-owner",
            "workspace_id": "unit-workspace",
            "visibility": "public",
            "versions": [snapshot],
        }
        documents.append(document)
        mapping[logical] = identifier
        mapped[logical] = {
            **document,
            "document_id": identifier,
            "principals": {
                "unit-owner": {"workspace_id": "unit-workspace", "role": "owner"}
            },
            "versions": {"1": snapshot},
        }
    cases = []
    rows = []
    for category, total in MODULE.CATEGORIES.items():
        for index in range(total):
            positive = category == "answerable"
            sources = (
                [
                    {
                        "document_id": doc["id"],
                        "version_number": 1,
                        "content_hash": doc["versions"][0]["content_hash"],
                        "quoted_text": doc["versions"][0]["content"],
                        "acceptable_answer_spans": [doc["versions"][0]["content"]],
                    }
                    for doc in documents
                ]
                if positive
                else []
            )
            case = {
                "id": f"{category}-{index}",
                "score_contract": "coverage-v2",
                "split": "held_out",
                "category": category,
                "principal": "unit-owner",
                "question": "What is the maintenance duration and who owns handover?"
                if positive
                else "Which unstated room number is required?",
                "expected_behavior": "answer" if positive else "refuse",
                "expected_sources": sources,
                "forbidden_sources": [],
                "required_facts": [["11 minutes"], ["route marshal"]]
                if positive
                else [],
                "ordered_steps": [],
            }
            cases.append(case)
            answered = positive and index < positives
            response = {
                "id": f"unit-query-{category}-{index}",
                "question": case["question"],
                "answer": " ".join(passages) if answered else None,
                "refused": not answered,
                "outcome": "completed" if answered else "refused",
                "sources": [
                    {
                        "document_id": mapping[doc["id"]],
                        "document_version": 1,
                        "content_hash": doc["versions"][0]["content_hash"],
                        "quoted_text": doc["versions"][0]["content"],
                        **(
                            {
                                "answer_spans": [
                                    {
                                        "start": 0,
                                        "end": len(doc["versions"][0]["content"]),
                                        "text": doc["versions"][0]["content"],
                                    }
                                ]
                            }
                            if arm == "candidate"
                            else {}
                        ),
                    }
                    for doc in documents
                ]
                if answered
                else [],
                "retrieval_trace": {"scores": []},
            }
            row = score_case(
                case, response, 200, mapped, require_answer_spans=arm == "candidate"
            )
            row["observed_response"] = copy.deepcopy(response)
            rows.append(row)
    report = {
        "schema_version": 2,
        "score_contract": "coverage-v2",
        "split": "held_out",
        "execution_arm": arm,
        "span_integrity_required": arm == "candidate",
        "corpus_manifest_sha256": "unit-corpus-hash",
        "selection_sha256": "same-freeze",
        "source_document_ids": mapping,
        "results": {
            method: {"cases": copy.deepcopy(rows), "summary": summarize(rows)}
            for method in MODULE.METHODS
        },
    }
    corpus = {
        "manifest": {
            "schema_version": 2,
            "score_contract": "coverage-v2",
            "manifest_sha256": "unit-corpus-hash",
            "principals": {
                "unit-owner": {"workspace_id": "unit-workspace", "role": "owner"}
            },
        },
        "documents": documents,
        "cases": cases,
    }
    return corpus, report


@pytest.mark.parametrize("forgery", ["answer", "citation"])
def test_portable_audit_rejects_forged_observed_evidence_despite_true_booleans(forgery):
    corpus, baseline = portable_fixture("baseline", 30)
    _, candidate = portable_fixture("candidate", 120)
    response = candidate["results"]["reranked"]["cases"][0]["observed_response"]
    if forgery == "answer":
        response["answer"] = (
            "Maintenance lasts 45 minutes and the wrong owner is responsible."
        )
    else:
        response["sources"][1]["quoted_text"] = "A fabricated handover quote."
    # The original arithmetic gate demonstrably accepts forged stored evidence.
    assert MODULE.compare_reports(baseline, candidate)["gate"] == "passed"
    auditor = getattr(MODULE, "audit_report", None)
    assert callable(auditor), "True booleans need a canonical observed-evidence audit"
    with pytest.raises(ValueError, match="observed evidence"):
        auditor(candidate, corpus)


def test_portable_audit_accepts_two_document_answers_and_six_false_refusals():
    corpus, baseline = portable_fixture("baseline", 30)
    _, candidate = portable_fixture("candidate", 114)
    auditor = getattr(MODULE, "audit_report", None)
    assert callable(auditor), "Portable evidence audit is required"
    assert auditor(candidate, corpus)["case_rows"] == 800
    assert (
        MODULE.compare_reports(baseline, candidate, corpus=corpus)["gate"] == "passed"
    )


@pytest.mark.parametrize(
    "damage",
    [
        "missing_snapshot",
        "extra_mapping",
        "duplicate_mapping",
        "wrong_question",
        "wrong_manifest",
    ],
)
def test_portable_audit_fails_closed_for_incomplete_or_unbound_evidence(damage):
    corpus, candidate = portable_fixture("candidate", 120)
    row = candidate["results"]["reranked"]["cases"][0]
    if damage == "missing_snapshot":
        del row["observed_response"]
    elif damage == "extra_mapping":
        candidate["source_document_ids"]["unlisted-document"] = (
            "00000000-0000-0000-0000-000000000003"
        )
    elif damage == "duplicate_mapping":
        candidate["source_document_ids"]["unit-source-2"] = candidate[
            "source_document_ids"
        ]["unit-source-1"]
    elif damage == "wrong_question":
        row["observed_response"]["question"] = "A different request"
    else:
        candidate["corpus_manifest_sha256"] = "another-corpus"
    with pytest.raises(ValueError):
        MODULE.audit_report(candidate, corpus)


@pytest.mark.parametrize(
    ("positives", "forge", "expected_exit"),
    [(114, False, 0), (113, False, 1), (120, True, 2)],
)
def test_portable_gate_cli_exit_contract(
    tmp_path, monkeypatch, positives, forge, expected_exit
):
    import json
    import sys

    import app.portfolio

    corpus, baseline = portable_fixture("baseline", 30)
    _, candidate = portable_fixture("candidate", positives)
    if forge:
        candidate["results"]["reranked"]["cases"][0]["observed_response"]["answer"] = (
            "Forged wrong duration and owner."
        )
    before = tmp_path / "baseline.json"
    after = tmp_path / "candidate.json"
    before.write_text(json.dumps(baseline), encoding="utf-8")
    after.write_text(json.dumps(candidate), encoding="utf-8")
    # The checksum-verifying loader is separately tested; this isolates CLI
    # argument routing, actual report reads, portable audit and exit decisions.
    monkeypatch.setattr(app.portfolio, "load_corpus", lambda path: corpus)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_answer_coverage_delivery.py",
            "--baseline",
            str(before),
            "--candidate",
            str(after),
            "--corpus-dir",
            str(tmp_path / "corpus"),
        ],
    )
    assert MODULE.main() == expected_exit
