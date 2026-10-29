"""Inert required-body graph proposal. Never an answer/evidence certificate.

Typed reference proposals originate in existing declaration/reference adapters.
No source-file syntax is imposed. Actual parser execution, quoted versus operative
status and reference absence REQUIRE independent semantic inspection. Source text
never selects application policy. No application imports.
Offsets are Python Unicode codepoints in the original immutable body.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass

CONTRACT = "required-reference-structural-closure-proposal-v1"
TRANSPORT = "source-bound-reference-proposal-dtos-v1"
MAX_DOCUMENTS = 8
MAX_UNIVERSE = 128
MAX_BODY_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_REFERENCES = 128
MAX_SOURCE_UNITS = 4096
MAX_DECLARATIONS = 512
MAX_CHUNKS = 4096
MAX_JSON_BYTES = 128 * 1024
SEPARATOR = "\n\n"
REMAINING_GATES = (
    "actual_reference_inventory_and_semantic_completeness",
    "actual_parser_capture_and_binding_observation_reconstruction",
    "operative_status_authority_scope_conditions_and_opposition",
    "actual_source_faithful_nli_and_answer_support",
    "caller_sql_authorization_and_complete_planning_universe",
    "all_source_access_membership_and_currentness_recheck",
    "effective_request_and_facet_obligation_reconstruction",
    "versioned_sourceproof_output_citation_and_history_integration",
)


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
class AuthorizedUniverse:
    """Caller-supplied scope receipt; this type does not establish authorization."""

    scope_json: str
    publications: tuple[SourceIdentity, ...]


@dataclass(frozen=True)
class Declaration:
    source: SourceIdentity
    kind: str
    label: str
    raw: RawRange
    label_range: RawRange


@dataclass(frozen=True)
class RequiredReference:
    source: SourceIdentity
    target_literal: str
    raw: RawRange
    literal_range: RawRange


@dataclass(frozen=True)
class TargetProposal:
    target: SourceIdentity
    basis: str
    declaration: Declaration | None


@dataclass(frozen=True)
class BoundEdge:
    reference: RequiredReference
    target: SourceIdentity
    binding_declaration: Declaration
    proposals: tuple[TargetProposal, ...]


@dataclass(frozen=True)
class SourceAnalysis:
    """Independently supplied adapter input, NOT an execution attestation.

    Expected origins are779 external_instruction_target declaration rows and
    contextual_source_proof reference ASTs. Root owns actual adapter validation.
    Pure tests use explicitly marked UNITONLY hand-authored proposals.
    """

    source: SourceIdentity
    origin_contract: str
    origin_json: str
    source_units: tuple[RawRange, ...]
    declarations: tuple[Declaration, ...]
    references: tuple[RequiredReference, ...]
    unresolved: tuple[str, ...] = ()


@dataclass(frozen=True)
class BindingEvidence:
    """Retained SOURCE relation and target declaration, not a successful flag.

    The integration consumer must independently reconstruct these actual adapter
    observations. Structural validation checks body identity/ranges/membership;
    it does not attest that a parser/NLI model executed or that the relation is
    operative. A unique title alone cannot replace this record.
    """

    reference: RequiredReference
    target: SourceIdentity
    target_declaration: Declaration
    source_relation: RawRange
    origin_json: str


Recordable = (
    RawRange
    | SourceIdentity
    | SourceChunk
    | SourceSnapshot
    | AuthorizedUniverse
    | Declaration
    | RequiredReference
    | TargetProposal
    | BoundEdge
    | SourceAnalysis
    | BindingEvidence
)
Record = dict[str, object]


class ClosureRefusal(ValueError):
    def __init__(
        self,
        code: str,
        detail: str = "",
    ) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def _require(
    condition: object,
    code: str,
    detail: str = "",
) -> None:
    if not condition:
        raise ClosureRefusal(code, detail)


def _native(
    value: object,
) -> None:
    if type(value) in (str, int, bool, type(None)):
        return
    if type(value) is list:
        for item in value:
            _native(item)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for item in value.values():
            _native(item)
        return
    raise ClosureRefusal("NON_NATIVE_RECORD")


def canonical(
    value: object,
) -> str:
    _native(value)
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def _record(
    value: Recordable,
) -> Record:
    def convert(
        item: object,
    ) -> object:
        if type(item) is tuple:
            return [convert(x) for x in item]
        if type(item) is dict:
            return {key: convert(x) for key, x in item.items()}
        return item

    return {key: convert(item) for key, item in asdict(value).items()}


def _same_record(
    left: Recordable,
    right: Recordable,
) -> bool:
    return type(left) is type(right) and canonical(_record(left)) == canonical(
        _record(right)
    )


def _json_object(
    raw: str,
) -> None:
    _require(type(raw) is str, "NON_CANONICAL_METADATA")
    _require(len(raw.encode("utf-8")) <= MAX_JSON_BYTES, "JSON_BUDGET")

    def pairs(
        values: list[tuple[str, object]],
    ) -> Record:
        result = {}
        for key, value in values:
            _require(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result

    try:
        parsed = json.loads(raw, object_pairs_hook=pairs)
    except (ValueError, TypeError) as error:
        raise ClosureRefusal("NON_CANONICAL_METADATA") from error
    _require(
        type(parsed) is dict and canonical(parsed) == raw, "NON_CANONICAL_METADATA"
    )


def body_hash(
    body: str,
) -> str:
    _require(type(body) is str, "INVALID_BODY")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def _range(
    body: str,
    start: int,
    end: int,
) -> RawRange:
    _require(
        type(start) is int and type(end) is int and 0 <= start < end <= len(body),
        "INVALID_SOURCE_RANGE",
    )
    return RawRange(start, end, body[start:end])


def _identity(
    identity: SourceIdentity,
) -> None:
    _require(type(identity) is SourceIdentity, "UNTYPED_IDENTITY")
    for field in (identity.document_id, identity.workspace_id, identity.snapshot_id):
        _require(
            type(field) is str and field.strip() and len(field) <= 512,
            "INVALID_IDENTITY",
        )
    _require(
        type(identity.document_version) is int and identity.document_version > 0,
        "INVALID_VERSION",
    )
    _require(
        type(identity.content_hash) is str
        and re.fullmatch(r"[0-9a-f]{64}", identity.content_hash) is not None,
        "INVALID_CONTENT_HASH",
    )


def make_snapshot(
    document_id: str,
    title: str,
    body: str,
    *,
    version: int = 1,
    workspace_id: str = "workspace",
    snapshot_id: str | None = None,
    metadata_json: str = "{}",
) -> SourceSnapshot:
    """Convenience constructor; no authorization or freshness attestation."""
    digest = body_hash(body)
    identity = SourceIdentity(
        document_id,
        version,
        digest,
        workspace_id,
        snapshot_id if snapshot_id is not None else f"{document_id}:{version}:{digest}",
    )
    chunk = SourceChunk(f"{document_id}:whole", 0, _range(body, 0, len(body)))
    return SourceSnapshot(identity, title, body, metadata_json, (chunk,))


def _inputs(
    snapshots: tuple[SourceSnapshot, ...],
    universe: AuthorizedUniverse | None,
) -> tuple[dict[str, SourceSnapshot], AuthorizedUniverse]:
    _require(
        type(snapshots) is tuple and 0 < len(snapshots) <= MAX_UNIVERSE,
        "UNIVERSE_BUDGET",
    )
    indexed = {}
    total = 0
    for source in snapshots:
        _require(type(source) is SourceSnapshot, "UNTYPED_SNAPSHOT")
        _identity(source.identity)
        doc = source.identity.document_id
        _require(doc not in indexed, "DUPLICATE_DOCUMENT", doc)
        _require(type(source.body) is str and source.body.strip(), "INVALID_BODY")
        size = len(source.body.encode("utf-8"))
        total += size
        _require(size <= MAX_BODY_BYTES and total <= MAX_TOTAL_BYTES, "BODY_BUDGET")
        _require(
            body_hash(source.body) == source.identity.content_hash,
            "CHANGED_SNAPSHOT",
            doc,
        )
        _require(
            type(source.title) is str
            and source.title.strip()
            and len(source.title) <= 2048,
            "INVALID_TITLE",
        )
        _json_object(source.metadata_json)
        _require(
            type(source.chunks) is tuple and 0 < len(source.chunks) <= MAX_CHUNKS,
            "MISSING_OR_OVERSIZED_CHUNKS",
        )
        chunk_ids = set()
        for ordinal, chunk in enumerate(source.chunks):
            _require(type(chunk) is SourceChunk, "UNTYPED_CHUNK")
            _require(
                type(chunk.ordinal) is int and chunk.ordinal == ordinal, "CHUNK_ORDER"
            )
            _require(
                type(chunk.chunk_id) is str
                and chunk.chunk_id.strip()
                and chunk.chunk_id not in chunk_ids,
                "CHUNK_IDENTITY",
            )
            _require(
                type(chunk.literal) is RawRange
                and chunk.literal
                == _range(source.body, chunk.literal.start, chunk.literal.end),
                "CHUNK_BODY",
            )
            _json_object(chunk.metadata_json)
            chunk_ids.add(chunk.chunk_id)
        cursor = 0
        for chunk in sorted(source.chunks, key=lambda x: x.literal.start):
            _require(chunk.literal.start <= cursor, "CHUNK_COVERAGE_GAP", doc)
            cursor = max(cursor, chunk.literal.end)
        _require(cursor == len(source.body), "CHUNK_COVERAGE_GAP", doc)
        indexed[doc] = source
    if universe is None:
        universe = AuthorizedUniverse("{}", tuple(s.identity for s in snapshots))
    _require(type(universe) is AuthorizedUniverse, "UNTYPED_UNIVERSE")
    _json_object(universe.scope_json)
    _require(
        type(universe.publications) is tuple
        and len(universe.publications) <= MAX_UNIVERSE,
        "UNIVERSE_BUDGET",
    )
    for identity in universe.publications:
        _identity(identity)
    _require(
        len({i.document_id for i in universe.publications})
        == len(universe.publications),
        "DUPLICATE_PUBLICATION",
    )
    _require(
        tuple(s.identity for s in snapshots) == universe.publications,
        "MISSING_OR_CHANGED_AUTHORIZED_SNAPSHOT",
    )
    _require(
        len({i.workspace_id for i in universe.publications}) == 1,
        "CROSS_WORKSPACE_NOT_SUPPORTED",
    )
    return indexed, universe


def _literal(
    body: str,
    raw: RawRange,
) -> None:
    _require(
        type(raw) is RawRange
        and type(raw.text) is str
        and raw == _range(body, raw.start, raw.end),
        "INVALID_BODY_LITERAL",
    )


def _analyses(
    snapshots: tuple[SourceSnapshot, ...],
    analyses: tuple[SourceAnalysis, ...],
) -> dict[str, SourceAnalysis]:
    _require(
        type(analyses) is tuple and len(analyses) == len(snapshots),
        "MISSING_SOURCE_ANALYSIS",
    )
    indexed = {}
    for source, analysis in zip(snapshots, analyses, strict=True):
        _require(type(analysis) is SourceAnalysis, "UNTYPED_ANALYSIS")
        _identity(analysis.source)
        _require(
            _same_record(analysis.source, source.identity), "ANALYSIS_SOURCE_IDENTITY"
        )
        _require(
            type(analysis.origin_contract) is str and analysis.origin_contract.strip(),
            "MISSING_ANALYSIS_ORIGIN",
        )
        _json_object(analysis.origin_json)
        _require(
            type(analysis.source_units) is tuple
            and 0 < len(analysis.source_units) <= MAX_SOURCE_UNITS,
            "MISSING_SOURCE_UNITS",
        )
        cursor = 0
        for raw in analysis.source_units:
            _literal(source.body, raw)
            _require(raw.start == cursor, "SOURCE_UNIT_COVERAGE")
            cursor = raw.end
        _require(cursor == len(source.body), "SOURCE_UNIT_COVERAGE")
        _require(
            type(analysis.declarations) is tuple
            and type(analysis.references) is tuple
            and type(analysis.unresolved) is tuple
            and all(type(u) is str and u.strip() for u in analysis.unresolved),
            "UNTYPED_ANALYSIS",
        )
        _require(len(analysis.declarations) <= MAX_DECLARATIONS, "DECLARATION_BUDGET")
        _require(len(analysis.references) <= MAX_REFERENCES, "REFERENCE_BUDGET")
        seen = set()
        for declaration in analysis.declarations:
            _require(type(declaration) is Declaration, "UNTYPED_DECLARATION")
            _identity(declaration.source)
            _require(
                _same_record(declaration.source, source.identity),
                "DECLARATION_SOURCE_IDENTITY",
            )
            _require(
                type(declaration.kind) is str
                and declaration.kind in {"procedure", "appendix"},
                "UNSUPPORTED_DECLARATION_KIND",
            )
            _literal(source.body, declaration.raw)
            _literal(source.body, declaration.label_range)
            _require(
                type(declaration.label) is str
                and declaration.label.strip()
                and declaration.label == declaration.label_range.text
                and declaration.raw.start
                <= declaration.label_range.start
                < declaration.label_range.end
                <= declaration.raw.end,
                "DECLARATION_LABEL_RANGE",
            )
            key = canonical(_record(declaration))
            _require(key not in seen, "DUPLICATE_DECLARATION")
            seen.add(key)
        seen = set()
        reference_end = 0
        for reference in analysis.references:
            _require(type(reference) is RequiredReference, "UNTYPED_REFERENCE")
            _identity(reference.source)
            _require(
                _same_record(reference.source, source.identity),
                "REFERENCE_SOURCE_IDENTITY",
            )
            _literal(source.body, reference.raw)
            _literal(source.body, reference.literal_range)
            _require(
                type(reference.target_literal) is str
                and reference.target_literal.strip()
                and reference.target_literal == reference.literal_range.text
                and reference.raw.start
                <= reference.literal_range.start
                < reference.literal_range.end
                <= reference.raw.end
                and any(
                    u.start <= reference.raw.start < reference.raw.end <= u.end
                    for u in analysis.source_units
                ),
                "REFERENCE_LITERAL_RANGE",
            )
            _require(
                reference.literal_range.start >= reference_end, "REFERENCE_SOURCE_ORDER"
            )
            reference_end = reference.literal_range.end
            key = canonical(_record(reference))
            _require(key not in seen, "DUPLICATE_REFERENCE")
            seen.add(key)
        indexed[source.identity.document_id] = analysis
    _require(
        sum(len(a.references) for a in analyses) <= MAX_REFERENCES, "REFERENCE_BUDGET"
    )
    return indexed


def _proposals(
    target_literal: str,
    snapshots: tuple[SourceSnapshot, ...],
    analyses: dict[str, SourceAnalysis],
) -> tuple[TargetProposal, ...]:
    proposals = []
    for source in snapshots:
        if source.title == target_literal:
            proposals.append(TargetProposal(source.identity, "EXACT_TITLE", None))
        for declaration in analyses[source.identity.document_id].declarations:
            if declaration.label == target_literal:
                proposals.append(
                    TargetProposal(source.identity, "EXACT_DECLARATION", declaration)
                )
    return tuple(proposals)


def target_proposals(
    target_literal: str,
    *,
    snapshots: tuple[SourceSnapshot, ...],
    analyses: tuple[SourceAnalysis, ...],
    universe: AuthorizedUniverse | None = None,
) -> tuple[TargetProposal, ...]:
    """Exact title/declaration equality only proposes identity; no edge is bound."""
    _require(type(target_literal) is str and target_literal.strip(), "INVALID_TARGET")
    _inputs(snapshots, universe)
    by_source = _analyses(snapshots, analyses)
    return _proposals(target_literal, snapshots, by_source)


def _bindings(
    binding_evidence: tuple[BindingEvidence, ...],
    indexed: dict[str, SourceSnapshot],
    analyses: dict[str, SourceAnalysis],
) -> dict[str, BindingEvidence]:
    _require(
        type(binding_evidence) is tuple and len(binding_evidence) <= MAX_REFERENCES,
        "UNTYPED_OR_OVERSIZED_BINDINGS",
    )
    result = {}
    for evidence in binding_evidence:
        _require(type(evidence) is BindingEvidence, "UNTYPED_BINDING_EVIDENCE")
        _require(type(evidence.reference) is RequiredReference, "UNTYPED_REFERENCE")
        _identity(evidence.reference.source)
        doc = evidence.reference.source.document_id
        _require(
            doc in analyses
            and any(
                _same_record(evidence.reference, r) for r in analyses[doc].references
            ),
            "BINDING_REFERENCE_MEMBERSHIP",
        )
        _identity(evidence.target)
        target_id = evidence.target.document_id
        _require(
            target_id in indexed and evidence.target == indexed[target_id].identity,
            "BINDING_TARGET_IDENTITY",
        )
        _require(
            type(evidence.target_declaration) is Declaration
            and any(
                _same_record(evidence.target_declaration, d)
                for d in analyses[target_id].declarations
            ),
            "BINDING_DECLARATION_MEMBERSHIP",
        )
        _literal(indexed[doc].body, evidence.source_relation)
        _require(
            evidence.source_relation == evidence.reference.raw,
            "BINDING_RELATION_CONTEXT",
        )
        _json_object(evidence.origin_json)
        key = canonical(_record(evidence.reference))
        _require(key not in result, "AMBIGUOUS_BINDING_EVIDENCE")
        result[key] = evidence
    return result


def reconstruct_closure(
    root_document_id: str,
    *,
    snapshots: tuple[SourceSnapshot, ...],
    analyses: tuple[SourceAnalysis, ...],
    binding_evidence: tuple[BindingEvidence, ...] = (),
    universe: AuthorizedUniverse | None = None,
    max_documents: int = MAX_DOCUMENTS,
) -> Record:
    """Rebuild an inert graph from independent immutable bodies/adapter DTOs.

    Actual root adapter observations must be independently reconstructed before
    integration. This component grants only structural consistency of the supplied
    observations. A CLOSED graph still has every REMAINING_GATE. No callback,
    producer successful flag, hash-only certificate or reference subset accepted.
    """
    _require(
        type(max_documents) is int and 1 <= max_documents <= MAX_DOCUMENTS,
        "INVALID_DOCUMENT_BOUND",
    )
    indexed, universe = _inputs(snapshots, universe)
    _require(
        type(root_document_id) is str and root_document_id in indexed, "MISSING_ROOT"
    )
    by_source = _analyses(snapshots, analyses)
    bindings = _bindings(binding_evidence, indexed, by_source)
    order, active, visited, edges = [], set(), set(), []

    def visit(
        document_id: str,
    ) -> None:
        _require(document_id not in active, "REQUIRED_REFERENCE_CYCLE", document_id)
        if document_id in visited:
            return
        _require(len(order) < max_documents, "REQUIRED_DOCUMENT_BUDGET")
        analysis = by_source[document_id]
        _require(not analysis.unresolved, "UNRESOLVED_REFERENCE_ANALYSIS", document_id)
        _require(analysis.declarations, "MISSING_SOURCE_DECLARATION", document_id)
        active.add(document_id)
        order.append(document_id)
        for reference in analysis.references:
            proposals = _proposals(reference.target_literal, snapshots, by_source)
            candidates = {p.target.document_id for p in proposals}
            _require(candidates, "MISSING_REQUIRED_TARGET", reference.target_literal)
            _require(
                len(candidates) == 1,
                "AMBIGUOUS_REQUIRED_TARGET",
                reference.target_literal,
            )
            target_id = next(iter(candidates))
            key = canonical(_record(reference))
            _require(
                key in bindings,
                "MISSING_INDEPENDENT_BINDING_EVIDENCE",
                reference.target_literal,
            )
            evidence = bindings[key]
            _require(
                evidence.target == indexed[target_id].identity, "BINDING_TARGET_DIFFERS"
            )
            _require(
                evidence.target_declaration.label == reference.target_literal
                and evidence.target_declaration.source == evidence.target,
                "BINDING_TARGET_DECLARATION_DIFFERS",
            )
            matches = [p.declaration for p in proposals if p.declaration is not None]
            _require(
                len(matches) == 1 and matches[0] == evidence.target_declaration,
                "AMBIGUOUS_TARGET_DECLARATION",
            )
            edge = BoundEdge(
                reference,
                indexed[target_id].identity,
                evidence.target_declaration,
                proposals,
            )
            edges.append({**_record(edge), "binding_evidence": _record(evidence)})
            visit(target_id)
        active.remove(document_id)
        visited.add(document_id)

    visit(root_document_id)
    rendered, inclusions = "", []
    for ordinal, document_id in enumerate(order):
        source = indexed[document_id]
        if ordinal:
            rendered += SEPARATOR
        start = len(rendered)
        rendered += source.body
        inclusions.append(
            {
                "ordinal": ordinal,
                "source": _record(source.identity),
                "source_range": _record(_range(source.body, 0, len(source.body))),
                "output_range": {"start": start, "end": len(rendered)},
                "citation_source": _record(source.identity),
            }
        )
    return {
        "contract": CONTRACT,
        "transport": TRANSPORT,
        "status": "PENDING_INDEPENDENT_GATES",
        "structural_status": "CLOSED",
        "support_or_permissions": "NOT_ASSESSED",
        "remaining_gates": list(REMAINING_GATES),
        "coordinate_system": "python-unicode-codepoints",
        "root_document_id": root_document_id,
        "max_documents": max_documents,
        "authorized_universe_receipt": _record(universe),
        "universe_completeness": "NOT_ESTABLISHED",
        "source_inventory": [_record(source) for source in snapshots],
        "independent_source_analyses": [_record(a) for a in analyses],
        "independent_binding_evidence": [_record(b) for b in binding_evidence],
        "ordered_document_ids": order,
        "edges": edges,
        "inclusions": inclusions,
        "separator": SEPARATOR,
        "rendered_text": rendered,
    }


def validate_closure(
    record: object,
    *,
    root_document_id: str,
    snapshots: tuple[SourceSnapshot, ...],
    analyses: tuple[SourceAnalysis, ...],
    binding_evidence: tuple[BindingEvidence, ...] = (),
    universe: AuthorizedUniverse | None = None,
    max_documents: int = MAX_DOCUMENTS,
) -> bool:
    """Replay actual independent inputs; producer record cannot supply its own DTOs."""
    try:
        _native(record)
        _require(type(record) is dict, "UNTYPED_RECORD")
        expected = reconstruct_closure(
            root_document_id,
            snapshots=snapshots,
            analyses=analyses,
            binding_evidence=binding_evidence,
            universe=universe,
            max_documents=max_documents,
        )
        return canonical(record) == canonical(expected)
    except (
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        IndexError,
        RecursionError,
        UnicodeError,
    ):
        return False
