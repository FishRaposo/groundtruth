"""Captured v3 whole-copy content selectors, without facet-existence claims."""

import json

from app.evidence_policy import reading_version, staged_reading_profile
from app.services.dependency_frames import (
    GOVERNORS,
    Graph,
    _local_procedure_reference,
    _nominal_governor_list,
    resolve_frames,
)


def _require(value, message):
    if not value:
        raise ValueError(message)


def _ranges(spans):
    return [{"start": span.start, "end": span.end, "text": span.text} for span in spans]


def _operator(graph, head, frame):
    seen = set()
    while head not in seen:
        seen.add(head)
        token = graph.ts[head]
        if (
            graph.lemma(head) in {"include", "with", "preserve", "retain"}
            and token["dep"] in {"prep", "advcl"}
            and token["head"] in frame.heads
        ):
            return head
        head = token["head"]
    raise ValueError("Copy-facet selector has no captured owning operator")


def _hyphenated_modifier(graph, index):
    token = graph.ts[index]
    parent = token["head"]
    if parent != index + 2 or parent >= len(graph.ts):
        return False
    noun, hyphen = graph.ts[parent], graph.ts[index + 1]
    return (
        noun["pos"] == "NOUN"
        and noun["dep"] == "compound"
        and hyphen["text"] == "-"
        and hyphen["dep"] == "punct"
        and hyphen["head"] == parent
        and graph.raw[token["end"] : noun["start"]] == "-"
    )


def _content_token(graph, index, heads, operators, frame):
    token = graph.ts[index]
    if index in heads:
        return (
            token["dep"] in {"pobj", "dobj", "obj"}
            and token["head"] in operators
            or token["dep"] == "conj"
            and token["head"] in heads
        )
    if token["dep"] in {"compound", "amod"} and token["pos"] in {"NOUN", "ADJ"}:
        if token["dep"] == "amod" and not _hyphenated_modifier(graph, index):
            return False
        at, seen = index, set()
        while at not in seen and graph.ts[at]["dep"] in {"compound", "amod"}:
            seen.add(at)
            at = graph.ts[at]["head"]
        return at in heads
    return (
        token["pos"] == "PRON"
        and _local_procedure_reference(graph, frame, index)
        or token["dep"] == "det"
        and graph.lemma(index) in {"all", "a", "an", "the"}
        and token["head"] in heads
        or token["dep"] == "cc"
        and graph.lemma(index) == "and"
        and token["head"] in heads
        or token["dep"] == "punct"
        and token["text"] in {",", "-"}
    )


def reconstruct_copy_facets(
    plan, requirement, use, full, *, reading_profile="contextual_source_v3"
):
    """Original graph/frames, every original selector/reference and output gate."""
    _require(
        staged_reading_profile(reading_profile)
        and plan.get("contract") == reading_version(reading_profile).request_plan
        and plan.get("reading_profile") == reading_profile,
        "Explicit actual v3 request required",
    )
    _require(
        requirement["kind"] == "procedure"
        and use["extent"] == "whole_requested"
        and use["governors"],
        "Whole requested copy with actual selectors required",
    )
    _require(
        not any(
            use.get(key) for key in ("modality", "units", "condition_ast", "negation")
        ),
        "Qualified copy-facet semantics remain unresolved",
    )
    annotation = json.loads(plan["graph_json"])
    graph = Graph(plan["question"], annotation)
    frames, _ = resolve_frames(plan["question"], annotation)
    matches = [
        frame
        for frame in frames
        if frame.kind == "procedure"
        and not frame.errors
        and frame.heads == tuple(use["head_token_indices"])
        and frame.tokens == tuple(use["consumed_token_indices"])
        and _ranges(frame.governors) == list(use["governors"])
        and _ranges(frame.references) == list(use["references"])
        and frame.topic == requirement["topic"]
        and frame.relation == requirement["relation"]
    ]
    _require(
        len(matches) == 1 and not matches[0].dependencies,
        "Actual closed original procedure selector production required",
    )
    frame = matches[0]
    owned = set()
    for span in use["governors"]:
        selected = [
            token
            for token in graph.ts
            if span["start"] <= token["start"] < token["end"] <= span["end"]
        ]
        _require(
            selected
            and selected[0]["start"] == span["start"]
            and selected[-1]["end"] == span["end"]
            and plan["question"][span["start"] : span["end"]] == span["text"],
            "Every complete original facet interval required",
        )
        owned.update(token["i"] for token in selected)
    heads = {
        index
        for index in owned
        if graph.ts[index]["pos"] == "NOUN" and graph.lemma(index) in GOVERNORS
    }
    _require(heads, "Existing recognized source-content heads required")
    operators = {_operator(graph, head, frame) for head in heads}
    content = owned - operators
    _require(
        _nominal_governor_list(graph, content)
        and all(
            _content_token(graph, index, heads, operators, frame) for index in content
        ),
        "Unknown facet modifier/attachment/reference/quantity remains unresolved",
    )
    references = []
    for span in use["references"]:
        tokens = [
            token
            for token in graph.ts
            if span["start"] <= token["start"] < token["end"] <= span["end"]
        ]
        _require(
            len(tokens) == 1
            and tokens[0]["i"] in content
            and _local_procedure_reference(graph, frame, tokens[0]["i"]),
            "Facet reference has no unique actual procedure antecedent",
        )
        references.append(
            {
                "request_range": span,
                "antecedent_head_indices": list(frame.heads),
                "method": "existing_captured_local_procedure_reference",
            }
        )
    ownership = {
        "contract": "captured-whole-copy-facets-v1",
        "head_token_indices": sorted(heads),
        "selector_token_indices": sorted(content),
        "operator_token_indices": sorted(operators),
        "reference_bindings": references,
        "facet_existence": "NOT_ASSERTED",
        "mandatory_gate": "complete_source_inventory_and_literal_output",
    }
    return [
        {
            "kind": "governors",
            "request_range": span,
            "method": "whole_literal_source_retention",
            "source_range": dict(full) if full is not None else None,
            "meaning": "retain_all_source_declared_content_without_asserting_existence",
            "copy_facet_ownership": ownership,
        }
        for span in use["governors"]
    ]
