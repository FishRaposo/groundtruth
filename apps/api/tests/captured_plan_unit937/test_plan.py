"""Real full-inventory planning candidates; UNITONLY support is separate."""

import json

from app.services.captured_plan_binding import prepare_candidate_plan

from tests.captured_inputs_unit932.fixtures import profile
from tests.captured_productions_unit931.fixtures import arguments

from .test_structure import captured


def case(name="labels"):
    args = arguments()
    row = captured(name)
    args.update(
        question=row["text"], capture=row["capture"], evidence_profile=profile()
    )
    return args


def test_actual_four_source_catalogue_generates_parent_and_literal_children():
    # Defect: syntax recognized but actual catalogue never reaches new requirements.
    plan = prepare_candidate_plan(**case())
    assert [r.kind for r in plan.requirements] == [
        "role_catalogue",
        "role_label",
        "role_label",
        "role_label",
    ]
    assert [json.loads(u.features_json).get("role_label") for u in plan.uses[1:]] == [
        "coordinator",
        "observer",
        "recorder",
    ]
    ledger = json.loads(plan.source_productions_json)
    assert len(ledger["sources"]) == 4
    assert len(ledger["source_inventory"]["units"]) == 20
    assert ledger["excluded_sources"] == []


def test_supported_actual_dependent_plan_is_structural_only_with_unbound_values():
    from app.services.captured_plan_binding import reconstruct_captured_plan
    from app.services.captured_planning_support import prepare_planning_assertions

    from tests.planning_library_unit830.test_support import metadata, retained

    args = dict(**case("actors-dependent"), support_metadata=metadata())
    prepared = prepare_planning_assertions(**args)
    observations, executions = retained(prepared)
    plan = reconstruct_captured_plan(
        **args, observations=observations, actual_executions=executions
    )
    assert plan.resolved_request
    assert plan.structure_resolved and plan.planning_supported
    assert [r.kind for r in plan.requirements].count("availability") == 4
    assert len(plan.requirements) == 8
    slots = json.loads(plan.value_slots_json)
    assert len(slots) == 3
    assert all(r["status"] == "UNBOUND_ACTOR_VALUE" for r in slots)
    dependent = [u for u in plan.uses if u.parent_id and u.execution_dependencies]
    assert len(dependent) == 3
    assert all(u.value_slot_id in {s["id"] for s in slots} for u in dependent)
    assert not plan.publication_ready
    assert plan.factual_witnesses == "NOT_ASSESSED"
    assert len(json.loads(plan.remaining_external_governing_json)) > 0
    assert plan.record()["contract"] == "staged-request-plan-v2"


def test_cross_document_assignments_and_opposing_values_all_reach_unbound_slot():
    from tests.staged_plan_unit837.fixtures_source import (
        ASSIGN,
        CAT,
        NAME,
        source,
        universe,
    )

    args = case("actors-dependent")
    opposed = list(ASSIGN)
    opposed[-2] = ("Sage", "PROPN", "Sage", "attr", 6)
    pairs = [
        source([NAME, CAT], doc="UNITONLY-catalogue"),
        source([ASSIGN], doc="UNITONLY-assignment"),
        source([opposed], doc="UNITONLY-opposing-assignment"),
    ]
    args.update(
        manifest=universe(tuple(p[0] for p in pairs)),
        snapshots=tuple(p[0] for p in pairs),
        source_captures=tuple(p[1] for p in pairs),
    )
    plan = prepare_candidate_plan(**args)
    member = next(
        r
        for r in json.loads(plan.members_json)
        if r["literal"]["text"] == "coordinator"
    )
    slot = next(
        r
        for r in json.loads(plan.value_slots_json)
        if r["member_binding_id"] == member["id"]
    )
    candidates = json.loads(slot["candidates_json"])
    assert {r["literal_value_candidate"]["text"] for r in candidates} == {
        "Rowan",
        "Sage",
    }
    assert len({r["source"]["document_id"] for r in candidates}) == 2
    assert all(not r["accepted"] for r in candidates)
    assert slot["status"] == "UNBOUND_ACTOR_VALUE"
