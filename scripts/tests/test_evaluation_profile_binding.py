"""A report cannot measure composite/activity behavior while claiming QA-only."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "profile_bound_evaluator",
    Path(__file__).parents[1] / "evaluate_portfolio_retrieval.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    return {
        "reader_null_threshold": 4,
        "reader_model_revision": "reader-pin",
        "answer_proposal_profile": "qa_plus_source_patterns_v1",
        "role_scope_policy": "ordinary_session_activity_v1",
    }, {
        "retrieval_trace": {"refusal_threshold": None},
        "provenance": {
            "answer_selection": {
                "mode": "reader",
                "threshold": 4,
                "revision": "reader-pin",
                "evidence_profile": {
                    "contract": "evidence-profile-v1",
                    "proposal_profile": "qa_plus_source_patterns_v1",
                    "role_scope_policy": "ordinary_session_activity_v1",
                },
            }
        },
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("proposal_profile", "qa_only_v1"),
        ("role_scope_policy", "literal_v1"),
        ("proposal_profile", None),
        ("role_scope_policy", None),
    ],
)
def test_mismatched_or_unrecorded_eligibility_cannot_pass_candidate_configuration(
    field, value
):
    settings, response = fixture()
    response["provenance"]["answer_selection"]["evidence_profile"][field] = value
    row = {"passed": True, "answer_quality_passed": True}
    MODULE.check_response_configuration(row, response, 200, settings, "candidate")
    assert row["passed"] is False
    assert row["answer_quality_passed"] is False
    assert row["execution_error"] is True


def test_explicit_matching_profile_and_historical_unpinned_reports_stay_compatible():
    settings, response = fixture()
    for expected in (
        settings,
        {key: value for key, value in settings.items() if key.startswith("reader_")},
    ):
        row = {"passed": True}
        MODULE.check_response_configuration(row, response, 200, expected, "candidate")
        assert row == {"passed": True}
