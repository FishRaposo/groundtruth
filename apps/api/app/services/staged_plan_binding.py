"""Independent versioned request semantics; never an answer/publication grant.

The old v2 compiler is recomputed on the actual original capture. Its closed
components are reused verbatim; new source meanings use a separate transport.
"""

import json
from dataclasses import asdict, dataclass, fields, replace

from . import effective_request as effective
from . import linguistic_requirements as legacy
from . import planning_declarations as declarations
from . import planning_support as support
from .answer_requirements import Requirement, _requirement_anchors
from .dependency_frames import ConditionClause, Span
from .planning_scope_bridge import reconstruct_scope_bridge
from .request_obligations import PartialRequest, RequestNode
from .request_parser import validate_capture
from .staged_request import compile_request

canonical = declarations.canonical
CONTRACT = "staged-request-plan-v1"
PROFILE = "contextual_source_v3"
MAX_REQUIREMENTS = 64


@dataclass(frozen=True)
class RequirementUse(legacy.RequirementUse):
    node_id: str = ""
    parent_id: str | None = None
    operation: str = ""
    features_json: str = "{}"
    source_uses_json: str = "[]"
    member_binding_id: str | None = None
    value_slot_id: str | None = None
    execution_dependencies: tuple[str, ...] = ()
    resolution: str = "UNRESOLVED"
    quantifiers: tuple[legacy.LiteralRange, ...] = ()
    negation: tuple[legacy.LiteralRange, ...] = ()


@dataclass(frozen=True)
class Blocker:
    owner_id: str
    reason: str
    retained_json: str = "{}"


@dataclass(frozen=True)
class Discharge:
    obligation_id: str
    node_id: str
    production: str
    state: str
    requirement_ids: tuple[str, ...]
    assertion_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class StagedRequestPlan:
    question: str
    requirements: tuple[Requirement, ...]
    uses: tuple[RequirementUse, ...]
    unresolved: tuple[Blocker, ...]
    partial_json: str
    legacy_component_json: str
    effective_candidate_json: str
    planning_support_json: str
    scope_bridge_json: str
    read_set_json: str
    sql_read_set_json: str
    discharges: tuple[Discharge, ...]
    members_json: str
    value_slots_json: str
    edges_json: str
    graph_sha256: str
    capture_sha256: str
    model_identity_json: str
    question_sha256: str
    graph_json: str
    consumption_json: str
    capture_kinds: tuple[str, ...]
    # These are external evidence/authority gates, not grammar ambiguity.
    factual_witnesses: str = "NOT_ASSESSED"
    answer_fact_nli: str = "NOT_ASSESSED"
    source_authority: str = "NOT_ASSESSED"
    sql_authorization_currentness: str = "NOT_ASSESSED"
    catalogue_completeness_policy: str = "NOT_ASSESSED"
    output_history: str = "NOT_ASSESSED"
    support_or_permissions: str = "NOT_ASSESSED"
    resolved_scope: str = "request_structure_and_supported_source_declarations_only"

    @property
    def resolved_request(self):
        return (
            bool(self.requirements)
            and not self.unresolved
            and all(row.state == "RESOLVED" for row in self.discharges)
        )

    def record(self):
        return json.loads(
            canonical(
                dict(
                    contract=CONTRACT,
                    reading_profile=PROFILE,
                    resolved_request=self.resolved_request,
                    **asdict(self),
                )
            )
        )


def _require(value, message):
    if not value:
        raise ValueError(message)


def _range(question, node):
    _require(bool(node.evidence), "Request node without original evidence")
    start = min(x.start for x in node.evidence)
    end = max(x.end for x in node.evidence)
    return legacy.LiteralRange(start, end, question[start:end])


def _known_components(
    old: legacy.RequestPlan, partial: PartialRequest
) -> dict[str, tuple[Requirement, legacy.RequirementUse]]:
    result = {}
    for node in partial.nodes:
        matches = []
        for requirement, use in zip(old.requirements, old.uses, strict=True):
            if (
                requirement.kind != "generic"
                and requirement.kind == node.kind
                and use.head_token_indices == node.head_indices
                and use.consumed_token_indices == node.token_indices
                and not any(
                    any(
                        e.start < requirement.input_end
                        and requirement.input_start < e.end
                        for e in unknown.evidence
                    )
                    for unknown in old.unresolved
                )
            ):
                matches.append((requirement, use))
        if len(matches) == 1:
            result[node.id] = matches[0]
    return result


def _known_slot_dispositions(
    partial: PartialRequest,
    known: dict[str, tuple[Requirement, legacy.RequirementUse]],
    annotation: dict,
) -> tuple[list[Blocker], list[Discharge]]:
    """Retain each deferred slot after the original node-order ledger phase."""
    blockers = []
    discharges = []
    for slot in partial.deferred:
        if slot.node_id in known:
            if slot.kind == "literal_subject_boundary" or _whole_copy_facet(
                slot, known[slot.node_id], partial.question, annotation
            ):
                discharges.append(
                    Discharge(
                        slot.id,
                        slot.node_id,
                        "closed_original_v2_literal_scope"
                        if slot.kind == "literal_subject_boundary"
                        else "whole_source_copy_requires_output_inventory",
                        "RESOLVED",
                        (known[slot.node_id][0].id,),
                    )
                )
            else:
                blockers.append(
                    Blocker(
                        slot.id,
                        "unsupported_deferred_semantics",
                        canonical(asdict(slot)),
                    )
                )
                discharges.append(
                    Discharge(
                        slot.id,
                        slot.node_id,
                        slot.kind,
                        "UNRESOLVED",
                        (known[slot.node_id][0].id,),
                    )
                )
    return blockers, discharges


def _whole_copy_facet(slot, known, question: str, annotation: dict) -> bool:
    """Recognized request to retain content, never a fact-existence verdict."""
    requirement, use = known
    if slot.kind == "procedure_facet_reference" and canonical(
        [asdict(x) for x in slot.evidence]
    ) == canonical([asdict(x) for x in use.governors]):
        from .staged_copy_facets import reconstruct_copy_facets

        try:
            reconstruct_copy_facets(
                {
                    "contract": CONTRACT,
                    "reading_profile": PROFILE,
                    "question": question,
                    "graph_json": canonical(annotation),
                },
                asdict(requirement),
                asdict(use),
                None,
            )
            return True
        except (ValueError, TypeError, KeyError, IndexError):
            pass
    if (
        slot.kind != "procedure_facet_reference"
        or requirement.kind != "procedure"
        or use.extent != "whole_requested"
        or use.modality
        or use.units
        or use.references
        or use.condition_ast
        or not use.governors
        or canonical([asdict(x) for x in slot.evidence])
        != canonical([asdict(x) for x in use.governors])
        or json.loads(slot.parameters_json).get("operation")
        != "independent_governor_output_coverage"
    ):
        return False
    # Use the existing guard authority, including its complete token ownership;
    # do not duplicate its lexical productions in this request representation.
    from .contextual_source_proof import _copy_governor

    for span in slot.evidence:
        selected = [
            token
            for token in annotation["tokens"]
            if span.start <= token["start"] < token["end"] <= span.end
        ]
        if (
            question[span.start : span.end] != span.text
            or not selected
            or selected[0]["start"] != span.start
            or selected[-1]["end"] != span.end
            or not _copy_governor(selected)
        ):
            return False
    return True


def _supported_slots(
    node: RequestNode,
    partial: PartialRequest,
    supported: support.PlanningSupportResult,
    kinds: set[str],
) -> bool:
    slots = tuple(slot for slot in partial.deferred if slot.node_id == node.id)
    successful = set(supported.supported_obligation_ids)
    return bool(slots) and all(
        slot.kind in kinds
        and slot.id in successful
        and not any(
            pending.id == slot.id for pending in supported.assertion_set.pending
        )
        for slot in slots
    )


def _catalogue_closed(
    node: RequestNode,
    partial: PartialRequest,
    rows: dict[str, tuple[effective.Requirement, ...]],
    supported: support.PlanningSupportResult,
) -> bool:
    return (
        node.kind == "role_catalogue"
        and node.operation in {"labels_only", "incumbents"}
        and _supported_slots(
            node, partial, supported, {"role_catalogue", "literal_subject_boundary"}
        )
        and any(row.parent_id is not None for row in rows[node.id])
    )


def _dependent_closed(
    node: RequestNode,
    partial: PartialRequest,
    structural: effective.EffectiveRequestPlan,
    rows: dict[str, tuple[effective.Requirement, ...]],
    supported: support.PlanningSupportResult,
    catalogues: set[str],
) -> bool:
    incoming = [edge for edge in partial.edges if edge.target_id == node.id]
    closures = [
        row
        for row in supported.assertion_set.argument_closures
        if row.node_id == node.id
    ]
    if (
        node.kind != "availability"
        or node.operation != "request_field_value"
        or len(incoming) != 1
        or incoming[0].kind != "catalogue_member_value"
        or incoming[0].source_id not in catalogues
        or len(closures) != 1
        or closures[0].status != "EXACT_INITIAL_RELATION"
        or not _supported_slots(node, partial, supported, {"literal_subject_boundary"})
    ):
        return False
    return _dependent_lineage(node, incoming[0], structural, rows)


def _dependent_lineage(
    node,
    reference,
    structural: effective.EffectiveRequestPlan,
    rows: dict[str, tuple[effective.Requirement, ...]],
) -> bool:
    source_rows, target_rows = rows[reference.source_id], rows[node.id]
    source_roots = [row for row in source_rows if row.parent_id is None]
    target_roots = [row for row in target_rows if row.parent_id is None]
    if len(source_roots) != 1 or len(target_roots) != 1:
        return False
    source_root, target_root = source_roots[0], target_roots[0]
    references = [
        edge
        for edge in structural.edges
        if edge.kind == "set_reference" and edge.target_id == target_root.id
    ]
    if (
        len(references) != 1
        or references[0].source_id != source_root.id
        or references[0].evidence_json
        != canonical([asdict(span) for span in reference.evidence])
    ):
        return False
    members = {
        member.id: member
        for member in structural.members
        if member.group_id == source_root.id
    }
    actors = {
        row.member_binding_id: row
        for row in source_rows
        if row.parent_id == source_root.id
    }
    targets = {
        row.member_binding_id: row
        for row in target_rows
        if row.parent_id == target_root.id
    }
    if (
        not members
        or set(members) != set(actors)
        or set(members) != set(targets)
        or len(source_rows) != len(members) + 1
        or len(target_rows) != len(members) + 1
    ):
        return False
    values = {value.id: value for value in structural.values}
    if len({actor.value_slot_id for actor in actors.values()}) != len(actors):
        return False
    return all(
        _member_dependency(
            member, actors[ident], targets[ident], values, structural.edges, node
        )
        for ident, member in members.items()
    )


def _member_dependency(
    member,
    actor: effective.Requirement,
    target: effective.Requirement,
    values: dict[str, effective.ValueSlot],
    edges: tuple[effective.Edge, ...],
    node: RequestNode,
) -> bool:
    slot = values.get(actor.value_slot_id) if actor.value_slot_id is not None else None
    if (
        actor.kind != "role_assignment"
        or slot is None
        or slot.requirement_id != actor.id
        or slot.member_binding_id != member.id
        or actor.role_label != member.literal
        or target.role_label != member.literal
        or target.value_slot_id != slot.id
        or target.features_json != node.feature_json
        or target.kind != node.kind
    ):
        return False
    dependencies = [
        edge
        for edge in edges
        if edge.kind == "actor_value_dependency" and edge.target_id == target.id
    ]
    membership = [
        edge
        for edge in edges
        if edge.kind == "availability_member" and edge.target_id == target.id
    ]
    return (
        len(dependencies) == len(membership) == 1
        and dependencies[0].source_id == actor.id
        and membership[0].source_id == target.parent_id
        and all(
            edge.member_binding_id == member.id and edge.value_slot_id == slot.id
            for edge in (*dependencies, *membership)
        )
    )


def _new_requirement(question, row, node):
    original = _range(question, node)
    features = json.loads(row.features_json)
    return Requirement(
        row.id,
        original.text,
        original.start,
        original.end,
        node.proposed_question,
        row.kind,
        node.scopes[0].text if len(node.scopes) == 1 else "",
        _requirement_anchors(node.scopes[0].text) if len(node.scopes) == 1 else (),
        (),
        features.get("relation", ""),
        row.role_label.text
        if row.role_label and row.kind in {"role_label", "role_assignment"}
        else features.get("attribute", ""),
        source_workspace=features.get("source_workspace"),
    )


def _new_use(question, row, node, edges):
    features = json.loads(row.features_json)

    # Unsupported semantic fields remain complete in features_json and block
    # resolution below. No emptied qualifier record enters a source proof.
    def literals(key):
        return tuple(legacy.LiteralRange(**x) for x in features.get(key, ()))

    clauses = tuple(
        ConditionClause(
            x["operator"],
            Span(*x["evidence"]),
            Span(*x["predicate"]),
            tuple(Span(*v) for v in x["subjects"]),
            tuple(Span(*v) for v in x["negation"]),
            tuple(Span(*v) for v in x["modality"]),
            tuple(x["token_indices"]),
            tuple(Span(*v) for v in x.get("complements", ())),
        )
        for x in features.get("condition_ast", ())
    )
    dependencies = tuple(
        e.value_slot_id
        for e in edges
        if e.kind == "actor_value_dependency" and e.target_id == row.id
    )
    return RequirementUse(
        row.id,
        _range(question, node),
        scopes=tuple(legacy.LiteralRange(x.start, x.end, x.text) for x in node.scopes),
        conditions=tuple(legacy.LiteralRange(*x.evidence) for x in clauses),
        condition_ast=clauses,
        modality=literals("modality"),
        units=literals("units"),
        governors=literals("governors"),
        references=literals("references"),
        order_evidence=literals("order"),
        scope_kind="activity" if len(node.scopes) == 1 else "unresolved",
        grammar=node.grammar,
        head_token_indices=node.head_indices,
        consumed_token_indices=node.token_indices,
        extent=features.get("extent", "unspecified"),
        node_id=node.id,
        parent_id=row.parent_id,
        operation=row.operation,
        features_json=row.features_json,
        source_uses_json=canonical([asdict(x) for x in row.source_uses]),
        member_binding_id=row.member_binding_id,
        value_slot_id=row.value_slot_id,
        execution_dependencies=dependencies,
        quantifiers=literals("quantifiers"),
        negation=literals("negation"),
    )


def reconstruct_staged_plan(
    question,
    capture,
    manifest,
    snapshots,
    source_captures,
    *,
    support_metadata,
    sql_read_set_json,
    observations,
    actual_executions,
    scope_bridge_record=None,
    max_requirements=MAX_REQUIREMENTS,
):
    """Recompute from actual inputs; no successful-plan callback or flag accepted.

    Runtime callers independently load/authorize the full universe and retain
    actual traces. Matching pure trace records alone do not attest inference.
    """
    _require(
        type(max_requirements) is int and 1 <= max_requirements <= MAX_REQUIREMENTS,
        "Explicit bounded requirement budget1..64 required",
    )
    annotation = validate_capture(question, capture)
    partial = compile_request(question, capture)
    old = legacy.plan_request(question, capture)
    bridge = reconstruct_scope_bridge(
        partial, manifest, snapshots, source_captures, procedure_productions=True
    )
    if scope_bridge_record is not None:
        declarations._native(scope_bridge_record)
        _require(
            type(scope_bridge_record) is dict
            and canonical(scope_bridge_record) == canonical(bridge),
            "Actual full scope bridge does not replay",
        )
    structural = effective.reconstruct_effective_request(
        question,
        capture,
        manifest,
        snapshots,
        source_captures,
        max_requirements=max_requirements,
        scope_bridge_record=bridge,
    )
    _require(
        not any(x.reason == "requirement_budget_exceeded" for x in structural.blockers),
        "Staged expansion budget exceeded; no partial result",
    )
    supported = support.reconstruct_planning_support(
        question,
        capture,
        manifest,
        snapshots,
        source_captures,
        support_metadata=support_metadata,
        sql_read_set_json=sql_read_set_json,
        observations=observations,
        actual_executions=actual_executions,
        scope_bridge_record=bridge,
    )
    _require(
        canonical(bridge["read_set"]) == structural.read_set_json,
        "Scope bridge/planning declaration read sets differ",
    )
    known = _known_components(old, partial)
    from .staged_production_obligations import request_productions

    copy_productions = request_productions(partial)
    requirements = []
    uses = []
    blockers = []
    discharges = []
    nodes = {n.id: n for n in partial.nodes}
    rows = {
        n.id: tuple(r for r in structural.requirements if r.node_id == n.id)
        for n in partial.nodes
    }
    for unknown in partial.unknowns:
        blockers.append(
            Blocker("request", "request:" + unknown.reason, canonical(asdict(unknown)))
        )
    catalogues = {
        node.id
        for node in partial.nodes
        if _catalogue_closed(node, partial, rows, supported)
    }
    dependents = {
        node.id
        for node in partial.nodes
        if _dependent_closed(node, partial, structural, rows, supported, catalogues)
    }
    for node in partial.nodes:
        if node.id in known:
            requirement, use = known[node.id]
            requirements.append(requirement)
            uses.append(
                RequirementUse(
                    **{f.name: getattr(use, f.name) for f in fields(use)},
                    node_id=node.id,
                    operation=node.operation,
                    features_json=node.feature_json,
                    resolution="CLOSED_ORIGINAL_V2_SYNTAX",
                    quantifiers=tuple(
                        legacy.LiteralRange(**x)
                        for x in json.loads(node.feature_json).get("quantifiers", ())
                    ),
                    negation=tuple(
                        legacy.LiteralRange(**x)
                        for x in json.loads(node.feature_json).get("negation", ())
                    ),
                )
            )
            discharges.append(
                Discharge(
                    "node:" + node.id,
                    node.id,
                    "independently_recomputed_original_v2",
                    "RESOLVED",
                    (requirement.id,),
                )
            )
            continue
        for row in rows[node.id]:
            requirements.append(_new_requirement(question, row, node))
            uses.append(_new_use(question, row, node, structural.edges))
        slots = tuple(s for s in partial.deferred if s.node_id == node.id)
        closed = (
            node.id in catalogues
            or node.id in dependents
            or node.id in copy_productions
        )
        if closed:
            discharges.extend(
                Discharge(
                    s.id,
                    node.id,
                    "source_declared_" + s.kind
                    if node.id in catalogues
                    else "captured_complete_copy_requires_source_nli_and_output"
                    if node.id in copy_productions
                    else "typed_set_reference_value_dependency",
                    "RESOLVED",
                    tuple(r.id for r in rows[node.id]),
                    tuple(
                        a.id
                        for a in supported.assertion_set.assertions
                        if a.obligation_id == s.id
                    ),
                )
                for s in slots
            )
            uses = [
                replace(
                    u,
                    resolution="SUPPORTED_SOURCE_DECLARATION"
                    if node.id in catalogues
                    else "CAPTURED_COPY_REQUEST_EXTERNAL_GATES_PENDING"
                    if node.id in copy_productions
                    else "SUPPORTED_DEPENDENT_REQUEST_STRUCTURE",
                )
                if u.node_id == node.id
                else u
                for u in uses
            ]
        else:
            blockers.append(
                Blocker(
                    node.id,
                    "unsupported_or_unresolved_source_defined_semantics",
                    canonical(
                        {
                            "node": asdict(node),
                            "slots": [asdict(s) for s in slots],
                            "pending": [
                                asdict(p) for p in supported.assertion_set.pending
                            ],
                        }
                    ),
                )
            )
            discharges.append(
                Discharge(
                    "node:" + node.id,
                    node.id,
                    "unsupported_source_production",
                    "UNRESOLVED",
                    tuple(r.id for r in rows[node.id]),
                )
            )
            discharges.extend(
                Discharge(
                    s.id,
                    node.id,
                    s.kind,
                    "UNRESOLVED",
                    tuple(r.id for r in rows[node.id]),
                )
                for s in slots
            )
    # Every original deferred slot has an explicit disposition, including slots
    # redundant with an independently closed original v2 production.
    known_blockers, known_discharges = _known_slot_dispositions(
        partial, known, annotation
    )
    blockers.extend(known_blockers)
    discharges.extend(known_discharges)
    if not partial.nodes:
        blockers.append(Blocker("request", "empty_request"))
    # v2 components may not retain dependencies on a replaced generic v2 row.
    ids = {r.id for r in requirements}
    if any(any(dep not in ids for dep in r.depends_on) for r in requirements):
        blockers.append(Blocker("request", "unresolved_original_v2_dependency_mapping"))
    _require(
        len(requirements) <= max_requirements,
        "Staged requirement budget exceeded; no truncation",
    )
    _require(len(ids) == len(requirements), "Duplicate staged requirement identity")
    _require(
        {u.node_id for u in uses} == set(nodes),
        "Every original node must retain requirements/uses",
    )
    _require(
        {d.obligation_id for d in discharges} >= {s.id for s in partial.deferred},
        "Every deferred obligation must retain a disposition",
    )
    return StagedRequestPlan(
        question,
        tuple(requirements),
        tuple(uses),
        tuple(blockers),
        canonical(partial.record()),
        canonical(old.record()),
        canonical(structural.record()),
        canonical(supported.record()),
        canonical(bridge),
        structural.read_set_json,
        sql_read_set_json,
        tuple(discharges),
        canonical([asdict(x) for x in structural.members]),
        canonical([asdict(x) for x in structural.values]),
        canonical([asdict(x) for x in structural.edges]),
        capture["annotation_sha256"],
        capture["capture_sha256"],
        canonical(capture["parser"]),
        partial.question_sha256,
        canonical(annotation),
        canonical(old.record()["consumption"]),
        supported.capture_kinds,
    )


def validate_staged_plan(record, **actual_inputs):
    try:
        declarations._native(record)
        return type(record) is dict and canonical(record) == canonical(
            reconstruct_staged_plan(**actual_inputs).record()
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
