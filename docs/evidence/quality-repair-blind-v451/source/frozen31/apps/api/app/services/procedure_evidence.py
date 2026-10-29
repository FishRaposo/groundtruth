"""Current authorized immutable procedure bodies and literal citation projection."""

from __future__ import annotations

import hashlib
import re
import uuid
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.cancellation import complete_read
from app.models.chunk import Chunk, ChunkWithScore
from app.models.document import Document, DocumentVersion
from app.models.query import AnswerSpan, QueryRequest
from app.services.access_control.scope import Principal
from app.services.answer_requirements import Requirement
from app.services.document.source_context import validated_snapshot_context
from app.services.requirement_binding import (
    _SECTION_HEAD,
    SupportClaim,
    condition_relation,
    named_anchors,
    support_claim,
)
from app.services.requirement_contract import (
    PROCEDURE_CONTRACT,
    PROCEDURE_COPY_CONTRACT,
    PROCEDURE_READ_SET_CONTRACT,
)
from app.services.retrieval.scoped import scoped_chunk_statement

MAX_BODY_BYTES = 128 * 1024
MAX_CHUNKS = 64


class ProcedureRejected(ValueError):
    """An unsupported source/content plan, never a runtime asset failure."""

    def __init__(
        self,
        code: str,
        source_range: tuple[int, int] | None = None,
        source_form: str | None = None,
        *,
        opposed_source_units: tuple[dict[str, Any], ...] = (),
    ) -> None:
        super().__init__(code)
        self.source_range = source_range
        self.source_form = source_form
        self.opposed_source_units = opposed_source_units


@dataclass(frozen=True)
class LocatedChunk:
    chunk: ChunkWithScore
    start: int
    end: int


@dataclass(frozen=True)
class ProcedureSource:
    body: str
    chunks: tuple[LocatedChunk, ...]
    identity: dict[str, Any]
    metadata: dict[str, Any]
    captured_scope: dict[str, Any] | None


@dataclass(frozen=True)
class ProcedureExtent:
    claim: SupportClaim
    raw_start: int
    raw_end: int
    closure: str
    boundary: tuple[int, int] | None = None


def single_chunk_source(chunk: ChunkWithScore) -> ProcedureSource:
    """A full-body chunk is self-mapping only when its immutable hash agrees."""
    from app.services.evidence_proposals import validate_source

    metadata = chunk.metadata or {}
    source = ProcedureSource(
        chunk.content,
        (LocatedChunk(chunk, 0, len(chunk.content)),),
        {
            "document_id": str(chunk.document_id),
            "document_version": metadata.get("document_version"),
            "content_hash": metadata.get("content_hash"),
        },
        metadata,
        None,
    )
    validate_source(source)
    return source


def inspection_identity(chunk: ChunkWithScore) -> dict[str, Any]:
    """Pin version, immutable bytes and curation independently of ranking."""
    return _inspection_payload(chunk, chunk.metadata or {})


def _inspection_payload(
    chunk: Chunk | ChunkWithScore, metadata: dict[str, Any]
) -> dict[str, Any]:
    return {
        "chunk_id": str(chunk.id),
        "document_id": str(chunk.document_id),
        "document_version": metadata.get("document_version"),
        "content_hash": metadata.get("content_hash"),
        "workspace_id": metadata.get("workspace_id"),
        "condition": deepcopy(metadata.get("condition")),
        "conflict_group": deepcopy(metadata.get("conflict_group")),
        "chunk_hash": hashlib.sha256(chunk.content.encode("utf-8")).hexdigest(),
    }


def _live_inspection(chunk: Chunk, document: Document) -> dict[str, Any]:
    return _inspection_payload(
        chunk,
        {
            "document_version": document.version_number,
            "content_hash": document.content_hash,
            "workspace_id": document.workspace_id,
            "condition": (document.metadata_ or {}).get("condition"),
            "conflict_group": (document.metadata_ or {}).get("conflict_group"),
        },
    )


def capture_read_set(
    chunks: list[ChunkWithScore], conflicts: list[dict[str, Any]], request: QueryRequest
) -> dict[str, Any]:
    return {
        "contract": PROCEDURE_READ_SET_CONTRACT,
        "document_ids": None
        if request.document_ids is None
        else sorted(str(i) for i in request.document_ids),
        "collection_ids": None
        if request.collection_ids is None
        else sorted(str(i) for i in request.collection_ids),
        "sources": [
            inspection_identity(chunk)
            for chunk in sorted(chunks, key=lambda c: str(c.id))
        ],
        "groups": [
            {
                "group": record["group"],
                "sources": deepcopy(record["inspection_sources"]),
            }
            for record in conflicts
            if record.get("inspection_method")
            in {PROCEDURE_CONTRACT, PROCEDURE_COPY_CONTRACT}
        ],
    }


async def check_read_set(
    db: AsyncSession,
    principal: Principal,
    request: QueryRequest,
    read_set: dict[str, Any],
) -> dict[str, Any]:
    """Recheck scoped sources and bounded groups without model/retrieval work."""
    if read_set.get("contract") != PROCEDURE_READ_SET_CONTRACT:
        return {"consistent": False, "reason": "procedure_inspection_snapshot_invalid"}
    expected = {uuid.UUID(source["chunk_id"]): source for source in read_set["sources"]}
    statement = scoped_chunk_statement(
        principal, request.document_ids, request.collection_ids
    )
    rows = list(
        (
            await complete_read(
                db.execute(
                    statement.where(Chunk.id.in_(expected)).execution_options(
                        populate_existing=True
                    )
                )
            )
        ).all()
    )
    actual = {chunk.id: _live_inspection(chunk, document) for chunk, document in rows}
    changed = [
        str(identifier)
        for identifier, source in expected.items()
        if actual.get(identifier) != source
    ]
    changed_groups = []
    group_cache = {}
    for group in read_set["groups"]:
        name = group["group"]
        if name not in group_cache:
            group_statement = (
                statement.where(
                    Document.metadata_["conflict_group"].as_string() == name
                )
                .limit(65)
                .execution_options(populate_existing=True)
            )
            members = list((await complete_read(db.execute(group_statement))).all())
            group_cache[name] = {
                str(chunk.id): _live_inspection(chunk, document)
                for chunk, document in members
            }
        if group_cache[name] != {
            source["chunk_id"]: source for source in group["sources"]
        }:
            changed_groups.append(name)
    return {
        "consistent": not changed and not changed_groups,
        "reason": None
        if not changed and not changed_groups
        else "procedure_inspection_changed",
        "changed_source_ids": changed,
        "changed_groups": sorted(set(changed_groups)),
    }


def invalidate_inspection(
    records: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    check: dict[str, Any],
) -> None:
    """Retain earlier evidence, but never advertise a stale completed inspection."""
    for record in records:
        if record.get("kind") == "procedure":
            record.update(status="unsupported", reason=check["reason"])
            if isinstance(record.get("procedure_completeness"), dict):
                record["procedure_completeness"] = {
                    **record["procedure_completeness"],
                    "status": "unsupported",
                    "coverage_complete": False,
                }
    for record in conflicts:
        if record.get("inspection_method") in {
            PROCEDURE_CONTRACT,
            PROCEDURE_COPY_CONTRACT,
        }:
            record["before_consistency_check"] = {
                "inspection_complete": record["inspection_complete"],
                "requested_fact_agreement": record["requested_fact_agreement"],
            }
            record.update(
                inspection_complete=False,
                requested_fact_agreement=False,
                relevant=True,
                outcome="comparison_unconfirmed",
                consistency_check=check,
            )


async def resolve_version(  # noqa: C901 - bounded immutable manifest validation
    db: AsyncSession,
    principal: Principal,
    request: QueryRequest,
    seed: ChunkWithScore,
    retrieved: dict[uuid.UUID, ChunkWithScore],
) -> ProcedureSource:
    """Resolve through the same SQL scope; copied live text never grants authority."""
    row = (
        await complete_read(
            db.execute(
                scoped_chunk_statement(
                    principal, request.document_ids, request.collection_ids
                )
                .where(Chunk.id == seed.id, Chunk.document_id == seed.document_id)
                .execution_options(populate_existing=True)
            )
        )
    ).first()
    if row is None:
        raise ProcedureRejected("procedure_current_source_unavailable")
    live, document = row
    metadata = seed.metadata or {}
    if (
        live.content != seed.content
        or document.version_number != metadata.get("document_version")
        or document.content_hash != metadata.get("content_hash")
        or document.workspace_id != metadata.get("workspace_id")
        or (document.metadata_ or {}).get("condition") != metadata.get("condition")
        or (document.metadata_ or {}).get("conflict_group")
        != metadata.get("conflict_group")
    ):
        raise ProcedureRejected("procedure_source_changed")
    snapshot = await complete_read(
        db.scalar(
            select(DocumentVersion)
            .where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.workspace_id == document.workspace_id,
                DocumentVersion.version_number == document.version_number,
                DocumentVersion.content_hash == document.content_hash,
            )
            .execution_options(populate_existing=True)
        )
    )
    if snapshot is None:
        raise ProcedureRejected("procedure_immutable_version_missing")
    body = snapshot.normalized_content
    if len(body.encode("utf-8")) > MAX_BODY_BYTES:
        raise ProcedureRejected("procedure_context_budget_exceeded")
    if hashlib.sha256(body.encode("utf-8")).hexdigest() != snapshot.content_hash:
        raise ProcedureRejected("procedure_snapshot_hash_mismatch")
    try:
        captured = validated_snapshot_context(snapshot)
    except (TypeError, ValueError, KeyError) as exc:
        raise ProcedureRejected("procedure_snapshot_scope_invalid") from exc
    manifest = snapshot.chunks
    if not isinstance(manifest, list) or not manifest or len(manifest) > MAX_CHUNKS:
        raise ProcedureRejected("procedure_projection_budget_exceeded")
    located = []
    ids: set[uuid.UUID] = set()
    indices: set[int] = set()
    for item in manifest:
        try:
            identifier = uuid.UUID(str(item["id"]))
            index, text = item["index"], item["content"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ProcedureRejected("procedure_chunk_manifest_invalid") from exc
        if (
            type(index) is not int
            or index < 0
            or index in indices
            or identifier in ids
            or not isinstance(text, str)
            or not text
        ):
            raise ProcedureRejected("procedure_chunk_manifest_invalid")
        start = body.find(text)
        if start < 0 or body.find(text, start + 1) >= 0:
            raise ProcedureRejected("procedure_chunk_mapping_ambiguous")
        known = retrieved.get(identifier)
        if known is not None and (
            known.document_id != document.id
            or known.content != text
            or (known.metadata or {}).get("document_version") != snapshot.version_number
            or (known.metadata or {}).get("content_hash") != snapshot.content_hash
        ):
            raise ProcedureRejected("procedure_chunk_identity_mismatch")
        chunk = known or ChunkWithScore(
            id=identifier,
            document_id=document.id,
            content=text,
            chunk_index=index,
            relevance_score=0.0,
            metadata={
                **metadata,
                "score_status": "not_ranked",
                "ranking_score": None,
                "origin": "immutable-procedure-context",
            },
        )
        if (
            known is not None
            and (known.metadata or {}).get("score_status") != "not_ranked"
        ):
            chunk = known.model_copy(
                update={
                    "metadata": {**(known.metadata or {}), "score_status": "ranked"}
                }
            )
        located.append(LocatedChunk(chunk, start, start + len(text)))
        ids.add(identifier)
        indices.add(index)
    located.sort(key=lambda value: value.chunk.chunk_index)
    if any(
        a.start >= b.start or a.end >= b.end
        for a, b in zip(located, located[1:], strict=False)
    ):
        raise ProcedureRejected("procedure_chunk_order_ambiguous")
    if not any(
        c.chunk.id == seed.id and c.chunk.content == seed.content for c in located
    ):
        raise ProcedureRejected("procedure_seed_not_in_snapshot")
    return ProcedureSource(
        body,
        tuple(located),
        {
            "document_id": str(document.id),
            "workspace_id": document.workspace_id,
            "document_version": snapshot.version_number,
            "content_hash": snapshot.content_hash,
        },
        metadata,
        captured,
    )


def bind_extent(
    requirement: Requirement,
    source: ProcedureSource,
    seed: ChunkWithScore,
    raw: dict[str, Any],
) -> ProcedureExtent:
    """The protected binder determines scope and literal extent on the full body."""
    located = next(c for c in source.chunks if c.chunk.id == seed.id)
    start, end = raw.get("start"), raw.get("end")
    if (
        type(start) is not int
        or type(end) is not int
        or not 0 <= start < end <= len(seed.content)
    ):
        raise ProcedureRejected("procedure_raw_offsets_invalid")
    if raw.get("text", seed.content[start:end]) != seed.content[start:end]:
        raise ProcedureRejected("procedure_raw_text_mismatch")
    first, last = located.start + start, located.start + end
    return _bind_document_extent(requirement, source, first, last)


def discover_procedure_candidates(
    requirement: Requirement,
    source: ProcedureSource,
) -> tuple[ProcedureExtent, ...]:
    """Unassessed extents from the exact grammar also used by QA binding."""
    from app.services.procedure_paragraphs import scope_matches
    from app.services.requirement_binding import procedure_discovery_ranges

    declared = _declared_paragraphs(source.body)
    if declared is not None:
        if not scope_matches(declared, requirement.topic):
            return ()
        return (_bind_document_extent(requirement, source, *declared.paragraphs[0]),)

    return tuple(
        _bind_document_extent(requirement, source, first, last)
        for first, last in procedure_discovery_ranges(requirement, source.body)
        if _legacy_discovery_instruction(source.body[first:last])
    )


def _declared_paragraphs(body):
    from app.services.procedure_paragraphs import ParagraphRejected, parse

    try:
        return parse(body)
    except ParagraphRejected as exc:
        raise ProcedureRejected(str(exc)) from exc


def _legacy_discovery_instruction(text):
    """Do not join an unterminated colon caption to a later prose paragraph.

    Legacy complete narrative sentences keep their open action vocabulary;
    this guard uses the literal paragraph boundary, not a new verb whitelist.
    """
    from app.services.requirement_binding import _step_markers

    if _step_markers(text):
        return True
    heading = _SECTION_HEAD.match(text)
    following = text[heading.end() :].lstrip() if heading else text.lstrip()
    ending = re.search(r"[.!?](?=\s|$)", following)
    first_sentence = following[: ending.end()] if ending else following
    return re.search(r"\n[^\S\n]*\n", first_sentence) is None


def _declared_extent(requirement, source, parsed, first, last):
    from app.services.procedure_paragraphs import scope_matches
    from app.services.requirement_binding import (
        _procedure_constraints,
        _procedure_numbers_present,
        _procedure_scope_prohibited,
    )

    if not scope_matches(parsed, requirement.topic):
        raise ProcedureRejected("procedure_activity_mismatch")
    value = source.body[parsed.start : parsed.end]
    if not parsed.start <= first < last <= parsed.end:
        raise ProcedureRejected("procedure_raw_not_in_extent")
    if condition_relation(requirement, source.body, source.metadata) != "applies":
        raise ProcedureRejected("procedure_source_condition_not_established")
    if _procedure_scope_prohibited(requirement, source.body):
        raise ProcedureRejected("procedure_scope_prohibited")
    if not _procedure_constraints(requirement.original_text, value):
        raise ProcedureRejected("procedure_original_constraint_missing")
    if not _procedure_numbers_present(requirement.original_text, value):
        raise ProcedureRejected("procedure_parameter_missing")
    claim = SupportClaim(
        f"The procedure for {requirement.topic} is: {value}",
        value,
        value,
        parsed.start,
        parsed.end,
        None,
    )
    return ProcedureExtent(
        claim, first, last, "declared_paragraph_end", parsed.end_marker
    )


def _bind_document_extent(requirement, source, first, last) -> ProcedureExtent:
    declared = _declared_paragraphs(source.body)
    if declared is not None:
        return _declared_extent(requirement, source, declared, first, last)
    claim = support_claim(requirement, source.body, first, last)
    if claim.rejection or claim.hypothesis is None:
        raise ProcedureRejected(claim.rejection or "procedure_binding_unverified")
    if condition_relation(requirement, source.body, source.metadata) != "applies":
        raise ProcedureRejected("procedure_source_condition_not_established")
    if not (0 <= claim.start <= first < last <= claim.end <= len(source.body)):
        raise ProcedureRejected("procedure_raw_not_in_extent")
    if source.body[claim.start : claim.end] != claim.value:
        raise ProcedureRejected("procedure_extent_not_literal")
    # A complete immutable EOF is evidence. A local chunk limit is never EOF.
    # Unknown trailing governing material is refused rather than dropped.
    tail = source.body[claim.end :]
    if tail.strip():
        offset = claim.end + len(tail) - len(tail.lstrip())
        heading = _SECTION_HEAD.match(source.body[offset:])
        target = (heading.group("scope") or heading.group("title")) if heading else ""
        named = set(named_anchors(target))
        if (
            heading is None
            or not named
            or not requirement.anchors
            or named.intersection(requirement.anchors)
            or (
                heading.group("scope") is None
                and not target.casefold().endswith("procedure")
            )
        ):
            raise ProcedureRejected("procedure_extent_unverified_tail")
        return ProcedureExtent(
            claim, first, last, "independent_section", (offset, offset + heading.end())
        )
    return ProcedureExtent(claim, first, last, "immutable_eof")


def project_cover(  # noqa: C901 - bounded exact-cover validation and cuts
    source: ProcedureSource,
    start: int,
    end: int,
    steps: tuple[tuple[int, int, int], ...],
) -> tuple[tuple[ChunkWithScore, AnswerSpan, int, int], ...]:
    """Mandatory exact cover, with semantic cuts inside verified overlaps."""
    if not 0 <= start < end <= len(source.body):
        raise ProcedureRejected("procedure_projection_range_invalid")
    cursor = start
    fragments = []
    while cursor < end:
        covering = [c for c in source.chunks if c.start <= cursor < c.end]
        if not covering:
            raise ProcedureRejected("procedure_chunk_cover_gap")
        current = max(covering, key=lambda c: c.end)
        cut = min(current.end, end)
        if cut < end:
            following = [c for c in source.chunks if c.start <= cut and c.end > cut]
            if not following:
                raise ProcedureRejected("procedure_chunk_cover_gap")
            following_start = min(c.start for c in following)
            semantic = [
                left
                for _, left, _ in steps
                if cursor < left <= cut and left >= following_start
            ]
            if not semantic:
                semantic = [
                    m.end()
                    for m in re.compile(r"[.!?](?=\s|$)").finditer(source.body, cursor)
                    if cursor < m.end() <= cut and m.end() >= following_start
                ]
            if semantic:
                cut = max(semantic)
        if cut <= cursor:
            raise ProcedureRejected("procedure_chunk_cover_invalid")
        span = AnswerSpan(
            start=cursor - current.start,
            end=cut - current.start,
            text=source.body[cursor:cut],
        )
        if current.chunk.content[span.start : span.end] != span.text:
            raise ProcedureRejected("procedure_chunk_cover_not_literal")
        fragments.append((current.chunk, span, cursor, cut))
        cursor = cut
    if "".join(span.text for _, span, _, _ in fragments) != source.body[start:end]:
        raise ProcedureRejected("procedure_chunk_cover_incomplete")
    return tuple(fragments)
