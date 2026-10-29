"""Actual request/source ownership for bounded complete-copy productions.

Structural ownership selects production obligations only. The entire source
and its unknown ledger remain retained. Source applicability, local/whole NLI,
complete output and publication currentness remain independent mandatory gates.
"""

import json
from dataclasses import asdict

from app.services import planning_declarations as source
from app.services.contextual_procedures import _envelope_declaration
from app.services.contextual_source_proof import (
    SourceGuardRefusal,
    _copy_clause,
    _declared_relation,
    _unit_graph,
)
from app.services.dependency_frames import WHOLE, Graph
from app.services.request_grammar import qualified_argument
from app.services.request_parser import validate_capture


def request_productions(partial):
    """Retain exact closed captured NP copy requests, never factual approval."""
    capture = json.loads(partial.raw_capture_json)
    graph = Graph(partial.question, validate_capture(partial.question, capture))
    frames = json.loads(partial.frame_proposals_json)
    productions = {}
    for node in partial.nodes:
        if node.kind != "procedure" or node.grammar not in {
            "requested_np_head",
            "requested_np_head_local_procedure_reference",
            "closed_whole_procedure_request",
        }:
            continue
        candidates = [
            row
            for row in frames
            if tuple(row["tokens"]) == node.token_indices
            and tuple(row["heads"]) == node.head_indices
            and not row["errors"]
        ]
        if len(candidates) != 1 or len(node.scopes) != 1:
            continue
        features = json.loads(node.feature_json)
        if features["extent"] != "whole_requested" or any(
            features.get(key)
            for key in (
                "condition_ast",
                "modality",
                "negation",
                "units",
                "order",
            )
        ):
            continue
        frame = candidates[0]
        facet_proof = _facet_proof(partial, node, features, frame)
        if facet_proof is None:
            continue
        head = node.head_indices[-1]
        owned_extent = [
            index
            for index in node.token_indices
            if graph.lemma(index) in WHOLE
            and graph.ts[index]["dep"] in {"amod", "det"}
            and graph.ts[index]["head"] == head
        ]
        quantifiers = features.get("quantifiers", [])
        facet_ids = set().union(
            *(
                set(row["copy_facet_ownership"]["selector_token_indices"])
                for row in facet_proof
            )
        )
        facet_quantifiers = [
            span
            for span in quantifiers
            if any(
                index in facet_ids
                and graph.ts[index]["start"] == span["start"]
                and graph.ts[index]["end"] == span["end"]
                for index in facet_ids
            )
        ]
        if not owned_extent or [
            span for span in quantifiers if span not in facet_quantifiers
        ] != [asdict(source.RawRange(*graph.span({index}))) for index in owned_extent]:
            continue
        literal = node.scopes[0]
        scope_tokens = [
            token
            for token in graph.ts
            if literal.start <= token["start"] < token["end"] <= literal.end
        ]
        scope_ids = {token["i"] for token in scope_tokens}
        articles = {
            index
            for index in graph.nominal(head)
            if graph.ts[index]["dep"] == "det"
            and graph.lemma(index) in {"a", "an", "the"}
        }
        if graph.nominal(head) - {head} - set(owned_extent) - articles - scope_ids:
            continue
        roots = [token["i"] for token in scope_tokens if token["head"] not in scope_ids]
        if (
            len(roots) != 1
            or not scope_tokens
            or scope_tokens[0]["start"] != literal.start
            or scope_tokens[-1]["end"] != literal.end
        ):
            continue
        argument = qualified_argument(graph, roots[0])
        if (
            argument["unclassified"]
            or set(argument["token_indices"]) != scope_ids
            or any(
                token["pos"] not in {"NOUN", "PROPN"}
                or token["i"] != roots[0]
                and token["dep"] != "compound"
                for token in scope_tokens
            )
        ):
            continue
        productions[node.id] = {
            "contract": "captured-complete-procedure-obligation-v1",
            "node_id": node.id,
            "node": asdict(node),
            "frame": frame,
            "scope_argument": argument,
            "extent_token_indices": owned_extent,
            "consumed_references": features.get("references", []),
            "consumed_governors": features.get("governors", []),
            "consumed_quantifiers": facet_quantifiers,
            "copy_facet_ownership": facet_proof,
            "remaining_gates": [
                "source_envelope",
                "applicability_nli",
                "complete_output",
                "publication_currentness",
            ],
            "factual_authority": "NOT_ASSESSED",
        }
    return productions


def _facet_proof(partial, node, features, frame):
    if not features.get("governors"):
        return [] if not features.get("references") else None
    from .staged_copy_facets import reconstruct_copy_facets

    use = {
        **features,
        "head_token_indices": list(node.head_indices),
        "consumed_token_indices": list(node.token_indices),
    }
    try:
        return reconstruct_copy_facets(
            {
                "contract": "staged-request-plan-v1",
                "reading_profile": "contextual_source_v3",
                "question": partial.question,
                "graph_json": source.canonical(
                    json.loads(partial.raw_capture_json)["annotation"]
                ),
            },
            {
                "kind": "procedure",
                "topic": frame["topic"],
                "relation": frame["relation"],
            },
            use,
            None,
        )
    except (ValueError, KeyError, TypeError, IndexError):
        return None


def scope_productions(partial):
    """Also bind a captured set-reference scope, without binding actor values."""
    from .request_relation import request_relation_closures

    result = request_productions(partial)
    nodes = {node.id: node for node in partial.nodes}
    closures = {
        row.node_id: row
        for row in request_relation_closures(
            partial.question,
            json.loads(partial.raw_capture_json),
            [asdict(node) for node in partial.nodes],
        )
    }
    for node in partial.nodes:
        edges = [edge for edge in partial.edges if edge.target_id == node.id]
        if (
            node.kind != "availability"
            or node.operation != "request_field_value"
            or len(edges) != 1
            or edges[0].kind != "catalogue_member_value"
            or closures[node.id].status != "EXACT_INITIAL_RELATION"
        ):
            continue
        parent = nodes[edges[0].source_id]
        if (
            parent.kind != "role_catalogue"
            or parent.operation != "incumbents"
            or len(parent.scopes) != 1
            or closures[parent.id].status != "EXACT_INITIAL_RELATION"
        ):
            continue
        features = json.loads(node.feature_json)
        references = features.get("references", [])
        if any(
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
        ) or references != [asdict(span) for span in edges[0].evidence]:
            continue
        result[node.id] = {
            "contract": "captured-dependent-field-obligation-v1",
            "node_id": node.id,
            "node": asdict(node),
            "scope": asdict(parent.scopes[0]),
            "set_reference": asdict(edges[0]),
            "relation_closure": asdict(closures[node.id]),
            "extent_token_indices": [],
            "consumed_references": references,
            "actor_values": "UNBOUND",
            "factual_authority": "NOT_ASSESSED",
        }
    return result


def _unit_copy_proof(snapshot, unit, declaration, relation, windows):
    if (unit.raw.start, unit.raw.end) == declaration.span():
        return relation
    graph = _unit_graph(
        snapshot.body,
        [
            (start, end, validate_capture(snapshot.body[start:end], capture))
            for start, end, capture in windows
        ],
        unit.raw.start,
        unit.raw.end,
    )
    proof = _copy_clause(graph, asdict(unit.raw))
    if proof["kind"] != "root_directive":
        raise SourceGuardRefusal(
            "Only an actual root directive has copy-production ownership"
        )
    return proof


def source_ownership(partial, manifest, snapshots, captures, inventory):
    """Own only exact declared headers and root directives of requested copies."""
    productions = request_productions(partial)
    _, validated = source._inputs(manifest, snapshots, captures)
    result = []
    for snapshot in snapshots:
        windows = validated[snapshot.identity.document_id]
        actual_windows = [
            (window.start, window.end, capture) for window, capture, _ in windows
        ]
        try:
            declaration = _envelope_declaration(snapshot.body)
        except ValueError:
            continue
        for production in productions.values():
            node = production["node"]
            features = json.loads(node["feature_json"])
            try:
                relation = _declared_relation(
                    snapshot.body,
                    declaration,
                    [
                        {"start": start, "end": end, "capture": capture}
                        for start, end, capture in actual_windows
                    ],
                    node["scopes"][0]["text"],
                    {"relation": features["relation"]},
                )
            except (ValueError, StopIteration, KeyError):
                continue
            for unit in inventory.units:
                if unit.source != snapshot.identity or not unit.raw.text.strip():
                    continue
                declarations = [
                    row for row in inventory.declarations if row.unit_id == unit.id
                ]
                if declarations:
                    # Actual role/field/reference declarations are never opaque
                    # procedural payload for another production.
                    continue
                try:
                    proof = _unit_copy_proof(
                        snapshot, unit, declaration, relation, actual_windows
                    )
                    result.append(
                        {
                            "node_id": node["id"],
                            "unit_id": unit.id,
                            "source": asdict(unit.source),
                            "raw": asdict(unit.raw),
                            "structural_copy_proof": proof,
                            "authority": "NOT_ASSESSED",
                        }
                    )
                except (ValueError, StopIteration, KeyError, SourceGuardRefusal):
                    continue
    return tuple(result)


_FACTUAL_DECLARATIONS = frozenset(
    {"literal_name", "role_catalogue", "role_assignment", "literal_field"}
)


def _ambiguity_literal(text):
    # A conservative duplicate-risk key only, never source/name equivalence.
    words = text.casefold().split()
    return tuple(words[1:] if words and words[0] in {"a", "an", "the"} else words)


def _declaration_key(row):
    scopes = tuple(_ambiguity_literal(span.text) for span in row.scope)
    if row.kind == "literal_name":
        subject = json.loads(row.payload_json).get("declared_subject", {}).get("text")
        return row.kind, row.source.document_id, _ambiguity_literal(subject or "")
    return (
        row.kind,
        scopes,
        None if row.kind == "role_catalogue" else _ambiguity_literal(row.literal.text),
    )


def _namespace_argument(argument, snapshot, windows):
    if argument.unknowns or argument.qualifiers or argument.quantifiers:
        raise ValueError("Qualified declared namespace remains mandatory")
    for window, _, annotation in windows:
        if (
            not window.start
            <= argument.literal.start
            < argument.literal.end
            <= window.end
        ):
            continue
        tokens = [
            token
            for token in annotation["tokens"]
            if argument.literal.start
            <= window.start + token["start"]
            < window.start + token["end"]
            <= argument.literal.end
        ]
        indices = {token["i"] for token in tokens}
        heads = [token["i"] for token in tokens if token["head"] not in indices]
        if (
            len(heads) != 1
            or heads[0] != argument.head_index
            or not any(token["pos"] == "PROPN" for token in tokens)
        ):
            continue
        articles = {
            token["i"]
            for token in tokens
            if token["dep"] == "det" and token["lemma"].casefold() in {"a", "an", "the"}
        }
        if any(
            token["i"] not in articles
            and (
                token["pos"] not in {"NOUN", "PROPN"}
                or token["i"] != heads[0]
                and token["dep"] != "compound"
            )
            for token in tokens
        ):
            continue
        if (
            snapshot.body[argument.literal.start : argument.literal.end]
            != argument.literal.text
            or tokens[0]["start"] + window.start != argument.literal.start
            or tokens[-1]["end"] + window.start != argument.literal.end
        ):
            continue
        return {
            "argument": asdict(argument),
            "head_index": heads[0],
            "token_indices": sorted(indices),
            "capture_window": {"start": window.start, "end": window.end},
            "status": "EXACT_CAPTURED_NAMED_COMPOUND",
        }
    raise ValueError("Generic or unowned declared namespace remains mandatory")


def _declaration_ownership(row, snapshot, windows, ambiguous):
    if row.kind not in _FACTUAL_DECLARATIONS or _declaration_key(row) in ambiguous:
        raise ValueError("Unknown, ambiguous or opposing declaration remains mandatory")
    if any(
        argument.unknowns
        or argument.quantifiers
        or any(qualifier.kind != "governing_scope" for qualifier in argument.qualifiers)
        for argument in row.arguments
    ):
        raise ValueError("Unassessed declaration argument remains mandatory")
    arguments = []
    if row.kind == "literal_name":
        arguments = [
            argument
            for argument in row.arguments
            if argument.kind == "declared_name" and argument.literal == row.literal
        ]
        if len(arguments) != 1:
            raise ValueError("Actual closed declared-name argument required")
    else:
        if len(row.scope) != 1:
            raise ValueError("One complete named governing scope required")
        arguments = [
            argument
            for argument in row.arguments
            if argument.kind == "governing_scope" and argument.literal == row.scope[0]
        ]
        if len(arguments) != 1:
            raise ValueError("Actual declared scope argument required")
    return {
        "declaration": asdict(row),
        "namespace": _namespace_argument(arguments[0], snapshot, windows),
    }


def _declared_unit_receipt(
    unit, rows, snapshot, windows, ambiguous, productions, complete
):
    record = {
        "source": asdict(unit.source),
        "unit_id": unit.id,
        "raw": asdict(unit.raw),
        "original_unit": asdict(unit),
        "disposition": "mandatory",
        "copy_node_ids": list(productions),
        "remaining_gates": [
            "requested_factual_role_nli_and_output",
            "full_target_alias_inspection",
            "source_authority_and_currentness",
        ],
        "factual_authority": "NOT_ASSESSED",
    }
    metadata = json.loads(snapshot.metadata_json)
    try:
        if not complete or not productions:
            raise ValueError("Actual bounded full-copy request/universe required")
        if (
            metadata.get("condition") is not None
            or metadata.get("conflict_group") is not None
        ):
            raise ValueError("Curated or conditioned source remains mandatory")
        if not unit.raw.text.strip():
            record.update(disposition="syntax_separator", productions=[])
            return record
        features = json.loads(unit.features_json)
        if (
            unit.unknowns
            or not rows
            or any(
                features.get(key)
                for key in (
                    "conditions",
                    "modality",
                    "negation",
                    "references",
                    "governors",
                    "quantifiers",
                    "unbound_condition_markers",
                )
            )
        ):
            raise ValueError(
                "Unknown/global/qualified/reference-bearing source remains mandatory"
            )
        proofs = [
            _declaration_ownership(row, snapshot, windows, ambiguous) for row in rows
        ]
        record.update(
            disposition="separately_owned_declared_factual_production",
            productions=proofs,
            scope_meaning="SAME_OR_OTHER_NAMESPACE_COPY_OBLIGATIONS_ONLY",
        )
    except ValueError as exc:
        record["reason"] = str(exc)
    return record


def declared_copy_ownership(partial, manifest, snapshots, captures, *, inventory=None):
    """Single actual per-unit COPY-only authority; no source/answer approval.

    Complete source/capture/read-set and target-alias ledgers remain mandatory.
    Declared factual productions can own copy obligations in the same namespace;
    their factual values still need any independently requested NLI and output.
    """
    from .staged_request import compile_request

    if partial != compile_request(
        partial.question, json.loads(partial.raw_capture_json)
    ):
        raise ValueError("Actual original partial request required")
    actual = source.declaration_inventory(manifest, snapshots, captures)
    if inventory is not None and source.canonical(
        inventory.record()
    ) != source.canonical(actual.record()):
        raise ValueError(
            "Declared-production inventory differs from full actual inputs"
        )
    _, validated = source._inputs(manifest, snapshots, captures)
    productions = request_productions(partial)
    counts = {}
    for row in actual.declarations:
        if row.kind in _FACTUAL_DECLARATIONS:
            key = _declaration_key(row)
            counts[key] = counts.get(key, 0) + 1
    ambiguous = {key for key, count in counts.items() if count > 1}
    universe_scope = json.loads(manifest.scope_json)
    complete = (
        manifest.selection_mode == "bounded_authorized_scan"
        and not actual.read_set.missing_publications
        and universe_scope.get("complete", True) is True
    )
    sources = []
    for snapshot in snapshots:
        units = [
            _declared_unit_receipt(
                unit,
                [row for row in actual.declarations if row.unit_id == unit.id],
                snapshot,
                validated[snapshot.identity.document_id],
                ambiguous,
                productions,
                complete,
            )
            for unit in actual.units
            if unit.source == snapshot.identity
        ]
        sources.append(
            {
                "identity": asdict(snapshot.identity),
                "units": units,
                "copy_ownership_complete": any(
                    unit["disposition"]
                    == "separately_owned_declared_factual_production"
                    for unit in units
                )
                and all(unit["disposition"] != "mandatory" for unit in units),
            }
        )
    return json.loads(
        source.canonical(
            {
                "contract": "captured-declared-production-copy-ownership-v1",
                "partial_request_sha256": source.digest(partial.record()),
                "inventory_sha256": source.digest(actual.record()),
                "read_set": actual.read_set.record(),
                "copy_productions": productions,
                "sources": sources,
                "authority_support_publication": "NOT_ASSESSED",
                "target_alias_inspection": "REQUIRED_SEPARATELY",
                "full_world_procedure_completeness": "NOT_ASSERTED",
            }
        )
    )
