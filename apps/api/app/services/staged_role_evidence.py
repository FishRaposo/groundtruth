"""Actual staged role facts: source proposals and complete local/whole NLI replay.

No owner/deputy projection, guessed actors, persistence or model fallback.
Access/currentness and publication remain independent caller obligations.
"""

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass
from typing import Literal, Protocol

from app.config import Settings
from app.models.chunk import ChunkWithScore
from app.services import answer_support
from app.services import effective_request as effective
from app.services import planning_declarations as declarations
from app.services import planning_support as support
from app.services.answer_requirements import Requirement
from app.services.evidence_proposals import EvidenceProposal, make_proposal
from app.services.planning_relevance import reconstruct_candidate_selection
from app.services.procedure_discovery import LocatedChunk, ProcedureSource
from app.services.staged_plan_binding import RequirementUse, StagedRequestPlan
from app.services.staged_plan_replay import _arguments, reconstruct_request
from app.services.staged_planning_runtime import (
    DEFAULT_ADAPTER_LIMITS,
    RuntimeLimits,
    _decision_boundary_snapshot,
    _retained_execution_receipts,
)
from app.services.staged_request import compile_request

canonical = declarations.canonical
digest = declarations.digest
CONTRACT = "staged-role-evidence-v1"
PATTERN = "staged-role-declaration-v1"


class RoleSourceUnrepresentable(ValueError):
    """A complete declaration/value has no unique normal chunk proposal."""


_KINDS = frozenset({"role_catalogue", "role_label", "role_assignment"})
_OUTER = frozenset(
    {
        "planning_universe_requires_independent_authorization_and_currentness",
        "source_authority_and_evidence_not_assessed",
    }
)


@dataclass(frozen=True)
class BoundRequirement(Requirement):
    use_json: str = "{}"
    plan_sha256: str = ""
    member_binding_id: str | None = None
    value_slot_id: str | None = None
    source_uses_json: str = "[]"


@dataclass(frozen=True)
class RoleEvidencePlan:
    bound_requirement: BoundRequirement
    plan_json: str
    inventory_json: str
    read_set_json: str
    planning_inputs_json: str
    retained_inputs_json: str
    authoritative_snapshots_json: str
    support_metadata_json: str
    catalogue: declarations.Declaration
    members: tuple[effective.MemberBinding, ...]
    child_requirement_ids: tuple[str, ...]
    source_declaration: declarations.Declaration
    candidate_value: declarations.RawRange | None
    role_label: declarations.RawRange | None
    proposals: tuple[EvidenceProposal, ...]
    checks: tuple[support.PlanningAssertion, ...]

    def record(self):
        return json.loads(
            canonical({"contract": CONTRACT + ":prepared", **asdict(self)})
        )


@dataclass(frozen=True)
class RoleFact:
    requirement_id: str
    kind: str
    value: str
    value_range: declarations.RawRange
    source_identity: declarations.SourceIdentity
    source_range: declarations.RawRange
    role_label: declarations.RawRange
    scope: tuple[declarations.RawRange, ...]
    member_binding_id: str
    value_slot_id: str | None
    proposal_id: str
    check_ids: tuple[str, ...]


@dataclass(frozen=True)
class CatalogueSetProof:
    requirement_id: str
    operation: str
    source_identity: declarations.SourceIdentity
    declaration_id: str
    source_range: declarations.RawRange
    members: tuple[effective.MemberBinding, ...]
    child_requirement_ids: tuple[str, ...]
    proposal_id: str
    check_ids: tuple[str, ...]
    completeness: str = "SOURCE_DECLARATION_ONLY"


@dataclass(frozen=True)
class RoleEvidence:
    prepared: RoleEvidencePlan
    supported: bool
    facts: tuple[RoleFact, ...]
    set_proof: CatalogueSetProof | None
    observations: tuple[support.NliObservation, ...]
    actual_executions: tuple[support.NliExecution, ...]
    assessments: tuple[support.ValidatedAssessment, ...]
    remaining_gates: tuple[str, ...] = (
        "source_authority_requires_independent_verification",
        "all_source_access_currentness_requires_publication_recheck",
        "catalogue_completeness_is_immutable_declaration_bounded",
        "complete_request_output_history_requires_independent_verification",
    )

    @property
    def bound_requirement(self):
        return self.prepared.bound_requirement

    @property
    def proposals(self):
        return self.prepared.proposals

    def record(self):
        return json.loads(canonical({"contract": CONTRACT, **asdict(self)}))


def _require(value, message):
    if not value:
        raise ValueError(message)


def _context(inputs):
    plan = reconstruct_request(
        inputs["planning_inputs"],
        question=inputs["question"],
        retained_inputs=inputs["retained_inputs"],
        authoritative_snapshots=inputs["authoritative_snapshots"],
        require_runtime=inputs["require_runtime"],
    )
    _require(plan.resolved_request, "Whole staged request remains unresolved")
    args = _arguments(inputs["planning_inputs"], inputs["authoritative_snapshots"])
    inventory = declarations.declaration_inventory(
        args["manifest"], args["snapshots"], args["source_captures"]
    )
    _require(
        args["manifest"].selection_mode == "bounded_authorized_scan"
        and not inventory.read_set.missing_publications,
        "Complete selected publication inventory required",
    )
    bridge = json.loads(plan.scope_bridge_json)
    selection = reconstruct_candidate_selection(
        compile_request(args["question"], args["capture"]),
        args["manifest"],
        args["snapshots"],
        args["source_captures"],
        scope_bridge_record=bridge,
    )
    active_reasons = (
        {row.reason for row in selection.active_blockers}
        if selection.used
        else set(inventory.blockers)
    )
    _require(
        not (active_reasons - _OUTER),
        "Unknown or qualified source inventory remains unresolved",
    )
    structural = effective.reconstruct_effective_request(
        args["question"],
        args["capture"],
        args["manifest"],
        args["snapshots"],
        args["source_captures"],
        scope_bridge_record=bridge,
    )
    supported = support.reconstruct_planning_support(**args, scope_bridge_record=bridge)
    _require(
        canonical(structural.record()) == plan.effective_candidate_json
        and canonical(supported.record()) == plan.planning_support_json,
        "Actual staged declaration/support lineage differs",
    )
    return plan, args, inventory, structural, supported


def _bound(plan: StagedRequestPlan, identifier: str):
    requirements = [row for row in plan.requirements if row.id == identifier]
    uses = [row for row in plan.uses if row.requirement_id == identifier]
    _require(
        len(requirements) == len(uses) == 1,
        "One actual staged requirement/use required",
    )
    requirement, use = requirements[0], uses[0]
    _require(requirement.kind in _KINDS, "Actual kind is not a staged role requirement")
    features = json.loads(use.features_json)
    _require(
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
                "references",
            )
        ),
        "Qualified role facts require a supported semantic production",
    )
    return BoundRequirement(
        **asdict(requirement),
        use_json=canonical(asdict(use)),
        plan_sha256=digest(plan.record()),
        member_binding_id=use.member_binding_id,
        value_slot_id=use.value_slot_id,
        source_uses_json=use.source_uses_json,
    ), use


def _scope_text(row: declarations.Declaration):
    return tuple(span.text for span in row.scope)


def _catalogue_context(
    use: RequirementUse,
    structural: effective.EffectiveRequestPlan,
    inventory: declarations.DeclarationInventory,
):
    rows = [row for row in structural.requirements if row.node_id == use.node_id]
    roots = [row for row in rows if row.parent_id is None]
    _require(
        len(roots) == 1 and roots[0].kind == "role_catalogue",
        "Actual catalogue parent required",
    )
    root = roots[0]
    members = tuple(
        member for member in structural.members if member.group_id == root.id
    )
    _require(
        bool(members) and len({member.declaration_id for member in members}) == 1,
        "One nonempty immutable catalogue required",
    )
    catalogue = next(
        row for row in inventory.declarations if row.id == members[0].declaration_id
    )
    _require(
        catalogue.kind == "role_catalogue"
        and tuple(member.literal for member in members) == catalogue.members
        and len(catalogue.scope) == 1,
        "Complete catalogue membership differs",
    )
    relevant = [
        row
        for row in inventory.declarations
        if row.kind == "role_assignment" and _scope_text(row) == _scope_text(catalogue)
    ]
    labels = {member.literal.text for member in members}
    _require(
        all(row.literal.text in labels for row in relevant),
        "Catalogue has an unlisted relevant role assignment",
    )
    for label in labels:
        _require(
            sum(row.literal.text == label for row in relevant) <= 1,
            "Ambiguous or opposing role assignments remain unresolved",
        )
    children = tuple(row.id for row in rows if row.parent_id == root.id)
    _require(len(children) == len(members), "Every catalogue member child required")
    return root, catalogue, members, children


def _source_value(
    bound: BoundRequirement,
    use: RequirementUse,
    catalogue: declarations.Declaration,
    members: tuple[effective.MemberBinding, ...],
    structural: effective.EffectiveRequestPlan,
    inventory: declarations.DeclarationInventory,
):
    if bound.kind == "role_catalogue":
        return catalogue, None, None
    member = next((row for row in members if row.id == use.member_binding_id), None)
    if member is None:
        raise ValueError("Actual member binding required")
    if bound.kind == "role_label":
        return catalogue, member.literal, member.literal
    slots = [
        slot
        for slot in structural.values
        if slot.id == use.value_slot_id
        and slot.requirement_id == bound.id
        and slot.member_binding_id == member.id
    ]
    _require(
        len(slots) == 1 and len(slots[0].candidate_uses) == 1,
        "One actual source actor candidate required; no guessed value",
    )
    declaration_id = slots[0].candidate_uses[0].declaration_id
    row = next(value for value in inventory.declarations if value.id == declaration_id)
    _require(
        row.kind == "role_assignment"
        and row.literal.text == member.literal.text
        and _scope_text(row) == _scope_text(catalogue),
        "Actor role/source scope differs",
    )
    _require(
        _actor_arguments_closed(row), "Qualified actor arguments remain unresolved"
    )
    payload = json.loads(row.payload_json)
    _require("value" in payload, "One exact literal actor required")
    actor = declarations.RawRange(**payload["value"])
    _require(
        bool(actor.text) and len(payload.get("values", [])) == 1,
        "Ambiguous actor values remain unresolved",
    )
    return row, actor, row.literal


def _actor_arguments_closed(row: declarations.Declaration) -> bool:
    scopes = [
        argument
        for argument in row.arguments
        if argument.kind == "governing_scope" and argument.literal in row.scope
    ]
    return all(
        not argument.unknowns
        and not argument.quantifiers
        and all(
            qualifier.kind == "governing_scope"
            and any(
                qualifier.raw.start
                <= scope.literal.start
                < scope.literal.end
                <= qualifier.raw.end
                and set(qualifier.token_indices)
                == set(scope.token_indices) | {qualifier.head_index}
                for scope in scopes
            )
            for qualifier in argument.qualifiers
        )
        for argument in row.arguments
    )


def _normal_source(snapshot: declarations.SourceSnapshot) -> ProcedureSource:
    chunks = tuple(
        LocatedChunk(
            ChunkWithScore(
                id=uuid.UUID(chunk.chunk_id),
                document_id=uuid.UUID(snapshot.identity.document_id),
                content=chunk.literal.text,
                chunk_index=chunk.ordinal,
                # Normal proposal transport binds the independently verified
                # identity. Keep original immutable metadata in full inputs;
                # runtime scoring extras are neither required nor trusted.
                metadata={
                    **json.loads(chunk.metadata_json),
                    "document_version": snapshot.identity.document_version,
                    "content_hash": snapshot.identity.content_hash,
                    "workspace_id": snapshot.identity.workspace_id,
                },
                relevance_score=0.0,
            ),
            chunk.literal.start,
            chunk.literal.end,
        )
        for chunk in snapshot.chunks
    )
    return ProcedureSource(
        snapshot.body,
        chunks,
        asdict(snapshot.identity),
        json.loads(snapshot.metadata_json),
        None,
    )


def _proposal(
    bound: BoundRequirement,
    source: declarations.SourceSnapshot,
    row: declarations.Declaration,
    value: declarations.RawRange | None,
    *,
    pattern_id=PATTERN,
) -> EvidenceProposal:
    selected = value or row.raw
    _require(
        source.body[selected.start : selected.end] == selected.text,
        "Candidate value offsets differ from actual body",
    )
    actual = _normal_source(source)
    located = [
        chunk
        for chunk in actual.chunks
        if chunk.start <= row.raw.start < row.raw.end <= chunk.end
        and chunk.start <= selected.start < selected.end <= chunk.end
    ]
    if len(located) != 1:
        raise RoleSourceUnrepresentable(
            "Role source unit/value is cross-chunk or ambiguously mapped; "
            "never truncate"
        )
    chunk = located[0]
    return make_proposal(
        bound.id,
        actual,
        chunk.chunk,
        selected.start - chunk.start,
        selected.end - chunk.start,
        origin="source_pattern",
        pattern_id=pattern_id,
        grammar_version="typed-source-patterns-v2",
    )


def _lineage_checks(
    bound: BoundRequirement,
    use: RequirementUse,
    root: effective.Requirement,
    proposal: EvidenceProposal,
    snapshots: tuple[declarations.SourceSnapshot, ...],
    supported: support.PlanningSupportResult,
):
    candidates = [
        row
        for row in supported.assertion_set.assertions
        if row.pair.requirement_id == root.id
        and (
            row.kind in {"catalogue_scope", "catalogue_literal_set"}
            or row.kind == "catalogue_member_relation"
            and (
                bound.kind == "role_catalogue"
                or row.member_binding_id == use.member_binding_id
            )
            or bound.kind == "role_assignment"
            and row.kind == "actor_role_relation"
            and row.member_binding_id == use.member_binding_id
            and row.value_slot_id == use.value_slot_id
        )
    ]
    expected = (
        2
        + (
            len(
                [
                    row
                    for row in supported.assertion_set.assertions
                    if row.pair.requirement_id == root.id
                    and row.kind == "catalogue_member_relation"
                ]
            )
            if bound.kind == "role_catalogue"
            else 1
        )
        + int(bound.kind == "role_assignment")
    )
    _require(
        len(candidates) == expected
        and (
            bound.kind != "role_assignment"
            or any(row.kind == "actor_role_relation" for row in candidates)
        ),
        "Complete805 hypothesis lineage required",
    )
    assessed = {row.assertion_id: row for row in supported.assessments}
    _require(
        all(row.id in assessed and assessed[row.id].supported for row in candidates),
        "Each actual805 source relationship must be supported",
    )
    sources = {snapshot.identity: snapshot for snapshot in snapshots}
    checks = []
    for original in candidates:
        snapshot = sources[original.source_identity]
        for phase, literal in (
            ("local", original.source_range),
            ("whole_body", declarations.RawRange(0, len(snapshot.body), snapshot.body)),
        ):
            relation = {
                "source_assertion": asdict(original),
                "bound_requirement": asdict(bound),
                "proposal": proposal.record(),
                "phase": phase,
            }
            identifier = "rfe-" + digest(relation)
            pair = support.PlanningPair(
                literal.text,
                original.pair.hypothesis,
                bound.id,
                proposal.proposal_id + ":" + identifier,
            )
            checks.append(
                support.PlanningAssertion(
                    identifier,
                    original.obligation_id,
                    "staged_role_" + phase,
                    original.declaration_id,
                    original.source_identity,
                    literal,
                    canonical(relation),
                    pair,
                    original.member_binding_id,
                    original.value_slot_id,
                )
            )
    _require(
        bool(checks) and len(checks) <= DEFAULT_ADAPTER_LIMITS.max_pairs,
        "Complete role pair inventory exceeds fixed budget; no truncation",
    )
    return tuple(checks)


def prepare_role_evidence(
    *,
    question,
    requirement_id,
    planning_inputs,
    retained_inputs,
    authoritative_snapshots,
    require_runtime=True,
) -> RoleEvidencePlan:
    inputs = {
        "question": question,
        "requirement_id": requirement_id,
        "planning_inputs": planning_inputs,
        "retained_inputs": retained_inputs,
        "authoritative_snapshots": authoritative_snapshots,
        "require_runtime": require_runtime,
    }
    return _prepare_role_from_context(inputs, _context(inputs))


def _prepare_role_from_context(inputs, context):
    """Shared source mechanics after the caller's actual whole-input replay."""
    plan, args, inventory, structural, supported = context
    bound, use = _bound(plan, inputs["requirement_id"])
    root, catalogue, members, children = _catalogue_context(use, structural, inventory)
    row, value, label = _source_value(
        bound, use, catalogue, members, structural, inventory
    )
    source = next(
        snapshot for snapshot in args["snapshots"] if snapshot.identity == row.source
    )
    proposal = _proposal(bound, source, row, value)
    checks = _lineage_checks(bound, use, root, proposal, args["snapshots"], supported)
    return RoleEvidencePlan(
        bound,
        canonical(plan.record()),
        canonical(inventory.record()),
        plan.read_set_json,
        canonical(inputs["planning_inputs"]),
        canonical(inputs["retained_inputs"]),
        canonical(inputs["authoritative_snapshots"]),
        canonical(support._metadata(args["support_metadata"])),
        catalogue,
        members,
        children,
        row,
        value,
        label,
        (proposal,),
        checks,
    )


class _AssessmentPlan(Protocol):
    @property
    def checks(self) -> tuple[support.PlanningAssertion, ...]: ...

    @property
    def support_metadata_json(self) -> str: ...


def _replay_receipts(
    prepared: _AssessmentPlan,
    observations: tuple[support.NliObservation, ...],
    actual_executions: tuple[support.NliExecution, ...],
    require_runtime: bool,
):
    _require(
        type(observations) is tuple and type(actual_executions) is tuple,
        "Immutable observed and actual role executions required",
    )
    expected = {check.id: check for check in prepared.checks}
    _require(
        len(observations) == len(actual_executions) == len(expected),
        "Complete local and whole-body role execution inventory required",
    )
    actual = {}
    ids = set()
    for row in actual_executions:
        _require(
            type(row) is support.NliExecution
            and type(row.assertion_id) is str
            and row.assertion_id in expected
            and row.assertion_id not in actual
            and type(row.execution_id) is str
            and row.execution_id.strip()
            and len(row.execution_id) <= 256
            and row.execution_id not in ids,
            "Typed unique actual role execution required",
        )
        _require(
            type(row.capture_kind) is str
            and row.capture_kind in {"runtime_capture", "UNITONLY"}
            and (not require_runtime or row.capture_kind == "runtime_capture"),
            "Only actual runtime role receipts can enter production",
        )
        actual[row.assertion_id] = row
        ids.add(row.execution_id)
    settings = json.loads(prepared.support_metadata_json)
    verified = {}
    for observed in observations:
        _require(
            type(observed) is support.NliObservation
            and type(observed.assertion_id) is str
            and observed.assertion_id in expected
            and observed.assertion_id not in verified,
            "Typed unique role observation required",
        )
        execution, check = (
            actual[observed.assertion_id],
            expected[observed.assertion_id],
        )
        _require(
            type(observed.pair) is support.PlanningPair
            and type(execution.pair) is support.PlanningPair
            and observed.pair == execution.pair == check.pair
            and observed.execution_id == execution.execution_id
            and observed.assessment_json == execution.assessment_json
            and observed.support_metadata_json == execution.support_metadata_json,
            "Role observation differs from actual source-bound execution",
        )
        _require(
            canonical(support._metadata(json.loads(execution.support_metadata_json)))
            == prepared.support_metadata_json,
            "Actual role model/settings differ",
        )
        numeric = support._numeric(execution.assessment_json, settings)
        _require(
            type(execution.pair_tokens) is int
            and execution.pair_tokens == numeric["pair_tokens"],
            "Actual role pair-token count differs",
        )
        verified[check.id] = support.ValidatedAssessment(
            check.id,
            execution.execution_id,
            check.pair,
            execution.support_metadata_json,
            execution.assessment_json,
            execution.pair_tokens,
            execution.capture_kind,
            numeric["supported"],
        )
    return tuple(verified[check.id] for check in prepared.checks)


def _bound_result(
    prepared: RoleEvidencePlan, assessments, observations, actual_executions
):
    supported = all(row.supported for row in assessments)
    bound = prepared.bound_requirement
    check_ids = tuple(check.id for check in prepared.checks)
    proposal = prepared.proposals[0]
    facts = ()
    proof = None
    if supported and bound.kind == "role_catalogue":
        proof = CatalogueSetProof(
            bound.id,
            json.loads(bound.use_json)["operation"],
            prepared.catalogue.source,
            prepared.catalogue.id,
            prepared.catalogue.raw,
            prepared.members,
            prepared.child_requirement_ids,
            proposal.proposal_id,
            check_ids,
        )
    elif supported:
        value, label = prepared.candidate_value, prepared.role_label
        if value is None or label is None or bound.member_binding_id is None:
            raise ValueError(
                "A supported scalar role requires exact value/member lineage"
            )
        facts = (
            RoleFact(
                bound.id,
                bound.kind,
                value.text,
                value,
                prepared.source_declaration.source,
                prepared.source_declaration.raw,
                label,
                prepared.source_declaration.scope,
                bound.member_binding_id,
                bound.value_slot_id,
                proposal.proposal_id,
                check_ids,
            ),
        )
    return RoleEvidence(
        prepared, supported, facts, proof, observations, actual_executions, assessments
    )


def reconstruct_role_evidence(
    *,
    question,
    requirement_id,
    planning_inputs,
    retained_inputs,
    authoritative_snapshots,
    proposal_id,
    observations: tuple[support.NliObservation, ...],
    actual_executions: tuple[support.NliExecution, ...],
    require_runtime=True,
) -> RoleEvidence:
    prepared = prepare_role_evidence(
        question=question,
        requirement_id=requirement_id,
        planning_inputs=planning_inputs,
        retained_inputs=retained_inputs,
        authoritative_snapshots=authoritative_snapshots,
        require_runtime=require_runtime,
    )
    _require(
        type(proposal_id) is str and proposal_id == prepared.proposals[0].proposal_id,
        "Actual role source-pattern proposal does not reconstruct",
    )
    assessments = _replay_receipts(
        prepared, observations, actual_executions, require_runtime
    )
    return _bound_result(prepared, assessments, observations, actual_executions)


def validate_role_evidence(record, **actual_inputs):
    try:
        declarations._native(record)
        return type(record) is dict and canonical(record) == canonical(
            reconstruct_role_evidence(**actual_inputs).record()
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        AttributeError,
        RecursionError,
    ):
        return False


async def assess_role_evidence(
    config: Settings,
    *,
    question,
    requirement_id,
    planning_inputs,
    retained_inputs,
    authoritative_snapshots,
    proposal_id=None,
    require_runtime=True,
    limits: RuntimeLimits = DEFAULT_ADAPTER_LIMITS,
    execution_capture_kind: Literal["runtime_capture", "UNITONLY"] = "runtime_capture",
) -> RoleEvidence:
    """Existing actual service; detached immediate receipts, no persistence/fallback."""
    _require(type(limits) is RuntimeLimits, "Typed existing runtime limits required")
    _require(
        type(execution_capture_kind) is str
        and execution_capture_kind in {"runtime_capture", "UNITONLY"}
        and (not require_runtime or execution_capture_kind == "runtime_capture"),
        "Explicit compatible role runtime capture kind required",
    )
    selected_config = config.model_copy(deep=True)
    inputs = json.loads(
        canonical(
            {
                "question": question,
                "requirement_id": requirement_id,
                "planning_inputs": planning_inputs,
                "retained_inputs": retained_inputs,
                "authoritative_snapshots": authoritative_snapshots,
                "require_runtime": require_runtime,
            }
        )
    )
    stage = "prepare"
    prepared = None
    executions = ()
    observations = ()
    boundary = (None, None)
    metadata_json = None
    try:
        prepared = prepare_role_evidence(**inputs)
        _require(
            proposal_id is None or proposal_id == prepared.proposals[0].proposal_id,
            "Requested role proposal does not match actual source",
        )
        _require(
            len(prepared.checks) <= limits.max_pairs,
            "Role runtime pair budget exceeded; no truncation",
        )
        metadata_json = canonical(
            answer_support.support_service.metadata(selected_config)
        )
        _require(
            canonical(support._metadata(json.loads(metadata_json)))
            == prepared.support_metadata_json,
            "Requested role service settings differ from planning settings",
        )
        pairs = tuple(
            answer_support.SupportPair(**asdict(check.pair))
            for check in prepared.checks
        )
        stage = "assess"
        async with asyncio.timeout(limits.inference_timeout_seconds):
            decisions = await answer_support.support_service.assess(
                list(pairs), selected_config
            )
        # No await or producer observation intervenes before detached capture.
        metadata_json = canonical(
            answer_support.support_service.metadata(selected_config)
        )
        boundary = _decision_boundary_snapshot(decisions)
        executions = _retained_execution_receipts(
            prepared.checks, pairs, decisions, metadata_json, execution_capture_kind
        )
        observations = tuple(
            support.NliObservation(
                row.assertion_id,
                row.execution_id,
                support.PlanningPair(**asdict(row.pair)),
                row.support_metadata_json,
                row.assessment_json,
            )
            for row in executions
        )
        stage = "reconstruct"
        return reconstruct_role_evidence(
            **inputs,
            proposal_id=prepared.proposals[0].proposal_id,
            observations=observations,
            actual_executions=executions,
        )
    except (Exception, asyncio.CancelledError) as exc:
        exc.__dict__["role_evidence_json"] = canonical(
            {
                "contract": CONTRACT + ":failure",
                "stage": stage,
                "exception_type": type(exc).__name__,
                "prepared": prepared.record() if prepared else None,
                "actual_metadata_json": metadata_json,
                "returned_decision_count": boundary[0],
                "boundary_assessments_json": boundary[1],
                "actual_executions": [asdict(row) for row in executions],
                "observations": [asdict(row) for row in observations],
            }
        )
        raise


async def assess_dependent_checks(config, prepared):
    try:
        return await _assess_dependent_checks(config, prepared)
    except (Exception, asyncio.CancelledError) as exc:
        if "dependent_field_execution_json" not in exc.__dict__:
            exc.__dict__["dependent_field_execution_json"] = canonical(
                {
                    "contract": "dependent-field-execution-failure-v1",
                    "stage": "before_service_return",
                    "requirement_id": prepared.bound_requirement.id,
                    "checks": [asdict(check) for check in prepared.checks],
                    "exception_type": type(exc).__name__,
                }
            )
        raise


async def _assess_dependent_checks(config, prepared):
    """The same actual local NLI boundary for source-bound dependent fields."""
    selected = config.model_copy(deep=True)
    limits = DEFAULT_ADAPTER_LIMITS
    _require(
        0 < len(prepared.checks) <= limits.max_pairs,
        "Complete dependent field pair budget exceeded",
    )
    metadata = canonical(answer_support.support_service.metadata(selected))
    _require(
        canonical(support._metadata(json.loads(metadata)))
        == prepared.support_metadata_json,
        "Dependent field settings differ from planning",
    )
    pairs = tuple(
        answer_support.SupportPair(**asdict(check.pair)) for check in prepared.checks
    )
    async with asyncio.timeout(limits.inference_timeout_seconds):
        decisions = await answer_support.support_service.assess(list(pairs), selected)
    metadata = None
    boundary = (None, None)
    try:
        metadata = canonical(answer_support.support_service.metadata(selected))
        boundary = _decision_boundary_snapshot(decisions)
        executions = _retained_execution_receipts(
            prepared.checks, pairs, decisions, metadata, "runtime_capture"
        )
    except (Exception, asyncio.CancelledError) as exc:
        exc.__dict__["dependent_field_execution_json"] = canonical(
            {
                "contract": "dependent-field-execution-failure-v1",
                "stage": "service_return",
                "requirement_id": prepared.bound_requirement.id,
                "checks": [asdict(check) for check in prepared.checks],
                "actual_metadata_json": metadata,
                "returned_decision_count": boundary[0],
                "boundary_assessments_json": boundary[1],
                "exception_type": type(exc).__name__,
            }
        )
        raise
    observations = tuple(
        support.NliObservation(
            row.assertion_id,
            row.execution_id,
            support.PlanningPair(**asdict(row.pair)),
            row.support_metadata_json,
            row.assessment_json,
        )
        for row in executions
    )
    return observations, executions
