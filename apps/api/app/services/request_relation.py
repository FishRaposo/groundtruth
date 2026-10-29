"""Own every actual request-argument component before proposing a relation.

Closed literal scope names retain all their bytes. Material not represented by
the initial operation/scope production stays unresolved; raw JSON is not NLI.
"""

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass

from app.services.dependency_frames import SCOPE_PREPS, Graph
from app.services.request_parser import validate_capture

from .request_grammar import operator, qualified_argument
from .staged_request import compile_request


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


@dataclass(frozen=True)
class RequestRelationClosure:
    node_id: str
    head_indices: tuple[int, ...]
    argument_ast_json: str
    scope_ast_json: str
    ownership_json: str
    operator_context_json: str
    unresolved_json: str
    status: str


def request_relation_closures(
    question: str, capture: dict, nodes: Sequence[dict]
) -> tuple[RequestRelationClosure, ...]:
    g = Graph(question, validate_capture(question, capture))
    delegated = _captured_delegations(question, capture, nodes, g)
    result = []
    for node in nodes:
        heads = node["head_indices"]
        unresolved = []
        scope_records = []
        ownership = []
        context = []
        if node["id"] in delegated:
            result.append(_dependent_closure(node, delegated[node["id"]]))
            continue
        if node["kind"] != "role_catalogue" or len(heads) != 1:
            result.append(
                RequestRelationClosure(
                    node["id"],
                    tuple(heads),
                    "{}",
                    "[]",
                    "[]",
                    "[]",
                    canonical(
                        [
                            {
                                "reason": "request_node_relation_not_supported",
                                "node_kind": node["kind"],
                            }
                        ]
                    ),
                    "UNRESOLVED",
                )
            )
            continue
        head = heads[0]
        argument = qualified_argument(g, head)
        op = operator(g, head)
        represented = {head}
        scope_owned = set()
        scope_links = set()
        articles = set()
        # These are the actual compiler's semantic head/nucleus productions,
        # not a catalogue of business roles or a modifier-word exclusion list.
        if g.lemma(head) not in {"role", "label", "holder", "incumbent"}:
            unresolved.append(
                {"reason": "unsupported_operation_head", "token_indices": [head]}
            )
        role_markers = [
            i
            for i in g.nominal(head)
            if i != head
            and g.lemma(i) == "role"
            and g.ts[i]["pos"] == "NOUN"
            and g.ts[i]["dep"] == "compound"
        ]
        if g.lemma(head) != "role" and len(role_markers) != 1:
            unresolved.append(
                {
                    "reason": "operation_nucleus_not_unique",
                    "token_indices": role_markers,
                }
            )
        represented.update(role_markers)
        scope_records, scope_owned, scope_links = _scope_ownership(
            g, question, node, head, op, unresolved
        )
        for i in argument["token_indices"]:
            if (
                g.ts[i]["dep"] == "det"
                and g.low(i) in {"a", "an", "the"}
                and g.ts[i]["head"] in represented
            ):
                articles.add(i)
        ownership = _argument_ownership(
            g,
            argument,
            represented,
            scope_owned,
            scope_links,
            articles,
            unresolved,
            tuple(row for row in delegated.values() if row["parent_id"] == node["id"]),
        )
        context = _operator_context(
            g, op, node, argument, scope_owned, scope_links, unresolved
        )
        result.append(
            RequestRelationClosure(
                node["id"],
                tuple(heads),
                canonical(argument),
                canonical(scope_records),
                canonical(ownership),
                canonical(context),
                canonical(unresolved),
                "UNRESOLVED" if unresolved else "EXACT_INITIAL_RELATION",
            )
        )
    return tuple(result)


def _literal(g, ids):
    span = g.span(ids)
    return {"start": span.start, "end": span.end, "text": span.text}


def _captured_delegations(question, capture, nodes, g: Graph) -> dict[str, dict]:
    """Only an independently retained actual compiler edge can own a child."""
    partial = compile_request(question, capture)
    actual = tuple(asdict(node) for node in partial.nodes)
    if canonical(actual) != canonical(tuple(nodes)):
        return {}
    by_id = {node["id"]: node for node in actual}
    result = {}
    for edge in partial.edges:
        if edge.kind != "catalogue_member_value":
            continue
        incoming = [row for row in partial.edges if row.target_id == edge.target_id]
        if len(incoming) != 1:
            continue
        proof = _dependent_child(
            g, question, by_id[edge.source_id], by_id[edge.target_id], asdict(edge)
        )
        if proof is not None:
            result[edge.target_id] = proof
    return result


def _dependent_child(g: Graph, question, parent: dict, child: dict, edge: dict):
    if (
        parent["kind"] != "role_catalogue"
        or parent["operation"] != "incumbents"
        or child["kind"] != "availability"
        or child["operation"] != "request_field_value"
        or len(parent["head_indices"]) != 1
        or len(parent["scopes"]) != 1
        or canonical(child["scopes"]) != canonical(parent["scopes"])
    ):
        return None
    head = parent["head_indices"][0]
    child_heads = [
        i
        for i in child["head_indices"]
        if g.ts[i]["dep"] == "conj" and g.ts[i]["head"] == head
    ]
    if len(child_heads) != 1 or set(child["head_indices"]) != {
        operator(g, head),
        child_heads[0],
    }:
        return None
    child_head = child_heads[0]
    features = json.loads(child["feature_json"])
    qualified = (
        "condition_ast",
        "modality",
        "negation",
        "units",
        "governors",
        "order",
        "quantifiers",
        "ownership_context_pending",
    )
    if any(features.get(key) for key in qualified) or canonical(
        features.get("references", [])
    ) != canonical(edge["evidence"]):
        return None
    if (
        g.ts[child_head]["dep"] != "conj"
        or g.ts[child_head]["head"] != head
        or operator(g, head) != operator(g, child_head)
    ):
        return None
    unknown = []
    scopes, scope_ids, links = _scope_ownership(
        g, question, parent, head, operator(g, head), unknown
    )
    argument = qualified_argument(g, child_head)
    refs = {
        token["i"]
        for token in g.ts
        for span in edge["evidence"]
        if span["start"] <= token["start"] < token["end"] <= span["end"]
    }
    child_ids = g.subtree(child_head)
    child_unknown = any(
        row["reason"] != "nominal_conjunction_requires_split"
        or row["token_indices"] != [child_head]
        for row in argument["unclassified"]
    )
    if (
        unknown
        or child_unknown
        or g.ts[child_head]["pos"] != "NOUN"
        or child_ids != refs | {child_head}
        or len(refs) != 1
    ):
        return None
    if not all(
        g.ts[i]["dep"] == "poss" and g.ts[i]["head"] == child_head and not g.children[i]
        for i in refs
    ):
        return None
    coordinators = {
        i
        for i in g.children[head]
        if g.ts[i]["dep"] == "cc"
        and g.ts[i]["pos"] == "CCONJ"
        and g.lemma(i) == "and"
        and not g.children[i]
    }
    if (
        len(coordinators) != 1
        or set(child["token_indices"]) != child_ids | scope_ids | links
    ):
        return None
    delegated = child_ids | coordinators
    if set(parent["token_indices"]) != g.subtree(head) - delegated:
        return None
    return {
        "parent_id": parent["id"],
        "child_id": child["id"],
        "child_head": child_head,
        "edge": edge,
        "argument": argument,
        "scope_records": scopes,
        "token_indices": sorted(delegated),
        "parent_argument_indices": sorted(g.subtree(head)),
    }


def _dependent_closure(node: dict, proof: dict) -> RequestRelationClosure:
    return RequestRelationClosure(
        node["id"],
        tuple(node["head_indices"]),
        canonical(proof["argument"]),
        canonical(proof["scope_records"]),
        canonical(
            [
                {
                    "owner": "actual_retained_dependency_argument",
                    "component": component,
                    "retained_edge": proof["edge"],
                }
                for component in proof["argument"]["components"]
            ]
        ),
        canonical(
            [
                {
                    "owner": "actual_retained_parent_argument",
                    "parent_node_id": proof["parent_id"],
                    "token_indices": proof["parent_argument_indices"],
                    "retained_edge": proof["edge"],
                }
            ]
        ),
        "[]",
        "EXACT_INITIAL_RELATION",
    )


def _scope_ownership(
    g: Graph,
    question: str,
    node: dict,
    head: int,
    op: int | None,
    unresolved: list[dict],
) -> tuple[list[dict], set[int], set[int]]:
    scope_records = []
    scope_owned = set()
    scope_links = set()
    for scope in node["scopes"]:
        ids = {
            t["i"]
            for t in g.ts
            if scope["start"] <= t["start"] and t["end"] <= scope["end"]
        }
        scope_heads = [i for i in ids if g.ts[i]["head"] not in ids]
        record = {
            "literal": scope,
            "token_indices": sorted(ids),
            "head_indices": scope_heads,
            "argument_ast": None,
        }
        literal_closed = (
            bool(ids)
            and question[scope["start"] : scope["end"]] == scope["text"]
            and g.ts[min(ids)]["start"] == scope["start"]
            and g.ts[max(ids)]["end"] == scope["end"]
            and len(scope_heads) == 1
        )
        if literal_closed:
            scope_head = scope_heads[0]
            closure = qualified_argument(g, scope_head)
            record["argument_ast"] = closure
            literal_closed = (
                set(closure["token_indices"]) == ids and not closure["unclassified"]
            )
            prep = g.ts[scope_head]["head"]
            linked = (
                g.ts[prep]["dep"] == "prep"
                and g.low(prep) in SCOPE_PREPS
                and g.ts[prep]["head"] in {head, op}
                and set(g.children[prep]) == {scope_head}
            )
            if linked:
                scope_links.add(prep)
            else:
                unresolved.append(
                    {"reason": "scope_link_not_closed", "token_indices": [prep]}
                )
        if literal_closed:
            scope_owned.update(ids)
        else:
            unresolved.append(
                {
                    "reason": "scope_argument_not_fully_literalized",
                    "token_indices": sorted(ids),
                }
            )
        scope_records.append(record)
    return scope_records, scope_owned, scope_links


def _argument_ownership(
    g: Graph,
    argument: dict,
    represented: set[int],
    scope_owned: set[int],
    scope_links: set[int],
    articles: set[int],
    unresolved: list[dict],
    delegated: tuple[dict, ...] = (),
) -> list[dict]:
    ownership = []
    consumed = represented | scope_owned | scope_links | articles
    delegated_ids = {i for row in delegated for i in row["token_indices"]}
    delegated_heads = {row["child_head"] for row in delegated}
    consumed |= delegated_ids
    for component in argument["components"]:
        ids = set(component["token_indices"])
        owner = (
            "literal_scope"
            if ids <= scope_owned
            else "operation_nucleus"
            if ids <= represented
            else "scope_link"
            if ids <= scope_links
            else "article_syntax"
            if ids <= articles
            else "actual_retained_dependent_child"
            if ids <= delegated_ids
            else "UNREPRESENTED"
        )
        ownership.append({"owner": owner, "component": component})
        if owner == "actual_retained_dependent_child":
            ownership[-1]["retained_children"] = [
                {
                    "node_id": row["child_id"],
                    "edge": row["edge"],
                    "token_indices": row["token_indices"],
                }
                for row in delegated
                if ids <= set(row["token_indices"])
            ]
        if owner == "UNREPRESENTED":
            unresolved.append(
                {
                    "reason": "unrepresented_request_argument_component",
                    "component": component,
                }
            )
    unresolved.extend(
        {"reason": "unclosed_request_argument_ast", "detail": row}
        for row in argument["unclassified"]
        if not (
            row["reason"] == "nominal_conjunction_requires_split"
            and set(row["token_indices"]) <= delegated_heads
        )
    )
    if set(argument["token_indices"]) - consumed:
        unresolved.append(
            {
                "reason": "unconsumed_request_argument",
                "token_indices": sorted(set(argument["token_indices"]) - consumed),
            }
        )
    return ownership


def _operator_context(
    g: Graph,
    op: int | None,
    node: dict,
    argument: dict,
    scope_owned: set[int],
    scope_links: set[int],
    unresolved: list[dict],
) -> list[dict]:
    context = []
    if op is None:
        unresolved.append(
            {"reason": "request_operator_not_closed", "token_indices": []}
        )
    else:
        for child in g.children[op]:
            ids = g.subtree(child)
            token = g.ts[child]
            if ids <= set(argument["token_indices"]):
                owner = "owned_argument"
            elif ids <= scope_owned | scope_links:
                owner = "shared_literal_scope"
            elif token["dep"] == "punct" and token["pos"] == "PUNCT" and ids == {child}:
                owner = "operator_punctuation"
            elif (
                token["dep"] in {"aux", "auxpass"}
                and token["tag"] != "MD"
                and ids == {child}
            ):
                owner = "operator_syntax"
            elif (
                node["operation"] == "incumbents"
                and g.low(child) == "who"
                and token["dep"] in {"nsubj", "dobj", "attr"}
                and ids == {child}
            ):
                owner = "incumbent_wh_operator"
            else:
                owner = "UNREPRESENTED"
                unresolved.append(
                    {
                        "reason": "unrepresented_request_operator_component",
                        "token_indices": sorted(ids),
                    }
                )
            context.append(
                {
                    "owner": owner,
                    "token_indices": sorted(ids),
                    "evidence": _literal(g, ids),
                }
            )
    return context
