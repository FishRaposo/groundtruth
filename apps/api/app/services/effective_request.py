"""Pure effective-request structural reconstruction; no publication authority."""

import json
from dataclasses import asdict, dataclass

from . import planning_declarations as declarations
from .planning_relevance import CandidateSelection, reconstruct_candidate_selection
from .request_obligations import PartialRequest, RequestNode
from .staged_request import compile_request, validate_partial_request

canonical = declarations.canonical
digest = declarations.digest
MAX_REQUIREMENTS = 64


@dataclass(frozen=True)
class SourceUse:
    declaration_id: str
    source: declarations.SourceIdentity
    unit_id: str
    kind: str
    raw: declarations.RawRange


@dataclass(frozen=True)
class Requirement:
    id: str
    node_id: str
    kind: str
    operation: str
    evidence_json: str
    features_json: str
    target_json: str
    parent_id: str | None = None
    role_label: declarations.RawRange | None = None
    member_binding_id: str | None = None
    value_slot_id: str | None = None
    source_uses: tuple[SourceUse, ...] = ()


@dataclass(frozen=True)
class MemberBinding:
    id: str
    group_id: str
    declaration_id: str
    literal: declarations.RawRange
    scope_json: str
    status: str = "UNASSESSED_MEMBERSHIP"


@dataclass(frozen=True)
class ValueSlot:
    id: str
    requirement_id: str
    member_binding_id: str
    candidate_uses: tuple[SourceUse, ...]
    candidates_json: str
    status: str = "UNBOUND_ACTOR_VALUE"


@dataclass(frozen=True)
class Edge:
    kind: str
    source_id: str
    target_id: str
    evidence_json: str
    member_binding_id: str | None = None
    value_slot_id: str | None = None


@dataclass(frozen=True)
class NameOverlay:
    obligation_id: str
    question_range_json: str
    candidate_uses: tuple[SourceUse, ...]
    status: str


@dataclass(frozen=True)
class ResolutionEntry:
    obligation_id: str
    node_id: str
    kind: str
    state: str
    candidate_ids: tuple[str, ...]
    child_ids: tuple[str, ...]
    pending: tuple[str, ...]


@dataclass(frozen=True)
class Blocker:
    owner_id: str
    reason: str
    retained_json: str = "{}"


@dataclass(frozen=True)
class PlanningObservation:
    obligation_id: str
    kind: str
    declaration_ids: tuple[str, ...]
    input_json: str
    retained_trace_json: str
    status: str = "UNASSESSED"


@dataclass(frozen=True)
class EffectiveRequestPlan:
    partial_json: str
    inventory_json: str
    read_set_json: str
    observations_json: str
    requirements: tuple[Requirement, ...]
    members: tuple[MemberBinding, ...]
    values: tuple[ValueSlot, ...]
    edges: tuple[Edge, ...]
    overlays: tuple[NameOverlay, ...]
    resolutions: tuple[ResolutionEntry, ...]
    blockers: tuple[Blocker, ...]
    resolved_request: bool = False
    support_or_permissions: str = "NOT_ASSESSED"
    universe_completeness: str = "NOT_ESTABLISHED"
    candidate_selection_json: str | None = None

    def record(self):
        payload = asdict(self)
        if self.candidate_selection_json is None:
            payload.pop("candidate_selection_json")
        return json.loads(
            canonical(dict(contract="staged-effective-request-proposal-v1", **payload))
        )


def reconstruct_effective_request(
    question,
    capture,
    manifest,
    snapshots,
    source_captures,
    *,
    planning_observations: tuple[PlanningObservation, ...] = (),
    max_requirements=MAX_REQUIREMENTS,
    scope_bridge_record=None,
):
    partial = compile_request(question, capture)
    inventory = declarations.declaration_inventory(manifest, snapshots, source_captures)
    selection = (
        None
        if scope_bridge_record is None
        else reconstruct_candidate_selection(
            partial,
            manifest,
            snapshots,
            source_captures,
            scope_bridge_record=scope_bridge_record,
        )
    )
    return _build(
        partial, inventory, capture, planning_observations, max_requirements, selection
    )


def validate_effective_request(
    record,
    *,
    question,
    capture,
    manifest,
    snapshots,
    source_captures,
    planning_observations: tuple[PlanningObservation, ...] = (),
    max_requirements=MAX_REQUIREMENTS,
    scope_bridge_record=None,
):
    try:
        declarations._native(record)
        return type(record) is dict and canonical(record) == canonical(
            reconstruct_effective_request(
                question,
                capture,
                manifest,
                snapshots,
                source_captures,
                planning_observations=planning_observations,
                max_requirements=max_requirements,
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


def resolve_request(
    partial,
    inventory,
    *,
    question,
    capture,
    manifest,
    snapshots,
    source_captures,
    planning_read_set,
    planning_observations: tuple[PlanningObservation, ...] = (),
    max_requirements=MAX_REQUIREMENTS,
    scope_bridge_record=None,
):
    _require(
        type(partial) is PartialRequest
        and type(inventory) is declarations.DeclarationInventory
        and type(planning_read_set) is declarations.PlanningReadSet,
        "Exact typed producer DTOs required; callbacks are not inputs",
    )
    _require(
        validate_partial_request(partial.record(), question=question, capture=capture),
        "Partial request does not reconstruct actual question/capture",
    )
    _require(
        declarations.validate_declaration_inventory(
            inventory.record(),
            manifest=manifest,
            snapshots=snapshots,
            captures=source_captures,
        ),
        "Declaration inventory does not reconstruct actual snapshots/captures",
    )
    _require(
        declarations.validate_planning_read_set(
            planning_read_set.record(),
            manifest=manifest,
            snapshots=snapshots,
            captures=source_captures,
        ),
        "Planning read set does not reconstruct actual inputs",
    )
    _require(
        canonical(planning_read_set.record()) == canonical(inventory.read_set.record()),
        "Inventory/read-set binding differs",
    )
    return reconstruct_effective_request(
        question,
        capture,
        manifest,
        snapshots,
        source_captures,
        planning_observations=planning_observations,
        max_requirements=max_requirements,
        scope_bridge_record=scope_bridge_record,
    )


def _require(value, message):
    if not value:
        raise ValueError(message)


def _use(row):
    return SourceUse(row.id, row.source, row.unit_id, row.kind, row.raw)


def _root_id(partial, node):
    return "r-" + digest(
        {"question_sha256": partial.question_sha256, "node_id": node.id}
    )


def _nominal_interval(question, capture, literal):
    """Only a closed actual nominal interval can receive a literal overlay.

    This does not reannotate the question or discharge source applicability.
    Operators, references, units/conditions and independent predicates cannot
    become invisible because a source calls the whole string a name.
    """
    if question[literal.start : literal.end] != literal.text:
        return False
    ts = capture["annotation"]["tokens"]
    ids = {
        t["i"] for t in ts if literal.start <= t["start"] and t["end"] <= literal.end
    }
    if not ids:
        return False
    ordered = sorted(ids)
    if (
        ts[ordered[0]]["start"] != literal.start
        or ts[ordered[-1]]["end"] != literal.end
    ):
        return False
    if any(
        ts[i]["pos"] not in {"NOUN", "PROPN", "ADJ", "DET", "NUM"}
        or ts[i]["dep"]
        in {"ROOT", "conj", "cc", "mark", "neg", "aux", "auxpass", "poss"}
        for i in ids
    ):
        return False
    heads = [i for i in ids if ts[i]["head"] not in ids]
    if len(heads) != 1 or ts[heads[0]]["pos"] not in {"NOUN", "PROPN"}:
        return False
    return all(
        i == heads[0] or ts[i]["dep"] in {"compound", "amod", "nmod", "nummod", "det"}
        for i in ids
    )


def _observations(
    observations: tuple[PlanningObservation, ...],
    partial: PartialRequest,
    inventory: declarations.DeclarationInventory,
) -> str:
    _require(
        type(observations) is tuple and len(observations) <= 128,
        "Bounded immutable planning observations required",
    )
    slots = {s.id for s in partial.deferred}
    decls = {d.id for d in inventory.declarations}
    result = []
    for item in observations:
        _require(
            type(item) is PlanningObservation and item.status == "UNASSESSED",
            "No planning observation acceptance is implemented",
        )
        _require(
            type(item.obligation_id) is str and item.obligation_id in slots,
            "Planning observation has no actual obligation",
        )
        _require(
            type(item.kind) is str
            and item.kind
            in {
                "name",
                "membership",
                "value",
                "applicability",
                "constraint",
                "temporal",
                "facet",
            },
            "Unknown planning observation kind",
        )
        _require(
            type(item.declaration_ids) is tuple
            and len(set(item.declaration_ids)) == len(item.declaration_ids)
            and all(type(v) is str and v in decls for v in item.declaration_ids),
            "Planning observation declaration binding differs",
        )
        declarations._json_object(item.input_json)
        declarations._json_object(item.retained_trace_json)
        result.append(asdict(item))
    return canonical(result)


def _candidate_inputs(inventory, selection: CandidateSelection | None):
    if selection is not None and selection.used:
        return (
            tuple(
                row
                for row in inventory.declarations
                if row.id in selection.candidate_declaration_ids
            ),
            tuple(
                unit
                for unit in inventory.units
                if unit.id in selection.candidate_unit_ids
            ),
            tuple(
                Blocker(
                    origin.source.document_id if origin.source else "source",
                    "source:" + origin.reason,
                    canonical(asdict(origin)),
                )
                for origin in selection.active_blockers
            ),
            canonical(selection.record()),
        )
    return (
        inventory.declarations,
        inventory.units,
        tuple(Blocker("source", "source:" + reason) for reason in inventory.blockers),
        None,
    )


def _build(
    partial: PartialRequest,
    inventory: declarations.DeclarationInventory,
    capture: dict,
    observations: tuple[PlanningObservation, ...],
    max_requirements: int,
    selection: CandidateSelection | None = None,
) -> EffectiveRequestPlan:
    _require(
        type(max_requirements) is int and 1 <= max_requirements <= MAX_REQUIREMENTS,
        "Explicit bounded requirement budget required",
    )
    observations_json = _observations(observations, partial, inventory)
    requirements = []
    members = []
    values = []
    edges = []
    overlays = []
    resolutions = []
    blockers = []
    nodes = {n.id: n for n in partial.nodes}
    roots = {n.id: _root_id(partial, n) for n in partial.nodes}
    for node in partial.nodes:
        requirements.append(
            Requirement(
                roots[node.id],
                node.id,
                node.kind,
                node.operation,
                canonical([asdict(x) for x in node.evidence]),
                node.feature_json,
                canonical([asdict(x) for x in node.scopes]),
            )
        )
    for unknown in partial.unknowns:
        blockers.append(
            Blocker("request", "request:" + unknown.reason, canonical(asdict(unknown)))
        )
    candidate_declarations, candidate_units, source_blockers, selection_json = (
        _candidate_inputs(inventory, selection)
    )
    blockers.extend(source_blockers)
    # Full original inventory/read set remain recorded. Only independently
    # replayed candidate selection can defer source-owned semantic blockers.
    source_unknowns = bool(
        any(u.unknowns for u in candidate_units)
        or inventory.read_set.missing_publications
        or inventory.read_set.universe.selection_mode != "bounded_authorized_scan"
        or any(d.kind == "external_instruction_target" for d in candidate_declarations)
    )
    choices, pending_by_node, eligible = _catalogue_choices(
        partial, candidate_declarations, source_unknowns
    )
    eligible = _bounded_catalogues(
        partial,
        requirements,
        eligible,
        choices,
        pending_by_node,
        blockers,
        max_requirements,
    )
    children_by_node, child_by_binding, value_by_binding = _expand_catalogues(
        partial,
        candidate_declarations,
        eligible,
        roots,
        requirements,
        members,
        values,
        edges,
        blockers,
    )
    _append_original_edges(
        partial,
        nodes,
        roots,
        members,
        child_by_binding,
        value_by_binding,
        requirements,
        edges,
        blockers,
    )
    _append_resolutions(
        partial,
        candidate_declarations,
        capture,
        nodes,
        roots,
        choices,
        pending_by_node,
        children_by_node,
        source_unknowns,
        overlays,
        resolutions,
        blockers,
    )
    if _cyclic(edges):
        blockers.append(Blocker("request", "cyclic_request_dependencies"))
    return EffectiveRequestPlan(
        canonical(partial.record()),
        canonical(inventory.record()),
        canonical(inventory.read_set.record()),
        observations_json,
        tuple(requirements),
        tuple(members),
        tuple(values),
        tuple(edges),
        tuple(overlays),
        tuple(resolutions),
        tuple(blockers),
        candidate_selection_json=selection_json,
    )


def _catalogue_choices(
    partial: PartialRequest,
    candidate_declarations: tuple[declarations.Declaration, ...],
    source_unknowns: bool,
) -> tuple[
    dict[str, tuple[declarations.Declaration, ...]],
    dict[str, list[str]],
    dict[str, declarations.Declaration],
]:
    eligible = {}
    choices = {}
    pending_by_node = {}
    for node in partial.nodes:
        if node.kind != "role_catalogue":
            continue
        matches, pending = _catalogue_matches(node, candidate_declarations)
        if node.operation not in {"labels_only", "incumbents"}:
            pending.append("unsupported_catalogue_operation")
        if source_unknowns:
            pending.append("source_semantic_unknowns")
        if partial.unknowns:
            pending.append("request_hard_unknowns")
        if len(matches) == 1 and not matches[0].members:
            pending.append("empty_catalogue")
        choices[node.id] = matches
        pending_by_node[node.id] = pending
        if len(matches) == 1 and not pending:
            eligible[node.id] = matches[0]
    return choices, pending_by_node, eligible


def _catalogue_matches(
    node: RequestNode, candidate_declarations: tuple[declarations.Declaration, ...]
) -> tuple[tuple[declarations.Declaration, ...], list[str]]:
    pending = []
    if len(node.scopes) != 1:
        matches = ()
        pending.append("ambiguous_or_absent_requested_scope")
    else:
        scope = node.scopes[0].text
        matches = tuple(
            d
            for d in candidate_declarations
            if d.kind == "role_catalogue"
            and len(d.scope) == 1
            and d.scope[0].text == scope
        )
        if not matches:
            pending.append("missing_catalogue")
        elif len(matches) > 1:
            pending.append("ambiguous_catalogue")
    return matches, pending


def _bounded_catalogues(
    partial: PartialRequest,
    requirements: list[Requirement],
    eligible: dict[str, declarations.Declaration],
    choices: dict[str, tuple[declarations.Declaration, ...]],
    pending_by_node: dict[str, list[str]],
    blockers: list[Blocker],
    max_requirements: int,
) -> dict[str, declarations.Declaration]:
    predicted = len(requirements)
    for node_id, row in eligible.items():
        dependents = sum(
            1
            for edge in partial.edges
            if edge.kind == "catalogue_member_value" and edge.source_id == node_id
        )
        predicted += len(row.members) * (1 + dependents)
    overflow = predicted > max_requirements
    if overflow:
        blockers.append(
            Blocker(
                "request",
                "requirement_budget_exceeded",
                canonical({"requested": predicted, "limit": max_requirements}),
            )
        )
        eligible = {}
        for node_id in choices:
            pending_by_node[node_id].append("requirement_budget_exceeded")
    return eligible


def _expand_catalogues(
    partial: PartialRequest,
    candidate_declarations: tuple[declarations.Declaration, ...],
    eligible: dict[str, declarations.Declaration],
    roots: dict[str, str],
    requirements: list[Requirement],
    members: list[MemberBinding],
    values: list[ValueSlot],
    edges: list[Edge],
    blockers: list[Blocker],
) -> tuple[dict[str, tuple[str, ...]], dict[str, str], dict[str, str]]:
    children_by_node = {}
    child_by_binding = {}
    value_by_binding = {}
    for node in partial.nodes:
        if node.id not in eligible:
            continue
        row = eligible[node.id]
        generated = []
        for literal in row.members:
            identity = {
                "parent": roots[node.id],
                "declaration_id": row.id,
                "literal": asdict(literal),
                "operation": node.operation,
            }
            binding_id = "m-" + digest(identity)
            child_id = "r-" + digest(dict(identity, kind="catalogue_child"))
            slot_id = (
                "v-" + digest(dict(identity, kind="supported_actor"))
                if node.operation == "incumbents"
                else None
            )
            kind = "role_assignment" if node.operation == "incumbents" else "role_label"
            members.append(
                MemberBinding(
                    binding_id,
                    roots[node.id],
                    row.id,
                    literal,
                    canonical([asdict(x) for x in row.scope]),
                )
            )
            requirements.append(
                Requirement(
                    child_id,
                    node.id,
                    kind,
                    node.operation,
                    canonical([asdict(x) for x in node.evidence]),
                    node.feature_json,
                    canonical([asdict(x) for x in node.scopes]),
                    roots[node.id],
                    literal,
                    binding_id,
                    slot_id,
                    (_use(row),),
                )
            )
            edges.append(
                Edge(
                    "set_member",
                    roots[node.id],
                    child_id,
                    canonical([asdict(x) for x in node.evidence]),
                    binding_id,
                    slot_id,
                )
            )
            child_by_binding[binding_id] = child_id
            generated.append(child_id)
            if slot_id:
                candidates = tuple(
                    d
                    for d in candidate_declarations
                    if d.kind == "role_assignment"
                    and d.literal.text == literal.text
                    and len(d.scope) == 1
                    and d.scope[0].text == node.scopes[0].text
                )
                values.append(
                    ValueSlot(
                        slot_id,
                        child_id,
                        binding_id,
                        tuple(_use(d) for d in candidates),
                        canonical(
                            [
                                {
                                    "declaration_id": d.id,
                                    "payload_json": d.payload_json,
                                    "arguments": [asdict(a) for a in d.arguments],
                                }
                                for d in candidates
                            ]
                        ),
                    )
                )
                value_by_binding[binding_id] = slot_id
                blockers.append(
                    Blocker(
                        child_id,
                        "actor_value_unbound",
                        canonical(
                            {"candidate_declaration_ids": [d.id for d in candidates]}
                        ),
                    )
                )
        children_by_node[node.id] = tuple(generated)
    return children_by_node, child_by_binding, value_by_binding


def _append_original_edges(
    partial: PartialRequest,
    nodes: dict[str, RequestNode],
    roots: dict[str, str],
    members: list[MemberBinding],
    child_by_binding: dict[str, str],
    value_by_binding: dict[str, str],
    requirements: list[Requirement],
    edges: list[Edge],
    blockers: list[Blocker],
) -> None:
    for edge in partial.edges:
        _require(
            edge.source_id in roots and edge.target_id in roots,
            "Original request edge endpoint missing",
        )
        evidence = canonical([asdict(x) for x in edge.evidence])
        if edge.kind == "catalogue_member_value":
            edges.append(
                Edge(
                    "set_reference",
                    roots[edge.source_id],
                    roots[edge.target_id],
                    evidence,
                )
            )
            node = nodes[edge.target_id]
            bound = [m for m in members if m.group_id == roots[edge.source_id]]
            if not bound:
                blockers.append(
                    Blocker(roots[node.id], "unresolved_catalogue_value_dependency")
                )
            for binding in bound:
                value_id = value_by_binding.get(binding.id)
                if value_id is None:
                    blockers.append(
                        Blocker(roots[node.id], "catalogue_actor_value_required")
                    )
                    continue
                child_id = "r-" + digest(
                    {
                        "parent": roots[node.id],
                        "member_binding_id": binding.id,
                        "value_slot_id": value_id,
                    }
                )
                requirements.append(
                    Requirement(
                        child_id,
                        node.id,
                        node.kind,
                        node.operation,
                        canonical([asdict(x) for x in node.evidence]),
                        node.feature_json,
                        canonical([asdict(x) for x in node.scopes]),
                        roots[node.id],
                        binding.literal,
                        binding.id,
                        value_id,
                    )
                )
                edges.append(
                    Edge(
                        "availability_member",
                        roots[node.id],
                        child_id,
                        evidence,
                        binding.id,
                        value_id,
                    )
                )
                edges.append(
                    Edge(
                        "actor_value_dependency",
                        child_by_binding[binding.id],
                        child_id,
                        evidence,
                        binding.id,
                        value_id,
                    )
                )
        elif edge.kind in {
            "value_dependency",
            "request_order",
            "local_procedure_facet",
            "request_facet",
        }:
            edges.append(
                Edge(edge.kind, roots[edge.source_id], roots[edge.target_id], evidence)
            )
        else:
            edges.append(
                Edge(
                    "unresolved:" + edge.kind,
                    roots[edge.source_id],
                    roots[edge.target_id],
                    evidence,
                )
            )
            blockers.append(
                Blocker("request", "unsupported_request_edge", canonical(asdict(edge)))
            )


def _append_resolutions(
    partial: PartialRequest,
    candidate_declarations: tuple[declarations.Declaration, ...],
    capture: dict,
    nodes: dict[str, RequestNode],
    roots: dict[str, str],
    choices: dict[str, tuple[declarations.Declaration, ...]],
    pending_by_node: dict[str, list[str]],
    children_by_node: dict[str, tuple[str, ...]],
    source_unknowns: bool,
    overlays: list[NameOverlay],
    resolutions: list[ResolutionEntry],
    blockers: list[Blocker],
) -> None:
    for slot in partial.deferred:
        candidates = ()
        child_ids = ()
        pending = []
        state = "UNRESOLVED"
        if slot.kind == "role_catalogue":
            candidates = tuple(d.id for d in choices.get(slot.node_id, ()))
            child_ids = children_by_node.get(slot.node_id, ())
            pending = list(pending_by_node.get(slot.node_id, ())) + [
                "independent_membership_evidence_required"
            ]
            if nodes[slot.node_id].operation == "incumbents":
                pending.append("independent_actor_value_evidence_required")
            if child_ids:
                state = "PROPOSED_EXPANSION"
        elif slot.kind == "literal_subject_boundary":
            uses = tuple(
                _use(row)
                for row in candidate_declarations
                if row.kind == "literal_name"
                and len(slot.evidence) == 1
                and row.literal.text == slot.evidence[0].text
            )
            closed = len(slot.evidence) == 1 and _nominal_interval(
                partial.question, capture, slot.evidence[0]
            )
            unique = len(uses) == 1 and closed and not source_unknowns
            status = "UNASSESSED_NAME_CANDIDATE" if unique else "UNRESOLVED_NAME"
            overlays.append(
                NameOverlay(
                    slot.id,
                    canonical(asdict(slot.evidence[0]))
                    if len(slot.evidence) == 1
                    else canonical([asdict(v) for v in slot.evidence]),
                    uses,
                    status,
                )
            )
            candidates = tuple(u.declaration_id for u in uses)
            pending = ["independent_name_applicability_evidence_required"]
            if not unique:
                pending.append("missing_ambiguous_or_unclosed_literal_name")
            else:
                state = "PROPOSED_OVERLAY"
        elif slot.kind == "verify_request_constraint":
            pending = ["constraint_evidence_required"]
        elif slot.kind == "procedure_facet_reference":
            pending = ["independent_required_content_and_output_coverage_required"]
        elif slot.kind == "temporal_attribute":
            candidates = tuple(
                row.id for row in candidate_declarations if row.kind == "literal_field"
            )
            pending = ["temporal_relation_and_qualifier_evidence_required"]
        else:
            pending = ["unsupported_deferred_obligation"]
        resolutions.append(
            ResolutionEntry(
                slot.id,
                slot.node_id,
                slot.kind,
                state,
                candidates,
                child_ids,
                tuple(pending),
            )
        )
        blockers.extend(
            Blocker(slot.id, reason, canonical(asdict(slot))) for reason in pending
        )


def _cyclic(edges):
    graph = {}
    for edge in edges:
        graph.setdefault(edge.source_id, []).append(edge.target_id)
    done = set()
    active = set()

    def visit(node):
        if node in active:
            return True
        if node in done:
            return False
        active.add(node)
        if any(visit(target) for target in graph.get(node, ())):
            return True
        active.remove(node)
        done.add(node)
        return False

    return any(visit(node) for node in tuple(graph))
