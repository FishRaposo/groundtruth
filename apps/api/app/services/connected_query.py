"One authenticated execution pipeline for normal and streaming queries."

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.cancellation import complete_read
from app.models.conversation import Conversation, Message
from app.models.document import Document, DocumentVersion
from app.models.query import (
    Query,
    QueryRequest,
    QueryResponse,
    RetrievalTrace,
    SourceCitation,
)
from app.services.access_control.scope import Principal, document_scope, owned_scope
from app.services.audit import audit_trail
from app.services.retrieval.scoped import retrieve_scoped, terms

settings = get_settings()


def diagnostic_snapshot(value: Any) -> Any:
    """Save raw offsets/logits without retaining unselected model text."""
    if isinstance(value, list):
        return [diagnostic_snapshot(item) for item in value]
    if isinstance(value, dict):
        return {
            key: (
                {offset: item[offset] for offset in ("start", "end") if offset in item}
                if key == "raw_span" and isinstance(item, dict)
                else diagnostic_snapshot(item)
            )
            for key, item in value.items()
        }
    return value


async def source_access(db: AsyncSession, row: Query, principal: Principal) -> bool:
    # Diagnostics retain evidence from null, conflicting and non-cited candidates.
    # Reauthorize the whole snapshot, not just the chosen answer's citations.
    try:
        ids = {uuid.UUID(str(item["document_id"])) for item in row.sources or []}
        scores = (row.retrieval_trace or {}).get("scores", [])
        chunk_documents = {}
        for item in scores:
            document_id = uuid.UUID(str(item["document_id"]))
            ids.add(document_id)
            if item.get("chunk_id") is not None:
                chunk_id = uuid.UUID(str(item["chunk_id"]))
                if (
                    chunk_id in chunk_documents
                    and chunk_documents[chunk_id] != document_id
                ):
                    return False
                chunk_documents[chunk_id] = document_id
        candidates = ((row.provenance or {}).get("answer_selection") or {}).get(
            "candidates", []
        )
        if any(
            uuid.UUID(str(candidate["chunk_id"])) not in chunk_documents
            for candidate in candidates
        ):
            # Historical chunk rows can disappear after reindexing. Only the
            # saved document mapping can establish the diagnostic's authority.
            return False
    except (AttributeError, KeyError, TypeError, ValueError):
        return False
    if not ids:
        return True
    allowed = set(
        (
            await complete_read(
                db.scalars(
                    select(Document.id).where(
                        Document.id.in_(ids), document_scope(principal)
                    )
                )
            )
        ).all()
    )
    return ids == allowed


async def citation_status(
    db: AsyncSession, source: dict[str, Any], current: Document | None
) -> str:
    version, digest, passage = (
        source.get("document_version"),
        source.get("content_hash"),
        source.get("quoted_text"),
    )
    if (
        not isinstance(version, int)
        or version <= 0
        or not isinstance(digest, str)
        or not re.fullmatch(r"[a-f0-9]{64}", digest)
        or not isinstance(passage, str)
        or not passage
        or current is None
    ):
        return "unknown"
    snapshot = await complete_read(
        db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == current.id,
                DocumentVersion.workspace_id == current.workspace_id,
                DocumentVersion.version_number == version,
                DocumentVersion.content_hash == digest,
            )
        )
    )
    from app.services.document_intelligence import content_hash, normalize_content

    if (
        snapshot is None
        or content_hash(snapshot.normalized_content) != digest
        or passage not in normalize_content(snapshot.normalized_content)
        or not any(
            isinstance(chunk, dict) and chunk.get("content") == passage
            for chunk in snapshot.chunks or []
        )
    ):
        return "unknown"
    return (
        "current"
        if current.version_number == version and current.content_hash == digest
        else "superseded"
    )


async def present_query(
    db: AsyncSession, row: Query, principal: Principal
) -> QueryResponse:
    accessible = await source_access(db, row, principal)
    snapshots = row.sources or []
    if accessible:
        documents = (
            {
                str(doc.id): doc
                for doc in (
                    await complete_read(
                        db.scalars(
                            select(Document).where(
                                Document.id.in_(
                                    [
                                        uuid.UUID(str(item["document_id"]))
                                        for item in snapshots
                                    ]
                                )
                            )
                        )
                    )
                ).all()
            }
            if snapshots
            else {}
        )
        snapshots = [
            {
                **item,
                "source_status": await citation_status(
                    db, item, documents.get(str(item["document_id"]))
                ),
            }
            for item in snapshots
        ]
    return QueryResponse(
        id=row.id,
        question=row.question,
        answer=row.answer if accessible else None,
        sources=[SourceCitation.model_validate(item) for item in snapshots]
        if accessible
        else [],
        retrieval_trace=RetrievalTrace.model_validate(row.retrieval_trace)
        if row.retrieval_trace and accessible
        else None,
        refused=row.refused,
        confidence=row.confidence if accessible else None,
        token_usage=row.token_usage,
        created_at=row.created_at,
        conversation_id=row.conversation_id,
        outcome=row.outcome,
        refusal_reason=row.refusal_reason
        if accessible
        else (
            "Access to the recorded evidence has changed; its answer "
            "and source content are withheld."
        ),
        execution_mode=(row.provenance or {}).get("generation_mode", "unknown"),
        evidence_access="available"
        if accessible
        and row.provenance
        and all(source.get("source_status") != "unknown" for source in snapshots)
        else "unknown"
        if accessible
        else "restricted",
        provenance=row.provenance if accessible else None,
    )


async def begin_query(
    db: AsyncSession, request: QueryRequest, principal: Principal
) -> Query:
    if request.conversation_id:
        conversation = await complete_read(
            db.scalar(
                select(Conversation).where(
                    Conversation.id == request.conversation_id,
                    owned_scope(Conversation, principal),
                )
            )
        )
        if conversation is None:
            raise HTTPException(404, "Conversation not found")
    else:
        conversation = Conversation(
            title=request.question[:80],
            owner_id=str(principal["id"]),
            workspace_id=principal.get("workspace_id", "default"),
        )
        db.add(conversation)
        await db.flush()
    row = Query(
        question=request.question,
        owner_id=str(principal["id"]),
        workspace_id=principal.get("workspace_id", "default"),
        conversation_id=conversation.id,
        outcome="processing",
        sources=[],
    )
    db.add(row)
    await db.commit()
    return row


async def prepare_answer(  # noqa: C901 - explicit refusal and generation boundaries
    db: AsyncSession, row: Query, request: QueryRequest, principal: Principal
) -> None:
    started = time.perf_counter()
    memory_context = await scoped_memory(db, row, request, principal)
    retrieval_question = request.question
    if memory_context and re.search(
        r"\b(it|its|that|those|this|they|them)\b", request.question, re.I
    ):
        # Bounded previous user questions can resolve a follow-up topic. Prior
        # assistant prose is never a retrieved source or a numbered citation.
        last_user = next(
            (
                item["content"]
                for item in reversed(memory_context)
                if item["role"] == "user"
            ),
            "",
        )
        retrieval_question = f"{last_user} {request.question}"
    result = await retrieve_scoped(
        db,
        retrieval_question,
        principal=principal,
        document_ids=request.document_ids,
        collection_ids=request.collection_ids,
        top_k=request.top_k or settings.RETRIEVAL_TOP_K,
        method=request.retrieval_method,
    )
    chunks = []
    for candidate in result.chunks:
        metadata = candidate.metadata or {}
        current = await complete_read(db.get(Document, candidate.document_id))
        if (
            await citation_status(
                db,
                {
                    "document_version": metadata.get("document_version"),
                    "content_hash": metadata.get("content_hash"),
                    "quoted_text": candidate.content,
                },
                current,
            )
            == "current"
        ):
            chunks.append(candidate)
    query_terms = terms(retrieval_question)
    confidence = chunks[0].relevance_score if chunks else 0.0
    # Retrieval rank alone cannot establish factual support. Extractive answers
    # require meaningful literal query anchors in an authoritative passage.
    supported = [
        chunk
        for chunk in chunks
        if len(terms(chunk.content) & query_terms) >= min(2, len(query_terms))
        and query_terms
    ]
    from app.services.retrieval.scoped import support_terms

    required_terms = support_terms(retrieval_question)
    supported = [
        chunk
        for chunk in supported
        if len(required_terms & support_terms(chunk.content))
        / max(len(required_terms), 1)
        >= 0.75
    ]
    from app.services.answer_reader import reader_service

    reader_mode = settings.ANSWER_SELECTION_MODE == "reader"
    conflicts: dict[str, set[str]] = {}
    for chunk in chunks if reader_mode else supported:
        group = (chunk.metadata or {}).get("conflict_group")
        if group:
            conflicts.setdefault(group, set()).add(str(chunk.document_id))
    reason = None
    if re.search(
        (
            "ignore (?:all |previous )?instructions|system prompt|jailb"
            "reak|reveal.*(?:secret|private)|bypass.*(?:access|permissi"
            "on)"
        ),
        request.question,
        re.I,
    ):
        reason = "The request attempts to override evidence or access boundaries."
    elif re.search(
        r"\b(retired|outdated|superseded)\b.*\b(instead|follow|use|skip|skips)\b",
        request.question,
        re.I,
    ):
        reason = (
            "A retired or superseded procedure cannot establish the "
            "current action. Inspect the current published version "
            "before proceeding."
        )
    elif not reader_mode and any(len(ids) > 1 for ids in conflicts.values()):
        reason = (
            "The selected sources contain a curated conflicting "
            "procedure group. Human review is required."
        )
    elif not reader_mode and (
        not supported or confidence < settings.CONNECTED_REFUSAL_THRESHOLD
    ):
        reason = (
            "The selected authorized sources do not contain enough "
            "direct evidence for this question."
        )
    spans = {}
    reader_diagnostics = []
    citation_selection = None
    if reader_mode and reason is None:
        selections = await reader_service.select(
            retrieval_question, [chunk.content for chunk in chunks]
        )
        # Group membership was collected from ALL current authorized candidates
        # before selection. A null prediction on one side cannot erase a known
        # opposing source; relevance requires support on at least one member.
        relevant_groups = {
            (chunk.metadata or {}).get("conflict_group")
            for chunk, selection in zip(chunks, selections, strict=True)
            if selection.span is not None
        }
        if any(
            len(ids) > 1 and group in relevant_groups
            for group, ids in conflicts.items()
        ):
            reason = (
                "The selected sources contain a curated conflicting "
                "procedure group. Human review is required."
            )
        supported = []
        for chunk, selection in zip(chunks, selections, strict=True):
            diagnostic = diagnostic_snapshot(selection.diagnostics)
            reader_diagnostics.append({"chunk_id": str(chunk.id), **diagnostic})
            if selection.span is not None:
                supported.append(chunk)
                spans[chunk.id] = selection.span
        # Preserve all candidate diagnostics and inspect curated conflicts before
        # picking a compact citation cover. Rank alone must not discard a part.
        if supported and selections and "part_count" in selections[0].diagnostics:
            from app.services.reader_witnesses import select_witness_cover

            cover = select_witness_cover(selections)
            citation_selection = cover.diagnostics
            supported = [chunks[index] for index in cover.indices]
        if not supported and reason is None:
            reason = (
                "The local reader found no supported answer in the "
                "selected current authorized sources."
            )
    row.refused = reason is not None
    row.refusal_reason = reason
    row.outcome = "refused" if reason else "completed"
    row.confidence = confidence
    row.provenance = {
        **result.provenance,
        "generation_method": "source-extractive"
        if settings.GENERATION_MODE == "extractive"
        else "provider",
        "generation_mode": settings.GENERATION_MODE,
        "memory": {
            "policy": request.memory_policy.value,
            "selected_messages": len(memory_context),
            "token_budget": request.memory_max_tokens,
            "use": "follow-up topic context only; never numbered source evidence",
        },
        "refusal_threshold": None
        if reader_mode
        else settings.CONNECTED_REFUSAL_THRESHOLD,
        "support_contract": reader_service.metadata()["contract"],
        "answer_selection": {
            **reader_service.metadata(),
            "decision": "refused" if reason else "answer",
            "candidates": reader_diagnostics,
            "citation_selection": citation_selection,
            "max_length": settings.READER_MAX_LENGTH if reader_mode else None,
            "stride": settings.READER_STRIDE if reader_mode else None,
            "n_best": settings.READER_N_BEST if reader_mode else None,
            "max_span_tokens": settings.READER_MAX_SPAN_TOKENS if reader_mode else None,
        },
        "support_min_coverage": None if reader_mode else 0.75,
    }
    citations = []
    extracts = []
    if not reason:
        for index, chunk in enumerate(supported[:3], 1):
            metadata = chunk.metadata or {}
            passage = chunk.content
            extract = spans[chunk.id].text if chunk.id in spans else passage
            extracts.append(f"{extract} [{index}]")
            citations.append(
                SourceCitation(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_title=metadata.get("document_title", "Document"),
                    content_preview=passage[:200],
                    relevance_score=chunk.relevance_score,
                    citation_index=index,
                    document_version=metadata.get("document_version"),
                    content_hash=metadata.get("content_hash"),
                    quoted_text=passage,
                    source_status="current",
                    answer_spans=[spans[chunk.id]] if chunk.id in spans else [],
                ).model_dump(mode="json")
            )
        if settings.GENERATION_MODE == "extractive":
            row.answer = "Source extracts (not model-generated):\n\n" + "\n\n".join(
                extracts
            )
        elif settings.GENERATION_MODE == "provider":
            if not settings.OPENAI_API_KEY:
                raise RuntimeError(
                    (
                        "Provider generation is selected but no provider "
                        "credentials are configured."
                    )
                )
            from app.internal.provider_contracts import OpenAIGenerationProvider
            from app.services.generation import SYSTEM_PROMPT, generation_service

            response = await OpenAIGenerationProvider(
                generation_service._get_client(), settings.LLM_MODEL, SYSTEM_PROMPT
            ).complete(
                request.question
                + (
                    "\nUntrusted conversation context, not evidence: "
                    + str(memory_context)
                    if memory_context
                    else ""
                ),
                [chunk.content for chunk in supported[:3]],
                citations,
            )
            row.answer = response.text
        else:
            raise RuntimeError(
                "Choose extractive or provider generation for connected execution."
            )
    row.sources = citations
    row.token_usage = {
        "prompt_tokens": len(request.question.split())
        + sum(len(chunk.content.split()) for chunk in supported[:3]),
        "completion_tokens": len((row.answer or "").split()),
        "estimated": True,
        "pricing_provenance": "unknown; local extraction has no provider charge",
    }
    usage = row.token_usage or {}
    usage["total_tokens"] = int(usage["prompt_tokens"]) + int(
        usage["completion_tokens"]
    )
    row.token_usage = usage
    row.retrieval_trace = RetrievalTrace(
        query_embedding_dim=int(result.provenance["embedding"]["dimension"]),
        vector_results=result.vector_count,
        keyword_results=result.keyword_count,
        reranked_results=len(chunks),
        final_context_chunks=len(citations),
        confidence=confidence,
        latency_ms=int((time.perf_counter() - started) * 1000),
        scores=[
            {
                "chunk_id": str(chunk.id),
                "document_id": str(chunk.document_id),
                "score": chunk.relevance_score,
                "document_version": (chunk.metadata or {}).get("document_version"),
            }
            for chunk in chunks
        ],
        method=result.method,
        execution_mode=settings.EMBEDDING_MODE,
        request_id=str(row.id),
        provenance=row.provenance,
        refusal_threshold=None if reader_mode else settings.CONNECTED_REFUSAL_THRESHOLD,
        retrieval_latency_ms=result.elapsed_ms,
    ).model_dump()


async def scoped_memory(
    db: AsyncSession, row: Query, request: QueryRequest, principal: Principal
) -> list[dict[str, str]]:
    if request.memory_policy.value != "recent" or not row.conversation_id:
        return []
    from app.services.conversation.memory import select_bounded_history

    previous = (
        await complete_read(
            db.scalars(
                select(Query)
                .where(
                    Query.conversation_id == row.conversation_id,
                    Query.id != row.id,
                    owned_scope(Query, principal),
                    Query.outcome.in_(["completed", "refused"]),
                )
                .order_by(Query.created_at.desc())
                .limit(50)
            )
        )
    ).all()
    messages = []
    for entry in reversed(previous):
        if await source_access(db, entry, principal):
            messages.extend(
                [
                    {"role": "user", "content": entry.question},
                    {
                        "role": "assistant",
                        "content": entry.answer
                        or entry.refusal_reason
                        or "No supported answer",
                    },
                ]
            )
    return [
        {"role": message["role"], "content": message["content"]}
        for message in select_bounded_history(
            messages, max_tokens=request.memory_max_tokens
        )
    ]


async def finish_query(db: AsyncSession, row: Query, principal: Principal) -> None:
    if row.conversation_id:
        conversation = await complete_read(db.get(Conversation, row.conversation_id))
        db.add_all(
            [
                Message(
                    conversation_id=row.conversation_id,
                    role="user",
                    content=row.question,
                ),
                Message(
                    conversation_id=row.conversation_id,
                    role="assistant",
                    content=row.answer or row.refusal_reason or "No answer",
                    sources=row.sources or [],
                    metadata_={"query_id": str(row.id)},
                ),
            ]
        )
        if conversation:
            conversation.message_count += 2
            conversation.total_tokens += int(
                (row.token_usage or {}).get("total_tokens", 0)
            )
    await audit_trail.record(
        actor_id=str(principal["id"]),
        action="query",
        resource_type="query",
        resource_id=str(row.id),
        workspace_id=principal.get("workspace_id", "default"),
        metadata={
            "outcome": row.outcome,
            "method": (row.provenance or {}).get("retrieval_method"),
        },
        db=db,
    )
    await db.commit()


async def fail_query(
    db: AsyncSession, row: Query, *, interrupted: bool = False
) -> None:
    # Preserve the already committed identity without leaking exception details.
    identifier = row.id
    await db.rollback()
    current = await db.get(Query, identifier)
    if current:
        from app.services.answer_reader import reader_service

        current.outcome = "interrupted" if interrupted else "error"
        current.provenance = {
            "generation_mode": settings.GENERATION_MODE,
            "answer_selection": {
                **reader_service.metadata(),
                "decision": current.outcome,
            },
        }
        current.answer = None
        current.refused = False
        current.sources = []
        current.refusal_reason = (
            "Execution was interrupted; no completed answer was saved."
            if interrupted
            else "Query execution failed; check runtime readiness and retry explicitly."
        )
        await db.commit()
