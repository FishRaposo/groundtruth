"""Pure whole-source declarations; no evidence, authority or completeness grants.

All graph reading uses actual supplied captures and immutable original offsets.
The initial closed productions are intentionally narrow. Unknown and opposing
source units remain in the inventory; no request or answer is resolved here.
"""

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace

from app.request_parser_catalog import MAX_QUESTION_CHARS
from app.services.request_parser import _native

MAX_DOCUMENTS = 128
MAX_BODY_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_WINDOWS = 256


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def body_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class RawRange:
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class SourceIdentity:
    document_id: str
    document_version: int
    content_hash: str
    workspace_id: str
    snapshot_id: str


@dataclass(frozen=True)
class SourceChunk:
    chunk_id: str
    ordinal: int
    literal: RawRange
    metadata_json: str = "{}"


@dataclass(frozen=True)
class SourceSnapshot:
    identity: SourceIdentity
    title: str
    body: str
    metadata_json: str
    chunks: tuple[SourceChunk, ...]


@dataclass(frozen=True)
class CaptureWindow:
    start: int
    end: int
    capture_json: str


@dataclass(frozen=True)
class SourceCaptures:
    identity: SourceIdentity
    windows: tuple[CaptureWindow, ...]


@dataclass(frozen=True)
class PlanningUniverse:
    scope_json: str
    publications: tuple[SourceIdentity, ...]
    selection_mode: str


@dataclass(frozen=True)
class SnapshotRead:
    identity: SourceIdentity
    title: str
    metadata_json: str
    chunks: tuple[SourceChunk, ...]


@dataclass(frozen=True)
class CaptureWindowRead:
    start: int
    end: int
    capture_sha256: str
    annotation_sha256: str
    parser_sha256: str


@dataclass(frozen=True)
class CaptureRead:
    identity: SourceIdentity
    windows: tuple[CaptureWindowRead, ...]


@dataclass(frozen=True)
class PlanningReadSet:
    universe: PlanningUniverse
    snapshot_reads: tuple[SnapshotRead, ...]
    capture_reads: tuple[CaptureRead, ...]
    missing_publications: tuple[SourceIdentity, ...]
    universe_completeness: str = "NOT_ESTABLISHED"
    support_or_permissions: str = "NOT_ASSESSED"

    def record(self):
        return json.loads(
            canonical(dict(contract="request-planning-read-set-v1", **asdict(self)))
        )


@dataclass(frozen=True)
class SourceQuantifier:
    kind: str
    raw: RawRange
    head_index: int
    token_indices: tuple[int, ...]
    semantic_status: str = "UNASSESSED_QUANTIFIER"


@dataclass(frozen=True)
class SourceQualifier:
    kind: str
    raw: RawRange
    head_index: int
    token_indices: tuple[int, ...]
    semantic_status: str = "UNASSESSED_QUALIFIER"


@dataclass(frozen=True)
class SourceArgument:
    kind: str
    head_index: int
    literal: RawRange
    core: RawRange
    token_indices: tuple[int, ...]
    qualifiers: tuple[SourceQualifier, ...]
    quantifiers: tuple[SourceQuantifier, ...]
    unknowns: tuple[str, ...]


@dataclass(frozen=True)
class SourceUnit:
    id: str
    source: SourceIdentity
    raw: RawRange
    capture_sha256: str
    capture_window: RawRange
    head_indices: tuple[int, ...]
    features_json: str
    grammar: str
    unknowns: tuple[str, ...]
    qualifiers: tuple[SourceQualifier, ...] = ()
    quantifiers: tuple[SourceQuantifier, ...] = ()


@dataclass(frozen=True)
class Declaration:
    id: str
    kind: str
    unit_id: str
    source: SourceIdentity
    raw: RawRange
    literal: RawRange
    scope: tuple[RawRange, ...]
    members: tuple[RawRange, ...]
    features_json: str
    payload_json: str
    status: str = "UNASSESSED_PROPOSAL"
    arguments: tuple[SourceArgument, ...] = ()


@dataclass(frozen=True)
class DeclarationInventory:
    read_set: PlanningReadSet
    units: tuple[SourceUnit, ...]
    declarations: tuple[Declaration, ...]
    blockers: tuple[str, ...]
    support_or_permissions: str = "NOT_ASSESSED"

    def record(self):
        return json.loads(
            canonical(
                dict(
                    contract="request-declaration-inventory-proposal-v2", **asdict(self)
                )
            )
        )


@dataclass(frozen=True)
class CatalogueProposal:
    operation: str
    scope_literal: str
    catalogues: tuple[Declaration, ...]
    actor_values_required: bool
    blockers: tuple[str, ...]
    read_set_sha256: str
    support_or_permissions: str = "NOT_ASSESSED"


def _require(value, message):
    if not value:
        raise ValueError(message)


def _json_object(raw):
    _require(type(raw) is str, "Canonical JSON string required")

    def pairs(items):
        out = {}
        for key, value in items:
            _require(key not in out, "Duplicate JSON field")
            out[key] = value
        return out

    value = json.loads(raw, object_pairs_hook=pairs)
    _native(value)
    _require(
        type(value) is dict and canonical(value) == raw,
        "Exact canonical JSON object required",
    )
    return value


def _identity(value: SourceIdentity) -> SourceIdentity:
    _require(type(value) is SourceIdentity, "Typed immutable source identity required")
    for name in ("document_id", "workspace_id", "snapshot_id"):
        field = getattr(value, name)
        _require(
            type(field) is str and field.strip() and len(field) <= 512,
            "Invalid immutable source identity",
        )
    _require(
        type(value.document_version) is int and value.document_version > 0,
        "Invalid immutable version",
    )
    _require(
        type(value.content_hash) is str
        and re.fullmatch("[0-9a-f]{64}", value.content_hash) is not None,
        "Invalid immutable content hash",
    )
    return value


def _range(body: str, start: int, end: int) -> RawRange:
    _require(
        type(start) is int and type(end) is int and 0 <= start < end <= len(body),
        "Invalid original-body range",
    )
    return RawRange(start, end, body[start:end])


def _required_literal(value: RawRange | None) -> RawRange:
    if value is None:
        raise ValueError("Nonempty source literal required")
    return value


def _snapshot(snapshot: SourceSnapshot):
    _require(type(snapshot) is SourceSnapshot, "Typed source snapshot required")
    _identity(snapshot.identity)
    _require(
        type(snapshot.body) is str and snapshot.body.strip(),
        "Nonempty canonical body required",
    )
    _require(
        len(snapshot.body.encode()) <= MAX_BODY_BYTES,
        "Whole source body budget exceeded",
    )
    _require(
        body_hash(snapshot.body) == snapshot.identity.content_hash,
        "Canonical body hash mismatch",
    )
    _require(type(snapshot.title) is str, "Literal title string required")
    _json_object(snapshot.metadata_json)
    _require(
        type(snapshot.chunks) is tuple and snapshot.chunks,
        "Complete nonempty immutable chunk membership required",
    )
    seen = set()
    for ordinal, chunk in enumerate(snapshot.chunks):
        _require(
            type(chunk) is SourceChunk
            and type(chunk.chunk_id) is str
            and chunk.chunk_id.strip()
            and chunk.chunk_id not in seen,
            "Invalid or duplicate chunk identity",
        )
        _require(
            type(chunk.ordinal) is int and chunk.ordinal == ordinal,
            "Chunk ordinal inventory differs",
        )
        _require(
            type(chunk.literal) is RawRange
            and chunk.literal
            == _range(snapshot.body, chunk.literal.start, chunk.literal.end),
            "Chunk literal does not match immutable body",
        )
        _json_object(chunk.metadata_json)
        seen.add(chunk.chunk_id)


def _inputs(
    manifest: PlanningUniverse,
    snapshots: tuple[SourceSnapshot, ...],
    captures: tuple[SourceCaptures, ...],
):
    from app.services.source_capture_validation import validate_serialized_capture

    _require(type(manifest) is PlanningUniverse, "Typed planning universe required")
    _json_object(manifest.scope_json)
    _require(
        type(manifest.publications) is tuple
        and len(manifest.publications) <= MAX_DOCUMENTS,
        "Planning universe document budget exceeded",
    )
    _require(
        type(manifest.selection_mode) is str
        and manifest.selection_mode
        in {"bounded_authorized_scan", "ranked_subset", "unknown"},
        "Unknown planning selection mode",
    )
    publications = {}
    for identity in manifest.publications:
        _identity(identity)
        _require(
            identity.document_id not in publications,
            "Ambiguous or duplicate publication membership",
        )
        publications[identity.document_id] = identity
    _require(
        type(snapshots) is tuple and type(captures) is tuple,
        "Immutable source/capture tuples required",
    )
    _require(
        len(snapshots) <= MAX_DOCUMENTS and len(captures) == len(snapshots),
        "Snapshot/capture count differs",
    )
    by_id = {}
    total = 0
    for snapshot in snapshots:
        _snapshot(snapshot)
        sid = snapshot.identity.document_id
        _require(
            sid not in by_id and publications.get(sid) == snapshot.identity,
            "Duplicate, unlisted or changed snapshot identity",
        )
        by_id[sid] = snapshot
        total += len(snapshot.body.encode())
    _require(total <= MAX_TOTAL_BYTES, "Total immutable source byte budget exceeded")
    validated = {}
    for item in captures:
        _require(type(item) is SourceCaptures, "Typed source captures required")
        _identity(item.identity)
        sid = item.identity.document_id
        _require(
            sid in by_id
            and sid not in validated
            and item.identity == by_id[sid].identity,
            "Capture membership/identity differs",
        )
        _require(
            type(item.windows) is tuple and 0 < len(item.windows) <= MAX_WINDOWS,
            "Source capture window budget exceeded",
        )
        cursor = 0
        windows = []
        for window in item.windows:
            _require(type(window) is CaptureWindow, "Typed capture window required")
            _require(
                type(window.start) is int
                and type(window.end) is int
                and window.start == cursor
                and window.start < window.end <= len(by_id[sid].body)
                and window.end - window.start <= MAX_QUESTION_CHARS,
                "Captures must cover the canonical body exactly within bounds",
            )
            capture = _json_object(window.capture_json)
            annotation = validate_serialized_capture(
                by_id[sid].body[window.start : window.end], window.capture_json
            )
            windows.append((window, capture, annotation))
            cursor = window.end
        _require(
            cursor == len(by_id[sid].body), "Source captures omit immutable body tail"
        )
        validated[sid] = windows
    _require(set(validated) == set(by_id), "Source capture membership differs")
    return by_id, validated


def _read_set(manifest: PlanningUniverse, by_id, validated) -> PlanningReadSet:
    snapshots = []
    captures = []
    missing = []
    for identity in manifest.publications:
        sid = identity.document_id
        if sid not in by_id:
            missing.append(identity)
            continue
        source = by_id[sid]
        snapshots.append(
            SnapshotRead(identity, source.title, source.metadata_json, source.chunks)
        )
        captures.append(
            CaptureRead(
                identity,
                tuple(
                    CaptureWindowRead(
                        window.start,
                        window.end,
                        capture["capture_sha256"],
                        capture["annotation_sha256"],
                        digest(capture["parser"]),
                    )
                    for window, capture, _ in validated[sid]
                ),
            )
        )
    return PlanningReadSet(manifest, tuple(snapshots), tuple(captures), tuple(missing))


class _Graph:
    def __init__(self, body, offset, annotation):
        self.body, self.offset, self.tokens = body, offset, annotation["tokens"]

    def literal(self, indices):
        ids = sorted(set(indices))
        if not ids:
            return None
        if ids != list(range(ids[0], ids[-1] + 1)):
            return None
        return _range(
            self.body,
            self.offset + self.tokens[ids[0]]["start"],
            self.offset + self.tokens[ids[-1]]["end"],
        )

    def subtree(self, head):
        found = set()
        pending = [head]
        while pending:
            current = pending.pop()
            if current in found:
                continue
            found.add(current)
            pending += self.tokens[current]["children"]
        return found

    def nominal(self, head, *, determiners=False):
        deps = {"compound", "amod", "nmod", "nummod", "poss", "case", "appos"}
        if determiners:
            deps.add("det")
        found = {head}
        pending = [head]
        while pending:
            current = pending.pop()
            for child in self.tokens[current]["children"]:
                if self.tokens[child]["dep"] in deps:
                    found.add(child)
                    pending.append(child)
        return found

    def phrase(self, head, *, scalar=False):
        if self.tokens[head]["pos"] not in (
            {"NOUN", "PROPN", "NUM"} if scalar else {"NOUN", "PROPN"}
        ):
            return None
        return self.argument(head, "literal_argument").literal

    def extent(self, indices):
        indices = sorted(set(indices))
        if not indices:
            return None
        return _range(
            self.body,
            self.offset + self.tokens[indices[0]]["start"],
            self.offset + self.tokens[indices[-1]]["end"],
        )

    def _coordination_root(self, index):
        while self.tokens[index]["dep"] == "conj":
            index = self.tokens[index]["head"]
        return index

    def _conjunct_component(self, ids, anchor):
        component = {anchor}
        pending = [anchor]
        while pending:
            current = pending.pop()
            for child in self.tokens[current]["children"]:
                if (
                    child in ids
                    and self.tokens[child]["dep"] == "conj"
                    and child not in component
                ):
                    component.add(child)
                    pending.append(child)
        return component

    def _coordinator_reasons(self, heads, operators):
        reasons = []
        targets = {head: [] for head in heads[1:]}
        for operator in operators:
            before = [head for head in heads if head < operator]
            after = [head for head in heads if head > operator]
            if not before or not after:
                reasons.append("operator_without_two_actual_arguments")
                continue
            target = after[0]
            if target not in targets:
                reasons.append("operator_without_actual_conjunct")
                continue
            targets[target].append(operator)
            if self.tokens[operator]["lemma"].casefold() != "and":
                reasons.append("unsupported_coordinator")
        return targets, reasons

    def _coordination_group(self, ids, anchor):
        component = self._conjunct_component(ids, anchor)
        heads = sorted(component)
        operators = sorted(
            i
            for i in ids
            if self.tokens[i]["dep"] == "cc" and self.tokens[i]["head"] in component
        )
        separators = sorted(
            i
            for i in ids
            if self.tokens[i]["dep"] == "punct"
            and self.tokens[i]["text"] == ","
            and self.tokens[i]["head"] in component
        )
        reasons = []
        if len(heads) < 2:
            reasons.append("missing_actual_conjunct")
        if heads[0] != anchor:
            reasons.append("ambiguous_conjunct_order")
        targets, operator_reasons = self._coordinator_reasons(heads, operators)
        reasons.extend(operator_reasons)
        for prior, target in zip(heads, heads[1:], strict=False):
            markers = targets[target]
            commas = [i for i in separators if prior < i < target]
            if len(markers) > 1:
                reasons.append("multiple_operators_for_one_conjunct")
            if not markers and not commas:
                reasons.append("unrepresented_conjunct_separator")
        if any(
            not any(
                prior < comma < target
                for prior, target in zip(heads, heads[1:], strict=False)
            )
            for comma in separators
        ):
            reasons.append("separator_without_actual_conjunct")
        return {
            "head_indices": heads,
            "operator_indices": operators,
            "separator_indices": separators,
            "operators": [
                asdict(_required_literal(self.literal({i}))) for i in operators
            ],
            "syntax_closed": not reasons,
            "reasons": list(dict.fromkeys(reasons)),
        }

    def coordination(self, indices):
        """Reconstruct actual conjunct sets; raw coordinator tokens are not closure.

        This is a bounded syntax production only. In particular, closure does
        not choose actors, support a catalogue or grant source authority.
        """
        ids = set(indices)

        anchors = {
            self._coordination_root(i) for i in ids if self.tokens[i]["dep"] == "conj"
        }
        anchors.update(
            self._coordination_root(self.tokens[i]["head"])
            for i in ids
            if self.tokens[i]["dep"] == "cc"
        )
        groups = []
        closed_markers = set()
        unresolved_markers = set()
        unresolved_heads = set()
        for anchor in sorted(anchors):
            group = self._coordination_group(ids, anchor)
            if group["syntax_closed"]:
                closed_markers.update(group["operator_indices"])
            else:
                unresolved_markers.update(group["operator_indices"])
                unresolved_heads.update(group["head_indices"])
            groups.append(group)
        return {
            "groups": groups,
            "closed_marker_indices": sorted(closed_markers),
            "unresolved_marker_indices": sorted(unresolved_markers),
            "unresolved_head_indices": sorted(unresolved_heads),
        }

    def quantifiers(self, indices):
        result = []
        for i in sorted(indices):
            t = self.tokens[i]
            word = t["lemma"].casefold()
            if t["dep"] == "nummod":
                kind = "cardinal"
            elif t["dep"] == "det" and word not in {"a", "an", "the"}:
                kind = (
                    "indefinite_quantity"
                    if word in {"some", "several", "many", "few", "much", "little"}
                    else "universal"
                    if word in {"all", "each", "every", "both", "any"}
                    else "unclassified_determiner"
                )
            else:
                continue
            owned = self.subtree(i) & set(indices)
            result.append(
                SourceQuantifier(
                    kind,
                    _required_literal(self.extent(owned)),
                    t["head"],
                    tuple(sorted(owned)),
                )
            )
        return tuple(result)

    def _nominal_qualifiers(self, nominal):
        qualifiers, unknowns = [], []
        for i in sorted(nominal):
            if self.tokens[i]["dep"] in {"amod", "poss", "nmod", "appos"}:
                subtree = self.subtree(i) & nominal
                qkind = (
                    "nominal_relation"
                    if self.tokens[i]["dep"] in {"poss", "nmod", "appos"}
                    else "nominal_modifier"
                )
                qualifiers.append(
                    SourceQualifier(
                        qkind,
                        _required_literal(self.extent(subtree)),
                        i,
                        tuple(sorted(subtree)),
                    )
                )
                unknowns.append("argument_qualifier_meaning_unassessed")
        return qualifiers, unknowns

    def argument(self, head, kind, *, allow_governing_scope=False):
        nominal = self.nominal(head, determiners=True)
        owned = set(nominal)
        qualifiers = []
        unknowns = []
        for anchor in sorted(nominal):
            for child in self.tokens[anchor]["children"]:
                t = self.tokens[child]
                if child in nominal or t["dep"] in {"conj", "cc", "punct"}:
                    continue
                subtree = self.subtree(child)
                owned.update(subtree)
                if t["dep"] == "prep":
                    known_scope = (
                        allow_governing_scope
                        and anchor == head
                        and t["lemma"].casefold() in {"for", "of", "in", "within"}
                    )
                    qkind = (
                        "governing_scope" if known_scope else "prepositional_qualifier"
                    )
                    if not known_scope:
                        unknowns.append("argument_qualifier_meaning_unassessed")
                else:
                    qkind = "unsupported_" + t["dep"]
                    unknowns.append("unsupported_argument_attachment")
                qualifiers.append(
                    SourceQualifier(
                        qkind,
                        _required_literal(self.extent(subtree)),
                        child,
                        tuple(sorted(subtree)),
                    )
                )
        nominal_qualifiers, nominal_unknowns = self._nominal_qualifiers(nominal)
        qualifiers.extend(nominal_qualifiers)
        unknowns.extend(nominal_unknowns)
        quantifiers = self.quantifiers(nominal)
        if quantifiers:
            unknowns.append("source_quantifier_meaning_unassessed")
        core_ids = nominal - {i for q in quantifiers for i in q.token_indices}
        core_ids -= {
            i
            for q in qualifiers
            if q.kind == "nominal_relation"
            for i in q.token_indices
        }
        if not core_ids:
            core_ids = {head}
        core = _required_literal(self.extent(core_ids))
        if sorted(owned) != list(range(min(owned), max(owned) + 1)):
            unknowns.append("noncontiguous_argument_projection")
        coordination = self.coordination(range(len(self.tokens)))
        if owned.intersection(
            coordination["unresolved_head_indices"]
            + coordination["unresolved_marker_indices"]
        ):
            unknowns.append("unclosed_source_coordination")
        return SourceArgument(
            kind,
            head,
            _required_literal(self.extent(owned)),
            core,
            tuple(sorted(owned)),
            tuple(qualifiers),
            quantifiers,
            tuple(dict.fromkeys(unknowns)),
        )

    def coordinated_arguments(self, head, kind, *, scalar=False):
        pending = [head]
        seen = set()
        result = []
        while pending:
            current = pending.pop(0)
            if current in seen:
                continue
            seen.add(current)
            if self.tokens[current]["pos"] not in (
                {"NOUN", "PROPN", "NUM"} if scalar else {"NOUN", "PROPN"}
            ):
                return ()
            result.append(self.argument(current, kind))
            pending += [
                c
                for c in self.tokens[current]["children"]
                if self.tokens[c]["dep"] == "conj"
            ]
        return tuple(sorted(result, key=lambda a: a.literal.start))

    def scope_arguments(self, head):
        result = []
        for child in self.tokens[head]["children"]:
            t = self.tokens[child]
            if t["dep"] != "prep" or t["lemma"].casefold() not in {
                "for",
                "of",
                "in",
                "within",
            }:
                continue
            for obj in t["children"]:
                if self.tokens[obj]["dep"] == "pobj":
                    result.extend(self.coordinated_arguments(obj, "governing_scope"))
        return tuple(result)

    def scopes(self, head):
        return tuple(a.literal for a in self.scope_arguments(head))

    def coordinated(self, head, *, scalar=False):
        return tuple(
            a.literal
            for a in self.coordinated_arguments(head, "literal_argument", scalar=scalar)
        )


_REFERENCES = {
    "note",
    "annex",
    "appendix",
    "instruction",
    "manual",
    "handbook",
    "guide",
    "policy",
    "protocol",
    "specification",
}
_CONDITIONS = {
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


def _condition_ranges(g, ids):
    conditions, condition_tokens = [], set()
    for i in sorted(ids):
        if g.tokens[i]["dep"] == "advcl":
            descendants = g.subtree(i) & ids
            if any(g.tokens[x]["lemma"].lower() in _CONDITIONS for x in descendants):
                phrase = g.literal(
                    {x for x in descendants if g.tokens[x]["pos"] != "PUNCT"}
                )
                if phrase:
                    conditions.append(phrase)
                    condition_tokens.update(descendants)
    return conditions, condition_tokens


def _token_feature_ranges(g, ids, condition_tokens):
    negation = []
    modality = []
    governors = []
    references = []
    quantifiers = []
    unbound_conditions = []
    for i in sorted(ids):
        t = g.tokens[i]
        lemma = t["lemma"].lower()
        one = g.literal({i})
        if t["dep"] == "neg" or lemma in {"not", "no", "never"}:
            negation.append(one)
        if t["tag"] == "MD":
            modality.append(one)
        if lemma in {"all", "each", "every", "both", "any"}:
            quantifiers.append(one)
        if t["dep"] == "mark" and lemma in _CONDITIONS and i not in condition_tokens:
            unbound_conditions.append(one)
        if lemma in {"govern", "apply", "require"}:
            phrase = g.literal(
                {x for x in g.subtree(i) & ids if g.tokens[x]["pos"] != "PUNCT"}
            )
            if phrase:
                governors.append(phrase)
        if lemma in _REFERENCES and t["pos"] in {"NOUN", "PROPN"}:
            phrase = g.phrase(i)
            if phrase:
                references.append(phrase)
    return negation, modality, governors, references, quantifiers, unbound_conditions


def _source_qualifier_kind(g, i, owned, roots):
    token = g.tokens[i]
    dep = token["dep"]
    word = token["lemma"].casefold()
    if dep == "advcl":
        known = any(
            g.tokens[j]["dep"] == "mark"
            and g.tokens[j]["lemma"].casefold() in _CONDITIONS
            for j in owned
        )
        kind = "condition_clause" if known else "unsupported_advcl"
    elif dep == "prep":
        kind = (
            "condition_pp"
            if word in _CONDITIONS
            else "unsupported_root_pp"
            if token["head"] in roots
            else "argument_pp"
        )
    elif dep == "advmod" and token["head"] in roots:
        kind = "unsupported_advmod"
    elif token["head"] in roots and dep not in {
        "ROOT",
        "nsubj",
        "nsubjpass",
        "attr",
        "oprd",
        "dobj",
        "acomp",
        "aux",
        "auxpass",
        "neg",
        "punct",
        "cc",
        "conj",
    }:
        kind = "unsupported_root_argument"
    else:
        return None
    return kind


def _typed_source_qualifiers(g, ids):
    typed_qualifiers = []
    roots = {i for i in ids if g.tokens[i]["dep"] == "ROOT"}
    for i in sorted(ids):
        owned = g.subtree(i) & ids
        kind = _source_qualifier_kind(g, i, owned, roots)
        if kind is None:
            continue
        # Convex original ranges preserve internal punctuation and every literal
        # attached token. This proposes structure, never semantic closure.
        clause = {j for j in owned if g.tokens[j]["pos"] != "PUNCT"}
        raw = _required_literal(g.extent(clause or owned))
        typed_qualifiers.append(SourceQualifier(kind, raw, i, tuple(sorted(owned))))
    return typed_qualifiers


def _features(g, ids):
    conditions, condition_tokens = _condition_ranges(g, ids)
    negation, modality, governors, references, quantifiers, unbound_conditions = (
        _token_feature_ranges(g, ids, condition_tokens)
    )
    typed_qualifiers = _typed_source_qualifiers(g, ids)
    for qualifier in typed_qualifiers:
        if qualifier.kind == "condition_pp" and qualifier.raw not in conditions:
            conditions.append(qualifier.raw)
    typed_quantifiers = g.quantifiers(ids)
    for q in typed_quantifiers:
        if q.raw not in quantifiers:
            quantifiers.append(q.raw)
    return {
        "conditions": [asdict(x) for x in conditions],
        "unbound_condition_markers": [asdict(x) for x in unbound_conditions],
        "negation": [asdict(x) for x in negation],
        "modality": [asdict(x) for x in modality],
        "governors": [asdict(x) for x in governors],
        "references": [asdict(x) for x in references],
        "quantifiers": [asdict(x) for x in quantifiers],
        "typed_qualifiers": [asdict(x) for x in typed_qualifiers],
        "typed_quantifiers": [asdict(x) for x in typed_quantifiers],
        "coordination_markers": [
            asdict(g.literal({i})) for i in sorted(ids) if g.tokens[i]["dep"] == "cc"
        ],
        "coordination_closure": g.coordination(ids),
        "raw_token_indices": sorted(ids),
        "operative_authority": "NOT_ASSESSED",
        "temporal_meaning": "NOT_ASSESSED",
    }


def _declaration(
    kind,
    unit,
    literal,
    scope=(),
    members=(),
    payload=None,
    status="UNASSESSED_PROPOSAL",
    arguments=(),
):
    fields = {
        "kind": kind,
        "unit_id": unit.id,
        "source": asdict(unit.source),
        "raw": asdict(unit.raw),
        "literal": asdict(literal),
        "scope": [asdict(x) for x in scope],
        "members": [asdict(x) for x in members],
        "features_json": unit.features_json,
        "payload_json": canonical(payload or {}),
        "status": status,
        "arguments": [asdict(x) for x in arguments],
    }
    return Declaration(
        digest(fields),
        kind,
        unit.id,
        unit.source,
        unit.raw,
        literal,
        scope,
        members,
        unit.features_json,
        fields["payload_json"],
        status,
        arguments,
    )


def _role_subject_label(g, subject):
    sh = g.tokens[subject]
    label_ids = set()
    plural = "Number=Plur" in sh["morph"] or sh["text"].casefold() == "roles"
    if not plural:
        for child in sh["children"]:
            ct = g.tokens[child]
            if ct["dep"] in {"compound", "appos", "nmod"} and ct["pos"] in {
                "NOUN",
                "PROPN",
            }:
                label_ids.update(g.nominal(child, determiners=True))
    role_label = g.literal(label_ids)
    return label_ids, role_label


def _role_declarations(
    g, unit, subject, comp, scope, common_arguments, member_arguments
):
    rows, unknowns = [], []
    members = tuple(a.literal for a in member_arguments)
    # A count or free adjective is never a role label. A named singular
    # role needs an actual nominal label constituent, with all other
    # modifiers still represented in the complete subject argument.
    label_ids, role_label = _role_subject_label(g, subject)
    if any(
        g.tokens[i]["dep"] in {"amod", "nummod", "poss"}
        for i in g.nominal(subject)
        if i != subject
    ):
        unknowns.append("role_subject_qualifier_unassessed")
    if role_label is not None:
        value_arguments = g.coordinated_arguments(comp, "actor_value", scalar=True)
        if value_arguments:
            values = [asdict(a.literal) for a in value_arguments]
            payload = {
                "values": values,
                "actor_support": "NOT_ASSESSED",
                "coordination_meaning": "NOT_ASSESSED",
            }
            if len(values) == 1:
                payload["value"] = values[0]
            else:
                unknowns.append("coordinated_actor_values_unresolved")
            label_argument = SourceArgument(
                "role_label",
                subject,
                role_label,
                role_label,
                tuple(sorted(label_ids)),
                (),
                (),
                (),
            )
            rows.append(
                _declaration(
                    "role_assignment",
                    unit,
                    role_label,
                    scope,
                    payload=payload,
                    arguments=common_arguments + (label_argument,) + value_arguments,
                )
            )
    elif members:
        explicit_empty = len(members) == 1 and members[0].text.lower() in {
            "none",
            "empty",
        }
        catalogue = () if explicit_empty else members
        rows.append(
            _declaration(
                "role_catalogue",
                unit,
                g.literal({subject}),
                scope,
                catalogue,
                payload={
                    "membership_support": "NOT_ASSESSED",
                    "explicit_empty_candidate": explicit_empty,
                },
                arguments=common_arguments + member_arguments,
            )
        )
        if explicit_empty:
            unknowns.append("empty_catalogue_not_supported")
    if not scope:
        unknowns.append("governing_scope_unresolved")
    return rows, unknowns


def _field_declarations(g, unit, comp, scope, common_arguments, subject_argument):
    rows, unknowns = [], []
    label = subject_argument.core
    value_arguments = g.coordinated_arguments(comp, "field_value", scalar=True)
    if label and value_arguments:
        values = [asdict(a.literal) for a in value_arguments]
        payload = {
            "values": values,
            "temporal_meaning": "NOT_ASSESSED",
            "coordination_meaning": "NOT_ASSESSED",
        }
        if len(values) == 1:
            payload["value"] = values[0]
        else:
            unknowns.append("coordinated_field_values_unresolved")
        rows.append(
            _declaration(
                "literal_field",
                unit,
                label,
                scope,
                payload=payload,
                arguments=common_arguments + value_arguments,
            )
        )
        if not scope:
            unknowns.append("governing_scope_unresolved")
    return rows, unknowns


def _subject_declarations(g, unit, lemma, subject, comp):
    rows, unknowns, all_arguments = [], [], []
    sh = g.tokens[subject]
    subject_argument = g.argument(
        subject, "declaration_subject", allow_governing_scope=True
    )
    scope_arguments = g.scope_arguments(subject)
    scope = tuple(a.literal for a in scope_arguments)
    common_arguments = (subject_argument, *scope_arguments)
    member_arguments = g.coordinated_arguments(comp, "catalogue_member")
    members = tuple(a.literal for a in member_arguments)
    all_arguments.extend(common_arguments)
    if (
        lemma in {"call", "name"}
        and sh["dep"] == "nsubjpass"
        and sh["pos"] == "NOUN"
        and members
    ):
        # The literal label is proposed; surrounding predicates/authority
        # remain retained in the whole source unit and are never discharged.
        for member in members:
            rows.append(
                _declaration(
                    "literal_name",
                    unit,
                    member,
                    scope,
                    payload={
                        "declared_subject": asdict(g.phrase(subject))
                        if g.phrase(subject)
                        else None
                    },
                    arguments=common_arguments
                    + g.coordinated_arguments(comp, "declared_name"),
                )
            )
    elif lemma == "be" and sh["lemma"].lower() in {"name", "label"} and members:
        for member in members:
            rows.append(
                _declaration(
                    "literal_name",
                    unit,
                    member,
                    scope,
                    arguments=common_arguments
                    + g.coordinated_arguments(comp, "declared_name"),
                )
            )
    elif lemma == "be" and sh["lemma"].lower() == "role":
        role_rows, role_unknowns = _role_declarations(
            g, unit, subject, comp, scope, common_arguments, member_arguments
        )
        rows.extend(role_rows)
        unknowns.extend(role_unknowns)
    elif lemma == "be":
        field_rows, field_unknowns = _field_declarations(
            g, unit, comp, scope, common_arguments, subject_argument
        )
        rows.extend(field_rows)
        unknowns.extend(field_unknowns)
    return rows, unknowns, all_arguments


def _argument_unknowns(g, ids, root, rows, all_arguments, features):
    unknowns = []
    all_arguments = list(all_arguments)
    if (
        features["coordination_closure"]["unresolved_head_indices"]
        or features["coordination_closure"]["unresolved_marker_indices"]
    ):
        unknowns.append("unclosed_source_coordination")
    for row in rows:
        all_arguments.extend(row.arguments)
    for argument in all_arguments:
        unknowns.extend(argument.unknowns)
    if features["typed_quantifiers"]:
        unknowns.append("source_quantifier_meaning_unassessed")
    if any(q["kind"].startswith("unsupported_") for q in features["typed_qualifiers"]):
        unknowns.append("unclassified_source_adjunct")
    # Every argument child belongs to a complete typed argument, an explicitly
    # retained qualifier, a coordination operator, or an unresolved remainder.
    # Raw token coverage alone is not a semantic closure certificate.
    if rows:
        consumed = {root}
        consumed.update(i for a in all_arguments for i in a.token_indices)
        consumed.update(
            i for q in features["typed_qualifiers"] for i in q["token_indices"]
        )
        consumed.update(
            i for i in ids if g.tokens[i]["dep"] in {"aux", "auxpass", "neg", "punct"}
        )
        consumed.update(features["coordination_closure"]["closed_marker_indices"])
        if ids - consumed:
            unknowns.append("unconsumed_source_argument")
    return unknowns


def _external_declarations(unit, features):
    rows = []
    for ref in features["references"]:
        literal = RawRange(**ref)
        rows.append(
            _declaration(
                "external_instruction_target",
                unit,
                literal,
                payload={
                    "candidate_document_ids": [],
                    "required_content_closure": "NOT_IMPLEMENTED",
                },
                status="UNRESOLVED_EXTERNAL_TARGET",
            )
        )
    return rows


def _source_context_unknowns(g, unit, ids, rows, features):
    unknowns = []
    if not rows:
        unknowns.append("unknown_source_grammar")
    if any(
        g.tokens[i]["dep"] in {"ccomp", "xcomp", "relcl"}
        or (g.tokens[i]["dep"] == "conj" and g.tokens[i]["pos"] in {"VERB", "AUX"})
        for i in ids
    ):
        unknowns.append("unclassified_source_predicate")
    if any(
        g.tokens[i]["dep"] == "cc" and g.tokens[i]["lemma"].lower() not in {"and"}
        for i in ids
    ):
        unknowns.append("ambiguous_source_coordination")
    if features["conditions"] or features["negation"] or features["modality"]:
        unknowns.append("conditioned_or_qualified_declaration")
    if features["unbound_condition_markers"]:
        unknowns.append("unbound_source_condition_marker")
    # Quotation/context never becomes operative simply because grammar matched.
    if any(
        char in unit.raw.text for char in ('"', "“", "”", "`")
    ) or unit.raw.text.lstrip().startswith(">"):
        unknowns.append("quoted_or_contextual_authority_unassessed")
    return unknowns


def _classify(g, unit, ids):
    roots = [i for i in ids if g.tokens[i]["dep"] == "ROOT"]
    if len(roots) != 1:
        return (), ("unknown_source_grammar",)
    root = roots[0]
    t = g.tokens[root]
    lemma = t["lemma"].lower()
    subjects = [
        i for i in t["children"] if g.tokens[i]["dep"] in {"nsubj", "nsubjpass"}
    ]
    complements = [
        i
        for i in t["children"]
        if g.tokens[i]["dep"] in {"attr", "oprd", "dobj", "acomp"}
    ]
    rows, unknowns, all_arguments = [], [], []
    if len(subjects) == 1 and len(complements) == 1:
        rows, unknowns, all_arguments = _subject_declarations(
            g, unit, lemma, subjects[0], complements[0]
        )
    features = json.loads(unit.features_json)
    unknowns.extend(_argument_unknowns(g, ids, root, rows, all_arguments, features))
    rows.extend(_external_declarations(unit, features))
    unknowns.extend(_source_context_unknowns(g, unit, ids, rows, features))
    return tuple(rows), tuple(dict.fromkeys(unknowns))


def _window_inventory(source, identity, window, capture, annotation):
    units, declarations, blockers = [], [], []
    g = _Graph(source.body, window.start, annotation)
    cursor = window.start
    for sentence in annotation["sentences"]:
        start, end = (
            window.start + sentence["start"],
            window.start + sentence["end"],
        )
        if start > cursor:
            raw = _range(source.body, cursor, start)
            uid = digest(
                {
                    "source": asdict(identity),
                    "raw": asdict(raw),
                    "capture_sha256": capture["capture_sha256"],
                }
            )
            units.append(
                SourceUnit(
                    uid,
                    identity,
                    raw,
                    capture["capture_sha256"],
                    _range(source.body, window.start, window.end),
                    (),
                    canonical({}),
                    "raw_gap",
                    () if raw.text.isspace() else ("unknown_source_grammar",),
                )
            )
        ids = set(range(sentence["token_start"], sentence["token_end"]))
        features = _features(g, ids)
        raw = _range(source.body, start, end)
        uid = digest(
            {
                "source": asdict(identity),
                "raw": asdict(raw),
                "capture_sha256": capture["capture_sha256"],
            }
        )
        unit = SourceUnit(
            uid,
            identity,
            raw,
            capture["capture_sha256"],
            _range(source.body, window.start, window.end),
            tuple(i for i in sorted(ids) if g.tokens[i]["dep"] == "ROOT"),
            canonical(features),
            "unclassified",
            (),
            tuple(
                SourceQualifier(
                    q["kind"],
                    RawRange(**q["raw"]),
                    q["head_index"],
                    tuple(q["token_indices"]),
                    q["semantic_status"],
                )
                for q in features["typed_qualifiers"]
            ),
            tuple(
                SourceQuantifier(
                    q["kind"],
                    RawRange(**q["raw"]),
                    q["head_index"],
                    tuple(q["token_indices"]),
                    q["semantic_status"],
                )
                for q in features["typed_quantifiers"]
            ),
        )
        rows, unknowns = _classify(g, unit, ids)
        unit = replace(
            unit,
            grammar="bounded_declared_production" if rows else "unknown",
            unknowns=unknowns,
        )
        units.append(unit)
        declarations.extend(rows)
        blockers.extend(unknowns)
        cursor = end
    if cursor < window.end:
        raw = _range(source.body, cursor, window.end)
        uid = digest(
            {
                "source": asdict(identity),
                "raw": asdict(raw),
                "capture_sha256": capture["capture_sha256"],
            }
        )
        units.append(
            SourceUnit(
                uid,
                identity,
                raw,
                capture["capture_sha256"],
                _range(source.body, window.start, window.end),
                (),
                canonical({}),
                "raw_gap",
                () if raw.text.isspace() else ("unknown_source_grammar",),
            )
        )
    return units, declarations, blockers


def _external_candidates(declarations, snapshots):
    declarations = list(declarations)
    blockers = []
    named = {}
    for source in snapshots:
        named.setdefault(source.title, []).append(source.identity.document_id)
    for row in declarations:
        if row.kind == "literal_name":
            named.setdefault(row.literal.text, []).append(row.source.document_id)
    for i, row in enumerate(declarations):
        if row.kind == "external_instruction_target":
            payload = json.loads(row.payload_json)
            payload["candidate_document_ids"] = sorted(
                set(named.get(row.literal.text, []))
            )
            updated = replace(row, payload_json=canonical(payload))
            declarations[i] = replace(
                updated,
                id=digest(
                    {
                        key: value
                        for key, value in asdict(updated).items()
                        if key != "id"
                    }
                ),
            )
            blockers.append("external_instruction_targets_initially_unresolved")
    return declarations, blockers


def declaration_inventory(
    manifest: PlanningUniverse,
    snapshots: tuple[SourceSnapshot, ...],
    captures: tuple[SourceCaptures, ...],
) -> DeclarationInventory:
    by_id, validated = _inputs(manifest, snapshots, captures)
    read_set = _read_set(manifest, by_id, validated)
    units = []
    declarations = []
    blockers = [
        "planning_universe_requires_independent_authorization_and_currentness",
        "source_authority_and_evidence_not_assessed",
    ]
    if manifest.selection_mode != "bounded_authorized_scan":
        blockers.append("ranked_or_unknown_universe_cannot_establish_closure")
    if read_set.missing_publications:
        blockers.append("uninspectable_selected_publication")
    for identity in manifest.publications:
        sid = identity.document_id
        if sid not in by_id:
            continue
        source = by_id[sid]
        windows = validated[sid]
        if len(windows) > 1:
            blockers.append("cross_window_semantics_not_established")
        for window, capture, annotation in windows:
            window_units, window_declarations, window_blockers = _window_inventory(
                source, identity, window, capture, annotation
            )
            units.extend(window_units)
            declarations.extend(window_declarations)
            blockers.extend(window_blockers)
    declarations, external_blockers = _external_candidates(declarations, snapshots)
    blockers.extend(external_blockers)
    return DeclarationInventory(
        read_set, tuple(units), tuple(declarations), tuple(dict.fromkeys(blockers))
    )


def validate_declaration_inventory(
    record,
    *,
    manifest: PlanningUniverse,
    snapshots: tuple[SourceSnapshot, ...],
    captures: tuple[SourceCaptures, ...],
) -> bool:
    try:
        _native(record)
        return type(record) is dict and canonical(record) == canonical(
            declaration_inventory(manifest, snapshots, captures).record()
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


def planning_read_set(
    manifest: PlanningUniverse,
    snapshots: tuple[SourceSnapshot, ...],
    captures: tuple[SourceCaptures, ...],
) -> PlanningReadSet:
    by_id, validated = _inputs(manifest, snapshots, captures)
    return _read_set(manifest, by_id, validated)


def validate_planning_read_set(
    record,
    *,
    manifest: PlanningUniverse,
    snapshots: tuple[SourceSnapshot, ...],
    captures: tuple[SourceCaptures, ...],
) -> bool:
    try:
        _native(record)
        return type(record) is dict and canonical(record) == canonical(
            planning_read_set(manifest, snapshots, captures).record()
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


def catalogue_candidates(
    inventory: DeclarationInventory, *, operation: str, scope_literal: str
) -> CatalogueProposal:
    _require(
        type(inventory) is DeclarationInventory, "Typed declaration inventory required"
    )
    _require(
        type(operation) is str and operation in {"labels_only", "incumbents"},
        "Explicit supported catalogue operation required",
    )
    _require(
        type(scope_literal) is str and scope_literal.strip(),
        "Exact literal requested governing scope required",
    )
    matches = tuple(
        row
        for row in inventory.declarations
        if row.kind == "role_catalogue"
        and any(scope.text == scope_literal for scope in row.scope)
    )
    blockers = list(inventory.blockers) + ["independent_membership_evidence_required"]
    if operation == "incumbents":
        blockers.append("independent_actor_value_evidence_required")
    if not matches:
        blockers.append("missing_literal_catalogue_declaration")
    if len(matches) > 1:
        blockers.append("multiple_catalogue_declarations")
    if any(not row.members for row in matches):
        blockers.append("empty_catalogue_not_supported")
    return CatalogueProposal(
        operation,
        scope_literal,
        matches,
        operation == "incumbents",
        tuple(dict.fromkeys(blockers)),
        digest(inventory.read_set.record()),
    )
