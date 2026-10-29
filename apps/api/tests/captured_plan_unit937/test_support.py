"""Protocol-only NI replay; no classifier or tokenizer runs."""

import json

from app.services.captured_planning_support import (
    prepare_planning_assertions,
    reconstruct_planning_support,
)

from tests.planning_library_unit830.test_support import metadata, retained

from .test_plan import case


def test_catalogue_requires_literal_scope_set_members_and_name_pairs():
    # Defect: empty NI inventory can otherwise masquerade as semantic readiness.
    prepared = prepare_planning_assertions(**case(), support_metadata=metadata())
    assert len(prepared.assertions) == 12
    assert {r.kind for r in prepared.assertions} == {
        "catalogue_scope:local",
        "catalogue_scope:context",
        "catalogue_literal_set:local",
        "catalogue_literal_set:context",
        "catalogue_member_relation:local",
        "catalogue_member_relation:context",
        "literal_name_relation:local",
        "literal_name_relation:context",
    }
    assert all("names an actor" not in r.pair.hypothesis for r in prepared.assertions)
    for row in prepared.assertions:
        lineage = json.loads(row.request_relation_json)
        assert lineage["context"]["publication_ready"] is False
        assert (
            lineage["context"]["governing_opposition_status"]
            == "MANDATORY_INDEPENDENT_REPLAY"
        )


def test_exact_independently_retained_pairs_are_required_and_facts_remain_external():
    from dataclasses import replace

    import pytest

    args = dict(**case(), support_metadata=metadata())
    prepared = prepare_planning_assertions(**args)
    observations, executions = retained(prepared)
    supported = reconstruct_planning_support(
        **args, observations=observations, actual_executions=executions
    )
    assert supported.accepted
    assert supported.accepted_scope == "captured_planning_source_relations_only"
    assert (
        "complete_governing_reference_curated_opposition_replay_required"
        in supported.remaining_gates
    )
    with pytest.raises(ValueError):
        reconstruct_planning_support(
            **args, observations=observations, actual_executions=executions[:-1]
        )
    wrong = replace(
        executions[0], pair=replace(executions[0].pair, premise="unrelated")
    )
    with pytest.raises(ValueError):
        reconstruct_planning_support(
            **args,
            observations=observations,
            actual_executions=(wrong, *executions[1:]),
        )


def test_each_member_pair_retains_exact_independent_member_binding():
    from app.services.captured_plan_binding import prepare_candidate_plan

    args = case("actors-dependent")
    candidate = prepare_candidate_plan(**args)
    members = {r["id"] for r in json.loads(candidate.members_json)}
    prepared = prepare_planning_assertions(**args, support_metadata=metadata())
    member_pairs = [
        a
        for a in prepared.assertions
        if a.kind.startswith("catalogue_member_relation:")
    ]
    assert len(member_pairs) == 6
    assert {a.member_binding_id for a in member_pairs} == members
    assert all(
        json.loads(a.request_relation_json)["member_binding_id"] == a.member_binding_id
        for a in member_pairs
    )
