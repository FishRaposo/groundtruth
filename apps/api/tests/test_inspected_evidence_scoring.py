"""A clean refusal cannot hide private-source exposure in new evidence records."""

import pytest
from app.portfolio.evaluation import score_case

from tests.test_portfolio_corpus import _coverage_case_and_response


@pytest.mark.parametrize(
    "location",
    [
        "inspected_sources",
        "candidates",
        "followup_retrieval",
        "requirements",
        "proposals",
        "pattern_observations",
        "role_scope_read_set",
    ],
)
def test_private_inspected_evidence_fails_the_quality_gate(location):
    case, response, documents = _coverage_case_and_response()
    case.update(
        category="unanswerable",
        expected_behavior="refuse",
        expected_sources=[],
        required_facts=[],
    )
    documents["relay"].update(visibility="private", owner="another-user")
    identity = {"document_id": "uuid-relay", "document_version": 2}
    selection = {"contract": "requirement-evidence-v1"}
    selection[location] = (
        {
            "contract": "role-scope-inspection-read-set-v1",
            "complete": True,
            "documents": [identity],
        }
        if location == "role_scope_read_set"
        else [{"sources": [identity]}]
        if location == "followup_retrieval"
        else [{"witnesses": [identity]}]
        if location == "requirements"
        else [identity]
    )
    response.update(
        answer=None,
        refused=True,
        outcome="refused",
        sources=[],
        provenance={"answer_selection": selection},
    )
    result = score_case(case, response, 200, documents)
    assert result["unauthorized_source_exposures"] == 1
    assert result["answer_quality_passed"] is False
    assert result["passed"] is False


@pytest.mark.parametrize("carries_source", [False, True])
def test_request_budget_metadata_does_not_hide_or_invent_source_exposure(
    carries_source,
):
    case, response, documents = _coverage_case_and_response()
    case.update(
        category="unanswerable",
        expected_behavior="refuse",
        expected_sources=[],
        required_facts=[],
    )
    documents["relay"].update(visibility="private", owner="another-user")
    observation = {
        "requirement_id": "r1",
        "origin": "source_pattern",
        "decision": "pattern_requirement_budget_exceeded",
        "observed_count": 17,
        "complete": False,
        "truncated": True,
    }
    if carries_source:
        observation.update(document_id="uuid-relay", document_version=2)
    response.update(
        answer=None,
        refused=True,
        outcome="refused",
        sources=[],
        retrieval_trace={"scores": []},
        provenance={
            "answer_selection": {
                "contract": "requirement-evidence-v2",
                "candidates": [observation],
                "pattern_observations": [observation],
            }
        },
    )
    result = score_case(case, response, 200, documents)
    assert result["unauthorized_source_exposures"] == int(carries_source)
    assert result["answer_quality_passed"] is not carries_source
