"""Compact new-profile typed facts, rebuilt from independent raw channels."""

import asyncio
import json
from copy import deepcopy
from dataclasses import asdict

from app.services import captured_availability_evidence as availability
from app.services import captured_role_evidence as role
from app.services import staged_role_consumer as transport

KINDS = role.KINDS
EXECUTION = "captured-role-execution-v1"
FIELD_EXECUTION = "captured-dependent-field-execution-v1"
FIELD_SET = "captured-dependent-field-set-v1"


def typed_requirement(requirement, context):
    if context.plan.record().get("contract") != "staged-request-plan-v2":
        return False
    if requirement.kind in KINDS:
        return True
    if requirement.kind != "availability":
        return False
    uses = [u for u in context.uses if u.requirement_id == requirement.id]
    role._require(len(uses) == 1, "One actual captured requirement use required")
    return bool(uses[0].execution_dependencies) or any(
        e["kind"] == "set_reference" and e["target_id"] == requirement.id
        for e in json.loads(context.plan.edges_json)
    )


async def assess_requirement(config, context, requirement, actors, fields):
    inputs = {
        "question": context.question,
        "planning_inputs": context.inputs(),
        "retained_inputs": deepcopy(context.inputs()),
        "authoritative_snapshots": context.snapshots(),
        "require_runtime": True,
    }
    try:
        return await _assess(config, context, requirement, actors, fields, inputs)
    except (Exception, asyncio.CancelledError) as exc:
        exc.__dict__["typed_prior_executions_json"] = role.canonical(
            [compact(e) for e in (*actors.values(), *fields.values())]
        )
        raise


async def _assess(config, context, requirement, actors, fields, inputs):
    if requirement.kind in KINDS:
        if requirement.id not in actors:
            actors[requirement.id] = await role.assess_role_evidence(
                config, requirement_id=requirement.id, **inputs
            )
        return actors[requirement.id]
    if requirement.id in fields:
        return fields[requirement.id]
    uses = [u for u in context.uses if u.requirement_id == requirement.id]
    role._require(len(uses) == 1, "Actual dependent use missing")
    if requirement.kind != "availability" or uses[0].parent_id is not None:
        return None
    references = [
        e
        for e in json.loads(context.plan.edges_json)
        if e["kind"] == "set_reference" and e["target_id"] == requirement.id
    ]
    role._require(len(references) == 1, "One captured dependent set reference required")
    root = references[0]["source_id"]
    ids = {
        u.requirement_id
        for u in context.uses
        if u.requirement_id == root or u.parent_id == root
    }
    for req in context.requirements:
        if req.id in ids and req.id not in actors:
            actors[req.id] = await role.assess_role_evidence(
                config, requirement_id=req.id, **inputs
            )
    children = [u for u in context.uses if u.parent_id == requirement.id]
    try:
        for child in children:
            fields[child.requirement_id] = await availability.assess(
                config, actors=actors, requirement_id=child.requirement_id, **inputs
            )
    except availability.FieldUnavailable:
        return None
    evidence = availability.aggregate(
        actors=actors, children=fields, requirement_id=requirement.id, **inputs
    )
    fields[requirement.id] = evidence
    return evidence


def compact(evidence):
    if type(evidence) is availability.AvailabilitySetEvidence:
        return {
            "contract": FIELD_SET,
            "requirement_id": evidence.bound_requirement.id,
            "proposal_id": evidence.proposals[0].proposal_id,
            "catalogue_requirement_id": evidence.set_proof.catalogue_requirement_id,
            "child_requirement_ids": list(evidence.set_proof.child_requirement_ids),
        }
    role._require(
        type(evidence) in (role.RoleEvidence, availability.AvailabilityEvidence),
        "Actual new-profile factual evidence required",
    )
    return json.loads(
        role.canonical(
            {
                "contract": FIELD_EXECUTION
                if type(evidence) is availability.AvailabilityEvidence
                else EXECUTION,
                "requirement_id": evidence.bound_requirement.id,
                "proposal_id": evidence.proposals[0].proposal_id,
                "observations": [asdict(r) for r in evidence.observations],
                "actual_executions": [asdict(r) for r in evidence.actual_executions],
            }
        )
    )


def reconstruct_execution(record, **inputs):
    role._require(
        type(record) is dict
        and set(record)
        == {
            "contract",
            "requirement_id",
            "proposal_id",
            "observations",
            "actual_executions",
        }
        and record["contract"] == EXECUTION,
        "Complete compact captured role execution required",
    )
    return role.reconstruct_role_evidence(
        **inputs,
        requirement_id=record["requirement_id"],
        proposal_id=record["proposal_id"],
        observations=transport._observations(record["observations"]),
        actual_executions=transport._executions(record["actual_executions"]),
    )


def reconstruct_selection(
    selection,
    *,
    question,
    planning_inputs,
    retained_inputs,
    authoritative_snapshots,
    retained_selection,
    require_runtime=True,
):
    records = [
        r["typed_role_execution"]
        for r in selection["candidates"]
        if "typed_role_execution" in r
    ]
    retained = [
        r["typed_role_execution"]
        for r in retained_selection["candidates"]
        if "typed_role_execution" in r
    ]
    role._require(
        role.canonical(records) == role.canonical(retained),
        "Captured factual receipts differ from independent retained capture",
    )
    inputs = {
        "question": question,
        "planning_inputs": planning_inputs,
        "retained_inputs": retained_inputs,
        "authoritative_snapshots": authoritative_snapshots,
        "require_runtime": require_runtime,
    }
    result, field_rows, set_rows = {}, [], []
    for candidate in selection["candidates"]:
        if "typed_role_execution" not in candidate:
            continue
        record = candidate["typed_role_execution"]
        if record.get("contract") == FIELD_EXECUTION:
            field_rows.append(candidate)
        elif record.get("contract") == FIELD_SET:
            set_rows.append(candidate)
        else:
            _store(result, candidate, reconstruct_execution(record, **inputs))
    actors = dict(result)
    for candidate in field_rows:
        record = candidate["typed_role_execution"]
        evidence = availability.reconstruct(
            actors=actors,
            requirement_id=record["requirement_id"],
            observations=transport._observations(record["observations"]),
            actual_executions=transport._executions(record["actual_executions"]),
            **inputs,
        )
        _store(result, candidate, evidence)
    children = {
        k: v for k, v in result.items() if type(v) is availability.AvailabilityEvidence
    }
    for candidate in set_rows:
        evidence = availability.aggregate(
            actors=actors,
            children=children,
            requirement_id=candidate["typed_role_execution"]["requirement_id"],
            **inputs,
        )
        _store(result, candidate, evidence)
    return result


def _store(result, candidate, evidence):
    identifier = evidence.bound_requirement.id
    role._require(
        candidate["requirement_id"] == identifier
        and identifier not in result
        and role.canonical(candidate["typed_role_execution"])
        == role.canonical(compact(evidence)),
        "Complete captured fact/member inventory differs",
    )
    result[identifier] = evidence


def view(evidence):
    # Only generic pure source/proposal presentation mechanics are reused.
    descriptor, group, observation, chunk, literal = transport.view(evidence)
    is_field = type(evidence) in (
        availability.AvailabilityEvidence,
        availability.AvailabilitySetEvidence,
    )
    contract = availability.CONTRACT if is_field else role.CONTRACT
    descriptor["typed_role_proof"]["contract"] = contract
    group["source_guard"]["contract"] = "captured-typed-role-source-v1"
    group["source_guard"]["consumer_proof"]["contract"] = contract
    observation.update(
        contract="captured-role-declaration-observation-v1",
        pattern_id=availability.PATTERN if is_field else role.PATTERN,
    )
    if type(evidence) is availability.AvailabilitySetEvidence:
        descriptor["value"]["contract"] = FIELD_SET
    elif evidence.prepared.candidate_value is not None:
        # Witness spans remain complete source clauses; only the independently
        # bound scalar enters later dependency questions and output values.
        literal = evidence.prepared.candidate_value.text
    return descriptor, group, observation, chunk, literal


def candidate(evidence):
    descriptor, _, observation, _, _ = view(evidence)
    proposal = evidence.proposals[0].record()
    return {
        **{
            k: descriptor[k]
            for k in ("chunk_id", "document_id", "document_version", "content_hash")
        },
        "requirement_id": evidence.bound_requirement.id,
        "origin": "source_pattern",
        "raw_span": proposal["chunk_range"],
        "null_margin": None,
        "proposal": proposal,
        "decision": "supported" if evidence.supported else "not_supported",
        "typed_role_execution": compact(evidence),
        "typed_role_descriptor": descriptor,
        "pattern_observation": observation,
    }


def groups(selection, evidence):
    _, group, observation, _, _ = view(evidence)
    role._require(
        role.canonical(selection["candidates"]) == role.canonical([candidate(evidence)])
        and role.canonical(selection["proposals"]) == role.canonical(group["origins"])
        and role.canonical(selection["pattern_observations"])
        == role.canonical([observation])
        and not selection.get("qa_observations"),
        "Captured fact output/proposal lineage differs",
    )
    return [group], {p["proposal_id"]: group for p in group["origins"]}


def value_identity(group):
    return role.canonical(group["value"])
