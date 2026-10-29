"""Actual943 captured source transports with UNITONLY NI; no API/model quality."""

import json
from copy import deepcopy

import pytest
from app.portfolio import coverage

from tests.captured_roles_unit943.fixtures import labels_selection


@pytest.fixture(scope="module")
def captured():
    plan, inputs, selection, _ = labels_selection()
    selection.update(
        contract="requirement-evidence-v5",
        evidence_profile=inputs["planning_inputs"]["evidence_profile"],
        request_plan=plan.record(),
        staged_request_inputs=inputs["planning_inputs"],
    )
    # The shared pure view contains tuples; the actual HTTP DTO is JSON-native.
    response = json.loads(
        json.dumps({"provenance": {"answer_selection": selection}}, allow_nan=False)
    )
    return response, inputs


def test_complete_actual_input2_plan2_exposure_inventory_is_inspectable(captured):
    # Defect: deliberate input1-only schema flags all new real responses as errors.
    response, inputs = captured
    sources, complete = coverage._staged_exposure_sources(response)
    assert complete
    assert {(s["document_id"], s["document_version"]) for s in sources} == {
        (s["document_id"], s["document_version"])
        for s in inputs["authoritative_snapshots"].values()
    }


@pytest.mark.parametrize("change", ["contract", "productions", "json", "proposal_link"])
def test_malformed_new_transport_is_incomplete_with_exposures_retained(
    captured, change
):
    response, _ = deepcopy(captured)
    selected = response["provenance"]["answer_selection"]
    if change == "contract":
        selected["staged_request_inputs"]["contract"] = "unknown-inputs-v2"
    elif change == "productions":
        selected["staged_request_inputs"]["source_productions"] = {}
    elif change == "json":
        selected["request_plan"]["operation_ledger_json"] = "{}"
    else:
        selected["pattern_observations"][0]["proposal_ids"] = ["absent-proposal"]
    sources, complete = coverage._staged_exposure_sources(response)
    assert not complete and sources


@pytest.mark.parametrize("retained", [False, True])
def test_known_new_execution_lineage_json_counts_its_exact_source_version(
    captured, retained
):
    response, _ = deepcopy(captured)
    selected = response["provenance"]["answer_selection"]
    if retained:
        response["retrieval_trace"] = {
            "provenance": {"answer_selection": deepcopy(selected)}
        }
        selected = response["retrieval_trace"]["provenance"]["answer_selection"]
    identity = {
        "document_id": "00000000-0000-0000-0000-000000000946",
        "document_version": 9,
    }
    selected["requirements"] = [
        {
            "retained_proof": {
                "request_relation_json": json.dumps({"source_identity": identity})
            }
        }
    ]
    sources, complete = coverage._staged_exposure_sources(response)
    assert complete
    assert identity in sources


def test_arbitrary_literal_and_metadata_json_are_not_parsed(captured):
    response, _ = deepcopy(captured)
    selected = response["provenance"]["answer_selection"]
    identity = {
        "document_id": "00000000-0000-0000-0000-000000000946",
        "document_version": 9,
    }
    selected["requirements"] = [{"value": json.dumps(identity), "metadata": identity}]
    sources, complete = coverage._staged_exposure_sources(response)
    assert complete and identity not in sources
