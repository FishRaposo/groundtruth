"""Actual ASGI fixture; model inference was doubled, not quality validation."""

import copy
import json
from pathlib import Path

import pytest

from scripts.tests.test_combined_profile_tools import script


def captured_context():
    payload = json.loads(
        (
            Path(__file__).parent / "fixtures/procedure-copy-v3-cover-v2-r1.json"
        ).read_text(encoding="utf-8")
    )
    response = payload["response"]
    corpus = {"documents": [], "manifest": {"schema_version": 2, "principals": {}}}
    seed = {"documents": {}}
    names = {}
    for index, (identity, snapshot) in enumerate(payload["source_snapshots"].items()):
        logical = f"source-{index}"
        names[identity] = logical
        version = snapshot["document_version"]
        corpus["manifest"]["principals"]["author"] = {
            "workspace_id": snapshot["workspace_id"]
        }
        corpus["documents"].append(
            {
                "id": logical,
                "workspace_id": snapshot["workspace_id"],
                "owner": "author",
                "visibility": "private",
                "metadata": snapshot["metadata"],
                "versions": [
                    {
                        "version_number": version,
                        "content_hash": snapshot["content_hash"],
                        "content": snapshot["body"],
                    }
                ],
            }
        )
        seed["documents"][logical] = {
            "document_id": identity,
            "versions": {str(version): {"content_hash": snapshot["content_hash"]}},
            "verified_publications": [snapshot],
        }
    source = response["sources"][0]
    # The citation includes surrounding context; the copied answer is narrower.
    # This source-declared prerequisite is in both the oracle body and answer.
    step = "obtain the signed card"
    assert step in payload["source_snapshots"][source["document_id"]]["body"]
    case = {
        "id": "retained-context-engineering-case",
        "score_contract": "coverage-v2",
        "category": "answerable",
        "expected_behavior": "answer",
        "question": payload["request"]["question"],
        "principal": "author",
        "required_facts": [[step]],
        "ordered_steps": [],
        "forbidden_sources": [],
        "expected_sources": [
            {
                "document_id": names[source["document_id"]],
                "version_number": source["document_version"],
                "content_hash": source["content_hash"],
                "quoted_text": step,
                "acceptable_answer_spans": [step],
            }
        ],
    }
    return corpus, seed, case, response


def erase_presentation(response, variant):
    selection = response["provenance"]["answer_selection"]
    if variant == "whole_proof":
        selection["requirements"] = []
    else:
        for item in selection["requirements"]:
            proof = item.get("procedure_completeness")
            if proof:
                proof.pop("condition_exclusion_inventory", None)
                certificate = proof["output_certificate"]
                certificate["contract"] = "procedure-output-cover-v1"
                certificate.pop("condition_exclusion_inventory", None)
    for key in ("conflicts", "procedure_contexts", "inspected_sources"):
        selection[key] = []
    selection["procedure_read_set"] = {"sources": [], "groups": []}


@pytest.mark.parametrize("variant", ["whole_proof", "cover_downgrade"])
def test_online_scoring_rejects_pruned_proof_with_retained_actual_trace(variant):
    corpus, seed, case, response = captured_context()
    evaluator = script("evaluate_portfolio_retrieval")
    documents = evaluator.map_documents(corpus, seed)
    original_trace = copy.deepcopy(response["retrieval_trace"])
    erase_presentation(response, variant)
    assert response["retrieval_trace"] == original_trace
    row = evaluator.build_case_row(
        case, response, 200, documents, require_answer_spans=True
    )
    assert row["procedure_completeness_correct"] is False
    assert not row["passed"] and not row["answer_quality_passed"]


@pytest.mark.parametrize("variant", ["whole_proof", "cover_downgrade"])
def test_portable_scoring_rejects_pruned_proof_with_retained_actual_trace(variant):
    corpus, seed, case, response = captured_context()
    evaluator = script("evaluate_portfolio_retrieval")
    documents = evaluator.map_documents(corpus, seed)
    row = evaluator.build_case_row(
        case, response, 200, documents, require_answer_spans=True
    )
    assert row["passed"], "The unmodified actual producer fixture must replay"
    original_trace = copy.deepcopy(row["observed_response"]["retrieval_trace"])
    erase_presentation(row["observed_response"], variant)
    assert row["observed_response"]["retrieval_trace"] == original_trace
    auditor = script("verify_answer_coverage_delivery")
    portable = auditor.portable_documents(
        {
            "source_document_ids": {
                key: value["document_id"] for key, value in documents.items()
            },
            "source_manifest": evaluator.public_source_manifest(documents),
        },
        corpus,
    )
    with pytest.raises(ValueError, match="observed evidence disagrees"):
        auditor.audit_row(row, case, portable, True)


@pytest.mark.parametrize("variant", ["whole_proof", "cover_downgrade"])
def test_portable_rechecks_even_coherently_recomputed_corruption(variant):
    corpus, seed, case, response = captured_context()
    evaluator = script("evaluate_portfolio_retrieval")
    documents = evaluator.map_documents(corpus, seed)
    erase_presentation(response, variant)
    # The report's metrics are recomputed from the corrupted response, rather
    # than left stale. Their internal agreement cannot establish a valid proof.
    row = evaluator.build_case_row(
        case, response, 200, documents, require_answer_spans=True
    )
    auditor = script("verify_answer_coverage_delivery")
    portable = auditor.portable_documents(
        {
            "source_document_ids": {
                key: value["document_id"] for key, value in documents.items()
            },
            "source_manifest": evaluator.public_source_manifest(documents),
        },
        corpus,
    )
    audited = auditor.audit_row(row, case, portable, True)
    assert audited["procedure_completeness_correct"] is False
    assert not audited["passed"] and not audited["answer_quality_passed"]
