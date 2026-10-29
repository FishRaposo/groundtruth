"""A complete labels request requires a typed source set, never a scalar."""

import json
from copy import deepcopy
from dataclasses import asdict, replace

import pytest
from app.services import captured_role_consumer as consumer
from app.services import captured_role_evidence as role

from .fixtures import context, fact, factual_receipts


def test_actual_nominal_labels_prepare_full_typed_catalogue_with_fixed_fact_checks():
    plan, inputs = context()
    prepared = role.prepare_role_evidence(
        requirement_id=plan.requirements[0].id, **inputs
    )
    assert [member.literal.text for member in prepared.members] == [
        "coordinator",
        "observer",
        "recorder",
    ]
    assert prepared.candidate_value is None
    assert len(prepared.child_requirement_ids) == 3
    assert prepared.checks
    assert all("actor" not in check.pair.hypothesis for check in prepared.checks)


def test_positive_unitonly_labels_remain_a_typed_complete_set_and_compact_replay():
    plan, inputs = context()
    evidence = fact(inputs, plan.requirements[0].id)
    assert evidence.supported and evidence.facts == ()
    assert [m.literal.text for m in evidence.set_proof.members] == [
        "coordinator",
        "observer",
        "recorder",
    ]
    descriptor, group, observation, _, literal = consumer.view(evidence)
    assert descriptor["value"]["contract"] == "declared-role-member-set-v1"
    assert descriptor["value"]["members"] == [
        asdict(m) for m in evidence.set_proof.members
    ]
    assert literal == evidence.prepared.catalogue.raw.text
    assert group["source_guard"]["consumer_proof"]["contract"] == role.CONTRACT
    compact = consumer.compact(evidence)
    assert set(compact) == {
        "contract",
        "requirement_id",
        "proposal_id",
        "observations",
        "actual_executions",
    }
    assert (
        consumer.reconstruct_execution(compact, **inputs).record() == evidence.record()
    )
    selected = {
        "candidates": [consumer.candidate(evidence)],
        "proposals": group["origins"],
        "pattern_observations": [observation],
        "qa_observations": [],
    }
    assert consumer.groups(selected, evidence)[0] == [group]
    replayed = consumer.reconstruct_selection(
        selected, retained_selection=deepcopy(selected), **inputs
    )
    assert replayed[evidence.bound_requirement.id].record() == evidence.record()
    forged = deepcopy(selected)
    forged["candidates"][0]["typed_role_descriptor"]["value"] = "scalar catalogue"
    with pytest.raises(ValueError):
        consumer.groups(forged, evidence)


@pytest.mark.parametrize("kind", ["negative", "tie"])
def test_planning_support_alone_never_accepts_factual_labels(kind):
    plan, inputs = context()
    evidence = fact(inputs, plan.requirements[0].id, kind)
    assert (
        not evidence.supported and evidence.set_proof is None and evidence.facts == ()
    )


@pytest.mark.parametrize(
    "change", ["missing", "hypothesis", "tokens", "metadata", "runtime"]
)
def test_raw_role_receipt_tampers_cannot_replay(change):
    plan, inputs = context()
    prepared = role.prepare_role_evidence(
        requirement_id=plan.requirements[0].id, **inputs
    )
    obs, executions = factual_receipts(prepared)
    if change == "missing":
        obs, executions = obs[:-1], executions[:-1]
    elif change == "hypothesis":
        executions = (
            replace(
                executions[0], pair=replace(executions[0].pair, hypothesis="forged")
            ),
            *executions[1:],
        )
    elif change == "tokens":
        executions = (replace(executions[0], pair_tokens=True), *executions[1:])
    elif change == "metadata":
        meta = json.loads(executions[0].support_metadata_json)
        meta["minimum_entailment_margin"] = 0
        executions = (
            replace(executions[0], support_metadata_json=role.canonical(meta)),
            *executions[1:],
        )
    else:
        inputs["require_runtime"] = True
    with pytest.raises(ValueError):
        role.reconstruct_role_evidence(
            requirement_id=plan.requirements[0].id,
            proposal_id=prepared.proposals[0].proposal_id,
            observations=obs,
            actual_executions=executions,
            **inputs,
        )
