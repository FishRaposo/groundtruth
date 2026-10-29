"""Dependent availability requires an independently replayed positive actor fact."""

import json
from dataclasses import asdict, dataclass

from app.services import captured_fact_support as factual
from app.services import captured_role_evidence as role
from app.services import planning_declarations as source
from app.services import staged_availability_evidence as legacy

CONTRACT = "captured-dependent-availability-evidence-v1"
PATTERN = "captured-dependent-field-v1"
FieldUnavailable = legacy.FieldUnavailable
AvailabilityFact = legacy.AvailabilityFact
AvailabilitySetProof = legacy.AvailabilitySetProof
AvailabilitySetPlan = legacy.AvailabilitySetPlan


@dataclass(frozen=True)
class AvailabilityPlan(legacy.AvailabilityPlan):
    fact_batches_json: str = "[]"


@dataclass(frozen=True)
class AvailabilityEvidence(legacy.AvailabilityEvidence):
    pass


@dataclass(frozen=True)
class AvailabilitySetEvidence(legacy.AvailabilitySetEvidence):
    pass


def _replay_actor(actors, identifier, inputs):
    supplied = actors.get(identifier)
    if type(supplied) is not role.RoleEvidence:
        raise FieldUnavailable("Actual retained captured actor execution required")
    return role.reconstruct_role_evidence(
        requirement_id=identifier,
        proposal_id=supplied.proposals[0].proposal_id,
        observations=supplied.observations,
        actual_executions=supplied.actual_executions,
        **inputs,
    )


def _binding(plan, requirement_id, actors, inputs):
    bound, use = role._bound(plan, requirement_id, {"availability"})
    edges = [
        r
        for r in json.loads(plan.edges_json)
        if r["kind"] == "actor_value_dependency" and r["target_id"] == requirement_id
    ]
    role._require(
        use.parent_id is not None and len(edges) == 1,
        "One actual dependent member/actor edge required",
    )
    edge = edges[0]
    evidence = _replay_actor(actors, edge["source_id"], inputs)
    if not evidence.supported or len(evidence.facts) != 1:
        raise FieldUnavailable("Prior actor relationship is not positively supported")
    fact = evidence.facts[0]
    role._require(
        fact.kind == "role_assignment"
        and fact.member_binding_id == use.member_binding_id == edge["member_binding_id"]
        and fact.value_slot_id == use.value_slot_id == edge["value_slot_id"]
        and use.execution_dependencies == (edge["source_id"],),
        "Captured actor/member/value-slot ancestry differs",
    )
    return bound, fact


def _closed_prior_arguments(row, subject, fact):
    for argument in row.arguments:
        extra = [q for q in argument.qualifiers if q.kind != "governing_scope"]
        if argument.quantifiers:
            return False
        if extra:
            if not (
                argument is subject
                and len(extra) == 1
                and extra[0].kind == "nominal_modifier"
                and extra[0].raw.text == fact.value
                and argument.unknowns == ("argument_qualifier_meaning_unassessed",)
            ):
                return False
        elif argument.unknowns:
            return False
    return True


def _field_matches(row, fact, bound, args):
    if row.kind != "literal_field" or [r.text for r in row.scope] != [
        r.text for r in fact.scope
    ]:
        return False
    subjects = [a for a in row.arguments if a.kind == "declaration_subject"]
    if len(subjects) != 1 or bound.attribute != "availability":
        return False
    subject = subjects[0]
    _, captures = source._inputs(
        args["manifest"], args["snapshots"], args["source_captures"]
    )
    for window, _, annotation in captures[row.source.document_id]:
        if not window.start <= subject.core.start < subject.core.end <= window.end:
            continue
        head = annotation["tokens"][subject.head_index]
        body = next(s.body for s in args["snapshots"] if s.identity == row.source)
        if (
            head["lemma"].casefold() != bound.attribute
            or head["dep"] != "nsubj"
            or body[subject.core.start : window.start + head["start"]].rstrip()
            != fact.value
            or subject.core.end != window.start + head["end"]
        ):
            continue
        # A captured ADJ modifier can be the exact previously supported literal.
        # It is never classified as an actor from capitalization or POS alone.
        if _closed_prior_arguments(row, subject, fact):
            return True
    return False


def prepare(*, actors, requirement_id, **inputs):
    plan, args, inventory, _ = role._context(inputs)
    bound, fact = _binding(plan, requirement_id, actors, inputs)
    matches = [
        r for r in inventory.declarations if _field_matches(r, fact, bound, args)
    ]
    if len(matches) != 1:
        raise FieldUnavailable("One exact actor/property declaration required")
    row = matches[0]
    payload = json.loads(row.payload_json)
    role._require(
        "value" in payload and len(payload.get("values", [])) == 1,
        "One complete literal availability value required",
    )
    value = source.RawRange(**payload["value"])
    snapshot = next(s for s in args["snapshots"] if s.identity == row.source)
    proposal = role._proposal(bound, snapshot, row, value, pattern_id=PATTERN)
    hypothesis = (
        f"For {fact.scope[0].text}, {fact.value}'s availability is {value.text}."
    )
    claims = (
        factual.FactSupportClaim(
            bound.id, proposal.proposal_id + ":availability", hypothesis
        ),
    )
    prepared = factual.prepare_fact_support(
        **role._fact_kwargs(inputs, row, claims, args["support_metadata"])
    )
    role._require(
        prepared.ready_for_assessment, "Dependent factual/governing context unresolved"
    )
    batches = [
        {
            "source": asdict(row.source),
            "raw": asdict(row.raw),
            "claims": [asdict(c) for c in claims],
        }
    ]
    return AvailabilityPlan(
        bound,
        fact,
        row,
        value,
        (proposal,),
        prepared.assertions,
        source.canonical(args["support_metadata"]),
        source.canonical(inputs["planning_inputs"]),
        source.canonical(batches),
    )


def reconstruct(*, observations, actual_executions, **inputs):
    prepared = prepare(**inputs)
    assessments = role._replay(prepared, inputs, observations, actual_executions)
    return AvailabilityEvidence(prepared, observations, actual_executions, assessments)


async def assess(config, *, execution_capture_kind="runtime_capture", **inputs):
    role._require(
        execution_capture_kind in {"runtime_capture", "UNITONLY"}
        and (
            not inputs.get("require_runtime", True)
            or execution_capture_kind == "runtime_capture"
        ),
        "Explicit compatible dependent execution kind required",
    )
    prepared = prepare(**inputs)
    selected = config.model_copy(deep=True)
    kwargs = next(role._batches(prepared, inputs))
    kwargs.pop("expected_support_metadata")
    result = await factual.assess_fact_support(
        config=selected, execution_capture_kind=execution_capture_kind, **kwargs
    )
    return reconstruct(
        observations=result.observations,
        actual_executions=result.actual_executions,
        **inputs,
    )


def aggregate(*, actors, children, requirement_id, **inputs):
    plan, args, _, _ = role._context(inputs)
    bound, use = role._bound(plan, requirement_id, {"availability"})
    references = [
        r
        for r in json.loads(plan.edges_json)
        if r["kind"] == "set_reference" and r["target_id"] == requirement_id
    ]
    role._require(
        use.parent_id is None and len(references) == 1,
        "Actual captured dependent set reference required",
    )
    catalogue = _replay_actor(actors, references[0]["source_id"], inputs)
    role._require(
        catalogue.supported and catalogue.set_proof is not None,
        "Positive typed catalogue required for dependent set",
    )
    if catalogue.set_proof is None:
        raise ValueError("Actual catalogue set proof required")
    ids = tuple(u.requirement_id for u in plan.uses if u.parent_id == requirement_id)
    evidence = []
    for identifier in ids:
        supplied = children.get(identifier)
        role._require(
            type(supplied) is AvailabilityEvidence,
            "Every availability child needs retained raw executions",
        )
        actual = reconstruct(
            actors=actors,
            requirement_id=identifier,
            observations=supplied.observations,
            actual_executions=supplied.actual_executions,
            **inputs,
        )
        role._require(
            actual.supported, "Every dependent member requires positive factual NI"
        )
        evidence.append(actual)
    role._require(
        len(evidence) == len(catalogue.set_proof.members)
        and {e.bound_requirement.member_binding_id for e in evidence}
        == {m.id for m in catalogue.set_proof.members},
        "Complete exact dependent member inventory required",
    )
    row = catalogue.prepared.catalogue
    snapshot = next(s for s in args["snapshots"] if s.identity == row.source)
    proposal = role._proposal(bound, snapshot, row, None, pattern_id=PATTERN)
    prepared = AvailabilitySetPlan(
        bound,
        row,
        None,
        (proposal,),
        tuple(c for e in evidence for c in e.prepared.checks),
        catalogue.prepared.support_metadata_json,
        source.canonical(inputs["planning_inputs"]),
    )
    proof = AvailabilitySetProof(
        "dependent_member_values",
        catalogue.set_proof.members,
        catalogue.bound_requirement.id,
        ids,
        tuple(f for e in evidence for f in e.facts),
    )
    return AvailabilitySetEvidence(prepared, proof, tuple(evidence))
