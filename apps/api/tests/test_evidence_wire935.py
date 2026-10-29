"""Known v5 wire aliases and native/nested schema parity; UNITONLY."""

import json
from copy import deepcopy

import pytest

from tests.test_evaluation_contract913 import scoring_fixture
from tests.test_evidence_exposure926 import negative, scored


@pytest.fixture(scope="module")
def original():
    return scoring_fixture()


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize(
    "field,channel,required",
    [
        ("planning_inputs_json", "staged_request_inputs", "manifest"),
        ("retained_inputs_json", "staged_request_inputs", "capture"),
        ("plan_json", "request_plan", "read_set_json"),
    ],
)
@pytest.mark.parametrize("damage", ["contract_only", "missing_source_field", "valid"])
def test_nested_full_transport_reuses_native_wire_completeness(
    original, retained, field, channel, required, damage
):
    case, response, docs, exposed, _, actual = negative(
        original, retained=retained, forbidden=False
    )
    record = deepcopy(actual[channel])
    if damage == "contract_only":
        record = {"contract": record["contract"]}
    elif damage == "missing_source_field":
        record.pop(required)
    exposed["requirements"] = [{field: json.dumps(record)}]
    nested = scored(case, response, docs)
    exposed.pop("requirements")
    exposed[channel] = record
    native = scored(case, response, docs)
    for row in (nested, native):
        assert row["source_exposure_inspection_complete"] is (damage == "valid")
        assert row["execution_error"] is (damage != "valid")
        assert row["passed"] is (damage == "valid")
        assert row["answer_quality_passed"] is (damage == "valid")


@pytest.mark.parametrize("retained", [False, True])
@pytest.mark.parametrize(
    "alias", ["same", "conflict", "bool", "zero", "negative", "float", "null"]
)
def test_both_version_aliases_must_be_native_positive_and_equal(
    original, retained, alias
):
    case, response, docs, exposed, identity, _ = negative(
        original, retained=retained, forbidden=False
    )
    number = identity["document_version"]
    identity["version_number"] = {
        "same": number,
        "conflict": number + 1,
        "bool": True,
        "zero": 0,
        "negative": -1,
        "float": float(number),
        "null": None,
    }[alias]
    exposed["inspected_sources"] = [identity]
    row = scored(case, response, docs)
    assert row["source_exposure_inspection_complete"] is (alias == "same")
    assert row["execution_error"] is (alias != "same")
    assert row["passed"] is (alias == "same")
    assert row["answer_quality_passed"] is (alias == "same")


@pytest.mark.parametrize("retained", [False, True])
def test_single_version_number_alias_remains_supported(original, retained):
    case, response, docs, exposed, identity, _ = negative(
        original, retained=retained, forbidden=False
    )
    identity["version_number"] = identity.pop("document_version")
    exposed["inspected_sources"] = [identity]
    row = scored(case, response, docs)
    assert row["source_exposure_inspection_complete"] and not row["execution_error"]
    assert row["unauthorized_source_exposures"] == 0 and row["passed"]
