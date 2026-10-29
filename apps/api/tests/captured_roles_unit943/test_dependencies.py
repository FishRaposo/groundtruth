"""Actual noun/ADJ captures bind only through prior positive role NI."""

import json
from dataclasses import replace

import pytest
from app.services import captured_availability_evidence as availability
from app.services import captured_role_consumer as consumer
from app.services.linguistic_dependencies import resolve_linguistic_requirement

from .fixtures import context, fact, factual_receipts


def actors(plan, inputs):
    return {
        r.id: fact(inputs, r.id)
        for r in plan.requirements
        if r.kind in {"role_catalogue", "role_assignment"}
    }


def test_actual_incumbents_keep_original_noun_and_adj_capture():
    plan, inputs = context("actors-dependent")
    evidence = actors(plan, inputs)
    values = [e.facts[0].value for e in evidence.values() if e.facts]
    assert values == ["Rowan", "Juniper", "Meadow"]
    juniper = next(
        e for e in evidence.values() if e.facts and e.facts[0].value == "Juniper"
    )
    original = json.loads(juniper.prepared.source_declaration.payload_json)[
        "original_candidate"
    ]
    assert original["original_value_token"]["pos"] == "ADJ"
    assert original["original_value_token"]["dep"] == "acomp"
    assert original["actor_value"] == "UNBOUND" and not original["accepted"]
    assert (
        juniper.facts[0].member_binding_id
        == juniper.bound_requirement.member_binding_id
    )
    assert juniper.facts[0].value_slot_id == juniper.bound_requirement.value_slot_id
    descriptor, group, _, _, value = consumer.view(juniper)
    assert value == group["value"] == "Juniper"
    assert descriptor["span"]["text"] == juniper.prepared.source_declaration.raw.text
    assert descriptor["span"]["text"] != value
    values = {key: consumer.view(e)[4] for key, e in evidence.items() if e.facts}
    child = next(r for r in plan.requirements if r.depends_on)
    current, binding = resolve_linguistic_requirement(child, plan, values)
    actual_value = values[child.depends_on[0]]
    assert current.topic == actual_value and actual_value in current.question
    assert binding["bindings"][0]["source_value"] == actual_value
    assert "." not in current.question


def test_actual_availability_including_adj_modifier_needs_prior_actor_and_own_ni():
    plan, inputs = context("actors-dependent")
    prior = actors(plan, inputs)
    children = {}
    for use in plan.uses:
        if not use.parent_id or not use.execution_dependencies:
            continue
        prepared = availability.prepare(
            actors=prior, requirement_id=use.requirement_id, **inputs
        )
        obs, executions = factual_receipts(prepared)
        child = availability.reconstruct(
            actors=prior,
            requirement_id=use.requirement_id,
            observations=obs,
            actual_executions=executions,
            **inputs,
        )
        assert child.supported and child.facts
        descriptor, group, _, _, scalar = consumer.view(child)
        assert scalar == group["value"] == child.facts[0].value.text
        assert descriptor["span"]["text"] == child.prepared.source_declaration.raw.text
        children[use.requirement_id] = child
    assert [e.facts[0].value.text for e in children.values()] == [
        "mornings",
        "afternoons",
        "evenings",
    ]
    root = next(
        r for r in plan.requirements if r.kind == "availability" and not r.depends_on
    )
    complete = availability.aggregate(
        actors=prior, children=children, requirement_id=root.id, **inputs
    )
    assert complete.supported and len(complete.facts) == 3
    with pytest.raises(ValueError):
        availability.aggregate(
            actors=prior,
            children=dict(list(children.items())[:-1]),
            requirement_id=root.id,
            **inputs,
        )


def test_missing_negative_or_forged_actor_fact_cannot_bind_dependent_value():
    plan, inputs = context("actors-dependent")
    child = next(u for u in plan.uses if u.parent_id and u.execution_dependencies)
    actor_id = child.execution_dependencies[0]
    with pytest.raises(ValueError):
        availability.prepare(actors={}, requirement_id=child.requirement_id, **inputs)
    unsupported = fact(inputs, actor_id, "negative")
    with pytest.raises(ValueError):
        availability.prepare(
            actors={actor_id: unsupported},
            requirement_id=child.requirement_id,
            **inputs,
        )
    accepted = fact(inputs, actor_id)
    forged = replace(accepted, facts=(replace(accepted.facts[0], value="forged"),))
    prepared = availability.prepare(
        actors={actor_id: forged}, requirement_id=child.requirement_id, **inputs
    )
    assert prepared.actor_fact.value == accepted.facts[0].value
    assert prepared.actor_fact.value != "forged"
