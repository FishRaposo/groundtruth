"""Catch implicit upgrades, JSON normalization and output-to-production cycles."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
from app.evidence_policy import EvidencePolicy
from app.services import captured_plan_inputs as transport
from app.services import planning_support as support

from .fixtures import arguments, authoritative, profile


@pytest.mark.parametrize("field", ["support_metadata", "observation", "execution"])
def test_non_native_inputs_cannot_be_silently_normalized(field):
    args = arguments()
    pair = support.PlanningPair(
        "UNITONLY932 premise", "UNITONLY932 hypothesis", "unassessed", "unassessed"
    )
    if field == "support_metadata":
        args[field] = {"invalid_tuple": ("never normalize",)}
    elif field == "observation":
        args["observations"] = (
            support.NliObservation(
                "unassessed",
                "unassessed",
                replace(pair, premise=("invalid",)),
                "{}",
                "{}",
            ),
        )
    else:
        args["actual_executions"] = (
            support.NliExecution(
                "unassessed", "unassessed", pair, ("invalid",), "{}", 1, "UNITONLY932"
            ),
        )
    with pytest.raises(ValueError):
        transport.capture_inputs_v2(**args, evidence_profile=profile())


@pytest.mark.parametrize(
    "selection", [None, {}, "contextual_source_v4", True, "old", "forged"]
)
def test_new_only_capture_rejects_default_old_and_noncanonical_selection(selection):
    if selection == "old":
        selection = EvidencePolicy(
            "qa_plus_source_patterns_v1",
            "ordinary_session_activity_v1",
            "source_declared_procedure_copy_v1",
            "scoped_note_context_v2",
            "contextual_source_v3",
        ).record()
    elif selection == "forged":
        selection = {**profile(), "source_production_contract": "forged"}
    with pytest.raises(ValueError):
        transport.capture_inputs_v2(**arguments(), evidence_profile=selection)


def test_output_receipts_are_retained_without_production_identity_or_acceptance():
    args = arguments()
    first = transport.capture_inputs_v2(**args, evidence_profile=profile())
    pair = support.PlanningPair(
        "UNITONLY932 unverified premise",
        "UNITONLY932 unverified hypothesis",
        "unassessed",
        "unassessed",
    )
    args["support_metadata"] = {"producer_success": True}
    args["observations"] = (
        support.NliObservation(
            "unassessed", "unassessed", pair, "{}", '{"forged_supported":true}'
        ),
    )
    args["actual_executions"] = (
        support.NliExecution(
            "unassessed",
            "unassessed",
            pair,
            "{}",
            '{"forged_supported":true}',
            1,
            "UNITONLY932_UNASSESSED",
        ),
    )
    second = transport.capture_inputs_v2(**args, evidence_profile=profile())
    assert first["request_productions"] == second["request_productions"]
    assert first["source_productions"] == second["source_productions"]
    result = transport.decode_inputs_v2(
        second,
        question=args["question"],
        authoritative_snapshots=authoritative(second),
        retained_inputs=deepcopy(second),
    )
    assert result.arguments["observations"] == args["observations"]
    assert result.arguments["actual_executions"] == args["actual_executions"]
    assert not result.request_productions["complete_plan"]
    assert not result.source_productions["full_plan_accepted"]
    assert (
        result.source_productions["source_NI_authority_currentness"] == "NOT_ASSESSED"
    )


def test_producer_record_detaches_profile_capture_and_metadata():
    args = arguments()
    selected = profile()
    record = transport.capture_inputs_v2(**args, evidence_profile=selected)
    before = deepcopy(record)
    selected["pattern_limits"].clear()
    args["capture"]["annotation"]["tokens"].clear()
    args["support_metadata"]["injected"] = True
    assert record == before


QUESTIONS = [
    row
    for row in json.loads(
        (Path(__file__).parent / "data/actual929.json").read_text(encoding="utf-8")
    )
    if row["kind"] == "question"
]


@pytest.mark.parametrize("observed", QUESTIONS, ids=[row["id"] for row in QUESTIONS])
def test_actual929_questions_survive_without_promised_resolution(
    observed,
):
    args = arguments()
    args.update(question=observed["text"], capture=observed["capture"])
    record = transport.capture_inputs_v2(**args, evidence_profile=profile())
    result = transport.decode_inputs_v2(
        json.loads(json.dumps(record)),
        question=observed["text"],
        authoritative_snapshots=authoritative(record),
        retained_inputs=deepcopy(record),
    )
    assert result.arguments["question"] == observed["text"]
    assert result.arguments["capture"] == observed["capture"]
    assert result.request_productions["original_capture"] == observed["capture"]
    assert not result.request_productions["complete_plan"]
    assert result.source_productions["excluded_sources"] == []
    assert not result.source_productions["full_plan_accepted"]
