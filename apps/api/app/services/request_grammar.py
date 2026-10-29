"""Bounded partial grammar; proposals do not resolve source/evidence obligations."""

import hashlib
import json
from dataclasses import asdict, replace

from app.services.dependency_frames import (
    ARG_DEPS,
    CONDITIONS,
    META,
    MODALS,
    NOMINAL_DEPS,
    SCOPE_PREPS,
    WHOLE,
    Graph,
    resolve_frames,
)
from app.services.request_parser import validate_capture

from .request_obligations import (
    DeferredSlot,
    HardUnknown,
    Literal,
    PartialRequest,
    RequestEdge,
    RequestNode,
    TokenUse,
    canonical,
)


def literal(span):
    return Literal(*span)


def ranges(g, indices):
    groups = []
    for i in sorted(indices):
        if not groups or i != groups[-1][-1] + 1:
            groups.append([])
        groups[-1].append(i)
    return tuple(literal(g.span(ids)) for ids in groups)


def owning_extent(g, ids, heads):
    """Nested quantification is a literal argument, not the owning extent."""
    return any(
        g.lemma(i) in WHOLE
        and g.ts[i]["head"] in heads
        and g.ts[i]["pos"] in {"ADJ", "DET"}
        and g.ts[i]["dep"] in {"amod", "det"}
        for i in ids
    )


def features(g, ids, frame=None, extent="unspecified"):
    def spans(indices):
        return [asdict(literal(g.span({i}))) for i in sorted(indices)]

    fields = {
        "raw_token_indices": sorted(ids),
        "condition_ast": [asdict(c) for c in g.condition_clauses(ids)],
        "modality": [asdict(literal(s)) for s in g.qualifier_spans(ids, MODALS)],
        "units": [asdict(literal(s)) for s in g.literal_units(ids)],
        "references": spans(g.reference(ids)),
        "negation": spans(i for i in ids if g.low(i) in {"no", "not", "never"}),
        "quantifiers": spans(i for i in ids if g.low(i) in WHOLE | {"both", "each"}),
        "attribute": "",
        "relation": "",
        "governors": [],
        "order": [],
        "extent": extent,
        "source_workspace": None,
    }
    if frame is not None:
        fields.update(
            attribute=frame.attribute,
            relation=frame.relation,
            governors=[asdict(literal(s)) for s in frame.governors],
            order=[asdict(literal(s)) for s in frame.order],
            source_workspace=frame.source_workspace,
            extent="whole_requested"
            if frame.kind == "procedure" and owning_extent(g, ids, frame.heads)
            else "unspecified",
        )
    return canonical(fields)


def node(
    g,
    kind,
    operation,
    head,
    ids,
    scopes=(),
    grammar="declared_partial_production",
    extent="unspecified",
):
    return RequestNode(
        f"{kind}:{head}",
        kind,
        operation,
        ranges(g, ids),
        (head,),
        tuple(sorted(ids)),
        tuple(literal(s) for s in scopes),
        features(
            g,
            ids,
            extent=extent,
        ),
        g.text(ids) + "?",
        grammar,
    )


def operator(g, head):
    at, seen = head, set()
    while at not in seen:
        seen.add(at)
        t = g.ts[at]
        passive_need = (
            g.lemma(at) == "need"
            and t["tag"] == "VBN"
            and any(g.ts[c]["dep"] == "auxpass" for c in g.children[at])
        )
        incumbency = g.lemma(at) in {"fill", "hold", "occupy", "be"} and any(
            g.low(c) == "who" for c in g.children[at]
        )
        if g.lemma(at) in META or passive_need or incumbency:
            return at
        if t["head"] == at:
            break
        at = t["head"]
    return None


def scopes(g, head, op):
    # An explicit field PP owns its subject; a sibling cannot overwrite it.
    candidates = list(g.direct_scopes(head))
    if not candidates:
        at = head
        while g.ts[at]["dep"] == "conj":
            at = g.ts[at]["head"]
        for sibling in g.conjuncts(at):
            candidates += g.direct_scopes(sibling)
    candidates += g.direct_scopes(op)
    # Repeated spellings at distinct original ranges remain distinct proposals.
    return list(
        {
            g.span(nominal)[:2]: (nominal, covered) for nominal, covered in candidates
        }.values()
    )


def role_nodes(g):
    result, ops = [], set()
    for t in g.ts:
        h = t["i"]
        role = g.lemma(h) == "role" and t["dep"] not in {"compound", "amod", "nmod"}
        modified = g.lemma(h) in {"label", "holder", "incumbent"} and any(
            g.lemma(c) == "role" for c in g.nominal(h)
        )
        if not (role or modified):
            continue
        op = operator(g, h)
        if op is None:
            continue
        operation = (
            "labels_only"
            if g.lemma(h) == "label"
            else "incumbents"
            if g.lemma(h) in {"holder", "incumbent"}
            or any(g.low(c) == "who" for c in g.children[op])
            else "unspecified"
        )
        declared = scopes(g, h, op)
        ids = g.nominal(h) | set().union(*(s[1] for s in declared))
        ids |= {
            c
            for c in g.children[op]
            if g.ts[c]["tag"] == "MD" or g.ts[c]["dep"] == "neg"
        }
        for c in g.condition_heads:
            if g.ts[c]["head"] == op:
                ids |= g.subtree(c)
        result.append(
            node(
                g,
                "role_catalogue",
                operation,
                h,
                ids,
                [g.span(s[0]) for s in declared],
                "requested_role_catalogue",
            )
        )
        ops.add(op)
    return result, ops


def constraint_nodes(g):
    result, ops = [], set()
    for t in g.ts:
        i = t["i"]
        if g.lemma(i) != "issue" or t["tag"] != "VBN":
            continue
        subjects = [
            c
            for c in g.children[i]
            if g.ts[c]["dep"] == "nsubjpass" and g.lemma(c) == "override"
        ]
        ids = g.local(i)
        if len(subjects) != 1 or not any(
            g.low(c) in {"no", "not", "never"} for c in ids
        ):
            continue
        result.append(
            node(
                g,
                "request_constraint",
                "verify_constraint",
                i,
                ids,
                grammar="negative_passive_issuance_constraint",
            )
        )
        ops.add(i)
    return result, ops


def _prepositional_argument_reason(g, at):
    t = g.ts[at]
    objects = [c for c in g.children[at] if g.ts[c]["dep"] == "pobj"]
    if (
        t["pos"] != "ADP"
        or len(objects) != 1
        or any(c not in objects and g.ts[c]["dep"] != "punct" for c in g.children[at])
    ):
        return "prepositional_argument_not_closed"
    return None


def _argument_token_kind(g, at, head):
    t = g.ts[at]
    nominal_verb = (
        at == head
        and t["dep"] in ARG_DEPS
        and any(g.ts[c]["dep"] in {"det", "amod", "compound"} for c in g.children[at])
        and not any(
            g.ts[c]["dep"] in {"dobj", "obj", "aux", "auxpass", "ccomp", "xcomp"}
            for c in g.children[at]
        )
    )
    adjectival_participle = (
        t["dep"] == "amod"
        and t["tag"] in {"VBN", "VBG"}
        and not any(
            g.ts[c]["dep"] in {"dobj", "obj", "aux", "auxpass", "ccomp", "xcomp"}
            for c in g.children[at]
        )
    )
    kind = "nominal_head" if at == head else "nominal_modifier"
    reason = None
    if t["pos"] in {"VERB", "AUX"} and not (nominal_verb or adjectival_participle):
        kind, reason = "unclassified_predicate", "operative_predicate_in_argument"
    elif t["dep"] in {"prep", "dative"}:
        kind = "prepositional_qualifier"
        reason = _prepositional_argument_reason(g, at)
    elif t["dep"] == "conj":
        kind, reason = "nominal_conjunction", "nominal_conjunction_requires_split"
    elif t["dep"] == "cc":
        kind = "coordination_operator"
    elif t["tag"] == "MD" or g.low(at) in MODALS:
        kind = "modality_or_negation"
        reason = "modal_argument_attachment_not_closed"
    elif t["dep"] == "nummod" or t["tag"] == "CD":
        kind = "numeric_modifier"
    elif g.low(at) in CONDITIONS:
        kind = "condition_qualifier"
    elif t["dep"] == "punct":
        kind = "literal_punctuation"
    elif at != head and t["dep"] not in NOMINAL_DEPS | {"pobj"}:
        kind, reason = "unclassified_attachment", "argument_attachment_not_closed"
    return kind, reason


def qualified_argument(g, head, *, method_boundary=None):
    """Inventory the complete attached argument; unknown edges never become names."""
    all_ids = g.subtree(head)
    components, unclassified, excluded = [], [], set()
    clauses = g.condition_clauses(all_ids)
    pending, covered = [head], set()
    while pending:
        at = pending.pop()
        if at in covered:
            continue
        t = g.ts[at]
        if at == method_boundary and t["dep"] == "acl":
            ids = g.subtree(at)
            components.append(
                {
                    "kind": "method_predicate_boundary",
                    "token_indices": sorted(ids),
                    "evidence": [asdict(x) for x in ranges(g, ids)],
                }
            )
            covered |= ids
            excluded |= ids
            # The owning method production and method_context below consume it.
            continue
        condition = next((c for c in clauses if c.predicate.start == t["start"]), None)
        if condition is not None and at in g.condition_heads:
            ids = g.subtree(at)
            components.append(
                {
                    "kind": "condition_clause",
                    "token_indices": sorted(ids),
                    "condition_ast": asdict(condition),
                    "evidence": [asdict(x) for x in ranges(g, ids)],
                }
            )
            if set(condition.token_indices) != ids:
                unclassified.append(
                    {
                        "reason": "condition_argument_not_closed",
                        "token_indices": sorted(ids),
                    }
                )
            covered |= ids
            continue
        kind, reason = _argument_token_kind(g, at, head)
        part = {
            "kind": kind,
            "token_indices": [at],
            "evidence": [asdict(literal(g.span({at})))],
        }
        if kind == "prepositional_qualifier":
            part["preposition"] = asdict(literal(g.span({at})))
            part["object_heads"] = [
                c for c in g.children[at] if g.ts[c]["dep"] == "pobj"
            ]
            part["conditional"] = g.low(at) in CONDITIONS
            part["qualified_argument_indices"] = sorted(g.subtree(at))
            part["qualifier_evidence"] = [asdict(x) for x in ranges(g, g.subtree(at))]
        components.append(part)
        if reason:
            unclassified.append({"reason": reason, "token_indices": [at]})
        covered.add(at)
        pending.extend(reversed(g.children[at]))
    assert covered == all_ids
    argument_ids = all_ids - excluded
    ignored = {
        c
        for c in argument_ids
        if c != head
        and (
            g.ts[c]["dep"] == "det"
            and g.low(c) in {"a", "an", "the"}
            or g.ts[c]["dep"] in {"amod", "det", "quantmod"}
            and g.lemma(c) in WHOLE
            and g.ts[c]["head"] == head
        )
    }
    selected = sorted(argument_ids - ignored)
    positions = {c: i for i, c in enumerate(selected)}
    key = [
        [
            g.ts[c]["text"],
            "ARG" if c == head else g.ts[c]["dep"],
            positions.get(g.ts[c]["head"], -1),
        ]
        for c in selected
    ]
    return {
        "head_index": head,
        "token_indices": sorted(all_ids),
        "argument_indices": sorted(argument_ids),
        "evidence": [asdict(x) for x in ranges(g, all_ids)],
        "components": components,
        "unclassified": unclassified,
        "comparison_key": None if unclassified else key,
    }


def method_context(g, predicate, subject, extra_owned=()):
    """Retain every non-NP qualifier; a shortened extent cannot certify closure."""
    components, unknown = [], []
    for child in g.children[predicate]:
        t = g.ts[child]
        modal = t["tag"] == "MD" or g.low(child) in MODALS
        if (
            child == subject
            or child in extra_owned
            or g.low(child) == "how"
            or not modal
            and t["dep"] in {"aux", "auxpass", "punct", "cc"}
        ):
            continue
        independent = t["dep"] == "conj" and (
            g.lemma(child) in META
            or any(
                g.low(c) in {"what", "who", "how", "why", "when", "where"}
                for c in g.children[child]
            )
        )
        if independent:
            continue  # Independently retained request, not name/qualifier text.
        ids = g.subtree(child)
        objects = [c for c in g.children[child] if g.ts[c]["dep"] == "pobj"]
        arguments = [qualified_argument(g, obj) for obj in objects]
        plain_extent_object = len(objects) == 1 and all(
            c == objects[0]
            or g.ts[c]["dep"] == "det"
            and g.low(c) in {"a", "an", "the"}
            for c in g.subtree(objects[0])
        )
        extent = (
            t["dep"] == "prep"
            and plain_extent_object
            and (
                g.low(child) == "from"
                and g.lemma(objects[0]) == "start"
                or g.low(child) == "to"
                and g.lemma(objects[0]) == "finish"
            )
        )
        kind = (
            "method_modality"
            if modal
            else "whole_method_extent"
            if extent
            else "method_qualifier"
        )
        components.append(
            {
                "kind": kind,
                "token_indices": sorted(ids),
                "evidence": [asdict(x) for x in ranges(g, ids)],
                "argument_closures": arguments,
                "condition_ast": [asdict(c) for c in g.condition_clauses(ids)],
            }
        )
        if not modal and any(
            g.ts[c]["pos"] in {"VERB", "AUX"} and c not in g.condition_heads
            for c in ids
        ):
            unknown.append(
                {"reason": "method_context_not_closed", "token_indices": sorted(ids)}
            )
        unknown += [u for argument in arguments for u in argument["unclassified"]]
    return components, unknown


def method_nodes(g, frames=()):
    # Frame classification licenses a procedure proposal, never its argument
    # closure. Recover that closure from the captured predicate/subject edges
    # instead of adopting a frame's shortened scope or predicate-head extent.
    proposed = {h for f in frames if f.kind == "procedure" for h in f.heads}
    unresolved = {h for f in frames if f.kind == "generic" for h in f.heads}
    result, ops = [], set()
    for t in g.ts:
        i = t["i"]
        if (
            i not in proposed | unresolved
            and g.lemma(i) not in {"perform", "execute", "do"}
            or t["tag"] != "VBN"
            and not (i in proposed and t["pos"] == "VERB" and t["tag"].startswith("VB"))
        ):
            continue
        parent = t["head"]
        direct = [
            c
            for c in g.children[i]
            if g.ts[c]["dep"] == "nsubjpass"
            or i in proposed
            and g.ts[c]["dep"] == "nsubj"
        ]
        nominal = (
            [parent]
            if t["dep"] == "acl" and g.ts[parent]["dep"] in {"nsubj", "nsubjpass"}
            else []
        )
        subjects = direct or nominal
        root = g.ts[parent]["head"] if nominal else i
        if len(subjects) != 1 or not any(g.low(c) == "how" for c in g.children[root]):
            continue
        objects = [c for c in g.children[i] if g.ts[c]["dep"] in {"obj", "dobj"}]
        active = g.ts[subjects[0]]["dep"] == "nsubj" and not nominal
        actors = subjects if active and objects else []
        ambiguous = bool(objects) and (
            not active
            or len(objects) != 1
            or any(g.ts[c]["dep"] == "dative" for c in g.children[i])
        )
        activity = None if ambiguous else objects[0] if actors else subjects[0]
        ids = g.local(root) | g.subtree(i, prune=g.predicates - {i, root})
        extent = activity is not None and (
            owning_extent(g, ids, {activity})
            or (
                any(g.low(p) == "from" and g.lemma(o) == "start" for p, o in g.pp(i))
                and any(g.low(p) == "to" and g.lemma(o) == "finish" for p, o in g.pp(i))
            )
        )
        if activity is None:
            candidates = [qualified_argument(g, h) for h in objects]
            candidate_ids = set().union(*(set(c["token_indices"]) for c in candidates))
            closure = {
                "head_index": None,
                "token_indices": sorted(candidate_ids),
                "argument_indices": [],
                "evidence": [asdict(x) for x in ranges(g, candidate_ids)],
                "components": [
                    {
                        "kind": "method_activity_candidates",
                        "token_indices": sorted(candidate_ids),
                        "evidence": [asdict(x) for x in ranges(g, candidate_ids)],
                        "argument_closures": candidates,
                    }
                ],
                "unclassified": [
                    {
                        "reason": "method_activity_role_ambiguous",
                        "token_indices": sorted(candidate_ids | set(subjects)),
                    }
                ],
                "comparison_key": None,
            }
        else:
            closure = qualified_argument(g, activity, method_boundary=i)
        context, unknown = method_context(g, i, activity, extra_owned=actors + objects)
        for actor in actors:
            argument = qualified_argument(g, actor)
            context.append(
                {
                    "kind": "method_actor",
                    "token_indices": argument["token_indices"],
                    "evidence": argument["evidence"],
                    "argument_closures": [argument],
                    "condition_ast": [
                        asdict(c)
                        for c in g.condition_clauses(argument["token_indices"])
                    ],
                }
            )
            unknown += argument["unclassified"]
        if i not in proposed and g.lemma(i) not in {"perform", "execute", "do"}:
            # A generic frame can retain a syntactic manner proposal, but its
            # unestablished procedure classification remains a hard obligation.
            unknown.append(
                {
                    "reason": "procedure_manner_classification_unresolved",
                    "token_indices": [i],
                }
            )
        closure["unclassified"] += unknown
        closure["components"] += context
        all_argument_ids = set(closure["token_indices"]) | {
            c for part in context for c in part["token_indices"]
        }
        closure["token_indices"] = sorted(all_argument_ids)
        closure["evidence"] = [asdict(x) for x in ranges(g, all_argument_ids)]
        if unknown:
            closure["comparison_key"] = None
        owned = ids | set(closure["token_indices"])
        n = node(
            g,
            "procedure",
            "request_procedure",
            i,
            owned,
            [g.span(closure["argument_indices"])] if activity is not None else [],
            "passive_method_request",
            extent="whole_requested" if extent else "unspecified",
        )
        fields = json.loads(n.feature_json)
        fields.update(
            argument_closure=closure,
            method_argument_roles={
                "activity_head": activity,
                "actor_heads": actors,
                "candidate_activity_heads": objects if ambiguous else [],
                "status": "unresolved" if ambiguous else "captured_argument_roles",
            },
            method_qualifiers=context,
            ownership_context_pending=[
                c for c in context if c["kind"] != "whole_method_extent"
            ],
        )
        result.append(replace(n, feature_json=canonical(fields)))
        ops.update({root, i})
    return result, ops


def method_candidates(g, predicate, methods):
    def root(at):
        while g.ts[at]["head"] != at:
            at = g.ts[at]["head"]
        return at

    return [
        m
        for m in methods
        if max(m.head_indices) < predicate
        and g.sent[max(m.head_indices)] == g.sent[predicate]
        and root(max(m.head_indices)) == root(predicate)
    ]


def unique_method_reference(g, obj, method, target):
    head = method.head_indices[0]
    anchor = head if g.ts[head]["dep"] != "acl" else g.ts[g.ts[head]["head"]]["head"]
    predicate = g.ts[obj]["head"]
    fields = json.loads(method.feature_json)
    closure = fields["argument_closure"]
    complex_kinds = {
        "prepositional_qualifier",
        "condition_clause",
        "nominal_conjunction",
    }
    if (
        closure["unclassified"]
        or fields["ownership_context_pending"]
        or target["unclassified"]
    ):
        return False
    if any(
        c["kind"] in complex_kinds for c in closure["components"] + target["components"]
    ):
        return False
    if g.ts[predicate]["dep"] != "conj" or g.ts[predicate]["head"] != anchor:
        return False
    if any(head < p < predicate and p != anchor for p in g.predicates):
        return False
    subject = set(closure["argument_indices"])
    return not any(
        c not in subject
        and (g.ts[c]["pos"] in {"NOUN", "PROPN"} or g.ts[c]["tag"] in {"PRP", "PRP$"})
        for c in g.local(anchor)
    )


def facet_ownership(g, obj, methods):
    target = qualified_argument(g, obj)
    pp = g.pp(obj)
    scope_heads = [head for prep, head in pp if g.low(prep) in SCOPE_PREPS]
    # A single explicit scope relation is a closed ownership projection only
    # after the entire target and recursively qualified scope both close.
    projected = target

    def matching(closure):
        found = []
        for method in methods:
            fields = json.loads(method.feature_json)
            key = fields["argument_closure"]["comparison_key"]
            if (
                target["comparison_key"] is not None
                and closure["comparison_key"] is not None
                and key is not None
                and not fields["ownership_context_pending"]
                and key == closure["comparison_key"]
            ):
                found.append(method)
        return found

    matches = matching(target)
    named_core = any(g.ts[c]["pos"] == "PROPN" for c in g.nominal(obj))
    if not matches and not named_core and len(pp) == len(scope_heads) == 1:
        projected = qualified_argument(g, scope_heads[0])
        matches = matching(projected)
    subjects = [set(projected["argument_indices"])]
    refs = g.reference(target["token_indices"])
    local = (
        len(refs) == 1
        and g.low(refs[0]) in {"it", "its"}
        and (
            refs[0] == obj
            or g.ts[refs[0]]["dep"] == "poss"
            and g.ts[refs[0]]["head"] == obj
        )
    )
    if (
        local
        and not pp
        and len(methods) == 1
        and unique_method_reference(g, obj, methods[0], target)
    ):
        return subjects, methods, methods[0], "unique_local_reference", target
    if not refs and len(matches) == 1:
        return subjects, matches, matches[0], "explicit_same_subject", target
    explicit = bool(pp) or any(
        g.ts[c]["pos"] == "PROPN" for c in target["token_indices"]
    )
    return (
        subjects,
        matches if explicit else methods,
        None,
        "deferred_subject_relation",
        target,
    )


def facet_nodes(g, methods):
    result, edges, ops = [], [], set()
    for t in g.ts:
        i = t["i"]
        if (
            i not in g.predicates
            or g.lemma(i) != "govern"
            or not any(g.low(c) == "what" for c in g.children[i])
        ):
            continue
        objects = [c for c in g.children[i] if g.ts[c]["dep"] in {"obj", "dobj"}]
        if len(objects) != 1:
            continue
        subjects, candidates, selected, relation, target = facet_ownership(
            g, objects[0], method_candidates(g, i, methods)
        )
        n = node(
            g,
            "procedure_facet",
            "requested_governance",
            i,
            g.local(i),
            [g.span(subject) for subject in subjects],
            "requested_governing_facet",
        )
        fields = json.loads(n.feature_json)
        fields.update(
            facet_target=target["evidence"],
            argument_closure=target,
            candidate_argument_closures=[
                {
                    "method_id": m.id,
                    "argument_closure": json.loads(m.feature_json)["argument_closure"],
                    "method_qualifiers": json.loads(m.feature_json)[
                        "method_qualifiers"
                    ],
                }
                for m in candidates
            ],
            candidate_method_ids=[m.id for m in candidates],
            request_ownership=relation,
        )
        n = replace(n, feature_json=canonical(fields))
        result.append(n)
        if selected is not None:
            edges.append(RequestEdge("procedure_facet", selected.id, n.id, n.evidence))
        ops.add(i)
    return result, edges, ops


def temporal_nodes(g, frames):
    return [
        node(
            g,
            "temporal_attribute",
            "request_field_value",
            f.heads[-1],
            set(f.tokens),
            f.scopes,
            "requested_ambiguous_temporal_field",
        )
        for f in frames
        if "ambiguous_temporal_attribute" in f.errors and f.heads
    ]


def base_nodes(g, frames, special, ops):
    result, unknowns = [], []
    heads = {h for n in special for h in n.head_indices}
    known = set().union(
        *(set(n.token_indices) for n in special),
        *(set(f.tokens) for f in frames if not f.errors),
    )
    syntax = (
        set(g.syntax)
        | ops
        | {
            c
            for p in ops
            for c in g.children[p]
            if g.ts[c]["dep"] in {"aux", "auxpass", "punct", "cc"}
            or g.low(c) in {"please", "together"}
        }
    )
    deferred_errors = {"role_catalogue_not_defined", "ambiguous_temporal_attribute"}
    outer_errors = {
        "unknown_interrogative_frame",
        "unrecognized_request_predicate",
        "unconsumed_original_tokens",
    }
    for index, f in enumerate(frames):
        matched = bool(set(f.heads) & heads)
        closed = (
            bool(f.heads)
            and set(f.heads) <= heads | ops
            and set(f.tokens) <= known | syntax
        )
        scoped = any(n.scopes and set(n.head_indices) & set(f.heads) for n in special)
        catalogue = bool(f.heads) and any(
            n.kind == "role_catalogue" and f.heads[-1] in n.head_indices
            for n in special
        )
        errors = [
            e
            for e in f.errors
            if not (
                matched
                and e in deferred_errors
                or closed
                and e in outer_errors
                or closed
                and scoped
                and e == "missing_explicit_scope"
                or closed
                and catalogue
                and e == "unknown_requested_head"
            )
        ]
        unknowns += [HardUnknown(e, (literal(f.original),), f.heads) for e in errors]
        if matched or closed:
            continue
        result.append(
            RequestNode(
                f"frame:{index}",
                f.kind,
                "request_procedure" if f.kind == "procedure" else "request_field_value",
                (literal(f.original),),
                f.heads,
                f.tokens,
                tuple(literal(s) for s in f.scopes),
                features(g, set(f.tokens), frame=f),
                f.question,
                f.grammar,
            )
        )
    return result, unknowns


def deferred_slots(nodes):
    result = []
    for n in nodes:
        kind = {
            "role_catalogue": "role_catalogue",
            "temporal_attribute": "temporal_attribute",
            "procedure_facet": "procedure_facet_reference",
            "request_constraint": "verify_request_constraint",
        }.get(n.kind)
        if kind:
            result.append(
                DeferredSlot(
                    "",
                    kind,
                    n.id,
                    n.evidence,
                    canonical(
                        {
                            "operation": n.operation,
                            **(
                                {
                                    key: json.loads(n.feature_json)[key]
                                    for key in (
                                        "candidate_method_ids",
                                        "request_ownership",
                                        "facet_target",
                                        "argument_closure",
                                        "candidate_argument_closures",
                                    )
                                }
                                if n.kind == "procedure_facet"
                                else {}
                            ),
                        }
                    ),
                )
            )
        closure = json.loads(n.feature_json).get("argument_closure")
        name_closed = (
            closure is None
            or not closure["unclassified"]
            and not any(
                c["kind"]
                in {
                    "condition_clause",
                    "condition_qualifier",
                    "modality_or_negation",
                    "nominal_conjunction",
                }
                or c.get("conditional", False)
                for c in closure["components"]
            )
        )
        if (
            name_closed
            and n.kind != "generic"
            and n.scopes
            and not (
                n.kind == "procedure_facet" and json.loads(n.feature_json)["references"]
            )
        ):
            result.append(
                DeferredSlot(
                    "",
                    "literal_subject_boundary",
                    n.id,
                    n.scopes,
                    canonical(
                        {
                            "relation": (
                                "literal_request_scope_requires_source_declaration"
                            )
                        }
                    ),
                )
            )
        conditions = (
            [
                part
                for part in closure["components"]
                if part["kind"] in {"condition_clause", "condition_qualifier"}
                or part.get("conditional", False)
            ]
            if closure
            else []
        )
        if conditions:
            result.append(
                DeferredSlot(
                    "",
                    "verify_request_constraint",
                    n.id,
                    tuple(
                        Literal(**span)
                        for part in conditions
                        for span in part.get("qualifier_evidence", part["evidence"])
                    ),
                    canonical(
                        {
                            "operation": "argument_condition_requires_evidence",
                            "qualifiers": conditions,
                        }
                    ),
                )
            )
        pending_context = json.loads(n.feature_json).get(
            "ownership_context_pending", []
        )
        if n.kind == "procedure" and pending_context:
            result.append(
                DeferredSlot(
                    "",
                    "procedure_facet_reference",
                    n.id,
                    tuple(
                        Literal(**span)
                        for part in pending_context
                        for span in part["evidence"]
                    ),
                    canonical(
                        {
                            "operation": "method_qualifier_binding_and_output",
                            "qualifiers": pending_context,
                        }
                    ),
                )
            )
        governors = json.loads(n.feature_json)["governors"]
        if n.kind == "procedure" and governors:
            result.append(
                DeferredSlot(
                    "",
                    "procedure_facet_reference",
                    n.id,
                    tuple(Literal(**s) for s in governors),
                    canonical({"operation": "independent_governor_output_coverage"}),
                )
            )
    return result


def set_edges(g, nodes):
    result = []
    for n in nodes:
        if n.kind != "availability":
            continue
        refs = g.reference(n.token_indices)
        head = max(n.head_indices)
        op = operator(g, head)
        prior = [
            p
            for p in nodes
            if p.kind == "role_catalogue"
            and max(p.head_indices) < head
            and g.sent[max(p.head_indices)] == g.sent[head]
            and op is not None
            and (
                operator(g, max(p.head_indices)) == op
                or g.ts[op]["dep"] == "conj"
                and g.ts[op]["head"] == operator(g, max(p.head_indices))
            )
        ]
        if (
            len(refs) == 1
            and g.low(refs[0]) == "their"
            and g.ts[refs[0]]["dep"] == "poss"
            and g.ts[refs[0]]["head"] == head
            and len(prior) == 1
            and prior[0].operation == "incumbents"
        ):
            result.append(
                RequestEdge(
                    "catalogue_member_value", prior[0].id, n.id, ranges(g, refs)
                )
            )
    return result


def order_edges(g, nodes):
    result = []
    conditional = set().union(
        *(set(c.token_indices) for c in g.condition_clauses(range(len(g.ts))))
    )
    for t in g.ts:
        i = t["i"]
        if g.low(i) != "then" or i in conditional:
            continue
        prior = [
            n for n in nodes if n.kind != "generic" and max(n.head_indices or (i,)) < i
        ]
        later = [
            n for n in nodes if n.kind != "generic" and max(n.head_indices or (i,)) > i
        ]
        if prior and later:
            target = min(later, key=lambda n: max(n.head_indices))
            result += [
                RequestEdge("request_order", n.id, target.id, ranges(g, {i}))
                for n in prior
            ]
    return result


def value_edges(frames, nodes):
    identifiers = {n.id for n in nodes}
    return [
        RequestEdge(
            "value_dependency",
            f"frame:{dep}",
            f"frame:{index}",
            tuple(literal(s) for s in f.references),
        )
        for index, f in enumerate(frames)
        for dep in f.dependencies
        if f"frame:{dep}" in identifiers and f"frame:{index}" in identifiers
    ]


def symbolic_unknowns(unknowns, nodes, edges):
    bound = {e.target_id for e in edges if e.kind == "catalogue_member_value"}
    target_heads = {n.head_indices for n in nodes if n.id in bound}
    return [
        u
        for u in unknowns
        if not (
            u.head_indices in target_heads
            and u.reason
            in {"unresolved_reference_or_dependent_attribute", "missing_explicit_scope"}
        )
    ]


def additional_unknowns(g, nodes):
    result = [
        HardUnknown(
            "external_required_target_not_supported", ranges(g, g.subtree(t["head"]))
        )
        for t in g.ts
        if g.lemma(t["i"]) in {"manual", "guide", "note", "policy"}
        and t["dep"] == "pobj"
        and g.low(t["head"]) in {"from", "per", "according"}
    ]
    result += [
        HardUnknown("role_query_operation_not_explicit", n.evidence, n.head_indices)
        for n in nodes
        if n.kind == "role_catalogue" and n.operation == "unspecified"
    ]
    result += [
        HardUnknown("ambiguous_catalogue_subject", n.scopes, n.head_indices)
        for n in nodes
        if n.kind == "role_catalogue" and len(n.scopes) > 1
    ]
    for n in nodes:
        closure = json.loads(n.feature_json).get("argument_closure")
        if closure:
            result += [
                HardUnknown(
                    "incomplete_argument:" + u["reason"],
                    ranges(g, u["token_indices"]),
                    n.head_indices,
                )
                for u in closure["unclassified"]
            ]
    result += [
        HardUnknown("unknown_why_request", ranges(g, {t["i"]}), (t["i"],))
        for t in g.ts
        if g.low(t["i"]) == "why"
    ]
    return result


def renumber(nodes, slots, edges):
    nodes = sorted(
        nodes, key=lambda n: (min(n.head_indices or n.token_indices or (0,)), n.kind)
    )
    ids = {n.id: f"p{i + 1}" for i, n in enumerate(nodes)}

    def remap(payload):
        fields = json.loads(payload)
        if "candidate_method_ids" in fields:
            fields["candidate_method_ids"] = [
                ids[c] for c in fields["candidate_method_ids"]
            ]
        for candidate in fields.get("candidate_argument_closures", []):
            candidate["method_id"] = ids[candidate["method_id"]]
        return canonical(fields)

    return (
        tuple(
            replace(n, id=ids[n.id], feature_json=remap(n.feature_json)) for n in nodes
        ),
        tuple(
            replace(
                s,
                id=f"d{i + 1}",
                node_id=ids[s.node_id],
                parameters_json=remap(s.parameters_json),
            )
            for i, s in enumerate(slots)
        ),
        tuple(
            replace(e, source_id=ids[e.source_id], target_id=ids[e.target_id])
            for e in edges
        ),
    )


def compile_partial(question, capture):
    annotation = validate_capture(question, capture)
    g = Graph(question, annotation)
    frames, _ = resolve_frames(question, annotation)
    if any(
        frame.kind == "procedure"
        and not frame.errors
        and len({g.sent[index] for index in frame.tokens}) > 1
        for frame in frames
    ):
        # The old whole-request shortcut can absorb a preceding independent
        # sentence. V3 derives clauses on the actual original graph instead;
        # this is not a narrowed or claimed-successful legacy RequestPlan.
        from app.services.dependency_frames import (
            _bind_relations,
            _close_reference_inventory,
            _collect_predicates,
            _nominal_interrogatives,
        )

        workspaces = {frame.source_workspace for frame in frames}
        frames, handled = _nominal_interrogatives(g)
        frames = _collect_predicates(g, frames, handled)
        frames = _close_reference_inventory(g, _bind_relations(g, frames))
        if len(workspaces) == 1:
            workspace = next(iter(workspaces))
            frames = [replace(frame, source_workspace=workspace) for frame in frames]
    roles, role_ops = role_nodes(g)
    constraints, constraint_ops = constraint_nodes(g)
    methods, method_ops = method_nodes(g, frames)
    facets, edges, facet_ops = facet_nodes(g, methods)
    special = roles + constraints + methods + facets + temporal_nodes(g, frames)
    base, unknowns = base_nodes(
        g, frames, special, role_ops | constraint_ops | method_ops | facet_ops
    )
    nodes = special + base
    unknowns += additional_unknowns(g, nodes)
    edges += set_edges(g, nodes) + order_edges(g, nodes) + value_edges(frames, nodes)
    unknowns = symbolic_unknowns(unknowns, nodes, edges)
    nodes, slots, edges = renumber(nodes, deferred_slots(nodes), edges)
    tokens = tuple(
        TokenUse(
            Literal(t["start"], t["end"], t["text"]),
            t["whitespace"],
            tuple(n.id for n in nodes if t["i"] in n.token_indices),
        )
        for t in annotation["tokens"]
    )
    return PartialRequest(
        question,
        hashlib.sha256(question.encode()).hexdigest(),
        capture["capture_sha256"],
        canonical(capture),
        nodes,
        slots,
        tuple(unknowns),
        edges,
        tokens,
        features(g, set(range(len(g.ts)))),
        canonical([asdict(f) for f in frames]),
    )
