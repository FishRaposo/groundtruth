"""Pure complete dependency closure for curated source exclusion candidates.

Actual captured syntax is a proposal. Closed syntax does not establish truth,
scope semantics, authorization, parser execution, or factual support.
"""

import re
from copy import deepcopy

from app.services import requirement_binding as _binding
from app.services.contextual_output import _same
from app.services.linguistic_source_scope import (
    _boundary_clear,
    _cuts,
    _Graph,
    _identity,
    _regions,
    _windows,
)
from app.services.requirement_binding import condition_relation, relation_present
from app.services.requirement_conflict_scope import source_relation_scope

CONTRACT = "captured-curated-source-closure-v1"
CAPTURE_CONTRACT = "curated-immutable-source-capture-v1"
_SUBJECT = {"nsubj", "nsubjpass", "csubj", "csubjpass"}


def source_identity(snapshot):
    return {
        k: snapshot.get(k)
        for k in ("document_id", "document_version", "content_hash", "workspace_id")
    }


def captured_units(snapshot, source_windows):
    """Validate whole immutable-body windows before yielding any graph unit."""
    body = snapshot["body"]
    _identity(
        body, {k: v for k, v in source_identity(snapshot).items() if v is not None}
    )
    windows = _windows(body, source_windows)
    regions = _regions(body)
    record = {
        "contract": CAPTURE_CONTRACT,
        "source_identity": source_identity(snapshot),
        "source_range": {"start": 0, "end": len(body)},
        "source_windows": deepcopy(source_windows),
    }
    units = []
    for first, last in _cuts(body, windows, regions):
        literal = {"start": first, "end": last, "text": body[first:last]}
        if not body[first:last].strip():
            units.append((None, literal, "separator"))
            continue
        start, _, annotation, _ = next(
            w for w in windows if w[0] <= first < last <= w[1]
        )
        graph = _Graph(body, start, annotation, first, last)
        uncertainty = next(
            (kind for left, right, kind in regions if first < right and left < last),
            None,
        )
        window = next(w for w in windows if w[0] <= first < last <= w[1])
        raw_window = body[window[0] : window[1]]
        first_content = window[0] + len(raw_window) - len(raw_window.lstrip())
        last_content = window[1] - len(raw_window) + len(raw_window.rstrip())
        if (first == first_content and not _boundary_clear(body, window[0])) or (
            last == last_content and not _boundary_clear(body, window[1])
        ):
            uncertainty = "unclosed_capture_boundary"
        # A window or unit cut cannot silently remove a non-punctuation parent.
        if any(
            graph.tokens[i]["head"] not in graph.indices
            and graph.tokens[i]["head"] != i
            for i in graph.indices
        ):
            uncertainty = "unclosed_capture_or_unit_edge"
        units.append((graph, literal, uncertainty))
    return record, units


def capture_inventory(record, snapshots):
    expected = {row["document_id"] for row in record["inspection_sources"]}
    captures = {}
    for row in record["source_scope_decisions"]:
        cap = row["source_capture"]
        identifier = cap["source_identity"]["document_id"]
        if identifier in captures or identifier not in expected:
            raise ValueError("Curated source capture inventory duplicated/unbound")
        canonical, _ = captured_units(snapshots[identifier], cap["source_windows"])
        _same(cap, canonical, "Curated capture differs from actual immutable source")
        captures[identifier] = cap["source_windows"]
    if set(captures) != expected:
        raise ValueError("Complete all-member curated source captures required")
    return captures


def recorded_capture_inventory(records, requirements, snapshots, factual_contract):
    """Validate all repeated source captures before any relevance filtering."""
    observed = {}
    for record in records:
        if requirements[record["requirement_id"]].kind == "procedure":
            continue
        if record.get("inspection_method") != factual_contract:
            raise ValueError("Uncaptured curated inspection cannot certify v3")
        for identifier, windows in capture_inventory(record, snapshots).items():
            if identifier in observed:
                _same(
                    windows,
                    observed[identifier],
                    "Curated captures differ across groups",
                )
            observed[identifier] = windows
    return observed


def closed_nominal(graph, head, *, allow_numeric_head=False):
    """Consume one entire positively typed nominal subtree, never a text span."""
    heads = {"NOUN", "PROPN"} | ({"NUM"} if allow_numeric_head else set())
    if graph.tokens[head]["pos"] not in heads:
        return None
    used, todo = set(), [head]
    while todo:
        at = todo.pop()
        used.add(at)
        for child in graph.children(at):
            token = graph.tokens[child]
            dep, pos = token["dep"], token["pos"]
            if pos == "PUNCT":
                used.add(child)
            elif (
                dep == "det"
                and pos == "DET"
                or dep in {"compound", "nmod", "poss"}
                and pos in {"NOUN", "PROPN"}
                or dep == "amod"
                and pos == "ADJ"
                or dep == "nummod"
                and pos == "NUM"
                or dep == "case"
                and pos in {"ADP", "PART"}
            ):
                todo.append(child)
            else:
                return None
    return used if graph.subtree(head) == used else None


def consume_clause(graph, used_indices):
    """Return exact token/edge ownership; unowned meaningful tokens never close."""
    if not set(used_indices) <= graph.indices:
        raise ValueError("Clause consumption names unbound token indices")
    punctuation = {i for i in graph.indices if graph.tokens[i]["pos"] == "PUNCT"}
    used = set(used_indices) | punctuation
    residual = graph.indices - used
    edges = {
        (i, graph.tokens[i]["head"])
        for i in graph.indices
        if graph.tokens[i]["head"] != i
    }
    consumed_edges = {(i, head) for i, head in edges if i in used and head in used}
    residual_edges = edges - consumed_edges
    return {
        "contract": CONTRACT,
        "consumed_token_indices": sorted(used & graph.indices),
        "residual_token_indices": sorted(residual),
        "consumed_edges": [list(edge) for edge in sorted(consumed_edges)],
        "residual_edges": [list(edge) for edge in sorted(residual_edges)],
        "complete": not residual and not residual_edges,
    }


def _simple_role(graph):
    roots = [i for i in graph.indices if graph.tokens[i]["head"] == i]
    if len(roots) != 1 or graph.tokens[roots[0]]["pos"] not in {"VERB", "AUX"}:
        return None
    root = roots[0]
    subjects = graph.children(root, _SUBJECT)
    objects = graph.children(root, {"dobj", "attr"})
    if len(subjects) != 1 or len(objects) != 1:
        return None
    subject, obj = closed_nominal(graph, subjects[0]), closed_nominal(graph, objects[0])
    if subject is None or obj is None:
        return None
    proof = consume_clause(graph, {root} | subject | obj)
    return proof if proof["complete"] else None


def _temporal(graph, literal, candidate):
    if candidate is None:
        return None
    roots = [i for i in graph.indices if graph.tokens[i]["head"] == i]
    if len(roots) != 1 or graph.tokens[roots[0]]["pos"] != "VERB":
        return None
    root = roots[0]
    subjects = graph.children(root, {"nsubj"})
    if len(subjects) != 1:
        return None
    subject = closed_nominal(graph, subjects[0])
    if subject is None or graph.span(subject)["text"].strip() != candidate["subject"]:
        return None
    first = literal["start"] + candidate["value_range"]["start"]
    last = literal["start"] + candidate["value_range"]["end"]
    values = {
        i
        for i in graph.indices
        if first <= graph.offset + graph.tokens[i]["start"]
        and graph.offset + graph.tokens[i]["end"] <= last
    }
    heads = [i for i in values if graph.tokens[i]["head"] not in values]
    if len(heads) != 1:
        return None
    nominal = closed_nominal(graph, heads[0], allow_numeric_head=True)
    if nominal != values:
        return None
    used = {root} | subject | values
    parent = graph.tokens[heads[0]]["head"]
    if parent != root:
        if (
            parent not in graph.children(root, {"prep"})
            or graph.tokens[parent]["pos"] != "ADP"
            or graph.tokens[heads[0]]["dep"] != "pobj"
        ):
            return None
        used.add(parent)
    elif graph.tokens[heads[0]]["dep"] not in {"dobj", "npadvmod"}:
        return None
    proof = consume_clause(graph, used)
    return {**candidate, "dependency_closure": proof} if proof["complete"] else None


_DECLARATION_LEMMAS = {"apply", "govern"}


def _scope_nominal(graph, head):
    """Nominal subtree plus literal of-complements and appositives."""
    ids = set(graph.nominal(head))
    for p, obj in graph.pp(head, {"of"}):
        ids.add(p)
        ids |= _scope_nominal(graph, obj)
    appos = [c for i in list(ids) for c in graph.children(i, {"appos"})]
    for c in appos:
        ids.add(c)
        ids |= _scope_nominal(graph, c)
    return ids


def _declaration_scope_text(graph, nominal_ids):
    return graph.span(nominal_ids)["text"].strip().strip(",;:.")


def _declared_scope(graph, literal, requirement):
    """Literal whole-unit scope declarations.

    "For <scope>, ..." declares the entire unit under that scope; "<ref>
    applies only to <scope>" / "<ref> does not govern <scope>" are the unit's
    own scope declarations. A positive declaration naming the requested scope
    keeps the unit; an ambiguous scope stays unclassified.
    """
    roots = [
        i
        for i in graph.indices
        if graph.tokens[i]["head"] == i and graph.tokens[i]["pos"] in {"VERB", "AUX"}
    ]
    if len(roots) != 1:
        return None
    root = roots[0]
    for p, obj in graph.pp(root, {"for"}):
        left = graph.offset + graph.tokens[p]["start"]
        if graph.body[literal["start"] : left].strip():
            continue
        scope = _declaration_scope_text(graph, _scope_nominal(graph, obj))
        if _binding._scope_target(requirement, scope) == "irrelevant":
            used = {p} | _scope_nominal(graph, obj)
            return "declared_foreign_scope", consume_clause(graph, used)
        return None
    verbs = [
        i
        for i in graph.indices
        if graph.lemma(i) in _DECLARATION_LEMMAS and graph.tokens[i]["pos"] == "VERB"
    ]
    if not verbs:
        return None
    used, grants = set(), 0
    for verb in verbs:
        result = _declaration_verb(graph, verb, set(verbs), requirement)
        if result is None:
            return None
        grant, additions = result
        grants += grant
        used |= additions
    if not grants:
        return None
    used |= set().union(*(graph.nominal(c) for c in graph.children(root, _SUBJECT)))
    proof = consume_clause(graph, used)
    return ("declared_scope_exclusion", proof) if proof["complete"] else None


def _declaration_verb(graph, verb, verbs, requirement):
    """One apply/govern declaration: (exclusion grant, consumed tokens).

    A positive declaration naming the requested scope blocks the whole unit
    exclusion (None); an unknown scope is conservative (None); a denial of a
    foreign scope carries no applicability information (grant 0).
    """
    head = graph.tokens[verb]["head"]
    if head != verb and head not in verbs:
        return None
    negated = any(graph.tokens[c]["dep"] == "neg" for c in graph.children(verb))
    targets = [obj for _, obj in graph.pp(verb, {"to"})] or graph.children(
        verb, {"dobj"}
    )
    if len(targets) != 1:
        return None
    nominal = _scope_nominal(graph, targets[0])
    scope = _declaration_scope_text(graph, nominal)
    decision = _binding._scope_target(requirement, scope)
    denied_same_scope = bool(
        negated
        and _binding._without_class(_binding._canonical_argument(scope))
        and _binding._without_class(_binding._canonical_argument(scope))
        == _binding._without_class(_binding._canonical_argument(requirement.topic))
    )
    if decision == "unknown" and not denied_same_scope:
        return None
    if negated:
        # Denying the requested scope excludes; denying another scope
        # carries no applicability information. A denied target naming the
        # same activity modulo its class suffix (e.g. "the standard
        # <activity> routine") denies the requested scope too.
        grant = int(decision == "applies" or denied_same_scope)
    else:
        if decision == "applies":
            return None  # Declared coverage of the requested scope.
        grant = 1
    used = {verb}
    used.update(
        c
        for c in graph.children(verb)
        if graph.tokens[c]["dep"] in {"advmod", "aux", "neg", "cc", "prep"}
    )
    used.update(
        m for p in graph.children(verb, {"prep"}) for m in graph.children(p, {"advmod"})
    )
    used |= nominal
    return grant, used


def _condition_class(requirement, value):
    return (
        isinstance(value, str)
        and re.fullmatch(
            rf"(?:exception|retest)(?:\s+{re.escape(requirement.topic)})?",
            value.strip(),
            re.I,
        )
        is not None
    )


def _condition_instruction(graph, literal, requirement, metadata):
    prefix = re.match(
        r"\s*(?:(?:for|when|if)\s+)?([^,;:.]+)[,;:]\s*", literal["text"], re.I
    )
    declared = metadata.get("condition")
    if prefix and _condition_class(requirement, prefix.group(1)):
        prefix_end = literal["start"] + prefix.end()
        prefix_nodes = {
            i
            for i in graph.indices
            if graph.offset + graph.tokens[i]["end"] <= prefix_end
        }
    elif _condition_class(requirement, declared):
        prefix_nodes = set()
    else:
        return None
    remaining = graph.indices - prefix_nodes
    roots = [
        i
        for i in remaining
        if graph.tokens[i]["pos"] != "PUNCT"
        and (graph.tokens[i]["head"] not in remaining or graph.tokens[i]["head"] == i)
    ]
    if len(roots) != 1:
        return None
    root = roots[0]
    if graph.tokens[root]["pos"] != "VERB" or graph.tokens[root]["tag"] != "VB":
        return None
    objects = graph.children(root, {"dobj"})
    if len(objects) != 1:
        return None
    obj = closed_nominal(graph, objects[0])
    if obj is None:
        return None
    proof = consume_clause(graph, prefix_nodes | {root} | obj)
    return proof if proof["complete"] else None


def closed_source_scope(requirement, snapshot, source_windows, temporal_candidate):
    capture, units = captured_units(snapshot, source_windows)
    cover = []
    for graph, literal, uncertainty in units:
        if graph is None:
            continue
        raw = literal["text"]
        condition = condition_relation(requirement, raw, snapshot.get("metadata", {}))
        relation = source_relation_scope(requirement, raw)
        temporal = (
            None
            if uncertainty
            else _temporal(graph, literal, temporal_candidate(requirement, raw))
        )
        foreign = (
            None if uncertainty or relation != "irrelevant" else _simple_role(graph)
        )
        conditioned = (
            None
            if uncertainty or condition != "irrelevant"
            else _condition_instruction(
                graph, literal, requirement, snapshot.get("metadata", {})
            )
        )
        declared = (
            None
            if uncertainty or temporal or foreign or conditioned
            else _declared_scope(graph, literal, requirement)
        )
        proof = (
            temporal["dependency_closure"]
            if temporal
            else foreign or conditioned or (declared[1] if declared else None)
        )
        cover.append(
            {
                "source_range": {"start": literal["start"], "end": literal["end"]},
                "premise": raw,
                "condition_relation": condition,
                "relation_scope": relation,
                "relation_present": relation_present(requirement, raw),
                "other_relation_proof": temporal,
                "dependency_closure": proof or consume_clause(graph, set()),
                "uncertainty": uncertainty,
                "exclusion_reason": "closed_other_field"
                if temporal
                else "closed_foreign_role"
                if foreign
                else "closed_disjoint_condition"
                if conditioned
                else declared[0]
                if declared
                else None,
            }
        )
    workspace = requirement.source_workspace
    actual_workspace = snapshot.get("workspace_id")
    excluded = (
        workspace is not None
        and actual_workspace is not None
        and actual_workspace != workspace
    )
    excluded |= bool(cover) and all(
        row["exclusion_reason"] is not None for row in cover
    )
    return {
        "source_identity": source_identity(snapshot),
        "source_range": {"start": 0, "end": len(snapshot["body"])},
        "premise": snapshot["body"],
        "condition_relation": condition_relation(
            requirement, snapshot["body"], snapshot.get("metadata", {})
        ),
        "relation_scope": source_relation_scope(requirement, snapshot["body"]),
        "relation_present": relation_present(requirement, snapshot["body"]),
        "source_capture": capture,
        "scope_cover": cover,
        "included": not excluded,
    }
