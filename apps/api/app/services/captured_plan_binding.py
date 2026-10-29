"""Explicit new-profile structure, retaining original captured syntax."""

import json
from dataclasses import asdict, dataclass, fields

from app.evidence_policy import recorded_evidence_policy
from app.services import request_grammar as grammar
from app.services.answer_requirements import Requirement
from app.services.captured_plan_requirements import (
    CapturedRequirementUse,
    closed_original_frames,
)
from app.services.captured_production_policy import selected_version
from app.services.captured_request_productions import reconstruct_request_productions
from app.services.planning_declarations import canonical
from app.services.request_parser import validate_capture
from app.services.staged_production_obligations import request_productions
from app.services.staged_request import compile_request


def _requirement_bound(profile):
    return (
        recorded_evidence_policy(profile).source_governance_profile
        == "requirement_bound_v1"
    )


@dataclass(frozen=True)
class CapturedCandidatePlan:
    structure_json: str
    source_productions_json: str
    requirements: tuple[Requirement, ...] = ()
    uses: tuple[CapturedRequirementUse, ...] = ()
    members_json: str = "[]"
    value_slots_json: str = "[]"
    edges_json: str = "[]"
    unresolved_json: str = "[]"
    operation_ledger_json: str = "[]"

    def record(self):
        return json.loads(
            canonical({"contract": "captured-plan-candidates-v1", **asdict(self)})
        )


@dataclass(frozen=True)
class CapturedRequestPlan(CapturedCandidatePlan):
    question: str = ""
    evidence_profile_json: str = "{}"
    planning_support_json: str = "{}"
    graph_json: str = "{}"
    graph_sha256: str = ""
    capture_sha256: str = ""
    question_sha256: str = ""
    model_identity_json: str = "{}"
    read_set_json: str = "{}"
    sql_read_set_json: str = "{}"
    structure_resolved: bool = False
    planning_supported: bool = False
    governance_status: str = "UNRESOLVED"
    remaining_external_governing_json: str = "[]"
    publication_ready: bool = False
    factual_witnesses: str = "NOT_ASSESSED"
    source_authority: str = "NOT_ASSESSED"
    sql_authorization_currentness: str = "NOT_ASSESSED"
    output_history: str = "NOT_ASSESSED"

    @property
    def partial_json(self):
        return self.structure_json

    @property
    def unresolved(self):
        from app.services.effective_request import Blocker

        return tuple(
            Blocker(r.get("owner_id", "request"), r["reason"], canonical(r))
            for r in json.loads(self.unresolved_json)
        )

    @property
    def resolved_request(self):
        return (
            self.structure_resolved
            and self.planning_supported
            and not json.loads(self.unresolved_json)
            and self.governance_status
            == (
                "SOURCE_EVIDENCE_CHECKS_PENDING"
                if _requirement_bound(json.loads(self.evidence_profile_json))
                else "ACCOUNTED_OPERATIONS_PER_FACT_GATES_PENDING"
            )
        )

    def record(self):
        return json.loads(
            canonical(
                {
                    "contract": "staged-request-plan-v2",
                    "reading_profile": "contextual_source_v4",
                    "resolved_request": self.resolved_request,
                    "unresolved": json.loads(self.unresolved_json),
                    **asdict(self),
                }
            )
        )


def reconstruct_captured_plan(
    *args, support_metadata, observations=(), actual_executions=(), **kwargs
):
    """Independently replay syntax, full sources and retained NI; never facts."""
    from app.services.captured_plan_inputs import _profile
    from app.services.captured_planning_support import reconstruct_planning_support

    if args:
        raise ValueError("Named original captured input arguments required")
    profile, _ = _profile(kwargs.get("evidence_profile"))
    requirement_bound = _requirement_bound(profile)
    candidate = prepare_candidate_plan(**kwargs)
    supported = reconstruct_planning_support(
        **kwargs,
        support_metadata=support_metadata,
        observations=observations,
        actual_executions=actual_executions,
    )
    structure = json.loads(candidate.structure_json)
    ledger = json.loads(candidate.source_productions_json)
    capture = kwargs["capture"]
    blockers = json.loads(candidate.unresolved_json)
    if supported.assertion_set.assertions and not all(
        a.supported for a in supported.assessments
    ):
        blockers.append({"reason": "mandatory_planning_relation_not_supported"})
    blockers.extend(
        {"owner_id": p.id, "reason": p.reason}
        for p in supported.assertion_set.pending
        if not requirement_bound or p.kind != "request_structure"
    )
    resolutions = {r["node_id"] for r in structure["production_resolutions"]}
    structure_resolved = (
        bool(candidate.requirements)
        and not structure["syntax_unresolved"]
        and all(
            n["id"] in resolutions or n["grammar"] == "captured_set_value_dependency_v1"
            for n in structure["nodes"]
        )
    )
    planning_supported = not supported.assertion_set.pending and all(
        a.supported for a in supported.assessments
    )
    external = [
        r for r in json.loads(candidate.operation_ledger_json) if r["remaining_gates"]
    ]
    if requirement_bound:
        external.extend(structure["pending_source_applicability"])
    if requirement_bound and ledger["read_set"]["missing_publications"]:
        external.append(
            {
                "reason": "incomplete_original_source_universe",
                "missing_publications": ledger["read_set"]["missing_publications"],
            }
        )
    governance_known = not any(
        r["disposition"] == "UNRESOLVED_POSSIBLE_GOVERNANCE"
        for r in json.loads(candidate.operation_ledger_json)
    )
    values = {f.name: getattr(candidate, f.name) for f in fields(candidate)}
    values["unresolved_json"] = canonical(blockers)
    return CapturedRequestPlan(
        **values,
        question=kwargs["question"],
        evidence_profile_json=canonical(profile),
        planning_support_json=canonical(supported.record()),
        graph_json=canonical(capture["annotation"]),
        graph_sha256=capture["annotation_sha256"],
        capture_sha256=capture["capture_sha256"],
        question_sha256=structure["historical_partial"]["question_sha256"],
        model_identity_json=canonical(capture["parser"]),
        read_set_json=canonical(ledger["read_set"]),
        sql_read_set_json=kwargs["sql_read_set_json"],
        structure_resolved=structure_resolved,
        planning_supported=planning_supported,
        governance_status="SOURCE_EVIDENCE_CHECKS_PENDING"
        if requirement_bound
        else "ACCOUNTED_OPERATIONS_PER_FACT_GATES_PENDING"
        if governance_known
        else "UNRESOLVED_POSSIBLE_GOVERNANCE",
        remaining_external_governing_json=canonical(external),
    )


def validate_captured_plan(record, *args, **kwargs):
    from app.services.request_parser import _native

    try:
        _native(record)
        return canonical(record) == canonical(
            reconstruct_captured_plan(*args, **kwargs).record()
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


def reconstruct_request(
    record, *, question, authoritative_snapshots, retained_inputs, require_runtime=False
):
    from app.services.captured_plan_inputs import decode_inputs_v2

    if type(require_runtime) is not bool:
        raise ValueError("Runtime provenance policy must be an exact boolean")
    decoded = decode_inputs_v2(
        record,
        question=question,
        authoritative_snapshots=authoritative_snapshots,
        retained_inputs=retained_inputs,
    )
    if require_runtime and any(
        row.capture_kind != "runtime_capture"
        for row in decoded.arguments["actual_executions"]
    ):
        raise ValueError("Actual runtime capture provenance required")
    return reconstruct_captured_plan(
        **decoded.arguments, evidence_profile=decoded.evidence_profile
    )


def prepare_candidate_plan(
    question,
    capture,
    manifest,
    snapshots,
    source_captures,
    *,
    sql_read_set_json,
    evidence_profile=None,
):
    from app.services.captured_plan_inputs import _profile
    from app.services.captured_source_productions import reconstruct_source_productions

    profile_record, profile = _profile(evidence_profile)
    structure = prepare_structure(question, capture, reading_profile=profile)
    ledger = reconstruct_source_productions(
        question,
        capture,
        manifest,
        snapshots,
        source_captures,
        sql_read_set_json=sql_read_set_json,
        reading_profile=profile,
    )
    from app.services.captured_plan_requirements import (
        derive_requirements,
        operation_ledger,
    )

    requirements, uses, members, values, edges, unresolved = derive_requirements(
        structure, ledger
    )
    operations, governance_unknowns = operation_ledger(ledger)
    missing = ledger["read_set"]["missing_publications"]
    if missing:
        governance_unknowns.append(
            {
                "reason": "incomplete_original_source_universe",
                "missing_publications": missing,
            }
        )
    request_unresolved = structure["unresolved"]
    requirement_bound = _requirement_bound(profile_record)
    if requirement_bound:
        # These exact independently rebuilt constraints need a selected source.
        # They remain mandatory consumer obligations, without blocking search.
        request_unresolved = [
            row
            for row in request_unresolved
            if row not in structure["pending_source_applicability"]
        ]
    return CapturedCandidatePlan(
        canonical(structure),
        canonical(ledger),
        tuple(requirements),
        tuple(uses),
        canonical([asdict(r) for r in members]),
        canonical([asdict(r) for r in values]),
        canonical([asdict(r) for r in edges]),
        canonical(
            request_unresolved
            + unresolved
            + ([] if requirement_bound else governance_unknowns)
        ),
        canonical(operations),
    )


def _require(value, message):
    if not value:
        raise ValueError(message)


def _literal(graph, indices):
    return asdict(grammar.literal(graph.span(indices)))


def _dependent(graph, head, scope_head, sentence, operation):
    children = [
        i
        for i in sentence
        if graph.ts[i]["dep"] == "conj" and graph.ts[i]["head"] in {head, scope_head}
    ]
    if not children:
        return None
    _require(
        operation == "incumbents" and len(children) == 1,
        "One captured incumbent-set antecedent is required",
    )
    child = children[0]
    refs = [i for i in graph.children[child] if graph.ts[i]["dep"] == "poss"]
    _require(
        graph.ts[child]["pos"] == "NOUN"
        and graph.lemma(child) == "availability"
        and len(refs) == 1
        and graph.low(refs[0]) == "their"
        and graph.ts[refs[0]]["pos"] == "PRON"
        and not graph.children[refs[0]]
        and graph.subtree(child) == {child, refs[0]},
        "Unclosed dependent field or antecedent remains unresolved",
    )
    coordinators = [
        i
        for i in sentence
        if graph.ts[i]["dep"] == "cc"
        and graph.ts[i]["head"] == graph.ts[child]["head"]
        and graph.lemma(i) == "and"
        and not graph.children[i]
    ]
    _require(len(coordinators) == 1, "Unique captured coordination required")
    return {
        "head": child,
        "reference": refs[0],
        "token_indices": sorted({child, refs[0], *coordinators}),
    }


def _nominal_sentence(graph, sentence):
    roots = [i for i in sentence if graph.ts[i]["dep"] == "ROOT"]
    _require(len(roots) == 1, "One captured sentence root required")
    head = roots[0]
    _require(
        graph.ts[head]["pos"] == "NOUN"
        and graph.lemma(head) in {"label", "holder", "incumbent"},
        "Unsupported nominal request root",
    )
    nominal = graph.nominal(head)
    operators = [
        i
        for i in nominal
        if graph.lemma(i) in grammar.META
        and graph.ts[i]["dep"] == "compound"
        and graph.ts[i]["pos"] == "NOUN"
    ]
    _require(len(operators) == 1, "One captured nominal operator required")
    operator = operators[0]
    _require(
        operator == min(sentence) and not graph.children[operator],
        "Qualified or nonleading nominal operator remains unresolved",
    )
    markers = {
        i
        for i in nominal
        if graph.lemma(i) == "role" and graph.ts[i]["dep"] == "compound"
    }
    _require(
        len(markers) == 1 and nominal == {head, operator} | markers,
        "Unrepresented role field modifier remains unresolved",
    )
    scopes = graph.direct_scopes(head)
    _require(len(scopes) == 1, "One actual scope argument required")
    scope, covered = scopes[0]
    scope_heads = [i for i in scope if graph.ts[i]["head"] not in scope]
    _require(len(scope_heads) == 1, "Ambiguous scope argument")
    scope_head = scope_heads[0]
    _require(
        all(
            graph.ts[i]["pos"] in {"NOUN", "PROPN"}
            and graph.ts[i]["dep"] in {"compound", "pobj"}
            for i in scope
        ),
        "Qualified scope remains unresolved",
    )
    operation = "labels_only" if graph.lemma(head) == "label" else "incumbents"
    dependent = _dependent(graph, head, scope_head, sentence, operation)
    delegated = set(dependent["token_indices"]) if dependent else set()
    punctuation = {
        i
        for i in sentence
        if graph.ts[i]["dep"] == "punct" and graph.ts[i]["head"] == head
    }
    _require(
        nominal | set(covered) | punctuation | delegated == set(sentence),
        "Unrepresented sentence material remains unresolved",
    )
    features = json.loads(grammar.features(graph, set(sentence)))
    _require(
        not any(
            features.get(k)
            for k in (
                "condition_ast",
                "modality",
                "units",
                "negation",
                "quantifiers",
                "governors",
                "order",
            )
        ),
        "Qualified request requires separate production",
    )
    refs = features.get("references", [])
    _require(
        refs == ([_literal(graph, {dependent["reference"]})] if dependent else []),
        "Unknown request reference remains unresolved",
    )
    return {
        "kind": "role_catalogue",
        "operation": operation,
        "head_indices": [head],
        "token_indices": sorted(set(sentence) - delegated),
        "scopes": [_literal(graph, scope)],
        "feature_json": canonical(features),
        "evidence": [_literal(graph, sentence)],
        "grammar": "captured_nominal_request_operator_v1",
        "proposed_question": "",
        "dependent": dependent,
        "ownership": {
            "operator": _literal(graph, {operator}),
            "original_operator_token": graph.ts[operator],
            "scope": _literal(graph, scope),
            "delegated_token_indices": sorted(delegated),
        },
    }


def prepare_structure(question, capture, *, reading_profile=None):
    """Derive new nodes by original ownership, never a resolved legacy plan."""
    _require(
        selected_version(reading_profile) is not None,
        "Explicit captured-production profile required",
    )
    original = reconstruct_request_productions(
        question, capture, reading_profile=reading_profile
    )
    partial = compile_request(question, capture)
    graph = grammar.Graph(question, validate_capture(question, capture))
    copied = request_productions(partial)
    nodes, unresolved, resolutions, edges = [], [], [], []
    historical = original["historical_partial"]
    frames, syntax = closed_original_frames(question, capture, historical)
    pending_copy = []
    from app.services.request_relation import request_relation_closures

    owned_relations = {
        row.node_id: asdict(row)
        for row in request_relation_closures(question, capture, historical["nodes"])
        if row.status == "EXACT_INITIAL_RELATION"
    }
    replaced = set()
    for sentence in capture["annotation"]["sentences"]:
        indices = list(range(sentence["token_start"], sentence["token_end"]))
        try:
            new = _nominal_sentence(graph, indices)
        except ValueError:
            continue
        overlapped = [
            n for n in historical["nodes"] if set(n["token_indices"]) & set(indices)
        ]
        _require(
            len(overlapped) == 1
            and set(overlapped[0]["token_indices"]) <= set(indices),
            "Overlapping historical ownership cannot be narrowed",
        )
        identifier = overlapped[0]["id"]
        dependent = new.pop("dependent")
        nodes.append({**new, "id": identifier})
        replaced.add(identifier)
        resolutions.append(
            {
                "node_id": identifier,
                "production": new["grammar"],
                "historical_node": overlapped[0],
            }
        )
        if dependent:
            child_id = identifier + ":dependent"
            features = json.loads(new["feature_json"])
            features["attribute"] = graph.ts[dependent["head"]]["text"]
            nodes.append(
                {
                    "id": child_id,
                    "kind": "availability",
                    "operation": "request_field_value",
                    "head_indices": [dependent["head"]],
                    "token_indices": dependent["token_indices"],
                    "scopes": new["scopes"],
                    "feature_json": canonical(features),
                    "evidence": [_literal(graph, dependent["token_indices"])],
                    "grammar": "captured_set_value_dependency_v1",
                    "proposed_question": "",
                    "ownership": dependent,
                }
            )
            edges.append(
                {
                    "kind": "catalogue_member_value",
                    "source_id": identifier,
                    "target_id": child_id,
                    "evidence": [_literal(graph, {dependent["reference"]})],
                }
            )
    for node in historical["nodes"]:
        if node["id"] in replaced:
            continue
        production = _original_production(node, copied, owned_relations, graph)
        if not production and node["id"] in frames:
            frame = frames[node["id"]][1]
            production = {
                "production": "captured_closed_atomic_frame",
                "original_frame": asdict(frame),
            }
            if node["kind"] == "procedure":
                pending_copy.append(
                    {
                        "owner_id": node["id"],
                        "reason": "pending_source_applicability",
                        "state": "PENDING_SOURCE_APPLICABILITY",
                        "original_frame": asdict(frame),
                        "original_features_json": node["feature_json"],
                    }
                )
        nodes.append({**node, "ownership": production} if production else node)
        if production:
            resolutions.append(
                {
                    "node_id": node["id"],
                    "production": production["production"],
                    "proof": production,
                }
            )
        else:
            unresolved.append(
                {
                    "owner_id": node["id"],
                    "reason": "unsupported_captured_request_production",
                    "original_node": node,
                }
            )
    nodes.sort(key=lambda n: (min(n["token_indices"]), n["id"]))
    _require(len(nodes) <= 64, "Request node limit exceeded; no truncation")
    retained_unknowns, consumption = _retained_unknowns_and_consumption(
        graph, historical, replaced, nodes, syntax
    )

    unresolved.extend(retained_unknowns)
    return json.loads(
        canonical(
            {
                "contract": "captured-request-structure-v1",
                "reading_profile": reading_profile,
                "question": question,
                "historical_partial": historical,
                "original_capture": capture,
                "nodes": nodes,
                "edges": historical["edges"] + edges,
                "unresolved": unresolved + pending_copy,
                "syntax_unresolved": unresolved,
                "pending_source_applicability": pending_copy,
                "production_resolutions": resolutions,
                "deferred": historical["deferred"],
                "tokens": historical["tokens"],
                "consumption": consumption,
                "features_json": historical["features_json"],
                "complete_plan": False,
                "factual_values": "UNBOUND",
            }
        )
    )


def _original_production(node, copied, relations, graph):
    if node["id"] in copied:
        return {"production": "captured_complete_copy", "proof": copied[node["id"]]}
    if node["id"] in relations and node["kind"] in {"role_catalogue", "availability"}:
        operators: set[int] = set()
        for head in node["head_indices"]:
            index = grammar.operator(graph, head)
            if type(index) is int:
                operators.add(index)
        if len(operators) == 1:
            return {
                "production": "captured_existing_request_argument",
                "proof": relations[node["id"]],
                "operator_token_indices": sorted(operators),
            }
    return None


def _retained_unknowns_and_consumption(graph, historical, replaced, nodes, syntax):
    unresolved = []
    for unknown in historical["unknowns"]:
        covered = [
            n
            for n in historical["nodes"]
            if n["id"] in replaced
            and n["evidence"] == unknown["evidence"]
            and n["head_indices"] == unknown["head_indices"]
        ]
        if unknown["reason"] != "unrecognized_request_predicate" or len(covered) != 1:
            unresolved.append(
                {"reason": "retained_historical_unknown", "original_unknown": unknown}
            )
    consumption = []
    for token in graph.ts:
        owners = [
            n["id"]
            for n in nodes
            if token["i"] in set(n["token_indices"]) | set(n["head_indices"])
            or token["i"] in n.get("ownership", {}).get("operator_token_indices", [])
            or token["dep"] == "punct"
            and token["head"] in n["head_indices"]
        ]
        consumption.append(
            {
                "token": _literal(graph, {token["i"]}),
                "whitespace": token["whitespace"],
                "owners": owners,
                "role": "declared_frame_syntax"
                if token["i"] in syntax
                else "request_argument",
            }
        )
        if not owners and token["pos"] != "PUNCT" and token["i"] not in syntax:
            unresolved.append(
                {"reason": "unowned_original_request_token", "original_token": token}
            )
    return unresolved, consumption
