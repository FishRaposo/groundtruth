"""Pure deterministic planning assertions and retained NLI execution replay."""

import json
import math
from dataclasses import asdict, dataclass

from app.support_catalog import BATCH_SIZE, MAX_PAIR_TOKENS, NLI

from . import effective_request as effective
from . import planning_declarations as source
from .answer_support import _assessment
from .request_relation import RequestRelationClosure, request_relation_closures

canonical = source.canonical
digest = source.digest


@dataclass(frozen=True)
class PlanningPair:
    premise: str
    hypothesis: str
    requirement_id: str
    reference_id: str


@dataclass(frozen=True)
class PlanningAssertion:
    id: str
    obligation_id: str
    kind: str
    declaration_id: str
    source_identity: source.SourceIdentity
    source_range: source.RawRange
    request_relation_json: str
    pair: PlanningPair
    member_binding_id: str | None = None
    value_slot_id: str | None = None


@dataclass(frozen=True)
class PendingObligation:
    id: str
    kind: str
    reason: str


@dataclass(frozen=True)
class AssertionSet:
    effective_plan_json: str
    support_metadata_json: str
    sql_read_set_json: str
    assertions: tuple[PlanningAssertion, ...]
    pending: tuple[PendingObligation, ...]
    argument_closures: tuple[RequestRelationClosure, ...] = ()

    def record(self):
        return json.loads(
            canonical(dict(contract="planning-assertions-v2", **asdict(self)))
        )


@dataclass(frozen=True)
class NliObservation:
    assertion_id: str
    execution_id: str
    pair: PlanningPair
    support_metadata_json: str
    assessment_json: str


@dataclass(frozen=True)
class NliExecution:
    execution_id: str
    assertion_id: str
    pair: PlanningPair
    support_metadata_json: str
    assessment_json: str
    pair_tokens: int
    capture_kind: str


@dataclass(frozen=True)
class ValidatedAssessment:
    assertion_id: str
    execution_id: str
    pair: PlanningPair
    support_metadata_json: str
    assessment_json: str
    pair_tokens: int
    capture_kind: str
    supported: bool


@dataclass(frozen=True)
class PlanningSupportResult:
    assertion_set: AssertionSet
    assessments: tuple[ValidatedAssessment, ...]
    supported_obligation_ids: tuple[str, ...]
    accepted: bool
    remaining_gates: tuple[str, ...]
    capture_kinds: tuple[str, ...]
    accepted_scope: str = "planning_source_relations_only"
    permissions: str = "NOT_ASSESSED"
    universe_completeness: str = "NOT_ESTABLISHED"
    execution_attestation: str = "INDEPENDENT_CALLER_RETAINED_TRACE_REPLAY"

    def record(self):
        return json.loads(
            canonical(dict(contract="planning-support-observations-v2", **asdict(self)))
        )


def prepare_planning_assertions(
    question,
    capture,
    manifest,
    snapshots,
    source_captures,
    *,
    support_metadata,
    sql_read_set_json,
    scope_bridge_record=None,
):
    metadata = _metadata(support_metadata)
    sql = source._json_object(sql_read_set_json)
    _require(
        sql.get("contract") == "request-planning-publications-v1"
        and sql.get("selection_mode") == "all_authorized_publications_v1",
        "Actual runtime SQL read-set binding required; "
        "no authorization is inferred here",
    )
    plan = effective.reconstruct_effective_request(
        question,
        capture,
        manifest,
        snapshots,
        source_captures,
        scope_bridge_record=scope_bridge_record,
    )
    inventory = source.declaration_inventory(manifest, snapshots, source_captures)
    partial = json.loads(plan.partial_json)
    request_features = json.loads(partial["features_json"])
    # Initial supported assertions are exact unqualified name/catalogue/actor
    # relations. Do not weaken a conditioned/modal/negative/qualified request
    # into a simpler entailed sentence merely because its source names match.
    request_qualified = any(
        request_features.get(key)
        for key in (
            "condition_ast",
            "modality",
            "negation",
            "units",
            "governors",
            "order",
        )
    ) or any(
        token["dep"] in {"advcl", "ccomp", "xcomp", "relcl", "neg", "mark"}
        or token["tag"] == "MD"
        for token in capture["annotation"]["tokens"]
    )
    original = {node["id"]: node for node in partial["nodes"]}
    argument_closures = request_relation_closures(
        question, capture, tuple(original.values())
    )
    closures = {row.node_id: row for row in argument_closures}
    requirements = {
        row.node_id: row for row in plan.requirements if row.parent_id is None
    }
    declarations = {row.id: row for row in inventory.declarations}
    bindings = {row.id: row for row in plan.members}
    assertions = []
    pending = []
    overlays = {row.obligation_id: row for row in plan.overlays}

    builder = _AssertionEmitter(original, closures, assertions)
    _resolution_assertions(
        plan,
        original,
        requirements,
        declarations,
        overlays,
        closures,
        request_qualified,
        pending,
        builder,
    )
    _actor_assertions(
        plan,
        requirements,
        declarations,
        bindings,
        closures,
        request_qualified,
        pending,
        builder,
    )
    outer = {
        "source:planning_universe_requires_independent_authorization_and_currentness",
        "source:source_authority_and_evidence_not_assessed",
        "actor_value_unbound",
        "independent_membership_evidence_required",
        "independent_actor_value_evidence_required",
        "independent_name_applicability_evidence_required",
    }
    for blocker in plan.blockers:
        if blocker.reason not in outer:
            pending.append(
                PendingObligation(blocker.owner_id, "retained_blocker", blocker.reason)
            )
    if len(assertions) > 128:
        assertions = []
        pending.append(
            PendingObligation(
                "planning", "budget", "planning_nli_assertion_budget_exceeded"
            )
        )
    return AssertionSet(
        canonical(plan.record()),
        canonical(metadata),
        sql_read_set_json,
        tuple(assertions),
        tuple(pending),
        argument_closures,
    )


def reconstruct_planning_support(
    question,
    capture,
    manifest,
    snapshots,
    source_captures,
    *,
    support_metadata,
    sql_read_set_json,
    observations: tuple[NliObservation, ...],
    actual_executions: tuple[NliExecution, ...],
    scope_bridge_record=None,
):
    prepared = prepare_planning_assertions(
        question,
        capture,
        manifest,
        snapshots,
        source_captures,
        support_metadata=support_metadata,
        sql_read_set_json=sql_read_set_json,
        scope_bridge_record=scope_bridge_record,
    )
    _require(
        type(observations) is tuple and type(actual_executions) is tuple,
        "Immutable observations and independently retained "
        "actual execution tuple required",
    )
    expected = {a.id: a for a in prepared.assertions}
    _require(
        len(observations) == len(expected) and len(actual_executions) == len(expected),
        "Complete mandatory observation and actual execution inventory required",
    )
    actual = {}
    execution_ids = set()
    for record in actual_executions:
        _require(
            type(record) is NliExecution
            and type(record.execution_id) is str
            and record.execution_id.strip()
            and len(record.execution_id) <= 256,
            "Typed retained actual execution required",
        )
        _require(
            record.assertion_id in expected
            and record.assertion_id not in actual
            and record.execution_id not in execution_ids,
            "Duplicate or unknown actual execution identity",
        )
        _require(
            type(record.capture_kind) is str
            and record.capture_kind in {"UNITONLY", "runtime_capture"},
            "Execution capture provenance must be explicit",
        )
        actual[record.assertion_id] = record
        execution_ids.add(record.execution_id)
    _require(
        set(actual) == set(expected), "Actual execution assertion membership differs"
    )
    verified = {}
    settings = json.loads(prepared.support_metadata_json)
    for observation in observations:
        _require(
            type(observation) is NliObservation
            and observation.assertion_id in expected
            and observation.assertion_id not in verified,
            "Typed unique actual observation required",
        )
        assertion = expected[observation.assertion_id]
        record = actual[observation.assertion_id]
        _require(
            type(observation.pair) is PlanningPair
            and type(record.pair) is PlanningPair
            and observation.pair == record.pair == assertion.pair,
            "Actual pair does not reconstruct exact source/requirement relation",
        )
        _require(
            observation.execution_id == record.execution_id
            and observation.support_metadata_json == record.support_metadata_json
            and observation.assessment_json == record.assessment_json,
            "Observation differs from independent retained actual execution",
        )
        meta = source._json_object(record.support_metadata_json)
        _require(
            canonical(_metadata(meta)) == prepared.support_metadata_json,
            "Actual model/threshold settings differ from requested pinned settings",
        )
        assessed = _numeric(record.assessment_json, settings)
        _require(
            type(record.pair_tokens) is int
            and record.pair_tokens == assessed["pair_tokens"],
            "Independent actual pair-token count differs",
        )
        verified[assertion.id] = ValidatedAssessment(
            assertion.id,
            record.execution_id,
            record.pair,
            record.support_metadata_json,
            record.assessment_json,
            record.pair_tokens,
            record.capture_kind,
            assessed["supported"],
        )
    _require(set(verified) == set(expected), "Mandatory assessment inventory differs")
    assessments = tuple(verified[a.id] for a in prepared.assertions)
    obligation_ids = tuple(dict.fromkeys(a.obligation_id for a in prepared.assertions))
    supported = tuple(
        identifier
        for identifier in obligation_ids
        if all(
            verified[a.id].supported
            for a in prepared.assertions
            if a.obligation_id == identifier
        )
    )
    accepted = (
        bool(prepared.assertions)
        and not prepared.pending
        and all(a.supported for a in assessments)
    )
    gates = [
        "source_authority_requires_separate_verification",
        "sql_authority_currentness_and_universe_requires_runtime_recheck",
        "catalogue_completeness_policy_requires_separate_verification",
        "answer_facts_output_access_history_require_separate_verification",
    ]
    gates.extend(item.reason for item in prepared.pending)
    if not all(a.supported for a in assessments):
        gates.append("mandatory_planning_relation_not_supported")
    return PlanningSupportResult(
        prepared,
        assessments,
        supported,
        accepted,
        tuple(dict.fromkeys(gates)),
        tuple(sorted({record.capture_kind for record in actual_executions})),
    )


def validate_planning_support(
    record,
    *,
    question,
    capture,
    manifest,
    snapshots,
    source_captures,
    support_metadata,
    sql_read_set_json,
    observations: tuple[NliObservation, ...],
    actual_executions: tuple[NliExecution, ...],
    scope_bridge_record=None,
):
    try:
        source._native(record)
        return type(record) is dict and canonical(record) == canonical(
            reconstruct_planning_support(
                question,
                capture,
                manifest,
                snapshots,
                source_captures,
                support_metadata=support_metadata,
                sql_read_set_json=sql_read_set_json,
                observations=observations,
                actual_executions=actual_executions,
                scope_bridge_record=scope_bridge_record,
            ).record()
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


def _require(value, message):
    if not value:
        raise ValueError(message)


def _join(labels):
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return labels[0] + " and " + labels[1]
    return ", ".join(labels[:-1]) + " and " + labels[-1]


def _metadata(record):
    source._native(record)
    expected = {
        "mode": "local_nli",
        "model": NLI.model,
        "revision": NLI.revision,
        "license": NLI.license,
        "device": "cpu",
        "max_pair_tokens": MAX_PAIR_TOKENS,
        "batch_size": BATCH_SIZE,
        "score_semantics": "raw contradiction/entailment/neutral logits; uncalibrated",
    }
    fields = set(expected) | {"minimum_entailment_margin"}
    _require(
        type(record) is dict and set(record) in (fields, fields | {"readiness"}),
        "Exact local NLI metadata required",
    )
    for key, value in expected.items():
        _require(
            type(record[key]) is type(value) and record[key] == value,
            "Pinned local NLI metadata differs",
        )
    if "readiness" in record:
        _require(
            type(record["readiness"]) is str
            and record["readiness"] in {"ready", "not_loaded"},
            "Failed/disabled NLI metadata cannot support planning",
        )
    margin = record["minimum_entailment_margin"]
    _require(
        type(margin) in (int, float) and math.isfinite(margin) and 0 <= margin <= 4,
        "NLI margin must be finite numeric0..4",
    )
    return {**expected, "minimum_entailment_margin": margin}


def _numeric(raw, settings):
    record = source._json_object(raw)
    _require(
        set(record)
        == {"label", "logits", "entailment_margin", "supported", "pair_tokens"},
        "Full actual NLI assessment schema required",
    )
    logits = record["logits"]
    _require(
        type(logits) is list
        and len(logits) == 3
        and all(
            type(value) in (int, float) and math.isfinite(value) for value in logits
        ),
        "Three actual finite raw NLI logits required",
    )
    try:
        actual = _assessment(logits, settings["minimum_entailment_margin"])
    except (RuntimeError, ValueError, TypeError, OverflowError) as exc:
        raise ValueError("Existing NLI numeric assessment failed") from exc
    _require(
        type(record["entailment_margin"]) in (int, float)
        and math.isfinite(record["entailment_margin"])
        and record["entailment_margin"] == actual.entailment_margin,
        "Actual entailment margin differs from logits",
    )
    _require(
        type(record["label"]) is str
        and record["label"] == actual.label
        and record["supported"] is actual.supported,
        "Actual NLI decision differs from existing numeric semantics",
    )
    _require(
        type(record["pair_tokens"]) is int
        and 0 < record["pair_tokens"] <= MAX_PAIR_TOKENS,
        "Actual token count must be positive integer within fixed512 bound",
    )
    return record


@dataclass
class _AssertionEmitter:
    original: dict[str, dict]
    closures: dict[str, RequestRelationClosure]
    assertions: list[PlanningAssertion]

    def emit(
        self,
        obligation: str,
        kind: str,
        row: source.Declaration,
        requirement: effective.Requirement,
        hypothesis: str,
        *,
        member_id: str | None = None,
        value_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        relation = {
            "requirement": asdict(requirement),
            "original_node": self.original[requirement.node_id],
            "owned_request_argument": asdict(self.closures[requirement.node_id]),
            "kind": kind,
            "declaration_id": row.id,
            "member_binding_id": member_id,
            "value_slot_id": value_id,
            "details": details or {},
        }
        identity = {
            "obligation_id": obligation,
            "kind": kind,
            "source_identity": asdict(row.source),
            "source_range": asdict(row.raw),
            "request_relation": relation,
            "hypothesis": hypothesis,
        }
        identifier = "pa-" + digest(identity)
        pair = PlanningPair(
            row.raw.text,
            hypothesis,
            requirement.id,
            row.source.document_id + ":planning:" + identifier,
        )
        self.assertions.append(
            PlanningAssertion(
                identifier,
                obligation,
                kind,
                row.id,
                row.source,
                row.raw,
                canonical(relation),
                pair,
                member_id,
                value_id,
            )
        )


def _resolution_assertions(
    plan: effective.EffectiveRequestPlan,
    original: dict[str, dict],
    requirements: dict[str, effective.Requirement],
    declarations: dict[str, source.Declaration],
    overlays: dict[str, effective.NameOverlay],
    closures: dict[str, RequestRelationClosure],
    request_qualified: bool,
    pending: list[PendingObligation],
    builder: _AssertionEmitter,
) -> None:
    for resolution in plan.resolutions:
        node = original[resolution.node_id]
        requirement = requirements[resolution.node_id]
        if request_qualified and resolution.kind in {
            "role_catalogue",
            "literal_subject_boundary",
        }:
            pending.append(
                PendingObligation(
                    resolution.obligation_id,
                    resolution.kind,
                    "request_relation_qualifiers_require_supported_assertion",
                )
            )
            continue
        if (
            resolution.kind in {"role_catalogue", "literal_subject_boundary"}
            and closures[resolution.node_id].status != "EXACT_INITIAL_RELATION"
        ):
            pending.append(
                PendingObligation(
                    resolution.obligation_id,
                    resolution.kind,
                    "unsupported_owned_request_argument",
                )
            )
            continue
        if (
            resolution.kind == "role_catalogue"
            and resolution.state == "PROPOSED_EXPANSION"
            and len(resolution.candidate_ids) == 1
        ):
            row = declarations[resolution.candidate_ids[0]]
            scope = row.scope[0].text
            builder.emit(
                resolution.obligation_id,
                "catalogue_scope",
                row,
                requirement,
                "The roles stated here are for " + scope + ".",
                details={"scope": asdict(row.scope[0]), "operation": node["operation"]},
            )
            literal_set = _join([member.text for member in row.members])
            builder.emit(
                resolution.obligation_id,
                "catalogue_literal_set",
                row,
                requirement,
                "The stated role labels for " + scope + " are " + literal_set + ".",
                details={
                    "scope": asdict(row.scope[0]),
                    "members": [asdict(member) for member in row.members],
                    "completeness": "SOURCE_DECLARATION_ONLY",
                },
            )
            members = [m for m in plan.members if m.group_id == requirement.id]
            for binding in members:
                builder.emit(
                    resolution.obligation_id,
                    "catalogue_member_relation",
                    row,
                    requirement,
                    binding.literal.text + " is a role for " + scope + ".",
                    member_id=binding.id,
                    details={
                        "literal": asdict(binding.literal),
                        "scope": json.loads(binding.scope_json),
                    },
                )
        elif (
            resolution.kind == "literal_subject_boundary"
            and resolution.obligation_id in overlays
            and overlays[resolution.obligation_id].status == "UNASSESSED_NAME_CANDIDATE"
            and len(resolution.candidate_ids) == 1
        ):
            row = declarations[resolution.candidate_ids[0]]
            builder.emit(
                resolution.obligation_id,
                "literal_name_relation",
                row,
                requirement,
                "The stated name is " + row.literal.text + ".",
                details={
                    "source_literal": asdict(row.literal),
                    "question_range": json.loads(
                        overlays[resolution.obligation_id].question_range_json
                    ),
                },
            )
        else:
            pending.append(
                PendingObligation(
                    resolution.obligation_id,
                    resolution.kind,
                    "unsupported_or_unresolved_obligation:"
                    + ",".join(resolution.pending),
                )
            )


def _actor_assertions(
    plan: effective.EffectiveRequestPlan,
    requirements: dict[str, effective.Requirement],
    declarations: dict[str, source.Declaration],
    bindings: dict[str, effective.MemberBinding],
    closures: dict[str, RequestRelationClosure],
    request_qualified: bool,
    pending: list[PendingObligation],
    builder: _AssertionEmitter,
) -> None:
    for value in plan.values:
        if request_qualified:
            pending.append(
                PendingObligation(
                    value.id,
                    "actor_role_relation",
                    "request_relation_qualifiers_require_supported_assertion",
                )
            )
            continue
        owner_node = next(
            r.node_id for r in plan.requirements if r.id == value.requirement_id
        )
        if closures[owner_node].status != "EXACT_INITIAL_RELATION":
            pending.append(
                PendingObligation(
                    value.id,
                    "actor_role_relation",
                    "unsupported_owned_request_argument",
                )
            )
            continue
        member = bindings[value.member_binding_id]
        if len(value.candidate_uses) != 1:
            pending.append(
                PendingObligation(
                    value.id,
                    "actor_role_relation",
                    "missing_or_ambiguous_actor_relation",
                )
            )
            continue
        row = declarations[value.candidate_uses[0].declaration_id]
        payload = json.loads(row.payload_json)
        if "value" not in payload or not row.scope:
            pending.append(
                PendingObligation(
                    value.id, "actor_role_relation", "incomplete_actor_relation"
                )
            )
            continue
        actor = source.RawRange(**payload["value"])
        requirement = requirements[
            next(r.node_id for r in plan.requirements if r.id == value.requirement_id)
        ]
        builder.emit(
            value.id,
            "actor_role_relation",
            row,
            requirement,
            actor.text
            + " fills the "
            + member.literal.text
            + " role for "
            + row.scope[0].text
            + ".",
            member_id=member.id,
            value_id=value.id,
            details={
                "actor": asdict(actor),
                "role": asdict(member.literal),
                "scope": [asdict(v) for v in row.scope],
            },
        )
