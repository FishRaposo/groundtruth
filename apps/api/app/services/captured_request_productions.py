"""Capture-preserving request production transport over the historical compiler."""

import json
from dataclasses import asdict

from app.services import request_grammar as grammar
from app.services.captured_production_policy import REQUEST_CONTRACT, selected_version
from app.services.request_obligations import canonical
from app.services.request_parser import _native, validate_capture
from app.services.staged_request import compile_request


def _require(value, message):
    if not value:
        raise ValueError(message)


def _span(graph, indices):
    return asdict(grammar.literal(graph.span(indices)))


def _nominal_governor(graph):
    roots = [token["i"] for token in graph.ts if token["dep"] == "ROOT"]
    _require(len(roots) == 1, "One captured nominal sentence/root required")
    head = roots[0]
    _require(graph.ts[head]["pos"] == "NOUN", "Captured nominal root required")
    nominal = graph.nominal(head)
    _require(
        graph.lemma(head) in {"label", "holder", "incumbent"}
        and any(
            graph.lemma(i) == "role" and graph.ts[i]["dep"] == "compound"
            for i in nominal
        ),
        "An existing explicitly modified role field is required",
    )
    candidates = [
        i
        for i in graph.children[head]
        if graph.lemma(i) in grammar.META
        and graph.ts[i]["pos"] == "NOUN"
        and graph.ts[i]["dep"] == "compound"
    ]
    _require(len(candidates) == 1, "A unique nominal request governor is required")
    operator = candidates[0]
    significant = [t["i"] for t in graph.ts if t["pos"] != "PUNCT"]
    _require(operator == min(significant), "The governor must lead its sentence")
    _require(not graph.children[operator], "Qualified request governor is unresolved")
    _require(
        all(
            graph.lemma(i) == "role"
            and graph.ts[i]["dep"] == "compound"
            or graph.low(i) in {"a", "an", "the"}
            and graph.ts[i]["dep"] == "det"
            for i in nominal - {head, operator}
        ),
        "Unrepresented nominal field semantics remain unresolved",
    )
    scopes = graph.direct_scopes(head)
    _require(len(scopes) == 1, "One complete governing scope is required")
    scope, covered = scopes[0]
    scope_head = [i for i in scope if graph.ts[i]["head"] not in scope]
    _require(len(scope_head) == 1, "One captured scope head is required")
    closure = grammar.qualified_argument(graph, scope_head[0])
    _require(
        not closure["unclassified"], "Unclosed scope attachment remains unresolved"
    )
    _require(
        all(
            graph.ts[i]["pos"] in {"NOUN", "PROPN"}
            and graph.ts[i]["dep"] in {"compound", "pobj"}
            or graph.ts[i]["dep"] == "det"
            and graph.low(i) in {"a", "an", "the"}
            for i in scope
        ),
        "Qualified scope semantics remain unresolved",
    )
    owned = nominal | set(covered)
    punctuation = {
        t["i"] for t in graph.ts if t["dep"] == "punct" and t["head"] == head
    }
    _require(
        owned | punctuation == set(range(len(graph.ts))),
        "Unrepresented sentence attachment remains unresolved",
    )
    features = json.loads(grammar.features(graph, set(range(len(graph.ts)))))
    _require(
        not any(
            features[key]
            for key in (
                "condition_ast",
                "modality",
                "units",
                "references",
                "negation",
                "quantifiers",
                "governors",
            )
        ),
        "Request qualifiers and references require independent representation",
    )
    return {
        "kind": "role_catalogue",
        "operation": "labels_only" if graph.lemma(head) == "label" else "incumbents",
        "head_indices": [head],
        "token_indices": sorted(owned | punctuation),
        "evidence": [_span(graph, range(len(graph.ts)))],
        "semantic_argument": _span(graph, nominal - {operator}),
        "scopes": [_span(graph, scope)],
        "scope_closure": closure,
        "governor": {
            "registry": "dependency_frames.META",
            "lemma": graph.lemma(operator),
            "token_indices": [operator],
            "evidence": _span(graph, {operator}),
            "original_token": graph.ts[operator],
            "meaning": "REQUEST_OPERATOR_PRODUCTION_ONLY",
        },
        "features": features,
        "consumption": [
            {
                "token": _span(graph, {i}),
                "whitespace": graph.ts[i]["whitespace"],
                "role": "request_governor"
                if i == operator
                else "request_field"
                if i in nominal
                else "scope_argument"
                if i in scope
                else "scope_operator"
                if i in covered
                else "syntax_punctuation",
            }
            for i in range(len(graph.ts))
        ],
    }


def reconstruct_request_productions(question, capture, *, reading_profile=None):
    """Reconstruct supplemental syntax; preserve the complete historical partial."""
    version = selected_version(reading_profile)
    original = canonical(capture)
    annotation = validate_capture(question, capture)
    partial = compile_request(question, capture)
    record = {
        "contract": REQUEST_CONTRACT,
        "reading_profile": reading_profile,
        "source_production_contract": version.source_productions if version else None,
        "policy_enabled": version is not None,
        "question": question,
        "original_capture": json.loads(canonical(capture)),
        "historical_partial": partial.record(),
        "productions": [],
        "remaining_semantics": [],
        "complete_plan": False,
        "source_NI_authority_currentness": "NOT_ASSESSED",
    }
    if version is not None:
        try:
            record["productions"] = [
                _nominal_governor(grammar.Graph(question, annotation))
            ]
        except ValueError as exc:
            record["remaining_semantics"] = [str(exc)]
    _require(
        canonical(capture) == original, "Captured input changed during reconstruction"
    )
    return json.loads(canonical(record))


def validate_request_productions(record, question, capture, *, reading_profile=None):
    try:
        _native(record)
        return canonical(record) == canonical(
            reconstruct_request_productions(
                question, capture, reading_profile=reading_profile
            )
        )
    except (ValueError, TypeError, KeyError, IndexError, RecursionError):
        return False
