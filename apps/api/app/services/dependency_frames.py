"""Pure request frames from validated dependencies, never model truth.

Field heads are a bounded ontology. Argument/modifier text stays literal and is
not reduced to a bare field; unclosed clauses and attachments remain unresolved.
"""

import re
from dataclasses import dataclass, replace
from typing import NamedTuple

META = frozenset(
    {
        "give",
        "list",
        "name",
        "identify",
        "state",
        "say",
        "tell",
        "provide",
        "supply",
        "explain",
        "describe",
        "include",
        "combine",
        "report",
        "specify",
        "present",
        "show",
        "quote",
    }
)
MODALS = frozenset(
    {
        "must",
        "may",
        "should",
        "can",
        "could",
        "would",
        "might",
        "shall",
        "cannot",
        "never",
        "not",
        "no",
    }
)
CONDITIONS = frozenset(
    {
        "if",
        "unless",
        "when",
        "without",
        "before",
        "after",
        "until",
        "except",
        "provided",
        "only",
    }
)
WHOLE = frozenset({"full", "whole", "complete", "entire", "all", "every", "ordered"})
GOVERNORS = frozenset(
    {
        "condition",
        "prohibition",
        "contingency",
        "exception",
        "restriction",
        "constraint",
        "dependency",
        "qualification",
        "applicability",
        "response",
        "handling",
        "limitation",
        "ban",
        "note",
        "convention",
        "prerequisite",
        "order",
    }
)
SCOPE_PREPS = frozenset({"for", "of", "in", "at", "during", "regarding", "to"})
PERFORM_LEMMAS = frozenset(
    {
        "perform",
        "do",
        "conduct",
        "execute",
        "carry",
        "run",
        "complete",
        "follow",
        "apply",
        "undertake",
        "handle",
        "rehearse",
        "practice",
    }
)
GOVERNS_LEMMAS = frozenset(
    {
        "govern",
        "control",
        "restrict",
        "prohibit",
        "require",
        "cover",
        "limit",
        "bind",
    }
)
CLAUSE_DEPS = frozenset({"ROOT", "conj", "ccomp", "xcomp", "advcl", "dep"})
CLAUSE_MODIFIER_DEPS = frozenset(
    {"acl", "relcl", "advcl", "ccomp", "xcomp", "parataxis"}
)
NOMINAL_DEPS = frozenset(
    {
        "det",
        "compound",
        "amod",
        "nmod",
        "nummod",
        "poss",
        "case",
        "advmod",
        "npadvmod",
    }
)
ARG_DEPS = frozenset(
    {"dobj", "obj", "attr", "nsubj", "nsubjpass", "csubj", "csubjpass"}
)
HEADS = {
    "lead": "owner",
    "leader": "owner",
    "owner": "owner",
    "deputy": "deputy",
    "quantity": "quantity",
    "count": "quantity",
    "number": "quantity",
    "capacity": "quantity",
    "allocation": "quantity",
    "limit": "quantity",
    "maximum": "quantity",
    "minimum": "quantity",
    "duration": "duration",
    "interval": "duration",
    "length": "duration",
    "location": "location",
    "place": "location",
    "venue": "location",
    "bay": "location",
    "desk": "location",
    "station": "location",
    "availability": "availability",
    "weekday": "weekday",
    "routine": "procedure",
    "procedure": "procedure",
    "step": "procedure",
    "instruction": "procedure",
    "process": "procedure",
    "method": "procedure",
    "protocol": "procedure",
    "sequence": "procedure",
    "exercise": "procedure",
    "width": "quantity",
    "amount": "quantity",
}


class Span(NamedTuple):
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class ConditionClause:
    """Request qualifier only. Its truth/applicability requires source proof."""

    operator: str
    evidence: Span
    predicate: Span
    subjects: tuple[Span, ...]
    negation: tuple[Span, ...]
    modality: tuple[Span, ...]
    token_indices: tuple[int, ...]
    complements: tuple[Span, ...] = ()


@dataclass(frozen=True)
class DependencyFrame:
    original: Span
    question: str
    kind: str
    topic: str
    attribute: str
    relation: str
    tokens: tuple[int, ...]
    heads: tuple[int, ...]
    scopes: tuple[Span, ...] = ()
    conditions: tuple[Span, ...] = ()
    modality: tuple[Span, ...] = ()
    units: tuple[Span, ...] = ()
    governors: tuple[Span, ...] = ()
    references: tuple[Span, ...] = ()
    order: tuple[Span, ...] = ()
    dependencies: tuple[int, ...] = ()
    errors: tuple[str, ...] = ()
    grammar: str = "dependency_frame"
    condition_ast: tuple[ConditionClause, ...] = ()
    source_workspace: str | None = None
    prepared_question: str = ""


class Graph:
    def __init__(self, raw, annotation):
        self.raw = raw
        self.ts = annotation["tokens"]
        self.recovered_field_heads = set()
        self.scope_continuations = {}
        self.children = [t["children"] for t in self.ts]
        self.sent = {
            i: n
            for n, s in enumerate(annotation["sentences"])
            for i in range(s["token_start"], s["token_end"])
        }
        self.predicates = {t["i"] for t in self.ts if self.is_predicate(t["i"])}
        # A coordinated sibling of a nominal head is nominal material even when
        # the tagger marks it VERB ("count, review time and location ...").
        self.predicates -= {
            i
            for i in self.predicates
            if self.ts[i]["dep"] == "conj"
            and self.ts[i]["head"] not in self.predicates
            and self.ts[self.ts[i]["head"]]["pos"] in {"NOUN", "PROPN"}
        }
        # Marked subordinate conditions qualify their governing request. They
        # are retained as AST, not emitted as independent requested facts.
        self.condition_heads = {
            i
            for i in self.predicates
            if self.ts[i]["dep"] == "advcl"
            and any(
                self.ts[c]["dep"] in {"mark", "advmod"} and self.low(c) in CONDITIONS
                for c in self.children[i]
            )
        }
        self.predicates -= self.condition_heads
        self.syntax = {
            t["i"]
            for t in self.ts
            if t["pos"] in {"PUNCT", "SPACE"}
            or t["dep"] == "cc"
            and t["text"].casefold() == "and"
        }

    def low(self, i):
        return self.ts[i]["text"].casefold()

    def lemma(self, i):
        return self.ts[i]["lemma"].casefold()

    def is_predicate(self, i):
        t = self.ts[i]
        if (
            self.lemma(i) in META
            and any(self.ts[c]["dep"] in {"dobj", "obj"} for c in self.children[i])
            and t["dep"] not in {"compound", "nmod", "amod"}
        ):
            return True
        if t["pos"] in {"PUNCT", "SPACE"} or t["dep"] not in CLAUSE_DEPS:
            return False
        children = [self.ts[c] for c in self.children[i]]
        return (
            t["dep"] == "ROOT"
            or self.lemma(i) in META
            or t["pos"] in {"VERB", "AUX"}
            or any(
                c["dep"] in {"nsubj", "nsubjpass", "aux", "auxpass", "csubj"}
                for c in children
            )
            or any(
                c["text"].casefold() in {"who", "what", "why", "where", "when", "how"}
                for c in children
            )
        )

    def subtree(self, i, *, prune=()):
        found = set()
        todo = [i]
        while todo:
            at = todo.pop()
            if at in found or at in prune:
                continue
            found.add(at)
            todo.extend(self.children[at])
        return found

    def local(self, i):
        return self.subtree(i, prune=self.predicates - {i})

    def span(self, indices):
        indices = sorted(indices)
        if not indices:
            return Span(0, 0, "")
        left, right = self.ts[indices[0]]["start"], self.ts[indices[-1]]["end"]
        return Span(left, right, self.raw[left:right])

    def text(self, indices):
        indices = sorted(set(indices))
        if not indices:
            return ""
        groups = []
        start = last = indices[0]
        for i in indices[1:]:
            if i != last + 1:
                groups.append(self.raw[self.ts[start]["start"] : self.ts[last]["end"]])
                start = i
            last = i
        groups.append(self.raw[self.ts[start]["start"] : self.ts[last]["end"]])
        return " ".join(groups).strip(" ,;?.!")

    def nominal(self, i):
        found = {i}
        todo = [i]
        while todo:
            at = todo.pop()
            for c in self.children[at]:
                t = self.ts[c]
                if (
                    t["dep"] in NOMINAL_DEPS
                    or t["dep"] == "punct"
                    and t["text"] in {"-", "–", "—"}
                    or (
                        t["dep"] in {"cc", "conj"}
                        and c > 0
                        and c + 1 < len(self.ts)
                        and (
                            self.ts[c - 1]["text"] == "-"
                            or self.ts[c + 1]["text"] == "-"
                        )
                    )
                ):
                    if c not in found:
                        found.add(c)
                        todo.append(c)
        return found

    def conjuncts(self, i):
        found = [i]
        for at in found:
            found.extend(
                c
                for c in self.children[at]
                if self.ts[c]["dep"] == "conj" and c not in self.predicates
            )
        return found

    def topic(self, indices):
        selected = sorted(indices)
        while selected and self.low(selected[0]) in {"the", "a", "an"}:
            selected.pop(0)
        return self.text(selected)

    def pp(self, i):
        result = []
        for p in self.children[i]:
            if self.ts[p]["dep"] not in {"prep", "dative"}:
                continue
            for obj in self.children[p]:
                if self.ts[obj]["dep"] in {"pobj", "pcomp"}:
                    result.append((p, obj))
        return result

    def direct_scopes(self, i):
        result = []
        pending = [i]
        seen = set()
        absorbed = set()
        while pending:
            at = pending.pop()
            if at in seen:
                continue
            seen.add(at)
            for p, obj in self.pp(at):
                if any(
                    self.lemma(c) == "workspace"
                    for other_p, other_obj in self.pp(at)
                    if other_p == p
                    for c in self.nominal(other_obj)
                ):
                    continue
                obj_ids = self.scope_nominal(obj)
                is_workspace = any(self.lemma(c) == "workspace" for c in obj_ids)
                is_unit = (
                    self.low(p) == "in"
                    and self.lemma(obj) in {"second", "minute", "hour"}
                    and not any(self.ts[c]["pos"] == "PROPN" for c in obj_ids)
                )
                if (
                    self.low(p) in SCOPE_PREPS
                    and not is_workspace
                    and not is_unit
                    and not self.reference(obj_ids)
                    and p not in absorbed
                ):
                    # Clause material anywhere inside the covered span belongs
                    # to the request complex; a conjunct with a declared field
                    # head is a requested sibling, not entity-name material.
                    clause_heads = {
                        i
                        for i in self.subtree(p)
                        if i != obj
                        and (
                            self.ts[i]["dep"] in CLAUSE_MODIFIER_DEPS
                            or (
                                self.ts[i]["dep"] == "conj"
                                and _head_kind(self, i)[0] != "generic"
                            )
                        )
                    }
                    result.append(
                        (
                            obj_ids,
                            self.subtree(
                                p, prune=self.recovered_field_heads | clause_heads
                            )
                            | self.scope_continuations.get(obj, set()),
                        )
                    )
                    absorbed.update(
                        c
                        for c in obj_ids
                        if self.ts[c]["dep"] == "prep" and self.low(c) == "of"
                    )
                pending.append(obj)
        return result

    def scope_nominal(self, head):
        """A declared nested 'of' PP is part of the literal entity qualifier."""
        ids = self.nominal(head) | self.scope_continuations.get(head, set())
        for p, obj in self.pp(head):
            if self.low(p) == "of":
                ids |= {p} | self.scope_nominal(obj)
        return ids

    def expletive(self, i):
        t = self.ts[i]
        return (
            self.low(i) == "there"
            and t["dep"] == "expl"
            and t["tag"] == "EX"
            and t["head"] != i
            and self.ts[t["head"]]["pos"] in {"AUX", "VERB"}
        )

    def reference(self, indices):
        conditional = set().union(*(self.subtree(h) for h in self.condition_heads))
        return [
            i
            for i in sorted(indices)
            if not self.expletive(i)
            and (
                self.ts[i]["dep"] == "poss"
                or self.ts[i]["tag"] in {"PRP", "PRP$"}
                or self.ts[i]["pos"] == "PRON"
                and self.ts[i]["tag"] != "DT"
                and (self.ts[i]["tag"] not in {"WP", "WP$"} or i in conditional)
                or self.low(i)
                in {"its", "their", "that", "those", "each", "it", "this", "these"}
            )
        ]

    def qualifier_spans(self, indices, words):
        result = []
        for i in sorted(indices):
            if self.low(i) in words:
                if words is CONDITIONS and (
                    self.ts[i]["dep"] not in {"mark", "prep", "advmod"}
                    or (i and self.ts[i - 1]["text"] == "-")
                    or (i + 1 < len(self.ts) and self.ts[i + 1]["text"] == "-")
                ):
                    continue
                result.append(
                    self.span((self.subtree(self.ts[i]["head"]) & set(indices)) | {i})
                    if words is CONDITIONS
                    else self.span({i})
                )
        return tuple(dict.fromkeys(result))

    def condition_clauses(self, indices):
        selected = set(indices)
        result = []
        for head in sorted(self.condition_heads):
            ids = self.subtree(head, prune=self.predicates - {head})
            while ids and self.ts[max(ids)]["dep"] in {"cc", "punct"}:
                ids.remove(max(ids))
            if not ids <= selected:
                continue
            markers = [
                c
                for c in self.children[head]
                if self.ts[c]["dep"] in {"mark", "advmod"} and self.low(c) in CONDITIONS
            ]
            subjects = [
                c
                for c in self.children[head]
                if self.ts[c]["dep"] in {"nsubj", "nsubjpass", "csubj"}
            ]
            if not subjects and any(self.expletive(c) for c in self.children[head]):
                subjects = [
                    c for c in self.children[head] if self.ts[c]["dep"] == "attr"
                ]
            if len(markers) != 1 or not subjects:
                continue
            result.append(
                ConditionClause(
                    self.low(markers[0]),
                    self.span(ids),
                    self.span({head}),
                    tuple(self.span(self.nominal(c)) for c in subjects),
                    tuple(
                        self.span({c})
                        for c in ids
                        if self.low(c) in {"no", "not", "never"}
                    ),
                    tuple(
                        self.span({c})
                        for c in ids
                        if self.low(c) in MODALS - {"no", "not", "never"}
                    ),
                    tuple(sorted(ids)),
                    tuple(
                        self.span(self.subtree(c) & ids)
                        for c in self.children[head]
                        if self.ts[c]["dep"]
                        not in {
                            "mark",
                            "nsubj",
                            "nsubjpass",
                            "csubj",
                            "neg",
                            "aux",
                            "auxpass",
                            "punct",
                            "cc",
                        }
                        and c in ids
                    ),
                )
            )
        for p in sorted(selected):
            if self.low(p) not in {"with", "without"} or self.ts[p]["dep"] != "prep":
                continue
            objects = [c for c in self.children[p] if self.ts[c]["dep"] == "pobj"]
            ids = self.subtree(p)
            if (
                len(objects) != 1
                or not ids <= selected
                or not any(self.low(c) in {"no", "not"} for c in ids)
            ):
                continue
            obj = objects[0]
            result.append(
                ConditionClause(
                    self.low(p),
                    self.span(ids),
                    self.span({obj}),
                    (self.span(self.nominal(self.ts[p]["head"])),),
                    tuple(
                        self.span({c})
                        for c in ids
                        if self.low(c) in {"no", "not", "never"}
                    ),
                    (),
                    tuple(sorted(ids)),
                )
            )
        return tuple(result)

    def literal_units(self, indices):
        found = []
        pattern = (
            r"(?<!\w)\d+(?:[.,]\d+)*(?:\s+[\wµμ]+(?:-[\wµμ]+)*(?:\s*/\s*[\wµμ]+)?)?"
        )
        for m in re.finditer(pattern, self.raw):
            covered = {
                t["i"]
                for t in self.ts
                if m.start() <= t["start"] and t["end"] <= m.end()
            }
            if covered and covered <= set(indices):
                found.append(Span(m.start(), m.end(), self.raw[m.start() : m.end()]))
        return tuple(found)

    def external_references(self, indices):
        return tuple(
            self.span(self.subtree(obj))
            for i in indices
            for p, obj in self.pp(i)
            if self.low(p) == "from" and p in indices
        )


ROLE_COLLECTIVES = frozenset({"role", "staffing", "staff", "crew", "personnel"})
DURATION_TIME_MODIFIERS = frozenset(
    {
        "dwell",
        "review",
        "preview",
        "observation",
        "reconciliation",
        "comparison",
    }
)


def _role_collective(g, head):
    """Bare collective role nouns request the declared session role pair.

    Only a collective (plural noun or collective head) without an explicit
    lead/deputy/owner qualifier expands; a qualified or singular role head is
    not a declared-catalogue request.
    """
    lemma = g.lemma(head)
    if lemma not in ROLE_COLLECTIVES:
        return False
    nominal = g.nominal(head)
    if any(g.lemma(i) in {"lead", "leader", "deputy", "owner"} for i in nominal):
        return False
    if any(g.low(i) in {"which", "what"} for i in nominal):
        return False
    if not any(
        g.lemma(i) in {"activity", "session"}
        or g.low(i).endswith(("-scoped", "-session"))
        for i in nominal - {head}
    ):
        return False
    return lemma != "role" or "Number=Plur" in (g.ts[head].get("morph") or "")


def _head_kind(g, head, phrase=None):
    lemma = g.lemma(head)
    if phrase is None:
        phrase = g.nominal(head)
    if _role_collective(g, head):
        return "role_pair", None
    if lemma == "role":
        return "generic", "role_catalogue_not_defined"
    if lemma in {"all", "every", "each"} and any(
        g.low(p) == "of" for p, _ in g.pp(head)
    ):
        return "procedure", None
    if lemma == "time":
        if any(g.lemma(i) == "start" for i in phrase):
            return "start_time", None
        if any(
            g.lemma(i) in DURATION_TIME_MODIFIERS
            or g.lemma(i).endswith("ing")
            and g.ts[i]["pos"] == "VERB"
            for i in phrase
        ):
            return "duration", None
        return "generic", "ambiguous_temporal_attribute"
    return HEADS.get(
        lemma, "generic"
    ), None if lemma in HEADS else "unknown_requested_head"


def _scope_candidates(g, head, predicate, prior):
    direct = g.direct_scopes(head)
    at = head
    while g.ts[at]["dep"] == "conj" and g.ts[at]["head"] not in g.predicates:
        at = g.ts[at]["head"]
        if not direct:
            direct.extend(g.direct_scopes(at))
    if not direct:
        _sibling_scopes(g, at, direct)
    direct.extend(g.direct_scopes(predicate))
    parent = g.ts[predicate]["head"]
    if parent != predicate and parent in g.predicates:
        direct.extend(g.direct_scopes(parent))
    if not direct and prior:
        return [(set(prior[0]), set(prior[0]))]
    return direct


def _sibling_scopes(g, at, direct):
    """A postmodifier on a coordinated NP group scopes each requested
    sibling. It remains literal; distinct fronted/direct scopes still
    conflict downstream."""
    for sibling in g.conjuncts(at):
        direct.extend(g.direct_scopes(sibling))
        if g.ts[sibling]["pos"] == "VERB" and sibling not in g.predicates:
            for obj in g.children[sibling]:
                if g.ts[obj]["dep"] in {"dobj", "obj"}:
                    direct.extend(g.direct_scopes(obj))
                    for conj in g.conjuncts(obj):
                        if conj != obj:
                            direct.extend(g.direct_scopes(conj))


def _named_subject(g, head):
    roots = [c for c in g.children[head] if g.ts[c]["dep"] in {"compound", "nmod"}]
    ids = set().union(*(g.nominal(c) for c in roots)) if roots else set()
    return ids if any(g.ts[i]["pos"] == "PROPN" for i in ids) else set()


def _close_scope(g, candidates):
    unique = []
    owned = set()
    for nominal, covered in candidates:
        owned |= covered
        if nominal and not any(g.topic(nominal) == g.topic(old) for old in unique):
            unique.append(nominal)
    errors = []
    if not unique:
        errors.append("missing_explicit_scope")
    elif len(unique) > 1:
        errors.append("competing_explicit_scopes")
    for ids in unique:
        if any(g.ts[i]["dep"] in {"acl", "relcl"} for i in ids):
            errors.append("unresolved_scope_qualification")
        if any(
            g.low(i) in SCOPE_PREPS | {"and", "or", "plus", "then"}
            and not (g.low(i) == "of" and g.ts[i]["dep"] == "prep")
            for i in ids
        ):
            # Even a well-formed model graph cannot make a raw relational or
            # coordination marker disappear into a compound entity name.
            errors.append("unclosed_raw_scope_relation")
    if any(
        g.ts[i]["dep"] == "conj" and g.ts[g.ts[i]["head"]]["pos"] in {"NOUN", "PROPN"}
        for i in owned
    ):
        errors.append("unresolved_coordinated_entity_scope")
    if any(g.ts[i]["dep"] in {"acl", "relcl"} for i in owned):
        errors.append("unclosed_scope_clause")
    return (
        g.topic(unique[0]) if len(unique) == 1 else "",
        tuple(g.span(i) for i in unique),
        owned,
        errors,
        unique,
    )


def _np_adjuncts(g, head, nominal, kind, scopes, errors):
    governors = []
    owned = set(nominal)
    property_owned = set(nominal)
    adjuncts = []
    units = []
    reference_ids = set(g.reference(nominal))
    for p, obj in g.pp(head):
        ids = g.subtree(p, prune=g.predicates | g.recovered_field_heads)
        if g.lemma(p) == "include" or g.low(p) == "with":
            heads = g.conjuncts(obj)
            governors.extend(g.span(g.nominal(h)) for h in heads)
            adjuncts.append(ids)
            if (
                kind != "procedure"
                or any(g.low(i) == "from" for i in ids)
                or any(g.ts[i]["dep"] in {"acl", "relcl"} for i in ids)
                or any(g.ts[i]["pos"] == "PROPN" for i in ids)
            ):
                errors.append("unresolved_required_governor_or_reference")
        elif g.low(p) == "in" and kind in {"quantity", "duration"}:
            units.append(g.span(g.subtree(obj)))
            owned |= ids
            property_owned |= ids
            if g.lemma(obj) in {"second", "minute", "hour"} and not any(
                g.ts[i]["pos"] == "PROPN" for i in g.nominal(obj)
            ):
                # Only a declared unit head can separate a literal measurement
                # request from a namespace. No conversion/equivalence follows.
                scopes = [x for x in scopes if x[1] != g.subtree(p)]
            else:
                errors.append("unresolved_unit_or_scope_argument")
        else:
            owned |= ids
            reference_ids.update(g.reference(g.subtree(obj)))
            if g.low(p) not in SCOPE_PREPS:
                property_owned |= ids
                errors.append("unclassified_nominal_argument")
    return owned, property_owned, governors, adjuncts, units, reference_ids, scopes


def _np_frame(g, predicate, head, prior, *, nominal_override=None, extra_scopes=None):
    nominal = g.nominal(head) if nominal_override is None else set(nominal_override)
    kind, error = _head_kind(g, head, nominal)
    errors = [error] if error else []
    scopes = _scope_candidates(g, head, predicate, prior)
    if extra_scopes:
        scopes.extend(extra_scopes)
    named = _named_subject(g, head)
    if named:
        scopes.append((named, named))
    owned, property_owned, governors, adjuncts, units, reference_ids, scopes = (
        _np_adjuncts(g, head, nominal, kind, scopes, errors)
    )
    owned, property_owned = _predicate_np_adjuncts(
        g, predicate, kind, owned, property_owned, governors, adjuncts, units
    )
    topic, scope_refs, scope_owned, scope_errors, unique = _close_scope(g, scopes)
    owned |= scope_owned
    errors.extend(scope_errors)
    refs = sorted(reference_ids)
    reference_spans = tuple(
        dict.fromkeys(
            g.span(g.nominal(g.ts[i]["head"] if g.ts[i]["dep"] == "det" else i))
            for i in refs
        )
    )
    entity_reference = (
        bool(refs)
        and kind
        in {
            "owner",
            "deputy",
            "procedure",
            "quantity",
            "duration",
            "location",
            "start_time",
            "weekday",
        }
        and len(unique) == 1
        and all(g.low(i) == "its" for i in refs)
    )
    if refs and not entity_reference:
        errors.append("unresolved_reference_or_dependent_attribute")
    if kind == "procedure" and not any(g.lemma(i) in WHOLE for i in nominal):
        errors.append("procedure_extent_not_declared")
    # Conditions attached to the request predicate apply to every coordinated
    # requested field. Keep their full syntax, subjects and negative operators.
    owned, condition_ast, conditions, modals = _np_conditions(
        g, predicate, owned, errors
    )
    if any(g.ts[i]["dep"] in {"acl", "relcl"} for i in owned):
        errors.append("unclosed_nominal_clause")
    # Keep the full qualified property; a field label never consumes modifiers.
    property_text = g.text(property_owned)
    suffix = "".join(", " + g.text(ids) for ids in adjuncts)
    for ids in adjuncts:
        owned |= ids
    reference_spans = tuple(
        dict.fromkeys(reference_spans + g.external_references(owned))
    )
    units = tuple(dict.fromkeys(tuple(units) + g.literal_units(owned)))
    question = (
        f"Who is {property_text}"
        if kind in {"owner", "deputy"}
        else f"What is {property_text}"
    ) + suffix
    if topic and not named and (not refs or entity_reference):
        question = f"For {topic}, " + question[0].lower() + question[1:]
    if conditions:
        question += ", " + ", ".join(s.text for s in conditions)
    prepared_question = question + "?"
    if errors:
        question = g.text(g.local(predicate))
    full = g.span(owned)
    frame = DependencyFrame(
        full,
        question + "?",
        kind,
        topic,
        property_text,
        g.lemma(head),
        tuple(sorted(owned)),
        (predicate, head),
        scope_refs,
        conditions,
        modals,
        units,
        tuple(governors),
        reference_spans,
        errors=tuple(dict.fromkeys(errors)),
        grammar="explicit_entity_attribute"
        if entity_reference
        else "requested_np_head",
        condition_ast=condition_ast,
        prepared_question=prepared_question,
    )
    return frame, unique


def _wh_tokens(g, predicate):
    return [
        i
        for i in g.local(predicate)
        if g.low(i) in {"who", "what", "which", "where", "when", "how", "why"}
    ]


def _wh_question(g, predicate, owned):
    content = {
        i
        for i in owned
        if g.ts[i]["pos"] != "SPACE"
        and not (g.ts[i]["dep"] == "cc" and g.ts[i]["head"] == predicate)
        and not (
            g.ts[i]["dep"] == "punct"
            and g.ts[i]["head"] == predicate
            and g.ts[i]["text"] in {".", "?", "!", ";", ","}
        )
    }
    ordered = sorted(content)
    wh = [
        i
        for i in ordered
        if g.low(i) in {"who", "what", "which", "where", "when", "how"}
    ]
    aux = [
        i
        for i in g.children[predicate]
        if g.ts[i]["dep"] in {"aux", "auxpass"} and i in content
    ]
    subjects = [
        i
        for i in g.children[predicate]
        if g.ts[i]["dep"] in {"nsubj", "nsubjpass"} and g.low(i) != "who"
    ]
    # Embedded WH retains the actual auxiliary rather than replacing its tense,
    # aspect, modality, passive voice or predicate with a generic scalar claim.
    embedded = (
        g.ts[predicate]["dep"] in {"ccomp", "xcomp"}
        and g.lemma(g.ts[predicate]["head"]) in META
    )
    if embedded and not aux and g.lemma(predicate) == "be" and subjects:
        aux = [predicate]
    if embedded and wh and aux and subjects and min(aux) > min(subjects):
        subject = set().union(*(g.nominal(i) for i in subjects))
        front = {wh[0]} | g.nominal(wh[0])
        if front & subject:
            return g.text(content) + "?"
        pieces = [
            g.text(front),
            g.text(aux),
            g.text(subject),
            g.text(content - front - set(aux) - subject),
        ]
        return " ".join(x for x in pieces if x) + "?"
    return g.text(content) + "?"


def _scope_pair(g, i):
    """(nominal, covered) — clause children of the scope head stay with
    their governing clause, not with the entity span."""
    prune = {c for c in g.children[i] if g.ts[c]["dep"] in CLAUSE_MODIFIER_DEPS}
    return g.nominal(i), g.subtree(i, prune=prune)


def _copular_complements(g, predicate):
    """Nominal/adjectival complement heads of a copular clause, incl. pp objects."""
    heads = [
        c
        for c in g.children[predicate]
        if g.ts[c]["dep"] in ARG_DEPS | {"acomp", "oprd"}
        and g.low(c) not in {"who", "what", "which"}
    ]
    out = list(heads)
    for c in heads:
        out.extend(obj for _, obj in g.pp(c))
    return out


def _copular_scope_pps(g, predicate):
    """Prep objects under the copula or its complements, as (prep, obj) pairs."""
    pairs = list(g.pp(predicate))
    for c in g.children[predicate]:
        if g.ts[c]["dep"] in {"acomp", "oprd", "attr"}:
            pairs.extend(g.pp(c))
    return pairs


def _clause_extent_pps(g, predicate, local):
    """from-start/to-finish adjuncts anywhere in the local verbal complex."""
    verbs = [i for i in local if g.ts[i]["pos"] == "VERB" or i == predicate]
    return any(
        g.low(p) == "from" and g.lemma(obj) == "start"
        for v in verbs
        for p, obj in g.pp(v)
    ) and any(
        g.low(p) == "to" and g.lemma(obj) == "finish"
        for v in verbs
        for p, obj in g.pp(v)
    )


def _role_targets(g, ids):
    """Coordinated declared role heads inside a nominal complement."""
    heads = set()
    for i in ids:
        for h in g.conjuncts(i):
            kind, _ = _head_kind(g, h)
            if kind in {"owner", "deputy", "role_pair"}:
                heads.add(h)
    return sorted(heads)


def _who_role_meaning(g, predicate, prior, local, low, args, scopes, errors):
    if "who" not in low or g.lemma(predicate) not in {
        "lead",
        "own",
        "manage",
        "run",
        "deputize",
    }:
        return None
    kind = "deputy" if g.lemma(predicate) == "deputize" else "owner"
    objs = [i for i in args if g.ts[i]["dep"] in {"dobj", "obj"}]
    scopes.extend(_scope_pair(g, i) for i in objs)
    return kind, "", [], scopes


def _when_availability_meaning(g, predicate, prior, local, low, args, scopes, errors):
    if "when" not in low or not any(
        g.lemma(i) in {"available", "availability"} for i in local
    ):
        return None
    return "availability", g.text(local), [], scopes


def _where_meaning(g, predicate, prior, local, low, args, scopes, errors):
    if "where" not in low:
        return None
    attribute = " ".join(g.text(g.nominal(i)) for i in args)
    if not scopes and not prior:
        scopes.extend(_scope_pair(g, i) for i in args)
    return "location", attribute, [], scopes


def _how_long_meaning(g, predicate, prior, local, low, args, scopes, errors):
    if "how" not in low or "long" not in low:
        return None
    attribute = " ".join(g.text(g.nominal(i)) for i in args)
    if not scopes and not prior:
        scopes.extend(_scope_pair(g, i) for i in args)
    return "duration", attribute, [], scopes


def _how_many_meaning(g, predicate, prior, local, low, args, scopes, errors):
    if "how" not in low or "many" not in low:
        return None
    many = next(i for i in local if g.low(i) == "many")
    unit_head = g.ts[many]["head"]
    unit = g.nominal(unit_head) - {i for i in local if g.low(i) in {"how", "many"}}
    return "quantity", g.text(unit), [g.span(unit)], scopes


def _how_procedure_meaning(g, predicate, prior, local, low, args, scopes, errors):
    if "how" not in low or not (
        any(g.lemma(i) in WHOLE for i in local)
        or _clause_extent_pps(g, predicate, local)
        or any(
            g.lemma(i) in PERFORM_LEMMAS and g.ts[i]["pos"] == "VERB"
            for i in local
            if g.low(i) not in {"who", "what", "which", "where", "when", "how", "why"}
        )
    ):
        return None
    if not scopes and not prior:
        scopes.extend(_scope_pair(g, i) for i in args)
    return "procedure", g.text(local), [], scopes


def _who_copular_meaning(g, predicate, prior, local, low, args, scopes, errors):
    if "who" not in low or g.lemma(predicate) != "be":
        return None
    role_heads = _role_targets(g, _copular_complements(g, predicate))
    if not role_heads:
        return None
    kinds = {_head_kind(g, h)[0] for h in role_heads}
    kind = (
        "role_pair"
        if kinds == {"owner", "deputy"} or "role_pair" in kinds
        else "owner"
        if "owner" in kinds
        else "deputy"
    )
    if not scopes:
        for prep, obj in _copular_scope_pps(g, predicate):
            if g.low(prep) in {"at", "for", "of"}:
                scopes.append(_scope_pair(g, obj))
    return kind, g.text(g.nominal(role_heads[0])), [], scopes


def _what_nominal_meaning(g, predicate, prior, local, low, args, scopes, errors):
    if "what" not in low or g.lemma(predicate) not in {"be", "apply", "is"}:
        return None
    complements = [
        c
        for c in g.children[predicate]
        if g.ts[c]["dep"] in ARG_DEPS | {"acomp", "oprd"}
        and g.low(c) not in {"who", "what", "which"}
    ]
    kind = "generic"
    attribute = ""
    if complements:
        head_kind, _ = _head_kind(g, complements[0])
        kind = head_kind
        attribute = g.text(g.nominal(complements[0]))
    if kind == "generic":
        errors.append("unknown_requested_head")
        return "generic", attribute, [], scopes
    if not scopes and not prior:
        for _prep, obj in g.pp(predicate):
            scopes.append(_scope_pair(g, obj))
    return kind, attribute, [], scopes


def _what_governs_meaning(g, predicate, prior, local, low, args, scopes, errors):
    if (
        "what" not in low
        or g.lemma(predicate) not in GOVERNS_LEMMAS
        or not any(
            g.ts[c]["dep"] == "nsubj" and g.low(c) == "what"
            for c in g.children[predicate]
        )
    ):
        return None
    objects = [c for c in g.children[predicate] if g.ts[c]["dep"] in {"dobj", "obj"}]
    attribute = " ".join(g.text(g.nominal(i)) for i in objects)
    return "procedure", attribute, [], scopes


_WH_MEANINGS = (
    _who_role_meaning,
    _when_availability_meaning,
    _where_meaning,
    _how_long_meaning,
    _how_many_meaning,
    _how_procedure_meaning,
    _who_copular_meaning,
    _what_nominal_meaning,
    _what_governs_meaning,
)


def _wh_meaning(g, predicate, prior, local, low, args, scopes, errors):
    for meaning in _WH_MEANINGS:
        result = meaning(g, predicate, prior, local, low, args, scopes, errors)
        if result is not None:
            return result
    errors.append("unknown_interrogative_frame")
    return "generic", "", [], scopes


def _copular_nominal(g, predicate, args, cues, prior):
    if g.lemma(predicate) != "be":
        return None
    if any(g.low(i) in {"when", "where", "how"} for i in cues):
        return None
    candidates = [
        i for i in args if _head_kind(g, i)[0] != "generic" or g.lemma(i) == "role"
    ]
    if len(candidates) != 1:
        return None
    g.syntax.add(predicate)
    g.syntax.update(cues)
    return _np_frame(g, predicate, candidates[0], prior)


def _wh_frame(g, predicate, prior, *, inherited_who=False):
    local, cues, low = _wh_local(g, predicate, inherited_who)
    modals = g.qualifier_spans(local, MODALS)
    condition_ast = g.condition_clauses(local)
    conditions = tuple(c.evidence for c in condition_ast)
    conditional_tokens = (
        set().union(*(set(c.token_indices) for c in condition_ast))
        if condition_ast
        else set()
    )
    request_modals = g.qualifier_spans(local - conditional_tokens, MODALS)
    args = [
        c
        for c in g.children[predicate]
        if g.ts[c]["dep"] in ARG_DEPS and g.low(c) not in {"who", "what", "which"}
    ]
    errors = []
    scopes = _wh_scopes(g, predicate, low, args)
    attribute = ""
    units = []
    kind = "generic"
    if "why" in low:
        errors.append("unknown_why_request")
    elif request_modals or g.qualifier_spans(
        local - conditional_tokens - set(cues), CONDITIONS
    ):
        errors.append("unresolved_condition_or_modality")
    else:
        nominal = _copular_nominal(g, predicate, args, cues, prior)
        if nominal is not None:
            return nominal
        kind, attribute, units, scopes = _wh_meaning(
            g, predicate, prior, local, low, args, scopes, errors
        )
    if not scopes and prior:
        scopes = [(set(prior[0]), set(prior[0]))]
    topic, scope_refs, scope_owned, scope_errors, unique = _close_scope(g, scopes)
    if kind != "generic":
        errors.extend(scope_errors)
    owned = local | scope_owned
    refs = [
        i
        for i in local
        if g.ts[i]["dep"] == "poss"
        or g.low(i) in {"that", "their", "its", "it", "each"}
    ]
    # An explicit unique entity target in the coordinated request can resolve
    # singular subject "it". This is entity grammar, not a data-value edge.
    entity_reference = (
        refs
        and all(
            g.low(i) == "it" and g.ts[i]["dep"] in {"nsubj", "nsubjpass"} for i in refs
        )
        and len(prior) == 1
    )
    if refs and not entity_reference:
        # "that role" re-mentions the declared session role pair; it is a
        # bound dependent reference, not a new catalogue request.
        role_bound = all(
            g.low(i) in {"that", "its", "their", "this", "the"}
            and g.lemma(g.ts[i]["head"]) == "role"
            for i in refs
        ) and bool(prior or scopes)
        if not role_bound:
            errors.append("unresolved_reference_or_dependent_attribute")
    question = _wh_question(g, predicate, local)
    if inherited_who:
        question = "Who " + question[0].lower() + question[1:]
    if (
        topic
        and scope_refs
        and not any(
            {
                i
                for i in local
                if s.start <= g.ts[i]["start"] and g.ts[i]["end"] <= s.end
            }
            for s in scope_refs
        )
    ):
        question = f"For {topic}, " + question[0].lower() + question[1:]
    frame = DependencyFrame(
        g.span(local),
        question,
        kind,
        topic,
        attribute or g.lemma(predicate),
        g.ts[predicate]["text"],
        tuple(sorted(owned)),
        (predicate,),
        scope_refs,
        conditions,
        modals,
        tuple(dict.fromkeys(tuple(units) + g.literal_units(owned))),
        references=tuple(
            g.span(g.nominal(g.ts[i]["head"] if g.ts[i]["dep"] == "det" else i))
            for i in refs
        ),
        errors=tuple(dict.fromkeys(errors)),
        grammar="interrogative_dependency_frame",
        condition_ast=condition_ast,
    )
    return frame, unique


def _generic(g, predicate, reason):
    ids = g.local(predicate)
    refs = [
        i
        for i in ids
        if g.ts[i]["dep"] == "poss"
        or g.low(i) in {"that", "their", "its", "it", "each"}
    ]
    return DependencyFrame(
        g.span(ids),
        g.text(ids) + "?",
        "generic",
        "",
        "",
        g.lemma(predicate),
        tuple(sorted(ids)),
        (predicate,),
        conditions=g.qualifier_spans(ids, CONDITIONS),
        modality=g.qualifier_spans(ids, MODALS),
        units=g.literal_units(ids),
        references=tuple(g.span(g.nominal(i)) for i in refs)
        + g.external_references(ids),
        errors=(reason,),
        grammar="unresolved_predicate",
    )


def _order_targets(g, frames):
    result = []
    for t in g.ts:
        if t["text"].casefold() != "then" or t["dep"] not in {"advmod", "cc"}:
            continue
        later = [
            (n, f)
            for n, f in enumerate(frames)
            if f.heads
            and max(f.heads) > t["i"]
            and g.sent[max(f.heads)] == g.sent[t["i"]]
        ]
        earlier = [
            f
            for f in frames
            if f.heads
            and max(f.heads) < t["i"]
            and g.sent[max(f.heads)] == g.sent[t["i"]]
        ]
        if later and earlier:
            target = min(later, key=lambda item: max(item[1].heads))[0]
            result.append((target, t["i"]))
    return result


def _bind_relations(g, frames):
    for target, index in _order_targets(g, frames):
        f = frames[target]
        frames[target] = replace(
            f,
            order=f.order + (g.span({index}),),
            tokens=tuple(sorted(set(f.tokens) | {index})),
        )
    for n, f in enumerate(frames):
        if f.kind != "availability" or not f.references:
            continue
        text = " ".join(r.text for r in f.references).casefold()
        if any(
            re.search(rf"\b{word}\b", text) for word in ("its", "their", "it", "each")
        ):
            continue
        if not re.search(
            r"\b(?:that\s+(?:role|person|owner)|lead|deputy|owner)\b", text
        ):
            continue
        prior = [
            (i, p)
            for i, p in enumerate(frames[:n])
            if p.kind in {"owner", "deputy"} and not p.errors
        ]
        if re.search(r"\bdeputy\b", text):
            prior = [(i, p) for i, p in prior if p.kind == "deputy"]
        elif re.search(r"\b(?:lead|owner)\b", text):
            prior = [(i, p) for i, p in prior if p.kind == "owner"]
        if len(prior) != 1:
            continue
        index, parent = prior[0]
        errors = tuple(
            e
            for e in f.errors
            if e
            not in {
                "unresolved_reference_or_dependent_attribute",
                "missing_explicit_scope",
            }
        )
        prepared = f.prepared_question or f.question
        if not all(
            s.text in prepared
            for group in (f.conditions, f.modality, f.units, f.governors, f.references)
            for s in group
        ):
            errors += ("prepared_question_missing_qualifier",)
        frames[n] = replace(
            f,
            dependencies=(index,),
            errors=errors,
            topic=f.topic or parent.topic,
            scopes=f.scopes or parent.scopes,
            question=prepared,
            grammar="explicit_prior_role_attribute",
        )
    return frames


def _predicate_frames(g, predicate, prior):
    frames = []
    local = g.local(predicate)
    nominal_wh = _nominal_wh_frames(g, predicate, prior)
    if nominal_wh is not None:
        return nominal_wh
    parent = g.ts[predicate]["head"]
    if (
        g.ts[predicate]["dep"] == "conj"
        and g.lemma(predicate) in {"lead", "deputize", "own", "manage", "run"}
        and any(g.low(i) == "who" for i in _wh_tokens(g, parent))
        and not _wh_tokens(g, predicate)
    ):
        return _inherited_who_frame(g, predicate, parent, prior)
    if _wh_tokens(g, predicate):
        return _wh_dispatch(g, predicate, prior)
    return _request_frames(g, predicate, local, frames, prior)


def _wh_dispatch(g, predicate, prior):
    frames = []
    if g.lemma(predicate) in META:
        # A WH clause embedded under a request verb: the request verb is
        # syntax, the embedded clause carries the question.
        wh_child = [
            c
            for c in g.children[predicate]
            if g.ts[c]["dep"] in CLAUSE_MODIFIER_DEPS | {"conj"} and _wh_tokens(g, c)
        ]
        if wh_child:
            g.syntax.add(predicate)
            frame, scopes = _wh_frame(g, wh_child[0], prior)
            if scopes and not frame.errors:
                prior = scopes
            return [frame], prior
    frame, scopes = _wh_frame(g, predicate, prior)
    frames.append(frame)
    if scopes and not frame.errors:
        prior = scopes
    return frames, prior


def _request_frames(g, predicate, local, frames, prior):
    first_person_need = (
        g.lemma(predicate) == "need"
        and all(
            g.low(c) in {"i", "we"}
            for c in g.children[predicate]
            if g.ts[c]["dep"] == "nsubj"
        )
        and any(g.ts[c]["dep"] in {"dobj", "obj"} for c in g.children[predicate])
    )
    meta = g.lemma(predicate) in META or first_person_need
    passive = g.lemma(predicate) in {"need", "require", "request"} and any(
        g.ts[c]["dep"] == "nsubjpass" for c in g.children[predicate]
    )
    conditional_tokens = (
        set().union(*(set(c.token_indices) for c in g.condition_clauses(local)))
        if g.condition_clauses(local)
        else set()
    )
    if (meta or passive) and not g.qualifier_spans(local - conditional_tokens, MODALS):
        dep = {"dobj", "obj", "attr"} if meta else {"nsubjpass"}
        objects = _request_objects(g, predicate, dep)
        if objects:
            flat = _flat_run_frames(g, predicate, objects, prior)
            if flat is not None:
                return flat
            g.syntax.add(predicate)
            g.syntax.update(
                c
                for c in g.children[predicate]
                if g.ts[c]["dep"] in {"aux", "auxpass"}
                or g.low(c) in {"me", "us", "together", "please"}
                or first_person_need
                and g.low(c) in {"i", "we"}
            )
            frames, prior = _object_frames(g, predicate, objects, prior)
            return frames, prior
        if any(
            c in g.predicates and g.ts[c]["dep"] in {"ccomp", "xcomp"}
            for c in g.children[predicate]
        ):
            g.syntax.add(predicate)
            return frames, prior
    frames.append(_generic(g, predicate, "unrecognized_request_predicate"))
    return frames, prior


def _inherited_who_frame(g, predicate, parent, prior):
    frame, scopes = _wh_frame(g, predicate, prior, inherited_who=True)
    parent_targets = [
        g.nominal(c) for c in g.children[parent] if g.ts[c]["dep"] in {"dobj", "obj"}
    ]
    child_targets = [ids for ids, _ in g.direct_scopes(predicate)]
    if (
        parent_targets
        and child_targets
        and {g.topic(i) for i in parent_targets} != {g.topic(i) for i in child_targets}
    ):
        frame = replace(
            frame,
            errors=frame.errors + ("coupled_role_subject_has_distinct_scopes",),
        )
    return [frame], scopes or prior


def _request_objects(g, predicate, dep):
    """Collect the requested object heads for a request predicate.

    A VERB conjunct or detached verbal modifier on the request verb
    contributes its own object ("give all steps and governing
    limitations", "provide its quantities, preview duration"). A
    mis-tagged flat entity name may leave no direct object at all; the
    nominal children then begin the requested run.
    """
    objects = [
        c
        for c in g.children[predicate]
        if g.ts[c]["dep"] in dep and g.low(c) not in {"me", "us"}
    ]
    for c in g.children[predicate]:
        if g.ts[c]["dep"] == "conj" and c in g.predicates and g.ts[c]["pos"] == "VERB":
            inner = [
                o
                for o in g.children[c]
                if g.ts[o]["dep"] in dep and g.low(o) not in {"me", "us"}
            ]
            if inner and (
                g.lemma(c) in META or all(g.lemma(o) in GOVERNORS for o in inner)
            ):
                objects.extend(inner)
                g.recovered_field_heads.add(c)
                g.syntax.add(c)
        elif (
            g.ts[c]["dep"] in {"advcl", "acl"}
            and c in g.predicates
            and g.ts[c]["pos"] == "VERB"
            and g.lemma(c) not in {"include", "preserve", "retain"}
            and g.lemma(c) not in META
        ):
            inner = [
                o
                for o in g.children[c]
                if g.ts[o]["dep"] in dep and g.low(o) not in {"me", "us"}
            ]
            if inner and any(_head_kind(g, o)[0] != "generic" for o in inner):
                objects.extend(inner)
                g.recovered_field_heads.add(c)
                g.syntax.add(c)
    if not objects:
        objects = [
            c
            for c in g.children[predicate]
            if g.ts[c]["dep"] in {"dative", "conj", "appos"}
            and g.ts[c]["pos"] in {"NOUN", "PROPN"}
            and c not in g.predicates
        ]
    return objects


def _nominal_interrogatives(g):
    """WH + coordinated nominal subject + passive predicate.

    Recover NP coordination when the statistical graph mistakes a modifier for
    a verb. The raw bounded subject grammar must independently close: every
    segment ends in an ontology field head, all modifiers remain literal, and
    the passive predicate/arguments remain in every evidence question.
    """
    result = []
    handled = set()
    for predicate in sorted(g.predicates):
        aux = [c for c in g.children[predicate] if g.ts[c]["dep"] == "auxpass"]
        if not aux:
            continue
        sentence = [i for i in range(len(g.ts)) if g.sent[i] == g.sent[predicate]]
        before = [i for i in sentence if i < min(aux)]
        if not before or g.low(before[0]) not in {"what", "which"}:
            continue
        # Do not consume another request clause or an unclosed factual modal.
        if any(g.low(i) in MODALS | CONDITIONS for i in before):
            continue
        chunks = _nominal_chunks(g, before)
        if not chunks or any(_head_kind(g, c[-1])[0] == "generic" for c in chunks):
            continue
        scopes = g.direct_scopes(predicate)
        topic, scope_refs, scope_owned, errors, _ = _close_scope(g, scopes)
        if errors:
            continue
        independent = {
            other
            for other in g.predicates
            if other != predicate
            and other >= min(aux)
            and other not in g.condition_heads
            and other in sentence
        }
        independent_tokens = (
            set().union(*(g.subtree(other) for other in independent))
            if independent
            else set()
        )
        tail = {i for i in sentence if i >= min(aux)} - independent_tokens
        ast = g.condition_clauses(tail)
        condition_tokens = (
            set().union(*(set(c.token_indices) for c in ast)) if ast else set()
        )
        unbound_conditions = g.qualifier_spans(tail - condition_tokens, CONDITIONS)
        for chunk in chunks:
            ids = set(chunk)
            field = chunk[-1]
            kind = _head_kind(g, field)[0]
            content = {before[0]} | ids | tail
            frame = DependencyFrame(
                g.span(content),
                g.text(content) + "?",
                kind,
                topic,
                g.text(ids),
                g.ts[predicate]["text"],
                tuple(sorted(content | scope_owned)),
                (predicate, field),
                scopes=scope_refs,
                conditions=tuple(c.evidence for c in ast),
                condition_ast=ast,
                modality=g.qualifier_spans(tail, MODALS),
                errors=("unresolved_condition_or_modality",)
                if unbound_conditions
                else (),
                grammar="passive_interrogative_nominal_coordination",
            )
            result.append(frame)
        handled.update(i for i in g.predicates if i in set(before) | tail)
        g.syntax.update(
            i for i in before if i not in set().union(*(set(c) for c in chunks))
        )
    return result, handled


def _elliptical_passive(g, predicate):
    if g.lemma(predicate) not in HEADS and g.lemma(predicate) != "role":
        return None
    modifiers = [
        c
        for c in g.children[predicate]
        if g.ts[c]["dep"] == "acl" and g.lemma(c) in {"need", "require", "request"}
    ]
    if len(modifiers) != 1:
        return None
    verb = modifiers[0]
    prior = [ids for ids, _ in g.direct_scopes(verb)]
    frames = []
    for head in g.conjuncts(predicate):
        frame, _ = _np_frame(g, verb, head, prior)
        # Elliptical "fields needed together" is request syntax; no finite
        # operating assertion or assignment is inferred.
        frame = replace(
            frame,
            errors=tuple(e for e in frame.errors if e != "unclosed_nominal_clause"),
        )
        frames.append(frame)
    g.syntax.update({verb} | {c for c in g.children[verb] if g.low(c) == "together"})
    return frames


def _standalone_procedure(g):
    """Closed nominal procedure request with literal governing content.

    This independent token grammar repairs nominal misattachments only. It
    cannot turn a second field/action, a relative clause, a named external
    reference or an alternative into a complete single procedure request.
    """
    intent = _procedure_intent(g)
    if intent is None:
        return None
    head, predicate, passive, request_ops = intent
    # The requested NP is a literal nominal sequence; do not swallow actual
    # pre-head clauses or independent coordinated factual obligations.
    begin = (
        predicate + 1
        if request_ops
        else next((i for i in range(head) if g.lemma(i) in WHOLE), head)
    )
    if request_ops and g.lemma(predicate) == "walk" and g.low(begin) == "through":
        begin += 1
    prehead = set(range(begin, head + 1))
    if not _procedure_modifiers_closed(g, head, prehead):
        return None
    tail = set(range(head + 1, len(g.ts)))
    adjunct_markers = [
        i
        for i in tail
        if g.lemma(i) in {"include", "retain", "preserve"}
        or g.low(i) in {"with", "plus"}
    ]
    coordination = _governor_coordination_start(g, tail, adjunct_markers, passive)
    if coordination is not None:
        adjunct_markers.append(coordination)
        adjunct_markers.sort()
    scopes = _scope_candidates(g, head, predicate, [])
    named = _named_subject(g, head)
    # Recover the literal modifier NP only when a nominal dependency head
    # establishes one. Capitalized adjectives cannot establish an activity.
    name_positions = (
        set().union(
            *(
                g.nominal(c)
                for c in g.children[head]
                if g.ts[c]["dep"] in {"compound", "nmod"}
                and g.ts[c]["pos"] in {"NOUN", "PROPN"}
            )
        )
        & prehead
    )
    if name_positions and (
        not scopes or any(g.ts[i]["pos"] == "PROPN" for i in name_positions)
    ):
        named = set(range(min(name_positions), head))
    if named:
        scopes.append((named, named))
    topic, scope_refs, scope_owned, errors, _ = _close_scope(g, scopes)
    if errors:
        return None
    ids = set(range(len(g.ts)))
    ast = g.condition_clauses(ids)
    ast_ids = set().union(*(set(c.token_indices) for c in ast)) if ast else set()
    if g.qualifier_spans(ids - ast_ids, CONDITIONS):
        return None
    governors = tuple(
        g.span(
            set(range(i, len(g.ts)))
            - {
                j
                for j in range(len(g.ts))
                if g.ts[j]["pos"] == "PUNCT" and g.ts[j]["text"] in {".", "?"}
            }
        )
        for i in adjunct_markers[:1]
    )
    references = g.external_references(ids)
    # Named required material remains a source dependency, not a grammar-only
    # claim that copying the main procedure can satisfy it.
    adjunct_ids = (
        set(range(adjunct_markers[0], len(g.ts))) if adjunct_markers else set()
    )
    passive_syntax = set(passive) | {
        c
        for i in passive
        for c in g.children[i]
        if g.ts[c]["dep"] in {"aux", "auxpass"}
    }
    if not _procedure_tail_closed(
        g, tail, scope_owned, ast_ids, adjunct_ids, passive_syntax, references, ids
    ):
        return None
    frame = DependencyFrame(
        g.span(ids),
        g.raw.rstrip(".? ") + "?",
        "procedure",
        topic,
        g.text(prehead),
        g.ts[head]["text"],
        tuple(sorted(ids)),
        (predicate, head),
        scopes=scope_refs,
        conditions=tuple(c.evidence for c in ast),
        modality=g.qualifier_spans(ids, MODALS),
        units=g.literal_units(ids),
        governors=governors,
        references=references,
        grammar="closed_whole_procedure_request",
        condition_ast=ast,
    )
    return frame


def resolve_frames(question, annotation):
    g = Graph(question, annotation)
    recovered = _recover_scalar_coordination(g) or _recover_role_procedure_bundle(g)
    standalone = (
        _method_procedure_request(g)
        or _how_whole_procedure(g)
        or _standalone_procedure(g)
    )
    if recovered is not None:
        frames = recovered
    elif standalone is not None:
        frames = [standalone]
    else:
        frames, handled = _nominal_interrogatives(g)
        frames = _collect_predicates(g, frames, handled)
    g.syntax.update(index for _, index in _order_targets(g, frames))
    covered = set().union(*(set(f.tokens) for f in frames)) if frames else set()
    leftovers = set(range(len(g.ts))) - covered - g.syntax
    if leftovers:
        frames.append(
            DependencyFrame(
                g.span(leftovers),
                g.text(leftovers) + "?",
                "generic",
                "",
                "",
                "",
                tuple(sorted(leftovers)),
                (),
                errors=("unconsumed_original_tokens",),
            )
        )
    if not frames:
        ids = set(range(len(g.ts)))
        frames.append(
            DependencyFrame(
                g.span(ids),
                question,
                "generic",
                "",
                "",
                "",
                tuple(sorted(ids)),
                (),
                errors=("no_request_argument",),
            )
        )
    frames.sort(
        key=lambda f: (
            min(f.heads)
            if recovered is not None and f.heads
            else min(f.tokens)
            if f.tokens
            else 0,
            min(f.heads) if f.heads else 0,
        )
    )
    frames = _bind_relations(g, frames)
    coupled_parents = {
        g.ts[f.heads[0]]["head"]
        for f in frames
        if f.heads and "coupled_role_subject_has_distinct_scopes" in f.errors
    }
    if coupled_parents:
        frames = [
            replace(f, errors=f.errors + ("coupled_role_subject_has_distinct_scopes",))
            if f.heads and f.heads[0] in coupled_parents
            else f
            for f in frames
        ]
    workspaces = re.findall(r"\bworkspace\s+([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)", question)
    if len(set(workspaces)) == 1:
        frames = [replace(f, source_workspace=workspaces[0]) for f in frames]
    elif len(set(workspaces)) > 1:
        ids = set(range(len(g.ts)))
        frames = [
            DependencyFrame(
                g.span(ids),
                question,
                "generic",
                "",
                "",
                "",
                tuple(sorted(ids)),
                (),
                errors=("competing_workspaces",),
                grammar="atomic_unresolved_workspace_conflict",
            )
        ]
    if any(t["dep"] == "cc" and t["text"].casefold() == "or" for t in g.ts):
        # An alternative is a coupled request. Independent positive head hints
        # cannot turn it into the conjunction supported by this consumer.
        ids = set(range(len(g.ts)))
        refs = [
            i
            for i in ids
            if g.ts[i]["dep"] == "poss"
            or g.low(i) in {"that", "their", "its", "it", "each"}
        ]
        frames = [
            DependencyFrame(
                g.span(ids),
                question,
                "generic",
                "",
                "",
                "",
                tuple(sorted(ids)),
                (),
                conditions=g.qualifier_spans(ids, CONDITIONS),
                modality=g.qualifier_spans(ids, MODALS),
                units=g.literal_units(ids),
                references=tuple(g.span(g.nominal(i)) for i in refs)
                + g.external_references(ids),
                errors=("alternative_request_coordination_not_defined",),
                grammar="atomic_unresolved_alternative",
            )
        ]
    frames = _close_reference_inventory(g, frames)
    return tuple(frames), tuple(sorted(g.syntax))


def _close_reference_inventory(g, frames):
    """Every original reference needs frame evidence, not raw token cover alone."""
    conditional = set().union(
        *(set(c.token_indices) for frame in frames for c in frame.condition_ast)
    )
    refs = [
        i
        for i in g.reference(range(len(g.ts)))
        if not (
            i not in conditional
            and g.ts[g.ts[i]["head"]]["dep"] == "ROOT"
            and g.ts[i]["dep"] == "nsubj"
            and g.low(i) in {"i", "we"}
            and g.lemma(g.ts[i]["head"]) in META | {"need"}
        )
    ]
    owned = set().union(*(set(frame.tokens) for frame in frames))
    orphaned = set(refs) - owned
    if orphaned:
        frames.append(
            DependencyFrame(
                g.span(orphaned),
                g.text(orphaned) + "?",
                "generic",
                "",
                "",
                "",
                tuple(sorted(orphaned)),
                (),
                references=tuple(g.span({i}) for i in sorted(orphaned)),
                errors=("unresolved_uninventoried_reference",),
                grammar="atomic_unresolved_reference",
            )
        )
    for n, frame in enumerate(frames):
        missing = tuple(
            g.span({i})
            for i in refs
            if i in frame.tokens
            and not any(
                s.start <= g.ts[i]["start"] and g.ts[i]["end"] <= s.end
                for s in frame.references
            )
        )
        if missing:
            references = frame.references + missing
            question = frame.question
            if not all(s.text in question for s in references):
                question = frame.original.text + "?"
            locally_bound = all(
                _local_procedure_reference(g, frame, i)
                for i in refs
                if i in frame.tokens
                and any(s.start == g.ts[i]["start"] for s in missing)
            )
            frames[n] = replace(
                frame,
                references=references,
                question=question,
                errors=frame.errors
                + (() if locally_bound else ("unresolved_uninventoried_reference",)),
                grammar=frame.grammar + "_local_procedure_reference"
                if locally_bound
                else frame.grammar,
            )
    return frames


def _local_procedure_reference(g, frame, i):
    """Bind a local possessive governor to its sole requested procedure NP.

    This is request-internal syntax, never a prior-evidence value dependency.
    The original graph, head indices and reference evidence reconstruct it.
    """
    procedures = [
        t["i"]
        for t in g.ts
        if HEADS.get(g.lemma(t["i"])) == "procedure" and t["pos"] in {"NOUN", "PROPN"}
    ]
    token = g.ts[i]
    conditional_ref = any(
        s.start <= token["start"] and token["end"] <= s.end for s in frame.conditions
    )
    if (
        g.low(i) == "its"
        and g.ts[i]["dep"] == "poss"
        and frame.topic
        and len(frame.scopes) == 1
        and not frame.errors
        and not conditional_ref
    ):
        # A possessive inside a request with one declared entity scope binds
        # to that entity: "its entry condition" is the entity's condition.
        return True
    if not (
        frame.kind == "procedure"
        and not frame.errors
        and frame.topic
        and len(procedures) == 1
        and procedures[0] in frame.heads
        and frame.grammar != "coordinated_role_procedure_request"
        and g.low(i) == "its"
        and g.ts[i]["dep"] == "poss"
        and g.lemma(g.ts[i]["head"]) in GOVERNORS
    ):
        return False
    token = g.ts[i]
    governed = any(
        s.start <= token["start"] and token["end"] <= s.end for s in frame.governors
    )
    conditional = any(
        s.start <= token["start"] and token["end"] <= s.end for s in frame.conditions
    )
    at, seen = g.ts[i]["head"], set()
    while at not in seen:
        seen.add(at)
        t = g.ts[at]
        if (
            g.lemma(at) in {"include", "preserve", "retain"}
            and t["dep"] in {"prep", "advcl"}
            and t["head"] in frame.heads
        ):
            return governed and not conditional
        at = t["head"]
    return False


def _predicate_np_adjuncts(
    g, predicate, kind, owned, property_owned, governors, adjuncts, units
):
    for c in g.children[predicate]:
        if (
            g.ts[c]["dep"] in {"advcl", "acl"}
            and g.lemma(c) in {"include", "preserve", "retain"}
            and kind == "procedure"
        ):
            inner = [o for o in g.children[c] if g.ts[o]["dep"] in {"dobj", "obj"}]
            external = any(
                g.ts[i]["pos"] == "PROPN" for o in inner for i in g.nominal(o)
            ) and not any(
                g.low(i) in {"its", "their"} for o in inner for i in g.nominal(o)
            )
            if not external:
                ids = g.subtree(c)
                adjuncts.append(ids)
                for o in inner:
                    governors.extend(g.span(g.nominal(h)) for h in g.conjuncts(o))
                g.recovered_field_heads.add(c)
    for p, obj in g.pp(predicate):
        if (
            g.low(p) == "in"
            and kind in {"quantity", "duration"}
            and g.lemma(obj) in {"second", "minute", "hour"}
            and not any(g.ts[c]["pos"] == "PROPN" for c in g.nominal(obj))
        ):
            unit = g.nominal(obj)
            units.append(g.span(unit))
            owned |= g.subtree(p)
            property_owned |= unit | {p}
        elif (
            (g.lemma(p) == "include" or g.low(p) == "with")
            and kind == "procedure"
            and all(g.lemma(h) in GOVERNORS for h in g.conjuncts(obj))
        ):
            ids = g.subtree(p)
            adjuncts.append(ids)
            governors.extend(g.span(g.subtree(h)) for h in g.conjuncts(obj))
    return owned, property_owned


def _np_conditions(g, predicate, owned, errors):
    for c in g.condition_heads:
        if g.ts[c]["head"] == predicate:
            owned |= g.subtree(c)
    condition_ast = g.condition_clauses(owned)
    conditions = tuple(c.evidence for c in condition_ast)
    modals = g.qualifier_spans(owned, MODALS)
    conditional_tokens = (
        set().union(*(set(c.token_indices) for c in condition_ast))
        if condition_ast
        else set()
    )
    unparsed_conditions = g.qualifier_spans(
        (owned | g.local(predicate)) - conditional_tokens, CONDITIONS
    )
    if unparsed_conditions or any(
        s.start not in {g.ts[i]["start"] for i in conditional_tokens} for s in modals
    ):
        errors.append("unresolved_condition_or_modality")
        owned |= g.local(predicate)
    return owned, condition_ast, conditions, modals


def _wh_local(g, predicate, inherited_who):
    local = g.local(predicate)
    cues = _wh_tokens(g, predicate)
    low = {g.low(i) for i in local}
    if inherited_who:
        low.add("who")
    if "why" in low:
        local = g.subtree(
            predicate,
            prune={
                i
                for i in g.predicates - {predicate}
                if g.ts[i]["dep"] not in {"ccomp", "xcomp"}
            },
        )
    return local, cues, low


def _wh_scopes(g, predicate, low, args):
    scopes = g.direct_scopes(predicate)
    if "who" in low:
        # A trailing scope on an elided-subject coordinated role verb also
        # scopes the preceding bare role verb. Explicit distinct targets remain
        # coupled/ambiguous unless each WH clause declares its own subject.
        shared = [
            i
            for i in g.predicates
            if g.ts[i]["head"] == predicate
            and g.ts[i]["dep"] == "conj"
            and not _wh_tokens(g, i)
            and g.lemma(i) in {"lead", "deputize", "own", "manage", "run"}
        ]
        if not scopes and not any(g.ts[i]["dep"] in {"dobj", "obj"} for i in args):
            scopes.extend(s for i in shared for s in g.direct_scopes(i))
    return scopes


SCOPE_QUALIFIERS = frozenset(
    {"ordinary", "session", "activity", "demonstration", "sample", "practice"}
)


def _flat_run_frames(g, predicate, objects, prior):
    """Reassemble a flat entity+field run shredded across clause deps.

    Formal request register threads entity names through arbitrary
    dative/dobj/conj/xcomp chains ("give the ordinary Silver Stroke dash
    rehearsal activity roles"). When the post-verbal region is contiguous
    nominal material, the corpus convention <qualifier*> <PROPN+> <NOUN NOUN>
    is the entity scope, the segment-final head is the requested field, and
    leading determiners/extent words stay with the field.
    """
    sentence = [i for i in range(len(g.ts)) if g.sent[i] == g.sent[predicate]]
    region = [i for i in sentence if i > predicate]
    first = min(i for o in objects for i in g.nominal(o) | {o})
    nominal_deps = {"dobj", "obj", "attr", "dative", "pobj"}
    nominal_pos = {"NOUN", "PROPN", "PRON", "VERB"}
    embedded = [c for c in g.children[predicate] if c in g.predicates]
    inside = set().union(*(g.nominal(o) | g.subtree(o) for o in objects))
    for c in g.children[predicate]:
        if (
            c not in g.predicates
            and g.ts[c]["dep"] in nominal_deps
            and g.ts[c]["pos"] in nominal_pos
        ):
            inside |= g.subtree(c)
    for c in embedded:
        for gc in g.children[c]:
            if g.ts[gc]["dep"] in nominal_deps and g.ts[gc]["pos"] in nominal_pos:
                inside |= g.subtree(gc)
    inside -= {predicate}
    split = _flat_segments(g, region, first, inside, {predicate} | set(embedded))
    if split is None:
        return None
    segments, seg_preps, boundary = split
    frames = []
    for n, seg in enumerate(segments):
        result = _flat_segment_frame(
            g, predicate, seg, prior, frames, seg_preps.get(n - 1)
        )
        if result is None:
            return None
        frame, prior = result
        if frame is not None:
            frames.append(frame)
    g.syntax.add(predicate)
    g.syntax.update(
        c for c in g.children[predicate] if g.ts[c]["dep"] in {"aux", "auxpass"}
    )
    # Embedded clause material between object pieces (a coordinated request
    # verb and its function words) belongs to the request syntax, not to any
    # requested field.
    g.syntax.update(boundary)
    g.recovered_field_heads.update(i for i in boundary if i in g.predicates)
    return frames, prior


def _flat_segments(g, region, first, inside, clause_heads):
    """Split the post-verbal region at coordinators, sentence punctuation,
    prepositions and embedded clause material; hyphen-joined modifiers stay
    inside their segment."""
    segments, current = [], []
    seg_preps = {}
    boundary = set()
    for i in region:
        t = g.ts[i]
        if (
            t["dep"] in {"cc"}
            or (t["pos"] == "PUNCT" and t["text"] != "-")
            or t["dep"] == "prep"
        ):
            if current:
                seg_preps[len(segments)] = i if t["dep"] == "prep" else None
                segments.append(current)
                current = []
            continue
        if i not in inside:
            if not current and i < first and t["pos"] in {"DET", "ADJ"}:
                current.append(i)
                continue
            if t["head"] not in clause_heads:
                # Material the flat run cannot account for (a deeper embedded
                # clause) means the region is not a flat entity+field run.
                return None
            boundary.add(i)
            if current:
                segments.append(current)
                current = []
            continue
        current.append(i)
    if current:
        segments.append(current)
    if not segments:
        return None
    return segments, seg_preps, boundary


def _flat_segment_frame(g, predicate, seg, prior, frames, prep):
    """Emit one segment's frame, fold governor facets into the procedure, or
    bail (None) when the run is not a flat entity+field sequence."""
    if any(
        i in g.predicates
        and (
            g.ts[i]["dep"] == "ROOT"
            or g.ts[i]["dep"] == "conj"
            and g.ts[i]["head"] != predicate
        )
        for i in seg
    ):
        return None
    head = (
        seg[0]
        if g.lemma(seg[0]) in {"all", "every", "each", "any"} and len(seg) > 2
        else seg[-1]
    )
    propns = [i for i in seg if g.ts[i]["pos"] == "PROPN"]
    if not propns:
        return _flat_field_frame(g, predicate, seg, head, prior, frames, prep)
    tail = [
        i
        for i in seg
        if i > max(propns)
        and i != head
        and g.ts[i]["pos"] in {"NOUN", "VERB", "ADJ", "PROPN"}
    ][:2]
    qualifiers = [i for i in seg if i < min(propns) and g.lemma(i) in SCOPE_QUALIFIERS]
    if len(tail) != 2:
        return None
    entity = set(qualifiers) | set(propns) | set(tail)
    field = set(seg) - entity
    if head not in field or _head_kind(g, head, field)[0] == "generic":
        return None
    if any(
        g.low(i) in MODALS | CONDITIONS | {"who", "what", "which", "or"} for i in seg
    ):
        return None
    frame, scopes = _np_frame(
        g,
        predicate,
        head,
        prior,
        nominal_override=field,
        extra_scopes=[(entity, entity)],
    )
    g.recovered_field_heads.update(i for i in seg if i in g.predicates)
    if scopes and not frame.errors:
        prior = scopes
    return frame, prior


def _flat_field_frame(g, predicate, seg, head, prior, frames, prep):
    """Field-only segment: emit the frame, fold governor facets into the
    procedure frame, or bail when the head is neither field nor governor."""
    field = set(seg)
    if _head_kind(g, head, field)[0] == "generic":
        target = frames[-1] if frames else None
        if (
            g.lemma(head) in GOVERNORS
            and target is not None
            and target.kind == "procedure"
            and not target.errors
        ):
            fold = set(seg)
            if prep is not None:
                fold.add(prep)
            frames[-1] = replace(
                target,
                governors=target.governors + (g.span(fold),),
                tokens=tuple(sorted(set(target.tokens) | fold)),
            )
            g.recovered_field_heads.update(i for i in seg if i in g.predicates)
            return None, prior
        return None
    frame, scopes = _np_frame(g, predicate, head, prior, nominal_override=field)
    g.recovered_field_heads.update(i for i in seg if i in g.predicates)
    if scopes and not frame.errors:
        prior = scopes
    return frame, prior


def _entity_continuations(g, objects):
    """Objects that continue a sibling object's scope entity name.

    The tagger sometimes splits a flat entity name at a scope preposition:
    "staffing for Ivory Cube face labeling and its routine" makes
    "labeling" a second object even though it is entity-name material.
    A VERB object with nominal left-modifiers starting immediately after
    a sibling's scope object is scope material, not a requested field.
    """
    out = {}
    for o in objects:
        if g.ts[o]["pos"] != "VERB" or o in g.predicates:
            continue
        mods = {
            c
            for c in g.children[o]
            if g.ts[c]["dep"] in {"compound", "amod", "advmod"}
            and g.ts[c]["pos"] in {"NOUN", "ADJ", "VERB", "PROPN"}
        }
        if not mods or min(mods) > o:
            continue
        for s in objects:
            if s == o:
                continue
            for p, tgt in g.pp(s):
                ids = g.scope_nominal(tgt)
                if g.low(p) in SCOPE_PREPS and ids and max(ids) + 1 == min(mods):
                    out[o] = (s, tgt, mods | {o})
    return out


def _object_frames(g, predicate, objects, prior):
    frames = []
    continuations = _entity_continuations(g, objects)
    extra_heads = {}
    for o, (s, tgt, ids) in continuations.items():
        g.scope_continuations[tgt] = g.scope_continuations.get(tgt, set()) | ids
        extra_heads.setdefault(s, []).extend(
            (c, set()) for c in g.conjuncts(o) if c != o
        )
    objects = [o for o in objects if o not in continuations]
    for obj in objects:
        # A nominal modifier containing a coordination can be attached
        # backwards by the graph ("quantity and rotation angle").
        # Split only a raw nominal list anchored by the requested
        # object, preserving every segment including unknown heads.
        nominal_ids = g.nominal(obj)
        left = min(nominal_ids)
        right = max(nominal_ids)
        region = list(range(left, right + 1))
        separators = [
            i
            for i in region
            if (g.low(i) == "and" or g.ts[i]["text"] == ",")
            and not (i and g.ts[i - 1]["text"] == "-")
            and not (i + 1 < len(g.ts) and g.ts[i + 1]["text"] == "-")
        ]
        if (
            separators
            and any(_head_kind(g, i)[0] != "generic" for i in nominal_ids)
            and len(g.conjuncts(obj)) == 1
        ):
            parts = []
            begin = left
            for stop in separators + [right + 1]:
                ids = set(range(begin, stop))
                if ids:
                    parts.append(ids)
                begin = stop + 1
            for ids in parts:
                frame, scopes = _np_frame(
                    g, predicate, max(ids), prior, nominal_override=ids
                )
                frames.append(frame)
                if scopes and not frame.errors:
                    prior = scopes
            g.syntax.update(separators)
            continue
        for head, extra in _requested_conjuncts(g, obj) + extra_heads.get(obj, []):
            frame, scopes = _np_frame(
                g,
                predicate,
                head,
                prior,
                nominal_override=None if not extra else g.nominal(head) | extra,
            )
            frames.append(frame)
            if scopes and not frame.errors:
                prior = scopes
    _merge_governor_frames(g, frames)
    return frames, prior


def _merge_governor_frames(g, frames):
    """A coordinated governor object ("give all steps and governing
    limitations") is governor material on the sibling procedure frame,
    not an independent requested field."""
    gov_idx = [
        n
        for n, f in enumerate(frames)
        if "unknown_requested_head" in f.errors and g.lemma(f.heads[-1]) in GOVERNORS
    ]
    if not gov_idx:
        return
    proc_idx = next(
        (m for m, t in enumerate(frames) if t.kind == "procedure" and not t.errors),
        None,
    )
    if proc_idx is None:
        return
    target = frames[proc_idx]
    frames[proc_idx] = replace(
        target,
        governors=target.governors + tuple(frames[n].original for n in gov_idx),
        tokens=tuple(
            sorted(set(target.tokens) | {i for n in gov_idx for i in frames[n].tokens})
        ),
    )
    for n in sorted(gov_idx, reverse=True):
        del frames[n]


def _requested_conjuncts(g, obj):
    heads = g.conjuncts(obj)
    recovered = [
        i
        for i in g.subtree(obj)
        if i not in heads
        and g.ts[i]["dep"] == "conj"
        and _head_kind(g, i)[0] != "generic"
        and (g.pp(i) or g.ts[g.ts[i]["head"]]["dep"] == "pobj")
        and any(g.ts[c]["dep"] == "det" for c in g.children[i])
    ]
    g.recovered_field_heads.update(recovered)
    out = []
    for h in sorted(heads + recovered):
        # A mis-tagged VERB conj member ("count, review time and location")
        # modifies its object; the object conjuncts are the requested fields.
        if g.ts[h]["pos"] == "VERB" and h not in g.predicates:
            objs = [c for c in g.children[h] if g.ts[c]["dep"] in {"dobj", "obj"}]
            if objs:
                g.recovered_field_heads.add(h)
                out.append((objs[0], {h}))
                out.extend((c, set()) for c in g.conjuncts(objs[0]) if c != objs[0])
                continue
        out.append((h, set()))
    return out


def _nominal_wh_frames(g, predicate, prior):
    cues = _wh_tokens(g, predicate)
    if not cues or any(g.low(i) not in {"who", "what", "which"} for i in cues):
        return None
    if g.lemma(predicate) not in {"be", "apply"}:
        return None
    local = g.local(predicate)
    ast_ids = set().union(*(set(c.token_indices) for c in g.condition_clauses(local)))
    if g.qualifier_spans(local - ast_ids, MODALS):
        return None
    roots = [
        c
        for c in g.children[predicate]
        if g.ts[c]["dep"] in ARG_DEPS
        and g.low(c) not in {"who", "what", "which"}
        and (_head_kind(g, c)[0] != "generic" or g.lemma(c) == "role")
    ]
    if len(roots) != 1:
        return None
    frames, scopes = _object_frames(g, predicate, roots, prior)
    g.syntax.update({predicate} | set(cues))
    if g.lemma(predicate) != "be":
        if len(frames) != 1:
            return None
        frames = [
            replace(
                f,
                question=_wh_question(g, predicate, local),
                relation=g.ts[predicate]["text"],
                tokens=tuple(sorted(set(f.tokens) | local)),
            )
            for f in frames
        ]
    return frames, scopes


def _nominal_chunks(g, before):
    chunks = []
    chunk = []
    for i in before[1:]:
        if g.ts[i]["text"] == "," or g.low(i) == "and":
            if chunk:
                chunks.append(chunk)
                chunk = []
        else:
            chunk.append(i)
    if chunk:
        chunks.append(chunk)
    return chunks


def _procedure_intent(g):
    candidates = [t["i"] for t in g.ts if HEADS.get(g.lemma(t["i"])) == "procedure"]
    if len(candidates) != 1:
        return None
    head = candidates[0]
    if not any(g.lemma(i) in WHOLE for i in range(head)):
        return None
    # All preceding independent requested field heads must stay separate.
    if any(HEADS.get(g.lemma(i)) not in {None, "procedure"} for i in range(head)):
        return None
    request_ops = [
        i
        for i in range(head)
        if g.lemma(i) in META
        or g.lemma(i) == "walk"
        and any(g.low(p) == "through" and head in g.subtree(obj) for p, obj in g.pp(i))
        or g.lemma(i) == "need"
        and any(g.low(c) in {"i", "we"} for c in g.children[i])
    ]
    wh = [i for i in range(head) if g.low(i) in {"what", "which"}]
    passive = [
        i
        for i in range(head + 1, len(g.ts))
        if g.lemma(i) in {"need", "require", "request"}
        and any(g.ts[c]["dep"] == "auxpass" for c in g.children[i])
    ]
    if not request_ops and not wh and not passive:
        return None
    if any(g.low(i) in MODALS for i in range(head) if g.ts[i]["dep"] in {"aux", "neg"}):
        return None
    predicate = request_ops[0] if request_ops else g.ts[head]["head"]
    return head, predicate, passive, request_ops


def _collect_predicates(g, frames, handled):
    prior = []
    prior_sentence = None
    contexts, context_heads = _request_assumption_contexts(g)
    handled.update(context_heads)
    for predicate in sorted(g.predicates):
        if predicate in handled or predicate in g.recovered_field_heads:
            continue
        if _attach_retention_clause(g, frames, predicate):
            handled.update(g.subtree(predicate) & g.predicates)
            continue
        elliptical = _elliptical_passive(g, predicate)
        if elliptical is not None:
            frames.extend(elliptical)
            continue
        if g.sent[predicate] != prior_sentence:
            context = contexts.get(g.sent[predicate])
            prior = [context[1]] if context else []
        prior_sentence = g.sent[predicate]
        found, prior = _predicate_frames(g, predicate, prior)
        if g.sent[predicate] in contexts:
            clause, subject = contexts[g.sent[predicate]]
            found = [_attach_request_assumption(g, f, clause, subject) for f in found]
        frames.extend(found)
        if any("unknown_why_request" in f.errors for f in found):
            handled.update(
                i for i in g.subtree(predicate) if g.ts[i]["dep"] in {"ccomp", "xcomp"}
            )
    return frames


def _session_have_premise(g, predicate, contexts):
    """Active form: "the session has no <n>". A declared session absence."""
    if g.lemma(predicate) != "have" or g.ts[predicate]["dep"] != "ROOT":
        return None
    local = g.local(predicate)
    subject = [c for c in g.children[predicate] if g.ts[c]["dep"] == "nsubj"]
    objects = [c for c in g.children[predicate] if g.ts[c]["dep"] in {"dobj", "obj"}]
    if len(subject) != 1 or len(objects) != 1 or g.lemma(subject[0]) != "session":
        return None
    subject_ids = g.scope_nominal(subject[0])
    object_ids = g.nominal(objects[0])
    if not any(g.low(i) == "no" for i in object_ids) or g.reference(subject_ids):
        return None
    closed = subject_ids | object_ids | {predicate} | g.syntax
    if local - closed:
        return None
    target = g.sent[predicate] + 1
    following = [i for i in range(len(g.ts)) if g.sent[i] == target]
    if not any(g.low(i) == "its" for i in following) or not any(
        g.lemma(i) in META and i in g.predicates for i in following
    ):
        return None
    ids = local - {
        i for i in local if g.ts[i]["pos"] == "PUNCT" and g.ts[i]["text"] in {".", "?"}
    }
    clause = ConditionClause(
        "request_assumption",
        g.span(ids),
        g.span({predicate}),
        (g.span(subject_ids),),
        tuple(g.span({i}) for i in object_ids if g.low(i) == "no"),
        (),
        tuple(sorted(ids)),
        (g.span(object_ids),),
    )
    contexts[target] = (clause, subject_ids)
    return predicate


def _passive_session_premise(g, predicate, heads, contexts):
    """Passive form: "no session <n> was issued/recorded/...". Same premise
    class: a declared session absence that qualifies an adjacent request."""
    if predicate in heads or g.ts[predicate]["dep"] not in {
        "ROOT",
        "conj",
        "parataxis",
    }:
        return None
    local = g.local(predicate)
    subjects = [
        c for c in g.children[predicate] if g.ts[c]["dep"] in {"nsubj", "nsubjpass"}
    ]
    if len(subjects) != 1:
        return None
    subject_ids = g.scope_nominal(subjects[0])
    negative = {i for i in subject_ids if g.low(i) in {"no", "not", "never", "none"}}
    if (
        not any(g.lemma(i) == "session" for i in subject_ids)
        or not negative
        or g.reference(subject_ids)
    ):
        return None
    aux = {c for c in g.children[predicate] if g.ts[c]["dep"] in {"aux", "auxpass"}}
    if local - (subject_ids | {predicate} | aux | g.syntax):
        return None
    anchor = g.ts[predicate]["head"]
    if g.ts[predicate]["dep"] == "conj" and anchor in g.predicates:
        target = g.sent[anchor]
    elif any(
        g.sent[i] == g.sent[predicate] and i != predicate and i not in heads
        for i in g.predicates
    ):
        target = g.sent[predicate]
    elif any(g.sent[i] == g.sent[predicate] - 1 for i in g.predicates):
        target = g.sent[predicate] - 1
    else:
        target = g.sent[predicate] + 1
    ids = local - {
        i for i in local if g.ts[i]["pos"] == "PUNCT" and g.ts[i]["text"] in {".", "?"}
    }
    clause = ConditionClause(
        "request_assumption",
        g.span(ids),
        g.span({predicate}),
        (g.span(subject_ids - negative),),
        tuple(g.span({i}) for i in negative),
        (),
        tuple(sorted(ids)),
        (g.span(subject_ids),),
    )
    contexts[target] = (clause, set())
    return predicate


def _preamble_premise(g, predicate, contexts):
    """A leading nominal run closed by ':' is declared request emphasis
    ("Both staffing and execution matter: give ..."), not a request itself."""
    colons = [
        c for c in g.children[predicate] if g.ts[c]["text"] == ":" and c < predicate
    ]
    for colon in colons:
        prefix = {i for i in range(colon) if g.sent[i] == g.sent[predicate]}
        if (
            not prefix
            or any(i in g.predicates for i in prefix)
            or any(g.ts[i]["pos"] == "PUNCT" for i in prefix)
            or not any(
                g.ts[i]["dep"] in {"nsubj", "nsubjpass", "dative", "preconj"}
                for i in prefix
            )
        ):
            continue
        clause = ConditionClause(
            "request_assumption",
            g.span(prefix),
            g.span({colon}),
            (),
            (),
            (),
            tuple(sorted(prefix)),
            (g.span(prefix),),
        )
        contexts.setdefault(g.sent[predicate], (clause, set()))
        g.syntax.update(prefix | {colon})


def _request_assumption_contexts(g):
    """A declared session premise qualifies the immediately following request.

    This is a condition to be proved by the source consumer, never assignment
    evidence or a permission grant. Other narrative/authority claims stay open.
    """
    contexts, heads = {}, set()
    for predicate in sorted(g.predicates):
        found = _session_have_premise(g, predicate, contexts)
        if found is not None:
            heads.add(found)
    for predicate in sorted(g.predicates):
        found = _passive_session_premise(g, predicate, heads, contexts)
        if found is not None:
            heads.add(found)
    for predicate in sorted(g.predicates):
        _preamble_premise(g, predicate, contexts)
    return contexts, heads


def _attach_request_assumption(g, frame, clause, subject):
    def qualified(question):
        return (
            question.rstrip("?") + ", provided that " + clause.evidence.text + "?"
            if question
            else ""
        )

    errors = frame.errors
    if frame.topic and subject and frame.topic != g.topic(subject):
        errors += ("request_context_scope_conflict",)
    return replace(
        frame,
        question=qualified(frame.question),
        prepared_question=qualified(frame.prepared_question),
        conditions=frame.conditions + (clause.evidence,),
        condition_ast=frame.condition_ast + (clause,),
        modality=tuple(
            dict.fromkeys(frame.modality + clause.negation + clause.modality)
        ),
        tokens=tuple(sorted(set(frame.tokens) | set(clause.token_indices))),
        errors=errors,
    )


def _procedure_modifiers_closed(g, head, prehead):
    if any(
        g.low(i) in {"and", "or", "why", "who", "where", "when"} or g.low(i) in MODALS
        for i in prehead
    ):
        return False
    # Compound nominal words may be assigned xcomp/advcl by the model; the
    # original NP stays literal, but finite/relative predicates are not licensed.
    if any(
        g.ts[i]["dep"] == "relcl" or g.ts[i]["tag"] in {"VBD", "VBZ", "VBP"}
        for i in prehead
        if i != head
    ):
        return False
    tail = set(range(head + 1, len(g.ts)))
    if any(g.ts[i]["dep"] == "relcl" for i in tail):
        return False
    non_request_verbs = [
        i
        for i in tail
        if g.ts[i]["tag"] in {"VB", "VBD", "VBZ", "VBP"}
        and g.lemma(i)
        not in {"include", "retain", "preserve", "be", "need", "request", "require"}
        and i not in set().union(*(g.subtree(c) for c in g.condition_heads))
    ]
    if non_request_verbs:
        return False
    if any(g.low(i) == "or" and g.ts[i]["dep"] == "cc" for i in tail):
        return False
    return True


def _nominal_governor_list(g, indices):
    """Explicit governing NPs, not arbitrary additional requested fields."""
    parts, part = [], []
    for i in sorted(indices):
        if g.ts[i]["pos"] == "PUNCT" and g.ts[i]["text"] in {".", "?"}:
            continue
        separator = g.ts[i]["text"] == "," or g.low(i) in {"and", "plus"}
        if separator and not (i and g.ts[i - 1]["text"] == "-"):
            if part:
                parts.append(part)
                part = []
        else:
            part.append(i)
    if part:
        parts.append(part)
    return bool(parts) and all(_governor_np(g, p) for p in parts)


def _governor_np(g, part):
    if any(
        g.low(i)
        in {"who", "what", "which", "how", "where", "when", "why"}
        | CONDITIONS
        | (MODALS - {"no", "not"})
        for i in part
    ):
        return False
    if any(
        g.ts[i]["pos"] == "PROPN" or g.ts[i]["tag"] in {"VB", "VBD", "VBP", "VBZ"}
        for i in part
    ):
        return False
    head = part[-1]
    return (
        g.lemma(head) in GOVERNORS
        or HEADS.get(g.lemma(head)) == "procedure"
        and any(g.lemma(i) in GOVERNORS for i in part[:-1])
    )


def _governor_coordination_start(g, tail, markers, passive):
    aux = [
        c
        for p in passive
        for c in g.children[p]
        if g.ts[c]["dep"] in {"aux", "auxpass"}
    ]
    stop = min(markers + aux + passive + [len(g.ts)])
    prefix = {i for i in tail if i < stop}
    first = min(prefix) if prefix else None
    if (
        first is not None
        and g.low(first) in {"and", "plus"}
        and _nominal_governor_list(g, prefix)
    ):
        return first
    return None


def _attach_retention_clause(g, frames, predicate):
    if (
        g.lemma(predicate) not in {"retain", "preserve"}
        or g.ts[predicate]["dep"] != "advcl"
    ):
        return False
    candidates = [
        n
        for n, f in enumerate(frames)
        if f.kind == "procedure"
        and not f.errors
        and f.heads
        and g.sent[f.heads[0]] == g.sent[predicate]
    ]
    ids = g.subtree(predicate)
    if len(candidates) != 1 or not _nominal_governor_list(g, ids - {predicate}):
        return False
    n = candidates[0]
    f = frames[n]
    span = g.span(ids - {i for i in ids if g.ts[i]["text"] in {".", "?"}})
    frames[n] = replace(
        f,
        question=f.question.rstrip("?") + ", " + span.text + "?",
        prepared_question=f.prepared_question.rstrip("?") + ", " + span.text + "?"
        if f.prepared_question
        else "",
        governors=f.governors + (span,),
        tokens=tuple(sorted(set(f.tokens) | ids)),
    )
    return True


def _method_procedure_request(g):
    if not g.ts or g.lemma(0) not in META or len(set(g.sent.values())) != 1:
        return None
    by = [t["i"] for t in g.ts if g.low(t["i"]) == "by" and t["dep"] == "prep"]
    if len(by) != 1:
        return None
    p = by[0]
    quotes = [c for c in g.children[p] if g.lemma(c) == "quote"]
    heads = [t["i"] for t in g.ts if HEADS.get(g.lemma(t["i"])) == "procedure"]
    if len(quotes) != 1 or len(heads) != 1:
        return None
    quote, head = quotes[0], heads[0]
    scope = set(range(1, p))
    prop = set(range(quote + 1, head + 1))
    tail = set(range(head + 1, len(g.ts)))
    if (
        not scope
        or any(
            g.low(i) in SCOPE_PREPS | MODALS | CONDITIONS | {"and", "or"} for i in scope
        )
        or not any(g.lemma(i) in WHOLE for i in prop)
    ):
        return None
    if not _nominal_governor_list(g, tail):
        return None
    if not _procedure_modifiers_closed(g, head, prop) or any(
        g.low(i) != "its" for i in g.reference(prop | tail)
    ):
        return None
    ids = set(range(len(g.ts)))
    gov = g.span(
        {
            i
            for i in tail
            if g.ts[i]["pos"] != "PUNCT" or g.ts[i]["text"] not in {".", "?", ","}
        }
    )
    question = f"For {g.topic(scope)}, what is {g.text(prop)}, including {gov.text}?"
    return DependencyFrame(
        g.span(ids),
        question,
        "procedure",
        g.topic(scope),
        g.text(prop),
        g.ts[head]["text"],
        tuple(sorted(ids)),
        (0, head),
        scopes=(g.span(scope),),
        governors=(gov,),
        references=tuple(g.span({i}) for i in g.reference(ids)),
        grammar="explicit_quote_method_request",
    )


def _how_whole_procedure(g):
    if len(set(g.sent.values())) != 1:
        return None
    roots = [
        t["i"]
        for t in g.ts
        if t["dep"] == "ROOT"
        and g.lemma(t["i"]) in {"perform", "carry", "do", "execute", "run"}
    ]
    cues = [
        t["i"]
        for t in g.ts
        if g.low(t["i"]) in {"who", "what", "which", "how", "where", "when", "why"}
    ]
    if len(roots) != 1 or len(cues) != 1 or g.low(cues[0]) != "how":
        return None
    pred = roots[0]
    markers = [t["i"] for t in g.ts if g.lemma(t["i"]) == "include"]
    stop = min(markers + [len(g.ts)])
    core = set(range(stop))
    if not any(g.lemma(i) in WHOLE for i in core):
        return None
    if markers and not _nominal_governor_list(g, set(range(markers[0] + 1, len(g.ts)))):
        return None
    subjects = [c for c in g.children[pred] if g.ts[c]["dep"] in {"nsubj", "nsubjpass"}]
    if len(subjects) != 1:
        return None
    scopes = [(g.scope_nominal(subjects[0]), g.subtree(subjects[0]))] + g.direct_scopes(
        pred
    )
    topic, refs, _, errors, _ = _close_scope(g, scopes)
    if errors:
        return None
    ids = set(range(len(g.ts)))
    ast = g.condition_clauses(ids)
    condition_ids = set().union(*(set(c.token_indices) for c in ast))
    governor_ids = set(range(markers[0], len(g.ts))) if markers else set()
    if any(
        i in g.predicates and i != pred and i not in condition_ids | governor_ids
        for i in ids
    ) or any(g.low(i) in {"and", "or", "then"} for i in core - condition_ids):
        return None
    if g.qualifier_spans(ids - condition_ids - set(cues), CONDITIONS):
        return None
    governors = tuple(
        g.span(
            set(range(p, len(g.ts))) - {i for i in ids if g.ts[i]["text"] in {".", "?"}}
        )
        for p in markers
    )
    return DependencyFrame(
        g.span(ids),
        g.raw.rstrip("? ") + "?",
        "procedure",
        topic,
        g.text(core),
        g.ts[pred]["text"],
        tuple(sorted(ids)),
        (pred,),
        scopes=refs,
        conditions=tuple(c.evidence for c in ast),
        condition_ast=ast,
        modality=g.qualifier_spans(ids, MODALS),
        units=g.literal_units(ids),
        governors=governors,
        grammar="whole_procedure_manner_question",
    )


def _recovery_conditions(g):
    ids = set(range(len(g.ts)))
    ast = g.condition_clauses(ids)
    owned = set().union(*(set(c.token_indices) for c in ast))
    if g.qualifier_spans(ids - owned, CONDITIONS) or g.qualifier_spans(
        ids - owned, MODALS
    ):
        return None
    return ast


def _nominal_parts(g, ids):
    parts, part, syntax = [], set(), set()
    for i in sorted(ids):
        separator = g.ts[i]["text"] == "," or g.low(i) == "and"
        hyphen = (
            i
            and g.ts[i - 1]["text"] == "-"
            or i + 1 < len(g.ts)
            and g.ts[i + 1]["text"] == "-"
        )
        if separator and not hyphen:
            if part:
                parts.append(part)
                part = set()
            syntax.add(i)
        else:
            part.add(i)
    if part:
        parts.append(part)
    return parts, syntax


def _scope_at_preposition(g, p):
    objects = [c for c in g.children[p] if g.ts[c]["dep"] in {"pobj", "pcomp"}]
    if len(objects) != 1:
        return []
    nominal = g.scope_nominal(objects[0])
    nested = [s for s in g.direct_scopes(objects[0]) if not s[0] <= nominal]
    return [(nominal, g.subtree(p))] + nested


def _raw_time_unit(g, p, stop):
    ids = set()
    for i in range(p + 1, stop):
        if g.ts[i]["text"] == "," or g.low(i) == "and":
            break
        ids.add(i)
    if (
        ids
        and g.lemma(max(ids)) in {"second", "minute", "hour"}
        and not any(g.ts[i]["pos"] == "PROPN" for i in ids)
    ):
        return ids
    return set()


def _recovered_frame(
    g, head, prop, scopes, ast, *, governors=(), units=(), errors=(), grammar
):
    kind, head_error = _head_kind(g, head)
    topic, scope_refs, scope_owned, scope_errors, _ = _close_scope(g, scopes)
    errors = tuple(errors) + tuple(scope_errors) + ((head_error,) if head_error else ())
    if kind == "procedure" and not any(g.lemma(i) in WHOLE for i in prop):
        errors += ("procedure_extent_not_declared",)
    conditions = tuple(c.evidence for c in ast)
    condition_ids = set().union(*(set(c.token_indices) for c in ast))
    governor_ids = {
        t["i"]
        for t in g.ts
        for s in governors
        if s.start <= t["start"] and t["end"] <= s.end
    }
    owned = set(prop) | scope_owned | condition_ids | governor_ids
    ref_ids = g.reference(owned)
    if any(g.low(i) != "its" for i in ref_ids):
        errors += ("unresolved_reference_or_dependent_attribute",)
    # An entity-scoped procedure's "its" does not bind a governor/condition's
    # antecedent. Such references need an explicit consumer relation, which this
    # recovery does not define. Keep their literal evidence and fail closed.
    if set(ref_ids) & governor_ids:
        errors += ("unresolved_governor_reference",)
    if set(ref_ids) & condition_ids:
        errors += ("unresolved_condition_reference",)
    if set(ref_ids) & scope_owned:
        errors += ("unresolved_scope_reference",)
    property_text = g.text(prop)
    question = (
        "Who is " if kind in {"owner", "deputy"} else "What is "
    ) + property_text
    if topic:
        question = f"For {topic}, " + question[0].lower() + question[1:]
    question += "".join(", " + s.text for s in governors + conditions)
    return DependencyFrame(
        g.span(owned),
        question + "?",
        kind,
        topic,
        property_text,
        g.lemma(head),
        tuple(sorted(owned)),
        (head,),
        scopes=scope_refs,
        conditions=conditions,
        modality=g.qualifier_spans(owned, MODALS),
        units=tuple(dict.fromkeys(tuple(units) + g.literal_units(owned))),
        governors=governors,
        references=tuple(g.span(g.nominal(i)) for i in ref_ids),
        errors=tuple(dict.fromkeys(errors)),
        grammar=grammar,
        condition_ast=ast,
    )


def _recover_scalar_coordination(g):
    """Close a raw coordinated NP list even if a nominal modifier is a verb.

    Every slot must expose a scalar head, with no finite action/WH clause. Its
    complete literal modifier phrase remains the requested property.
    """
    operators = [i for i in g.predicates if g.lemma(i) in META]
    ast = _recovery_conditions(g)
    if (
        len(operators) != 1
        or ast is None
        or any(
            g.low(t["i"]) in {"who", "what", "which", "how", "where", "when", "why"}
            for t in g.ts
        )
    ):
        return None
    pred = operators[0]
    condition_ids = set().union(*(set(c.token_indices) for c in ast))
    stop = min(condition_ids | {len(g.ts)})
    prep_ids = [
        i
        for i in range(pred + 1, stop)
        if g.ts[i]["dep"] in {"prep", "dative"}
        and g.low(i) in SCOPE_PREPS
        and not (g.low(i) == "in" and _raw_time_unit(g, i, stop))
    ]
    boundary = min(prep_ids + [stop])
    region = {i for i in range(pred + 1, boundary) if g.ts[i]["text"] not in {".", "?"}}
    parts, syntax = _nominal_parts(g, region)
    scalar = {"quantity", "duration", "location", "start_time", "weekday"}
    heads = [
        max((i for i in part if HEADS.get(g.lemma(i)) in scalar), default=-1)
        for part in parts
    ]
    if (
        len(parts) < 2
        or -1 in heads
        or not any(g.ts[i]["dep"] in {"appos", "advcl"} for i in region)
    ):
        return None
    if any(
        g.ts[i]["tag"] in {"VB", "VBD", "VBP", "VBZ", "MD"} or g.low(i) == "then"
        for i in region
    ):
        return None
    if any(
        i != pred and i not in region and i not in condition_ids for i in g.predicates
    ):
        return None
    scopes = [s for p, _ in g.pp(pred) if p < pred for s in _scope_at_preposition(g, p)]
    if prep_ids:
        scopes += _scope_at_preposition(g, boundary)
    if not scopes:
        return None
    frames = []
    for part, head in zip(parts, heads, strict=True):
        if any(
            g.ts[i]["pos"] == "VERB"
            and g.ts[i]["tag"] == "VBG"
            and (i + 1 not in part or HEADS.get(g.lemma(i + 1)) not in scalar)
            for i in part
        ):
            return None
        units = tuple(
            g.span(_raw_time_unit(g, i, max(part) + 1))
            for i in part
            if g.low(i) == "in" and _raw_time_unit(g, i, max(part) + 1)
        )
        frames.append(
            _recovered_frame(
                g,
                head,
                part,
                scopes,
                ast,
                units=units,
                grammar="closed_coordinated_scalar_nps",
            )
        )
    g.syntax.update(syntax | {pred})
    return frames


def _bundle_procedure_scopes(g, proc):
    scopes = []
    for nominal, covered in g.direct_scopes(proc):
        # A parser may attach a coordinated governor below the PP's noun. A
        # scope owns the nominal and its connecting preposition, not that tail.
        links = {
            g.ts[i]["head"]
            for i in nominal
            if g.ts[i]["head"] in covered and g.ts[g.ts[i]["head"]]["dep"] == "prep"
        }
        scopes.append((nominal, nominal | links))
    return scopes


def _bundle_role_scopes(g, parts, front_scopes, predicate):
    scopes, errors = [], []
    for part in parts:
        head = max(part)
        prefix = part - {head}
        nominal_roots = {
            i
            for i in prefix
            if g.ts[i]["head"] == head
            and g.ts[i]["dep"] in {"compound", "nmod"}
            and g.ts[i]["pos"] in {"NOUN", "PROPN"}
        }
        nominal_tokens = {i for i in prefix if g.ts[i]["pos"] in {"NOUN", "PROPN"}}
        components = set().union(
            *(
                g.nominal(i)
                for i in prefix
                if g.ts[i]["head"] == predicate
                and g.ts[i]["dep"] in ARG_DEPS
                and g.ts[i]["pos"] in {"NOUN", "PROPN"}
            )
        )
        ambiguous = (
            bool(nominal_tokens and not nominal_roots)
            or not part <= g.nominal(head) | components
        )
        own = ([(prefix, prefix)] if nominal_roots else []) + front_scopes
        scopes.append(own or (scopes[0] if scopes else []))
        errors.append(("unresolved_role_scope_attachment",) if ambiguous else ())
    return scopes, errors


def _recover_role_procedure_bundle(g):
    """Meta collection of role NPs with/alongside a separate whole procedure."""
    operators = [
        i
        for i in g.predicates
        if g.lemma(i) == "combine"
        or g.lemma(i) == "need"
        and any(g.low(c) in {"i", "we"} for c in g.children[i])
    ]
    ast = _recovery_conditions(g)
    if len(operators) != 1 or ast is None:
        return None
    pred = operators[0]
    connectors = [
        t["i"]
        for t in g.ts
        if g.low(t["i"]) in {"with", "alongside"} and t["dep"] == "prep"
    ]
    procedure_heads = [
        t["i"] for t in g.ts if HEADS.get(g.lemma(t["i"])) == "procedure"
    ]
    if len(connectors) != 1 or len(procedure_heads) != 1:
        return None
    connector, proc = connectors[0], procedure_heads[0]
    if not pred < connector < proc:
        return None
    parts, syntax = _nominal_parts(g, set(range(pred + 1, connector)))
    if not parts or any(
        HEADS.get(g.lemma(max(p))) not in {"owner", "deputy"} for p in parts
    ):
        return None
    condition_ids = set().union(*(set(c.token_indices) for c in ast))
    if any(
        g.low(i) in {"who", "what", "which", "how", "where", "when", "why"}
        for i in range(len(g.ts))
        if i not in condition_ids
    ):
        return None
    if any(i != pred and i not in condition_ids for i in g.predicates):
        return None
    front_scopes = [
        s for p, _ in g.pp(pred) if p < pred for s in _scope_at_preposition(g, p)
    ]
    role_scopes, role_errors = _bundle_role_scopes(g, parts, front_scopes, pred)
    scopes = role_scopes[0]
    if not scopes:
        return None
    prop = set(range(connector + 1, proc + 1))
    own_scopes = _bundle_procedure_scopes(g, proc)
    collection_scopes = [s for group in role_scopes for s in group]
    target_scopes = own_scopes or collection_scopes
    role_topics = {_close_scope(g, group)[0] for group in role_scopes}
    conflict = bool(g.reference(prop)) and (
        len(role_topics) != 1
        or own_scopes
        and role_topics != {_close_scope(g, own_scopes)[0]}
    )
    tail = set(range(proc + 1, len(g.ts))) - condition_ids - g.syntax
    scope_owned = set().union(*(s[1] for s in own_scopes)) if own_scopes else set()
    tail -= scope_owned
    markers = [i for i in tail if g.lemma(i) == "include"]
    govern = tail - set(markers)
    if govern and not _nominal_governor_list(g, govern):
        return None
    governors = (g.span(tail),) if tail else ()
    frames = [
        _recovered_frame(
            g,
            max(p),
            p,
            group,
            ast,
            errors=errors,
            grammar="coordinated_role_procedure_request",
        )
        for p, group, errors in zip(parts, role_scopes, role_errors, strict=True)
    ]
    frames.append(
        _recovered_frame(
            g,
            proc,
            prop,
            target_scopes,
            ast,
            governors=governors,
            errors=("conflicting_entity_reference_scope",) if conflict else (),
            grammar="coordinated_role_procedure_request",
        )
    )
    neutral = {i for i in g.children[pred] if g.low(i) in {"i", "we", "please"}}
    g.syntax.update(syntax | neutral | {pred, connector})
    return frames


def _procedure_tail_closed(
    g, tail, scope_owned, ast_ids, adjunct_ids, passive_syntax, references, ids
):
    if tail - scope_owned - ast_ids - adjunct_ids - g.syntax - passive_syntax:
        return False
    if any(g.ts[i]["pos"] == "PROPN" for i in adjunct_ids):
        return False
    if any(
        HEADS.get(g.lemma(i))
        in {"owner", "deputy", "quantity", "duration", "location", "availability"}
        and g.ts[i]["dep"] not in {"compound", "nmod", "amod"}
        for i in adjunct_ids
    ):
        return False
    if references and not all(
        g.lemma(i) in {"start", "finish"}
        for i in ids
        if g.ts[i]["dep"] == "pobj" and g.low(g.ts[i]["head"]) == "from"
    ):
        return False
    return True
