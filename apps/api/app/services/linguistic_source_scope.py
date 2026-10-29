"""Lossless source-unit scope candidates from independently supplied captures.

Dependencies propose syntax, not operative authority, semantics or publication.
Unknown units are retained and block negative scope pruning. Every consumer must
discharge the explicit pending source, namespace/applicability and reference gates.
No legacy source scope, action vocabulary or policy registry is changed here.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy

from app.request_parser_catalog import MAX_QUESTION_CHARS
from app.services.request_parser import _native, validate_capture

CONTRACT = "declared-source-scope-cover-v2"
MAX_BODY_BYTES = 128 * 1024
MAX_WINDOWS = 256
_NOMINAL = frozenset({"det", "compound", "amod", "nmod", "nummod", "poss", "case"})
_SUBJECT = frozenset({"nsubj", "nsubjpass", "csubj", "csubjpass"})
_DOC = frozenset(
    {
        "note",
        "document",
        "instruction",
        "procedure",
        "routine",
        "method",
        "rule",
        "guidance",
    }
)
_ROLE = {"lead": "owner", "leader": "owner", "owner": "owner", "deputy": "deputy"}
_GOVERN = frozenset({"apply", "govern", "concern"})
_REFERENCES = frozenset(
    {
        "appendix",
        "annex",
        "manual",
        "handbook",
        "reference",
        "guide",
        "policy",
        "roster",
        "schedule",
        "protocol",
        "specification",
    }
)
_CONDITIONS = frozenset(
    {
        "if",
        "unless",
        "when",
        "while",
        "before",
        "after",
        "until",
        "without",
        "except",
        "provided",
        "whether",
    }
)
_MODALS = frozenset(
    {"must", "may", "should", "can", "could", "would", "might", "shall", "not", "never"}
)
_UNIVERSAL = frozenset({"all", "each", "every", "any"})
_NONOPERATIVE = frozenset({"fixture", "example", "quotation"})


def _json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def _literal(body, start, end):
    return {"start": start, "end": end, "text": body[start:end]}


def _identity(body, identity):
    _native(identity)
    required = {"document_id", "document_version", "content_hash"}
    if type(body) is not str or not body.strip():
        raise ValueError("A nonempty canonical source body is required")
    encoded = body.encode("utf-8")
    if len(encoded) > MAX_BODY_BYTES:
        raise ValueError("Whole source body budget exceeded")
    if (
        type(identity) is not dict
        or not required <= identity.keys()
        or identity.keys() - required - {"workspace_id", "snapshot_id"}
    ):
        raise ValueError("Immutable source identity schema mismatch")
    if (
        type(identity["document_version"]) is not int
        or identity["document_version"] < 1
        or type(identity["document_id"]) is not str
        or not identity["document_id"].strip()
        or identity["content_hash"] != hashlib.sha256(encoded).hexdigest()
    ):
        raise ValueError("Immutable source identity mismatch")
    for key in ("workspace_id", "snapshot_id"):
        if key in identity and (
            type(identity[key]) is not str or not identity[key].strip()
        ):
            raise ValueError("Invalid immutable source identity field")
    return deepcopy(identity)


def _windows(body, windows):
    _native(windows)
    if type(windows) is not list or not 0 < len(windows) <= MAX_WINDOWS:
        raise ValueError("Ordered source capture windows required")
    cursor = 0
    result = []
    for window in windows:
        if type(window) is not dict or set(window) != {"start", "end", "capture"}:
            raise ValueError("Source capture window schema mismatch")
        start, end = window["start"], window["end"]
        if (
            type(start) is not int
            or type(end) is not int
            or start != cursor
            or not start < end <= len(body)
            or end - start > MAX_QUESTION_CHARS
        ):
            raise ValueError(
                "Source capture windows must cover the canonical body exactly"
            )
        annotation = validate_capture(body[start:end], window["capture"])
        result.append((start, end, annotation, window["capture"]))
        cursor = end
    if cursor != len(body):
        raise ValueError("Source capture windows omit the immutable tail")
    return result


def _regions(body):  # noqa: C901 - literal quote/fence state machine
    """Literal quotation/fence boundaries; uncertainty never grants authority."""
    regions = []
    opened = None
    for match in re.finditer(r"(?m)^.*(?:\n|$)", body):
        line = match.group()
        fence = re.match(r"\s*(`{3,}|~{3,})", line)
        if fence:
            if opened is None:
                opened = (match.start(), fence[1][0])
            elif fence[1][0] == opened[1]:
                regions.append((opened[0], match.end(), "fenced"))
                opened = None
        elif opened is None and re.match(r"\s*>", line):
            regions.append((match.start(), match.end(), "quoted"))
    if opened is not None:
        regions.append((opened[0], len(body), "unclosed_fence"))
    pairs = {'"': '"', "'": "'", "“": "”", "‘": "’", "`": "`"}
    cursor = 0
    while cursor < len(body):
        if any(first <= cursor < last for first, last, _ in regions):
            cursor += 1
            continue
        char = body[cursor]
        if (
            char == "'"
            and cursor
            and cursor + 1 < len(body)
            and body[cursor - 1].isalnum()
            and body[cursor + 1].isalnum()
        ):
            cursor += 1
            continue
        if char not in pairs:
            cursor += 1
            continue
        closing = body.find(pairs[char], cursor + 1)
        if closing < 0:
            regions.append((cursor, len(body), "unclosed_quote"))
            break
        regions.append((cursor, closing + 1, "quoted"))
        cursor = closing + 1
    return regions


class _Graph:
    def __init__(self, body, offset, annotation, start, end):
        self.body, self.offset, self.tokens = body, offset, annotation["tokens"]
        self.indices = {
            t["i"]
            for t in self.tokens
            if start <= offset + t["start"]
            and offset + t["end"] <= end
            and t["pos"] != "SPACE"
        }

    def children(self, i, deps=None):
        return [
            j
            for j in self.tokens[i]["children"]
            if j in self.indices and (deps is None or self.tokens[j]["dep"] in deps)
        ]

    def lemma(self, i):
        return self.tokens[i]["lemma"].casefold()

    def subtree(self, i):
        todo, found = [i], set()
        while todo:
            at = todo.pop()
            if at in found or at not in self.indices:
                continue
            found.add(at)
            todo.extend(self.children(at))
        return found

    def nominal(self, i):
        todo, found = [i], set()
        while todo:
            at = todo.pop()
            if at in found:
                continue
            found.add(at)
            todo.extend(self.children(at, _NOMINAL))
        return found

    def span(self, indices):
        ordered = sorted(indices)
        return _literal(
            self.body,
            self.offset + self.tokens[ordered[0]]["start"],
            self.offset + self.tokens[ordered[-1]]["end"],
        )

    def pp(self, i, preps):
        return [
            (p, obj)
            for p in self.children(i, {"prep", "agent"})
            if self.lemma(p) in preps
            for obj in self.children(p, {"pobj"})
        ]

    def named(self, indices):
        return {
            self.tokens[i]["text"].casefold()
            for i in indices
            if self.tokens[i]["pos"] == "PROPN"
        }

    def consumed(self, used):
        allowed = {
            i
            for i in self.indices
            if self.tokens[i]["pos"] == "PUNCT"
            or self.lemma(i) == "only"
            and self.tokens[i]["dep"] == "advmod"
            or self.tokens[i]["dep"] in {"aux", "auxpass", "neg"}
        }
        return self.indices <= set(used) | allowed

    def nominal_closed(self, i):
        allowed = self.nominal(i) | {
            j
            for j in self.subtree(i)
            if self.tokens[j]["pos"] == "PUNCT" or self.lemma(j) == "only"
        }
        return self.subtree(i) <= allowed


def _canonical(text):
    return re.sub(
        r"^(?:the|a|an)\s+", "", " ".join(text.split()), flags=re.I
    ).casefold()


def _relation(target, named, asked):
    if _canonical(target["text"]) == _canonical(asked):
        return "literal_topic_match_candidate"
    requested = {
        word.casefold()
        for word in re.findall(r"[^\W_]+(?:[-’'][^\W_]+)*", asked)
        if any(c.isupper() for c in word)
    }
    if named and requested and named.isdisjoint(requested):
        return "different_named_scope_candidate"
    return "unresolved"


def _scope(g, head, declaration, *, inherited=False, full=True):
    indices = g.nominal(head)
    if any(g.tokens[i]["pos"] == "PRON" for i in indices):
        full = False
    return {
        "target": g.span(indices),
        "named_tokens": sorted(g.named(indices)),
        "declaration": declaration,
        "inherited": inherited,
        "disclosure_required": inherited,
        "full_governing_scope_candidate": full,
    }


def _declaration(g, root, literal):
    subjects = g.children(root, _SUBJECT)
    if len(subjects) != 1 or g.lemma(subjects[0]) not in _DOC:
        return None
    subject = subjects[0]
    if g.named(g.nominal(subject)):
        return None
    prep = []
    targets = []
    if g.lemma(root) in {"apply", "be"}:
        prep = g.pp(root, {"to"} if g.lemma(root) == "apply" else {"for"})
        targets = [obj for _, obj in prep]
    elif g.lemma(root) in _GOVERN:
        targets = g.children(root, {"dobj"})
    if len(targets) != 1:
        return None
    target = targets[0]
    used = {root, *[p for p, _ in prep]} | g.nominal(subject) | g.nominal(target)
    full = g.consumed(used) and g.nominal_closed(subject) and g.nominal_closed(target)
    # Negative or merely possible applicability cannot establish the positive
    # governing premise needed to inherit a note's restricted context.
    full &= not any(
        g.tokens[i]["dep"] == "neg" or g.tokens[i]["tag"] == "MD" for i in g.indices
    )
    if (
        not g.named(g.nominal(target))
        and len(
            g.nominal(target) - {i for i in g.indices if g.tokens[i]["dep"] == "det"}
        )
        < 2
    ):
        full = False
    return _scope(g, target, literal, full=full)


def _role(g, root, literal, active):
    subjects = g.children(root, _SUBJECT)
    if len(subjects) != 1:
        return None
    subject = subjects[0]
    if g.lemma(root) == "lead":
        targets = g.children(root, {"dobj"})
        actors = [subject]
        used = {root}
        if g.tokens[subject]["dep"] == "nsubjpass":
            by = g.pp(root, {"by"})
            targets, actors = [subject], [obj for _, obj in by]
            used |= {p for p, _ in by}
        if len(targets) != 1 or len(actors) != 1:
            return None
        target, actor = targets[0], actors[0]
        scope = _scope(g, target, literal)
        used |= g.nominal(target) | g.nominal(actor)
        full = g.consumed(used) and g.nominal_closed(target) and g.nominal_closed(actor)
        role = "owner"
    elif g.lemma(root) == "be" and g.lemma(subject) in _ROLE:
        actors = g.children(root, {"attr"})
        preps = g.pp(subject, {"for", "of"}) + g.pp(root, {"for"})
        if len(actors) != 1 or len(preps) > 1:
            return None
        actor = actors[0]
        used = {root} | g.nominal(subject) | g.nominal(actor)
        if preps:
            p, target = preps[0]
            scope = _scope(g, target, literal)
            used |= {p} | g.nominal(target)
        elif active:
            scope = {**deepcopy(active), "inherited": True, "disclosure_required": True}
        else:
            return None
        full = g.consumed(used) and g.nominal_closed(actor)
        role = _ROLE[g.lemma(subject)]
    else:
        return None
    scope["full_governing_scope_candidate"] &= full
    return scope, [
        {
            "role": role,
            "actor": g.span(g.nominal(actor)),
            "target": deepcopy(scope["target"]),
            "status": "unassessed_literal_assignment",
        }
    ] if full else []


def _global(g, root):
    if any(
        g.lemma(i) in {"global", "globally", "universal", "universally", "regardless"}
        for i in g.indices
    ):
        return True
    targets = []
    for predicate in g.indices:
        if g.tokens[predicate]["pos"] not in {"VERB", "AUX"}:
            continue
        targets += g.children(predicate, _SUBJECT)
        if g.lemma(predicate) in _GOVERN:
            targets += g.children(predicate, {"dobj"})
            targets += [obj for _, obj in g.pp(predicate, {"to", "for"})]
    return any(
        any(g.lemma(i) in _UNIVERSAL for i in g.nominal(target))
        and not g.named(g.nominal(target))
        for target in targets
    )


def _features(g, literal):
    conditions = (
        [deepcopy(literal)]
        if any(
            g.lemma(i) in _CONDITIONS or g.tokens[i]["dep"] in {"advcl", "mark"}
            for i in g.indices
        )
        else []
    )
    modality = [
        g.span({i})
        for i in sorted(g.indices)
        if g.lemma(i) in _MODALS or g.tokens[i]["tag"] == "MD"
    ]
    quantities = [
        g.span(g.nominal(g.tokens[i]["head"]))
        for i in sorted(g.indices)
        if g.tokens[i]["dep"] == "nummod"
    ]
    references = [
        {"target": g.span(g.subtree(i)), "status": "unresolved_reference_candidate"}
        for i in sorted(g.indices)
        if g.lemma(i) in _REFERENCES
    ]
    return conditions, modality, quantities, references


def _imperative(g, root):
    return (
        g.tokens[root]["pos"] == "VERB"
        and g.tokens[root]["tag"] == "VB"
        and not any(g.tokens[i]["dep"] in _SUBJECT for i in g.indices)
    )


def _instruction_scope(g, root, literal, active, conditions, references):
    """A fronted PP binds this clause only; an operative note binds inheritance."""
    fronted = [
        (p, obj)
        for p, obj in g.pp(root, {"for"})
        if g.tokens[p]["start"] == min(g.tokens[i]["start"] for i in g.indices)
        and g.tokens[obj]["end"] <= g.tokens[root]["start"]
    ]
    if len(fronted) == 1:
        _, target = fronted[0]
        scope = _scope(g, target, literal, full=g.nominal_closed(target))
    elif active and not fronted:
        scope = {**deepcopy(active), "inherited": True, "disclosure_required": True}
    else:
        return None
    referenced = (
        set().union(*(g.subtree(i) for i in g.indices if g.lemma(i) in _REFERENCES))
        if references
        else set()
    )
    foreign = g.named(g.indices - referenced) - set(scope["named_tokens"])
    full = scope["full_governing_scope_candidate"] and not conditions and not foreign
    # An explicit second governing PP inside a reference cannot disappear merely
    # because the referenced object itself inherited the note's first scope.
    for i in referenced:
        for _, obj in g.pp(i, {"for", "to"}):
            if g.named(g.nominal(obj)) - set(scope["named_tokens"]):
                full = False
    scope["full_governing_scope_candidate"] = full
    return scope


def _nonoperative_container(g, root):
    if (
        g.lemma(root) in _NONOPERATIVE
        and g.tokens[root]["pos"] == "NOUN"
        and any(g.tokens[i]["text"] == ":" for i in g.children(root, {"punct"}))
    ):
        return True
    if g.lemma(root) != "be":
        return False
    return any(
        g.lemma(i) in _NONOPERATIVE
        and any(
            g.lemma(j) in {"test", "synthetic", "invent", "quote"}
            for j in g.children(i, {"amod", "compound"})
        )
        for i in g.children(root, {"attr", "acomp"})
    )


def _classify(g, literal, active, nonoperative):  # noqa: C901 - one closed dependency scope pass
    conditions, modality, quantities, references = _features(g, literal)
    unit = {
        **literal,
        "kind": "unknown",
        "scope": None,
        "scope_relation": "unresolved",
        "role_facts": [],
        "conditions": conditions,
        "modality": modality,
        "quantities": quantities,
        "references": references,
        "reference_closure": "pending_actual_reference_resolution",
        "unresolved": [],
        "exclusion_candidate": False,
    }
    if nonoperative:
        uncertain = (
            nonoperative.startswith("unclosed") or nonoperative == "untrusted_container"
        )
        unit.update(
            kind="unknown" if uncertain else "nonoperative_region",
            scope_relation="unresolved" if uncertain else "non_governing",
            unresolved=[nonoperative],
        )
        return unit, None, False
    roots = [i for i in g.indices if g.tokens[i]["head"] == i]
    if len(roots) != 1:
        unit["unresolved"] = ["no_complete_dependency_root"]
        return unit, None, False
    root = roots[0]
    if _nonoperative_container(g, root):
        unit.update(
            kind="unknown",
            unresolved=["nonoperative_container"],
            scope_relation="unresolved",
        )
        return unit, None, True
    if _global(g, root):
        unit.update(
            kind="global_governor",
            scope_relation="global_candidate",
            unresolved=["global_governing_scope_requires_discharge"],
        )
        return unit, None, False
    scope = _declaration(g, root, literal)
    if scope is not None:
        unit.update(kind="governing_declaration", scope=scope)
        full = scope["full_governing_scope_candidate"] and not conditions
        scope["full_governing_scope_candidate"] = full
        if not full:
            unit["unresolved"].append("unmodeled_governing_complement")
        return unit, deepcopy(scope) if full else None, False
    role = _role(g, root, literal, active)
    if role is not None:
        scope, facts = role
        if conditions:
            scope["full_governing_scope_candidate"] = False
            unit["unresolved"].append("conditional_role_scope_requires_discharge")
        unit.update(kind="role_assignment", scope=scope, role_facts=facts)
        if (
            active
            and not scope["inherited"]
            and _canonical(scope["target"]["text"])
            != _canonical(active["target"]["text"])
        ):
            active = None
        return unit, active, False
    scope = (
        _instruction_scope(g, root, literal, active, conditions, references)
        if _imperative(g, root)
        else None
    )
    if scope:
        full = scope["full_governing_scope_candidate"]
        unit.update(kind="reference" if references else "instruction", scope=scope)
        if not full:
            unit["unresolved"].append("conditional_or_cross_scope_instruction")
        return unit, active if full and scope["inherited"] else None, False
    if references:
        unit["kind"] = "reference"
    unit["unresolved"].append("unresolved_source_unit")
    return unit, None, False


def _cuts(body, windows, regions):
    boundaries = {0, len(body)}
    for start, end, annotation, _ in windows:
        boundaries.update({start, end})
        boundaries.update(
            start + s[key] for s in annotation["sentences"] for key in ("start", "end")
        )
    boundaries.update(match.end() for match in re.finditer(r"\n", body))
    boundaries.update(n for start, end, _ in regions for n in (start, end))
    ordered = sorted(boundaries)
    for first, last in zip(ordered, ordered[1:], strict=False):
        raw = body[first:last]
        if not raw.strip():
            yield first, last
            continue
        left = first + len(raw) - len(raw.lstrip())
        right = last - len(raw) + len(raw.rstrip())
        if first < left:
            yield first, left
        yield left, right
        if right < last:
            yield right, last


def _boundary_clear(body, offset):
    if offset in (0, len(body)):
        return True
    left = body[:offset].rstrip()
    return bool(
        left
        and left[-1] in ".!?"
        and (body[offset - 1].isspace() or body[offset].isspace())
    )


def source_scope(body, identity, windows, *, asked_topic):
    """Reconstruct all literal units and conservative scope candidates; no truth."""
    bound = _identity(body, identity)
    if (
        type(asked_topic) is not str
        or not asked_topic.strip()
        or len(asked_topic) > 512
    ):
        raise ValueError("Actual requested topic must be nonempty bounded text")
    asked_topic.encode("utf-8")
    validated = _windows(body, windows)
    regions = _regions(body)
    active = None
    container = False
    units = []
    for first, last in _cuts(body, validated, regions):
        literal = _literal(body, first, last)
        if not literal["text"].strip():
            units.append(
                {
                    **literal,
                    "kind": "separator",
                    "scope": None,
                    "scope_relation": "separator",
                    "role_facts": [],
                    "conditions": [],
                    "modality": [],
                    "quantities": [],
                    "references": [],
                    "reference_closure": "not_applicable_separator",
                    "unresolved": [],
                    "exclusion_candidate": False,
                }
            )
            continue
        start, end, annotation, _ = next(
            w for w in validated if w[0] <= first < last <= w[1]
        )
        graph = _Graph(body, start, annotation, first, last)
        nonoperative = next(
            (kind for left, right, kind in regions if first < right and left < last),
            None,
        )
        unit, active, new_container = _classify(
            graph, literal, active, "untrusted_container" if container else nonoperative
        )
        container |= new_container
        # Each independently captured edge must coincide with a literal sentence
        # boundary; a parser's local sentence partition cannot prove that itself.
        raw_window = body[start:end]
        first_content = start + len(raw_window) - len(raw_window.lstrip())
        last_content = end - len(raw_window) + len(raw_window.rstrip())
        if (first == first_content and not _boundary_clear(body, start)) or (
            last == last_content and not _boundary_clear(body, end)
        ):
            unit["unresolved"].append("capture_boundary")
            if unit["scope"]:
                unit["scope"]["full_governing_scope_candidate"] = False
            active = None
        if unit["scope"]:
            unit["scope_relation"] = _relation(
                unit["scope"]["target"], set(unit["scope"]["named_tokens"]), asked_topic
            )
        units.append(unit)
    blockers = [
        n
        for n, u in enumerate(units)
        if u["kind"] == "global_governor"
        or u["kind"] not in {"separator", "nonoperative_region"}
        and (u["scope"] is None or not u["scope"]["full_governing_scope_candidate"])
    ]
    for n, unit in enumerate(units):
        unit["id"] = f"u{n + 1}"
        unit["blocking_governors"] = [f"u{i + 1}" for i in blockers]
        unit["exclusion_candidate"] = (
            unit["scope_relation"] == "different_named_scope_candidate"
            and bool(unit["scope"] and unit["scope"]["full_governing_scope_candidate"])
            and not blockers
        )
    return {
        "contract": CONTRACT,
        "identity": bound,
        "body_sha256": bound["content_hash"],
        "body_length": len(body),
        "asked_topic": asked_topic,
        "capture_windows": [
            {
                "start": start,
                "end": end,
                "capture_sha256": record["capture_sha256"],
                "annotation_sha256": record["annotation_sha256"],
                "parser": deepcopy(record["parser"]),
            }
            for start, end, _, record in validated
        ],
        "units": units,
        "blocking_units": [f"u{i + 1}" for i in blockers],
        "reference_inventory_complete": False,
        "claim_semantics": "lossless_literal_units_with_unassessed_scope_candidates",
        "consumer_obligations": [
            {
                "kind": kind,
                "status": "pending_independent_discharge",
                "source_range": {"start": 0, "end": len(body)},
                "asked_topic": asked_topic,
            }
            for kind in (
                "independent_capture_origin",
                "operative_source_authority",
                "namespace_and_applicability_nli",
                "unknown_and_global_governors",
                "actual_required_reference_closure",
                "factual_nli_and_output_access_history",
            )
        ],
        "support_or_permissions": "NOT_ASSESSED",
    }


def validate_source_scope(record, body, identity, windows, *, asked_topic):
    """Replay against actual caller-held inputs, not producer-selected evidence."""
    try:
        _native(record)
        return type(record) is dict and _json(record) == _json(
            source_scope(body, identity, windows, asked_topic=asked_topic)
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
