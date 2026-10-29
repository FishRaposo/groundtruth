"""Whole-body candidate relevance only; all authorization/evidence gates remain.

Never reduces the planning read set. Exclusion requires the unchanged finite
source-cover consumer to reconstruct irrelevance for every captured nominal
scope. Unknown request/source material retains all affected candidates.
"""

import json
from dataclasses import asdict

from app.services import contextual_procedures as procedures
from app.services import declared_source_scope as scope
from app.services import planning_declarations as declarations
from app.services.dependency_frames import Graph
from app.services.request_grammar import qualified_argument
from app.services.request_obligations import Literal, PartialRequest
from app.services.request_parser import validate_capture
from app.services.request_relation import request_relation_closures
from app.services.staged_request import compile_request

canonical = declarations.canonical
MAX_NOMINAL_SCOPES = 16  # Same bound as current declared_scope_index._candidate.


def _node_request_scopes(
    partial: PartialRequest, qualified: tuple[str, ...], productions=None
) -> tuple[list[Literal], list[str]]:
    blockers: list[str] = []
    values: list[Literal] = []
    for node in partial.nodes:
        production = (productions or {}).get(node.id, {})
        scopes = node.scopes or (
            (Literal(**production["scope"]),) if "scope" in production else ()
        )
        if not scopes:
            blockers.append("unscoped_request_obligation")
        features = json.loads(node.feature_json)
        if any(
            features.get(key)
            and not (
                key == "references"
                and features[key] == production.get("consumed_references")
                or key == "governors"
                and features[key] == production.get("consumed_governors")
            )
            for key in qualified
        ) or features.get("ownership_context_pending"):
            blockers.append("qualified_node_requires_resolution")
        for literal in scopes:
            if partial.question[
                literal.start : literal.end
            ] != literal.text or not scope._nominal(
                literal.text, scope._SUBJECT_BLOCKERS
            ):
                blockers.append("unsupported_nominal_scope")
            if literal not in values:
                values.append(literal)
    return values, blockers


def _request_scopes(partial, productions=None):
    if type(partial) is not PartialRequest:
        raise ValueError("Typed actual partial request required")
    rebuilt = compile_request(partial.question, json.loads(partial.raw_capture_json))
    if rebuilt != partial:
        raise ValueError("Partial request differs from actual question/capture replay")
    blockers = []
    if partial.unknowns or not partial.nodes:
        blockers.append("unknown_request_obligations")
    # Conditions/references/modality are preserved and never collapsed to the
    # namespace just to obtain an exclusion. The later resolver owns them.
    qualified = (
        "condition_ast",
        "governors",
        "modality",
        "negation",
        "order",
        "quantifiers",
        "references",
        "units",
    )
    productions = productions or {}
    extents = [
        asdict(partial.tokens[index].token)
        for production in productions.values()
        for index in production["extent_token_indices"]
    ]
    extents.extend(
        span
        for production in productions.values()
        for span in production.get("consumed_quantifiers", [])
    )
    references = [
        span
        for production in productions.values()
        for span in production.get("consumed_references", [])
    ]
    global_features = json.loads(partial.features_json)
    governors = [
        span
        for production in productions.values()
        for span in production.get("consumed_governors", [])
    ]
    if any(
        [
            value
            for value in global_features.get(key, [])
            if not (
                key == "quantifiers"
                and value in extents
                or key == "references"
                and value in references
                or key == "governors"
                and value in governors
            )
        ]
        for key in qualified
    ):
        blockers.append("qualified_request_requires_resolution")
    values, node_blockers = _node_request_scopes(
        partial,
        qualified
        if not productions
        else tuple(key for key in qualified if key != "quantifiers"),
        productions,
    )
    if productions and any(
        json.loads(node.feature_json).get("quantifiers") and node.id not in productions
        for node in partial.nodes
    ):
        node_blockers.append("qualified_node_requires_resolution")
    blockers.extend(node_blockers)
    if not 0 < len(values) <= MAX_NOMINAL_SCOPES:
        blockers.append("nominal_scope_budget_or_absence")
    relations = request_relation_closures(
        partial.question,
        json.loads(partial.raw_capture_json),
        [asdict(node) for node in partial.nodes],
    )
    if len(relations) != len(partial.nodes) or any(
        row.status != "EXACT_INITIAL_RELATION" and row.node_id not in productions
        for row in relations
    ):
        blockers.append("actual_owned_request_argument_or_quantity_unresolved")
    return tuple(values), tuple(dict.fromkeys(blockers)), relations


def _source_scope_closure(snapshot, captures, cover):
    """Prove a literal compound nominal from actual captured structure only.

    The old lexical body-cover remains unchanged. This additional negative-
    selection guard cannot infer a meaning for unknown modifiers or qualifiers.
    Its only closed non-head production is a literal NOUN/PROPN compound;
    a/an/the syntax is retained separately, using the existing805 distinction.
    """
    parsed = []
    for window in captures.windows:
        raw = snapshot.body[window.start : window.end]
        capture = json.loads(window.capture_json)
        parsed.append((window, Graph(raw, validate_capture(raw, capture))))
    records = []
    seen = set()
    for unit in cover["units"]:
        for literal in unit["scope_evidence"]:
            key = (literal["start"], literal["end"], literal["text"])
            if key in seen:
                continue
            seen.add(key)
            record = {
                "literal": literal,
                "status": "UNRESOLVED",
                "reason": "source_scope_capture_not_closed",
                "argument_ast": None,
                "token_indices": [],
                "head_indices": [],
                "capture_window": None,
            }
            for window, graph in parsed:
                if not window.start <= literal["start"] < literal["end"] <= window.end:
                    continue
                start, end = (
                    literal["start"] - window.start,
                    literal["end"] - window.start,
                )
                ids = {
                    token["i"]
                    for token in graph.ts
                    if start <= token["start"] and token["end"] <= end
                }
                heads = [
                    i
                    for i in ids
                    if graph.ts[i]["head"] not in ids or graph.ts[i]["head"] == i
                ]
                record.update(
                    token_indices=sorted(ids),
                    head_indices=heads,
                    capture_window={"start": window.start, "end": window.end},
                )
                if (
                    not ids
                    or len(heads) != 1
                    or graph.ts[min(ids)]["start"] != start
                    or graph.ts[max(ids)]["end"] != end
                ):
                    record["reason"] = "source_nominal_head_or_literal_unresolved"
                    break
                head = heads[0]
                argument = qualified_argument(graph, head)
                record["argument_ast"] = argument
                owned = set(argument["token_indices"])
                articles = {
                    i
                    for i in owned - ids
                    if graph.ts[i]["dep"] == "det"
                    and graph.low(i) in {"a", "an", "the"}
                    and graph.ts[i]["head"] == head
                    and not graph.children[i]
                }
                if (
                    graph.ts[head]["pos"] not in {"NOUN", "PROPN"}
                    or owned != ids | articles
                    or argument["unclassified"]
                ):
                    record["reason"] = (
                        "source_nominal_ownership_or_unknown_qualification"
                    )
                    break
                components_closed = all(
                    i == head
                    or i in articles
                    or graph.ts[i]["pos"] in {"NOUN", "PROPN"}
                    and graph.ts[i]["dep"] == "compound"
                    and graph.ts[i]["head"] in ids
                    for i in owned
                )
                if not components_closed:
                    record["reason"] = "source_nominal_qualifier_requires_resolution"
                    break
                record.update(status="EXACT_LITERAL_COMPOUND_SCOPE", reason=None)
                break
            records.append(record)
    return records


def _candidate(identity, literal, origin, declaration_range):
    return {
        "source": asdict(identity),
        "literal": literal,
        "origin": origin,
        "declaration_range": declaration_range,
        "resolution": "UNASSESSED_CANDIDATE",
    }


def _names(snapshot, cover):
    candidates = []
    # These exact body ranges were classified by the existing finite parser,
    # never by title/metadata, an inferred entity type, or a new source DSL.
    for unit in cover["units"]:
        for literal in unit["scope_evidence"]:
            candidates.append(
                _candidate(
                    snapshot.identity,
                    literal,
                    "reconstructed_source_cover",
                    {"start": unit["start"], "end": unit["end"]},
                )
            )
    identity = {
        key: value
        for key, value in asdict(snapshot.identity).items()
        if key != "snapshot_id"
    }
    body = snapshot.body
    # Preserve the current recognized routine and literal envelope parsers as
    # independent candidate producers. Neither supplies an exclusion proof.
    declarations_found = list(procedures._DECLARATION.finditer(body))
    if len(declarations_found) == 1:
        declaration = declarations_found[0]
        subject = procedures._SUBJECT.fullmatch(declaration["subject"])
        if subject:
            try:
                record = procedures.routine_inventory(
                    body, identity, requested_subject=declaration["subject"]
                )
            except procedures.RoutineRejected:
                pass
            else:
                start = declaration.start("subject") + subject.start("namespace")
                end = declaration.start("subject") + subject.end("namespace")
                candidates.append(
                    _candidate(
                        snapshot.identity,
                        {"start": start, "end": end, "text": body[start:end]},
                        "recognized_routine_inventory",
                        record["declaration_range"],
                    )
                )
    try:
        declaration = procedures._envelope_declaration(body)
        record = procedures.declared_envelope_inventory(
            body, identity, requested_subject=declaration["subject"]
        )
    except procedures.RoutineRejected:
        pass
    else:
        candidates.append(
            _candidate(
                snapshot.identity,
                record["namespace"],
                "recognized_declared_envelope",
                record["declaration_range"],
            )
        )
    return candidates


def _source_decision(
    identity: declarations.SourceIdentity,
    snapshot: declarations.SourceSnapshot | None,
    captures_by_id: dict[str, declarations.SourceCaptures],
    scopes: tuple[Literal, ...],
    blockers: tuple[str, ...],
):
    candidates = []
    proof = {
        "source": asdict(identity),
        "status": "retained",
        "reason": "uninspectable_selected_publication",
        "cover": None,
        "scope_comparisons": [],
        "source_nominal_closures": [],
    }
    if snapshot is not None:
        cover = scope.source_cover(snapshot.body, asdict(identity))
        if not scope.validate_source_cover(cover, snapshot.body, asdict(identity)):
            raise ValueError(
                "Reconstructed whole-body cover differs from authoritative snapshot"
            )
        comparisons = [
            {
                "request_scope": asdict(literal),
                "relevance": scope.scope_relevance(cover, literal.text),
            }
            for literal in scopes
        ]
        proof.update(
            cover=cover,
            scope_comparisons=comparisons,
            reason="unknown_or_potentially_governing_source",
        )
        candidates.extend(_names(snapshot, cover))
        nominal_closures = _source_scope_closure(
            snapshot, captures_by_id[identity.document_id], cover
        )
        proof["source_nominal_closures"] = nominal_closures
        source_scope_closed = bool(nominal_closures) and all(
            row["status"] == "EXACT_LITERAL_COMPOUND_SCOPE" for row in nominal_closures
        )
        has_local_namespace = any(unit["subjects"] for unit in cover["units"])
        if blockers:
            proof["reason"] = "request_scope_unresolved"
        elif not source_scope_closed:
            proof["reason"] = "actual_source_nominal_or_qualification_unresolved"
        elif (
            has_local_namespace
            and comparisons
            and all(row["relevance"]["status"] == "irrelevant" for row in comparisons)
        ):
            proof.update(
                status="excluded",
                reason="reconstructed_all_regions_declared_elsewhere",
            )
        elif any(row["relevance"]["status"] == "relevant" for row in comparisons):
            proof["reason"] = "declared_or_global_scope"
    return proof, candidates


def reconstruct_scope_bridge(
    partial, manifest, snapshots, captures, *, procedure_productions=False
):
    """Return detached proof proposals retaining every actual input/read member.

    `partial` must replay from its actual raw capture. `manifest`, immutable
    snapshots and full-body source captures use current planning_declarations
    types and validation. A missing publication is retained, never excluded.
    The returned `excluded` IDs are ONLY relevance proposals for obligation
    selection: do not filter SQL, snapshots, captures or the read set with them.
    """
    from .staged_production_obligations import scope_productions

    productions = scope_productions(partial) if procedure_productions else {}
    scopes, blockers, relations = _request_scopes(partial, productions)
    read_set = declarations.planning_read_set(manifest, snapshots, captures)
    if manifest.selection_mode != "bounded_authorized_scan":
        blockers = (*blockers, "universe_selection_not_complete_scan")
    by_id = {snapshot.identity.document_id: snapshot for snapshot in snapshots}
    captures_by_id = {item.identity.document_id: item for item in captures}
    retained, excluded, decisions, candidates = [], [], [], []
    for identity in manifest.publications:
        snapshot = by_id.get(identity.document_id)
        proof, found_candidates = _source_decision(
            identity, snapshot, captures_by_id, scopes, blockers
        )
        candidates.extend(found_candidates)
        (excluded if proof["status"] == "excluded" else retained).append(
            identity.document_id
        )
        decisions.append(proof)
    # Duplicate literal name proposals across distinct immutable publications
    # stay unresolved. They never decide what request text names or is about.
    distinct = {}
    for candidate in candidates:
        key = (
            canonical(candidate["source"]),
            canonical(candidate["literal"]),
            candidate["origin"],
        )
        distinct.setdefault(key, candidate)
    candidates = list(distinct.values())
    identities_by_name = {}
    for candidate in candidates:
        identities_by_name.setdefault(
            scope._canonical(candidate["literal"]["text"]), set()
        ).add(canonical(candidate["source"]))
    for candidate in candidates:
        if len(identities_by_name[scope._canonical(candidate["literal"]["text"])]) > 1:
            candidate["resolution"] = "ambiguous_literal"
    return json.loads(
        canonical(
            {
                "contract": "staged-planning-scope-bridge-v2",
                "partial_request": partial.record(),
                "universe": asdict(manifest),
                "snapshots": [asdict(row) for row in snapshots],
                "captures": [asdict(row) for row in captures],
                "read_set": read_set.record(),
                "request_scopes": [asdict(row) for row in scopes],
                "request_scope_blockers": blockers,
                "request_relation_closures": [asdict(row) for row in relations],
                **(
                    {"procedure_production_obligations": productions}
                    if productions
                    else {}
                ),
                "retained": retained,
                "excluded": excluded,
                "source_decisions": decisions,
                "name_candidates": candidates,
                "authority": "NOT_ASSESSED",
                "support": "NOT_ASSESSED",
                "permissions": "NOT_ASSESSED",
                "complete_plan": "NOT_ESTABLISHED",
                "exclusion_scope": (
                    "candidate_obligation_selection_only_preserve_full_read_set"
                ),
            }
        )
    )


def validate_scope_bridge(
    record, partial, manifest, snapshots, captures, *, procedure_productions=False
):
    """Replay from independently loaded authoritative inputs; reject flags."""
    try:
        return type(record) is dict and canonical(record) == canonical(
            reconstruct_scope_bridge(
                partial,
                manifest,
                snapshots,
                captures,
                procedure_productions=procedure_productions,
            )
        )
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
        RecursionError,
    ):
        return False
