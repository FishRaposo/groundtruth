"""Dependent factual fields from actual supported actor-slot lineage.

The request and its original set reference remain unchanged. Availability is
an actual declared property with its own local/whole-body NLI, never presence.
"""

import json
from dataclasses import asdict, dataclass

from . import planning_declarations as source
from . import planning_support as support
from . import staged_role_evidence as role

CONTRACT = "staged-dependent-availability-evidence-v1"
PATTERN = "staged-dependent-field-v1"


class FieldUnavailable(ValueError):
    """The authoritative inventory does not bind this dependent field."""


@dataclass(frozen=True)
class AvailabilityPlan:
    bound_requirement: role.BoundRequirement
    actor_fact: role.RoleFact
    source_declaration: source.Declaration
    candidate_value: source.RawRange
    proposals: tuple
    checks: tuple
    support_metadata_json: str
    planning_inputs_json: str


@dataclass(frozen=True)
class AvailabilityEvidence:
    prepared: AvailabilityPlan
    observations: tuple
    actual_executions: tuple
    assessments: tuple

    @property
    def supported(self):
        return all(row.supported for row in self.assessments)

    @property
    def bound_requirement(self):
        return self.prepared.bound_requirement

    @property
    def proposals(self):
        return self.prepared.proposals

    @property
    def set_proof(self):
        return None

    @property
    def facts(self):
        return (
            (
                AvailabilityFact(
                    self.bound_requirement.id,
                    self.prepared.candidate_value,
                    self.prepared.actor_fact,
                    self.prepared.source_declaration,
                ),
            )
            if self.supported
            else ()
        )


@dataclass(frozen=True)
class AvailabilityFact:
    requirement_id: str
    value: source.RawRange
    actor: role.RoleFact
    declaration: source.Declaration


@dataclass(frozen=True)
class AvailabilitySetProof:
    operation: str
    members: tuple
    catalogue_requirement_id: str
    child_requirement_ids: tuple[str, ...]
    values: tuple[AvailabilityFact, ...]


@dataclass(frozen=True)
class AvailabilitySetPlan:
    bound_requirement: role.BoundRequirement
    source_declaration: source.Declaration
    candidate_value: None
    proposals: tuple
    checks: tuple
    support_metadata_json: str
    planning_inputs_json: str


@dataclass(frozen=True)
class AvailabilitySetEvidence:
    prepared: AvailabilitySetPlan
    set_proof: AvailabilitySetProof
    children: tuple[AvailabilityEvidence, ...]

    @property
    def bound_requirement(self):
        return self.prepared.bound_requirement

    @property
    def proposals(self):
        return self.prepared.proposals

    @property
    def supported(self):
        return all(child.supported for child in self.children)

    @property
    def assessments(self):
        return tuple(row for child in self.children for row in child.assessments)

    @property
    def facts(self):
        return self.set_proof.values


def _requirement_use(plan, requirement_id):
    requirements = [row for row in plan.requirements if row.id == requirement_id]
    uses = [row for row in plan.uses if row.requirement_id == requirement_id]
    role._require(
        len(requirements) == len(uses) == 1,
        "Unique actual dependent requirement and use required",
    )
    return requirements[0], uses[0]


def aggregate(*, actors, children, requirement_id, **inputs):
    context = role._context(inputs)
    plan, args, _, structural, _ = context
    requirement, use = _requirement_use(plan, requirement_id)
    references = [
        edge
        for edge in structural.edges
        if edge.kind == "set_reference" and edge.target_id == requirement_id
    ]
    role._require(
        requirement.kind == "availability"
        and use.parent_id is None
        and len(references) == 1,
        "Actual availability set root/reference required",
    )
    catalogue = _replay_actor(actors, references[0].source_id, inputs, context)
    if catalogue is None or not catalogue.supported or catalogue.set_proof is None:
        raise ValueError("Actual supported catalogue set required")
    expected = [
        row.requirement_id for row in plan.uses if row.parent_id == requirement_id
    ]
    actual = [
        _replay_child(children.get(identifier), actors, identifier, inputs, context)
        for identifier in expected
    ]
    role._require(
        len(expected) == len(actual) == len(catalogue.set_proof.members)
        and set(expected) == {child.bound_requirement.id for child in actual},
        "Every actual dependent member needs separate factual evidence",
    )
    role._require(
        {child.bound_requirement.member_binding_id for child in actual}
        == {member.id for member in catalogue.set_proof.members},
        "Dependent set membership differs from actual catalogue",
    )
    bound = role.BoundRequirement(
        **asdict(requirement),
        use_json=source.canonical(asdict(use)),
        plan_sha256=source.digest(plan.record()),
        member_binding_id=None,
        value_slot_id=None,
        source_uses_json=use.source_uses_json,
    )
    # Use the validated typed snapshot from the actual role context, not a
    # projected scalar catalogue fact or the actor's mere presence.
    source_snapshot = next(
        row
        for row in args["snapshots"]
        if row.identity == catalogue.prepared.catalogue.source
    )
    proposal = role._proposal(
        bound, source_snapshot, catalogue.prepared.catalogue, None, pattern_id=PATTERN
    )
    prepared = AvailabilitySetPlan(
        bound,
        catalogue.prepared.catalogue,
        None,
        (proposal,),
        tuple(row for child in actual for row in child.prepared.checks),
        catalogue.prepared.support_metadata_json,
        source.canonical(inputs["planning_inputs"]),
    )
    proof = AvailabilitySetProof(
        "dependent_member_values",
        catalogue.set_proof.members,
        catalogue.bound_requirement.id,
        tuple(expected),
        tuple(fact for child in actual for fact in child.facts),
    )
    return AvailabilitySetEvidence(prepared, proof, tuple(actual))


def _replay_actor(actors, identifier, inputs, context):
    supplied = actors.get(identifier)
    if type(supplied) is not role.RoleEvidence:
        raise ValueError("Actual retained actor execution required")
    prepared = role._prepare_role_from_context(
        {**inputs, "requirement_id": identifier}, context
    )
    role._require(
        supplied.proposals[0].proposal_id == prepared.proposals[0].proposal_id,
        "Actor raw proposal differs from reconstructed source",
    )
    assessments = role._replay_receipts(
        prepared,
        supplied.observations,
        supplied.actual_executions,
        inputs.get("require_runtime", True),
    )
    return role._bound_result(
        prepared, assessments, supplied.observations, supplied.actual_executions
    )


def _replay_child(supplied, actors, identifier, inputs, context):
    if type(supplied) is not AvailabilityEvidence:
        raise ValueError("Every availability member needs retained executions")
    prepared = _prepare(actors, identifier, inputs, context)
    assessments = role._replay_receipts(
        prepared,
        supplied.observations,
        supplied.actual_executions,
        inputs.get("require_runtime", True),
    )
    return AvailabilityEvidence(
        prepared, supplied.observations, supplied.actual_executions, assessments
    )


def _binding(plan, structural, requirement_id, actors, inputs, context):
    requirement, use = _requirement_use(plan, requirement_id)
    role._require(
        requirement.kind == "availability" and use.parent_id is not None,
        "Actual member availability requirement required",
    )
    edges = [
        row
        for row in structural.edges
        if row.kind == "actor_value_dependency" and row.target_id == requirement_id
    ]
    role._require(len(edges) == 1, "Unique actual actor dependency required")
    edge = edges[0]
    evidence = _replay_actor(actors, edge.source_id, inputs, context)
    if not evidence.supported:
        raise FieldUnavailable("The actual actor dependency is not supported")
    role._require(
        len(evidence.facts) == 1,
        "Actor must have exactly one reconstructed declaration fact",
    )
    fact = evidence.facts[0]
    role._require(
        fact.kind == "role_assignment"
        and fact.member_binding_id == use.member_binding_id == edge.member_binding_id
        and fact.value_slot_id == use.value_slot_id == edge.value_slot_id
        and use.execution_dependencies == (fact.value_slot_id,),
        "Actual actor/member/value-slot ancestry differs",
    )
    features = json.loads(use.features_json)
    role._require(
        not any(
            features.get(key)
            for key in (
                "condition_ast",
                "modality",
                "negation",
                "units",
                "governors",
                "order",
                "quantifiers",
            )
        ),
        "Qualified dependent fields remain unresolved",
    )
    return role.BoundRequirement(
        **asdict(requirement),
        use_json=source.canonical(asdict(use)),
        plan_sha256=source.digest(plan.record()),
        member_binding_id=use.member_binding_id,
        value_slot_id=use.value_slot_id,
        source_uses_json=use.source_uses_json,
    ), fact


def _field_matches(row, fact, bound, args):
    if row.kind != "literal_field" or tuple(span.text for span in row.scope) != tuple(
        span.text for span in fact.scope
    ):
        return False
    subjects = [
        argument for argument in row.arguments if argument.kind == "declaration_subject"
    ]
    if len(subjects) != 1:
        return False
    subject = subjects[0]
    _, windows = source._inputs(
        args["manifest"], args["snapshots"], args["source_captures"]
    )
    for window, _, annotation in windows[row.source.document_id]:
        if not window.start <= subject.core.start < subject.core.end <= window.end:
            continue
        tokens = annotation["tokens"]
        head = tokens[subject.head_index]
        nominal = [
            token
            for token in tokens
            if subject.core.start
            <= window.start + token["start"]
            < window.start + token["end"]
            <= subject.core.end
        ]
        actor = [token for token in nominal if token["i"] != head["i"]]
        if (
            not actor
            or head["lemma"].casefold() != bound.relation
            or any(
                token["dep"] != "compound" or token["pos"] not in {"NOUN", "PROPN"}
                for token in actor
            )
        ):
            continue
        raw = next(
            snapshot.body
            for snapshot in args["snapshots"]
            if snapshot.identity == row.source
        )
        if (
            raw[window.start + actor[0]["start"] : window.start + actor[-1]["end"]]
            != fact.value
        ):
            continue
        if any(
            argument.unknowns
            or argument.quantifiers
            or any(
                qualifier.kind != "governing_scope" for qualifier in argument.qualifiers
            )
            for argument in row.arguments
        ):
            continue
        return True
    return False


def prepare(*, actors, requirement_id, **inputs):
    return _prepare(actors, requirement_id, inputs, role._context(inputs))


def _prepare(actors, requirement_id, inputs, context):
    plan, args, inventory, structural, _ = context
    bound, fact = _binding(plan, structural, requirement_id, actors, inputs, context)
    matches = [
        row for row in inventory.declarations if _field_matches(row, fact, bound, args)
    ]
    if len(matches) != 1:
        raise FieldUnavailable(
            "One unambiguous actual actor/property declaration required"
        )
    row = matches[0]
    payload = json.loads(row.payload_json)
    role._require(
        "value" in payload and len(payload["values"]) == 1,
        "One literal factual availability value required",
    )
    value = source.RawRange(**payload["value"])
    snapshot = next(
        snapshot for snapshot in args["snapshots"] if snapshot.identity == row.source
    )
    proposal = role._proposal(bound, snapshot, row, value, pattern_id=PATTERN)
    scope = fact.scope[0].text
    hypothesis = f"For {scope}, {fact.value}'s {bound.relation} is {value.text}."
    checks = []
    for phase, literal in (
        ("local", row.raw),
        ("whole_body", source.RawRange(0, len(snapshot.body), snapshot.body)),
    ):
        lineage = {
            "contract": CONTRACT,
            "requirement": asdict(bound),
            "actor_fact": asdict(fact),
            "source_declaration": asdict(row),
            "proposal": proposal.record(),
            "phase": phase,
        }
        ident = "afe-" + source.digest(lineage)
        checks.append(
            support.PlanningAssertion(
                ident,
                bound.id,
                "dependent_availability_" + phase,
                row.id,
                row.source,
                literal,
                source.canonical(lineage),
                support.PlanningPair(
                    literal.text,
                    hypothesis,
                    bound.id,
                    proposal.proposal_id + ":" + ident,
                ),
                fact.member_binding_id,
                fact.value_slot_id,
            )
        )
    return AvailabilityPlan(
        bound,
        fact,
        row,
        value,
        (proposal,),
        tuple(checks),
        source.canonical(support._metadata(args["support_metadata"])),
        source.canonical(inputs["planning_inputs"]),
    )


def reconstruct(*, observations, actual_executions, **inputs):
    prepared = prepare(**inputs)
    assessments = role._replay_receipts(
        prepared, observations, actual_executions, inputs.get("require_runtime", True)
    )
    return AvailabilityEvidence(prepared, observations, actual_executions, assessments)


async def assess(config, **inputs):
    prepared = prepare(**inputs)
    observations, executions = await role.assess_dependent_checks(config, prepared)
    return reconstruct(
        **inputs, observations=observations, actual_executions=executions
    )
