"""Typed role execution transport and independently reconstructed output views.

No inference, access grant or legacy role projection occurs in the pure replay.
Catalogue values remain typed sets; source spans are separate display material.
"""

import json
import uuid
from copy import deepcopy
from dataclasses import asdict
from typing import TypedDict

from app.models.chunk import ChunkWithScore
from app.services import planning_support as support
from app.services import staged_availability_evidence as availability
from app.services import staged_role_evidence as role

KINDS = frozenset({"role_catalogue", "role_label", "role_assignment"})
EXECUTION = "staged-role-execution-v1"
FIELD_EXECUTION = "staged-dependent-field-execution-v1"
FIELD_SET = "staged-dependent-field-set-v1"


class ReplayInputs(TypedDict):
    question: str
    planning_inputs: dict
    retained_inputs: dict
    authoritative_snapshots: dict
    require_runtime: bool


def typed_requirement(requirement, context):
    if requirement.kind in KINDS:
        return True
    if requirement.kind != "availability":
        return False
    use = next(row for row in context.uses if row.requirement_id == requirement.id)
    return bool(use.execution_dependencies) or any(
        edge["kind"] == "set_reference" and edge["target_id"] == requirement.id
        for edge in json.loads(context.plan.edges_json)
    )


async def assess_requirement(config, context, requirement, actors, fields):
    import asyncio

    try:
        return await _assess_requirement(config, context, requirement, actors, fields)
    except (Exception, asyncio.CancelledError) as exc:
        exc.__dict__["typed_prior_executions_json"] = role.canonical(
            [compact(evidence) for evidence in (*actors.values(), *fields.values())]
        )
        raise


async def _assess_requirement(config, context, requirement, actors, fields):
    actual = context.inputs()
    inputs: ReplayInputs = {
        "question": context.question,
        "planning_inputs": actual,
        "retained_inputs": deepcopy(actual),
        "authoritative_snapshots": context.snapshots(),
        "require_runtime": True,
    }
    if requirement.kind in KINDS:
        if requirement.id in actors:
            return actors[requirement.id]
        evidence = await role.assess_role_evidence(
            config, requirement_id=requirement.id, **inputs
        )
        actors[requirement.id] = evidence
        return evidence
    if requirement.id in fields:
        return fields[requirement.id]
    use = next(row for row in context.uses if row.requirement_id == requirement.id)
    if requirement.kind != "availability" or use.parent_id is not None:
        return None
    references = [
        edge
        for edge in json.loads(context.plan.edges_json)
        if edge["kind"] == "set_reference" and edge["target_id"] == requirement.id
    ]
    if len(references) != 1:
        return None
    root = references[0]["source_id"]
    required_actor_ids = {
        row.requirement_id
        for row in context.uses
        if row.requirement_id == root or row.parent_id == root
    }
    for actor_requirement in context.requirements:
        if (
            actor_requirement.id in required_actor_ids
            and actor_requirement.id not in actors
        ):
            actors[actor_requirement.id] = await role.assess_role_evidence(
                config, requirement_id=actor_requirement.id, **inputs
            )
    children = [row for row in context.uses if row.parent_id == requirement.id]
    try:
        prepared = [
            availability.prepare(
                actors=actors, requirement_id=row.requirement_id, **inputs
            )
            for row in children
        ]
    except availability.FieldUnavailable:
        return None
    for child in prepared:
        observations, executions = await role.assess_dependent_checks(config, child)
        result = availability.reconstruct(
            actors=actors,
            requirement_id=child.bound_requirement.id,
            observations=observations,
            actual_executions=executions,
            **inputs,
        )
        fields[result.bound_requirement.id] = result
    result = availability.aggregate(
        actors=actors, children=fields, requirement_id=requirement.id, **inputs
    )
    fields[requirement.id] = result
    return result


def compact(evidence):
    if isinstance(evidence, availability.AvailabilitySetEvidence):
        return {
            "contract": FIELD_SET,
            "requirement_id": evidence.bound_requirement.id,
            "proposal_id": evidence.proposals[0].proposal_id,
            "catalogue_requirement_id": evidence.set_proof.catalogue_requirement_id,
            "child_requirement_ids": list(evidence.set_proof.child_requirement_ids),
        }
    contract = (
        FIELD_EXECUTION
        if isinstance(evidence, availability.AvailabilityEvidence)
        else EXECUTION
    )
    return json.loads(
        role.canonical(
            {
                "contract": contract,
                "requirement_id": evidence.bound_requirement.id,
                "proposal_id": evidence.proposals[0].proposal_id,
                "observations": [asdict(row) for row in evidence.observations],
                "actual_executions": [
                    asdict(row) for row in evidence.actual_executions
                ],
            }
        )
    )


def _observations(rows):
    if type(rows) is not list:
        raise ValueError("Actual typed role observations required")
    return tuple(
        support.NliObservation(**{**row, "pair": support.PlanningPair(**row["pair"])})
        for row in rows
    )


def _executions(rows):
    if type(rows) is not list:
        raise ValueError("Actual typed role execution receipts required")
    return tuple(
        support.NliExecution(**{**row, "pair": support.PlanningPair(**row["pair"])})
        for row in rows
    )


def reconstruct_execution(record, **actual_inputs):
    if (
        type(record) is not dict
        or set(record)
        != {
            "contract",
            "requirement_id",
            "proposal_id",
            "observations",
            "actual_executions",
        }
        or record["contract"] != EXECUTION
    ):
        raise ValueError("Complete compact typed role execution required")
    return role.reconstruct_role_evidence(
        **actual_inputs,
        requirement_id=record["requirement_id"],
        proposal_id=record["proposal_id"],
        observations=_observations(record["observations"]),
        actual_executions=_executions(record["actual_executions"]),
    )


def _store_reconstruction(result, candidate, evidence):
    identifier = evidence.bound_requirement.id
    if (
        candidate["requirement_id"] != identifier
        or identifier in result
        or role.canonical(compact(evidence))
        != role.canonical(candidate["typed_role_execution"])
    ):
        raise ValueError("Typed declaration execution/member inventory differs")
    result[identifier] = evidence


def reconstruct_selection(
    selection,
    *,
    question,
    planning_inputs,
    retained_inputs,
    authoritative_snapshots,
    retained_selection,
):
    actual_records = [
        row["typed_role_execution"]
        for row in selection["candidates"]
        if "typed_role_execution" in row
    ]
    retained_records = [
        row["typed_role_execution"]
        for row in retained_selection["candidates"]
        if "typed_role_execution" in row
    ]
    if role.canonical(actual_records) != role.canonical(retained_records):
        raise ValueError(
            "Typed executions differ from separately retained service-return capture"
        )
    result = {}
    inputs: ReplayInputs = {
        "question": question,
        "planning_inputs": planning_inputs,
        "retained_inputs": retained_inputs,
        "authoritative_snapshots": authoritative_snapshots,
        "require_runtime": True,
    }
    fields, sets = [], []
    for candidate in selection["candidates"]:
        if "typed_role_execution" not in candidate:
            continue
        record = candidate["typed_role_execution"]
        if record.get("contract") == FIELD_EXECUTION:
            fields.append(candidate)
            continue
        if record.get("contract") == FIELD_SET:
            sets.append(candidate)
            continue
        evidence = reconstruct_execution(record, **inputs)
        _store_reconstruction(result, candidate, evidence)
    actors = dict(result)
    for candidate in fields:
        record = candidate["typed_role_execution"]
        evidence = availability.reconstruct(
            actors=actors,
            requirement_id=record["requirement_id"],
            observations=_observations(record["observations"]),
            actual_executions=_executions(record["actual_executions"]),
            **inputs,
        )
        _store_reconstruction(result, candidate, evidence)
    children = {
        key: value
        for key, value in result.items()
        if isinstance(value, availability.AvailabilityEvidence)
    }
    for candidate in sets:
        record = candidate["typed_role_execution"]
        evidence = availability.aggregate(
            actors=actors,
            children=children,
            requirement_id=record["requirement_id"],
            **inputs,
        )
        _store_reconstruction(result, candidate, evidence)
    return result


def view(evidence):
    prepared = evidence.prepared
    proposal = evidence.proposals[0].record()
    snapshot = next(
        row
        for row in json.loads(prepared.planning_inputs_json)["snapshots"]
        if row["identity"]["document_id"] == proposal["document_id"]
    )
    chunk = next(
        row for row in snapshot["chunks"] if row["chunk_id"] == proposal["chunk_id"]
    )
    raw = prepared.source_declaration.raw
    literal = raw.text
    origin = proposal["document_range"]["start"] - proposal["chunk_range"]["start"]
    member = prepared.bound_requirement
    set_proof = asdict(evidence.set_proof) if evidence.set_proof else None
    value = (
        {
            "contract": "declared-role-member-set-v1",
            "operation": evidence.set_proof.operation,
            "members": [asdict(row) for row in evidence.set_proof.members],
        }
        if evidence.set_proof
        else prepared.candidate_value.text
        if prepared.candidate_value
        else None
    )
    is_field = isinstance(
        evidence,
        (availability.AvailabilityEvidence, availability.AvailabilitySetEvidence),
    )
    contract = availability.CONTRACT if is_field else role.CONTRACT
    pattern = availability.PATTERN if is_field else role.PATTERN
    if isinstance(evidence, availability.AvailabilitySetEvidence):
        value = {
            "contract": FIELD_SET,
            "members": [asdict(row) for row in evidence.facts],
        }
    descriptor = {
        "chunk_id": proposal["chunk_id"],
        "document_id": proposal["document_id"],
        "document_version": proposal["document_version"],
        "content_hash": proposal["content_hash"],
        "value": value,
        "span": {"start": raw.start - origin, "end": raw.end - origin, "text": literal},
        "document_range": {"start": raw.start, "end": raw.end},
        "proof_edges": [],
        "typed_role_proof": {
            "contract": role.CONTRACT,
            "kind": member.kind,
            "member_binding_id": member.member_binding_id,
            "value_slot_id": member.value_slot_id,
            "source_declaration_id": prepared.source_declaration.id,
            "check_ids": [row.id for row in prepared.checks],
        },
    }
    if set_proof is not None:
        descriptor["typed_set_proof"] = set_proof
    descriptor["typed_role_proof"]["contract"] = contract
    margin = min(
        json.loads(row.assessment_json)["entailment_margin"]
        for row in evidence.assessments
    )
    check_by_id = {row.id: row for row in prepared.checks}
    guard = {
        "contract": "staged-typed-role-source-v1",
        "consumer_proof": {
            "contract": contract,
            "kind": member.kind,
            "source_identity": asdict(prepared.source_declaration.source),
            "typed_set_proof": set_proof,
            "facts": [asdict(row) for row in evidence.facts],
            "nli_assessments": [
                {
                    "name": row.assertion_id,
                    "premise": row.pair.premise,
                    "hypothesis": row.pair.hypothesis,
                    "source_identity": asdict(
                        check_by_id[row.assertion_id].source_identity
                    ),
                    "source_range": asdict(check_by_id[row.assertion_id].source_range),
                    "assessment": json.loads(row.assessment_json),
                }
                for row in evidence.assessments
            ],
        },
    }
    observation = {
        "contract": "staged-role-declaration-observation-v1",
        "requirement_id": member.id,
        "origin": "source_pattern",
        "pattern_id": pattern,
        "proposal_ids": [proposal["proposal_id"]],
        "source_declaration_id": prepared.source_declaration.id,
    }
    group = {
        "requirement_id": member.id,
        "origins": [proposal],
        "descriptor": descriptor,
        "supported": evidence.supported,
        "margin": margin,
        "value": value,
        "source_guard": guard,
    }
    source_identity = prepared.source_declaration.source
    transport = ChunkWithScore(
        id=uuid.UUID(proposal["chunk_id"]),
        document_id=uuid.UUID(proposal["document_id"]),
        content=chunk["literal"]["text"],
        chunk_index=chunk["ordinal"],
        metadata={
            **json.loads(chunk["metadata_json"]),
            "document_version": source_identity.document_version,
            "content_hash": source_identity.content_hash,
            "workspace_id": source_identity.workspace_id,
        },
        relevance_score=0.0,
    )
    return descriptor, group, observation, transport, literal


def candidate(evidence):
    descriptor, group, observation, _, _ = view(evidence)
    proposal = evidence.proposals[0].record()
    return {
        **{
            name: descriptor[name]
            for name in ("chunk_id", "document_id", "document_version", "content_hash")
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
    descriptor, group, observation, _, _ = view(evidence)
    expected = candidate(evidence)
    if len(selection["candidates"]) != 1 or role.canonical(
        selection["candidates"][0]
    ) != role.canonical(expected):
        raise ValueError("Typed role candidate differs from actual retained execution")
    if role.canonical(selection["proposals"]) != role.canonical(
        group["origins"]
    ) or role.canonical(selection["pattern_observations"]) != role.canonical(
        [observation]
    ):
        raise ValueError("Typed role normal proposal/discovery lineage differs")
    if selection.get("qa_observations"):
        raise ValueError("Typed declaration evidence cannot substitute QA observations")
    return [group], {proposal["proposal_id"]: group for proposal in group["origins"]}


def value_identity(group):
    return role.canonical(group["value"])
