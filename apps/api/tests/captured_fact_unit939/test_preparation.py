import json
from copy import deepcopy
from pathlib import Path

import pytest
from app.services.captured_fact_support import (
    FactSupportClaim,
    prepare_fact_support,
)

from tests.staged_plan_unit837.fixtures_source import (
    ASSIGN,
    CAT,
    COND,
    EXTERNAL,
    FIELD,
    UNKNOWN,
)

from .fixtures import case


def test_clean_exact_clause_builds_mandatory_local_and_context_pairs():
    record, args = case()
    claims = (
        FactSupportClaim(
            "UNITONLY-request",
            "UNITONLY-reference",
            "The coordinator role for Cedar inspection is Rowan.",
        ),
    )
    prepared = prepare_fact_support(record, **args, claims=claims)
    assert prepared.ready_for_assessment
    assert [a.channel for a in prepared.assertions] == ["local", "context"]
    assert all(
        a.pair.premise == args["selected_clause"]["text"] for a in prepared.assertions
    )
    assert all(a.pair.hypothesis == claims[0].hypothesis for a in prepared.assertions)
    assert len({a.id for a in prepared.assertions}) == 2
    assert prepared.scope == "specified_hypothesis_model_support_only"


def prepare(record, args, **kwargs):
    claims = (
        FactSupportClaim(
            "UNITONLY-request",
            "UNITONLY-reference",
            "The coordinator role for Cedar inspection is Rowan.",
        ),
    )
    return prepare_fact_support(record, **args, claims=claims, **kwargs)


def test_closed_parallel_literal_slots_are_accounted_without_actor_or_fact_acceptance():
    record, args = case([CAT, ASSIGN, FIELD])
    prepared = prepare(record, args)
    assert prepared.ready_for_assessment
    cover = json.loads(prepared.governing_context_json)
    assert len(cover["unit_accounting"]) == len(
        record["source_productions"]["source_inventory"]["units"]
    )
    assert cover["namespace_disjointness"] == "NOT_ASSERTED"
    assert cover["full_source_ledger"] == record["source_productions"]
    assert cover["model_support"] == "UNASSESSED_NI"
    assert not cover["publication_ready"]
    assert all(
        row["semantic_status"] == "UNASSESSED_NI" for row in cover["unit_accounting"]
    )


def test_actual917_labels_context_retains_parallel_universe():
    record, args = case(actual=True)
    catalogue = next(
        row
        for row in record["source_productions"]["source_inventory"]["declarations"]
        if row["kind"] == "role_catalogue"
    )
    args.update(source_identity=catalogue["source"], selected_clause=catalogue["raw"])
    prepared = prepare(record, args)
    assert prepared.ready_for_assessment, prepared.pending
    assert all(
        row.pair.premise == catalogue["raw"]["text"] for row in prepared.assertions
    )
    cover = json.loads(prepared.governing_context_json)
    assert len(cover["unit_accounting"]) == 20
    assert cover["full_source_ledger"] == record["source_productions"]
    assert cover["namespace_disjointness"] == "NOT_ASSERTED"
    assert any(
        row["disposition"] == "strict_931_instruction_syntax_owned"
        for row in cover["unit_accounting"]
    )
    assert prepared.record()["model_support"] == "UNASSESSED_NI"


@pytest.mark.parametrize(
    "groups", [[ASSIGN, COND], [ASSIGN, EXTERNAL], [ASSIGN, UNKNOWN], [ASSIGN, ASSIGN]]
)
def test_pending_qualification_reference_unknown_or_same_slot_has_no_pairs(groups):
    record, args = case(groups)
    prepared = prepare(record, args)
    assert not prepared.ready_for_assessment and prepared.pending
    assert prepared.assertions == ()
    cover = json.loads(prepared.governing_context_json)
    assert cover["context"] is None
    assert len(cover["unit_accounting"]) == len(
        record["source_productions"]["source_inventory"]["units"]
    )


@pytest.mark.parametrize(
    "curated", [{"condition": "unresolved"}, {"conflict_group": "unresolved"}]
)
def test_curated_condition_and_opposition_block_preparation(curated):
    record, args = case(curated=curated)
    assert not prepare(record, args).ready_for_assessment


@pytest.mark.parametrize(
    "damage",
    [
        "retained",
        "source_body",
        "snapshot_id",
        "workspace",
        "profile",
        "source_scope",
        "clause",
        "metadata",
    ],
)
def test_raw_input_profile_source_scope_and_full_authority_are_replayed(damage):
    record, args = case()
    if damage == "retained":
        args["retained_inputs"]["capture"]["capture_sha256"] = "0" * 64
    elif damage == "profile":
        record["evidence_profile"]["evidence_reading_profile"] = "contextual_source_v3"
    elif damage == "source_scope":
        args["authoritative_snapshots"]["unretained"] = deepcopy(
            next(iter(args["authoritative_snapshots"].values()))
        )
    elif damage == "clause":
        args["selected_clause"]["start"] += 1
    elif damage == "metadata":
        args["expected_support_metadata"]["minimum_entailment_margin"] = 0
    else:
        source = next(iter(args["authoritative_snapshots"].values()))
        key = {
            "source_body": "body",
            "snapshot_id": "snapshot_id",
            "workspace": "workspace_id",
        }[damage]
        source[key] += " changed"
    with pytest.raises(ValueError):
        prepare(record, args)


@pytest.mark.parametrize(
    "claims",
    [(), [], (FactSupportClaim("", "r", "h"),), (FactSupportClaim("r", "s", "h"),) * 2],
)
def test_claim_inventory_is_typed_bounded_and_unique(claims):
    record, args = case()
    with pytest.raises(ValueError):
        prepare_fact_support(record, **args, claims=claims)


def test_preparation_is_detached_and_caller_keeps_request_binding_responsibility():
    record, args = case()
    prepared = prepare(record, args)
    exported = prepared.record()
    exported["assertions"].clear()
    record["source_productions"].clear()
    assert len(prepared.assertions) == 2
    assert prepared.record()["model_support"] == "UNASSESSED_NI"
    assert (
        "fixed_caller_request_entity_attribute_units_conditions_and_all_raw_proposals"
        in prepared.record()["remaining_gates"]
    )


QUESTIONS = [
    row
    for row in json.loads(
        (Path(__file__).parent / "data/actual929.json").read_text(encoding="utf-8")
    )
    if row["kind"] == "question"
]


@pytest.mark.parametrize("observed", QUESTIONS, ids=[row["id"] for row in QUESTIONS])
def test_retained_actual929_request_graphs_are_preserved_without_answer_acceptance(
    observed,
):
    record, args = case(observed=observed)
    prepared = prepare(record, args)
    cover = json.loads(prepared.governing_context_json)
    assert (
        cover["full_source_ledger"]["original_inputs"]["capture"] == observed["capture"]
    )
    assert prepared.record()["model_support"] == "UNASSESSED_NI"
