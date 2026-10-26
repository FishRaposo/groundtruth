"""A measured reader result cannot silently use a different support contract."""

import copy
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "requirements_evaluator",
    Path(__file__).parents[1] / "evaluate_portfolio_retrieval.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    settings = {
        "reader_null_threshold": 4,
        "reader_model_revision": "reader-pin",
        "answer_support_mode": "local_nli",
        "support_model_revision": "support-pin",
        "support_min_margin": 3,
        "selection_contract": "requirement-evidence-v1",
    }
    selection = {
        "mode": "reader",
        "threshold": 4,
        "revision": "reader-pin",
        "contract": "requirement-evidence-v1",
        "evidence_support": {
            "mode": "local_nli",
            "revision": "support-pin",
            "minimum_entailment_margin": 3,
        },
    }
    return settings, {
        "provenance": {"answer_selection": selection},
        "retrieval_trace": {"refusal_threshold": None},
    }


@pytest.mark.parametrize(
    "field,value",
    [("mode", "disabled"), ("revision", "other-pin"), ("minimum_entailment_margin", 0)],
)
def test_changed_support_runtime_cannot_pass(field, value):
    settings, response = fixture()
    response["provenance"]["answer_selection"]["evidence_support"][field] = value
    row = {"passed": True, "answer_quality_passed": True}
    MODULE.check_response_configuration(row, response, 200, settings, "candidate")
    assert row["passed"] is False
    assert row["execution_error"] is True


def test_missing_requirement_contract_cannot_pass():
    settings, response = fixture()
    response["provenance"]["answer_selection"].pop("contract")
    row = {"passed": True}
    MODULE.check_response_configuration(row, response, 200, settings, "candidate")
    assert row["passed"] is False


def test_matching_support_and_legacy_reports_remain_compatible():
    settings, response = fixture()
    for expected in [
        settings,
        {key: value for key, value in settings.items() if key.startswith("reader_")},
    ]:
        row = {"passed": True}
        MODULE.check_response_configuration(
            row, copy.deepcopy(response), 200, expected, "candidate"
        )
        assert row == {"passed": True}
