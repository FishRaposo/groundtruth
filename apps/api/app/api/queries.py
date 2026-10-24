import asyncio
import json
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import anyio
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.api.deps import get_current_user
from app.config import get_settings
from app.db.session import get_db
from app.internal.context import get_request_context
from app.models.query import (
    Query,
    QueryListItem,
    QueryListResponse,
    QueryRequest,
    QueryResponse,
    RetrievalTrace,
)
from app.services.audit import audit_trail
from app.services.citation import citation_service
from app.services.conversation.memory import (
    SQLConversationMemory,
    prepare_memory_context,
)
from app.services.cost_tracking import cost_tracker
from app.services.generation import generation_service
from app.services.refusal import refusal_service
from app.services.reranking import reranking_service
from app.services.retrieval import retrieval_service

router = APIRouter(tags=["queries"])
settings = get_settings()


def encode_sse(payload: dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


async def _prepare_request_memory(
    request: QueryRequest, db: AsyncSession
) -> tuple[SQLConversationMemory, bool, str | None]:
    "Prepare optional memory while mapping missing conversations to HTTP 404."
    memory = SQLConversationMemory(db)
    enabled = (
        request.conversation_id is not None and request.memory_policy.value == "recent"
    )
    try:
        context = await prepare_memory_context(
            conversation_id=(
                str(request.conversation_id) if request.conversation_id else None
            ),
            policy=request.memory_policy,
            max_tokens=request.memory_max_tokens,
            question=request.question,
            memory=memory,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return memory, enabled, context


@router.post("/queries", response_model=QueryResponse)
async def create_query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> QueryResponse:
    """Process a question through the full retrieval-augmented generation pipeline.

    Retrieves relevant chunks, checks for refusal, generates an answer with
    citations, and records the full retrieval trace.
    """
    if settings.AUTH_ENABLED and not settings.connected:
        raise HTTPException(
            503,
            (
                "Legacy evaluation mode is library-only with authentication"
                " enabled. Configure explicit connected embedding and "
                "generation modes."
            ),
        )
    if settings.connected:
        from app.services.connected_query import (
            begin_query,
            fail_query,
            finish_query,
            prepare_answer,
            present_query,
        )

        row = await begin_query(db, request, current_user)
        try:
            await prepare_answer(db, row, request, current_user)
            await finish_query(db, row, current_user)
        except asyncio.CancelledError:
            with anyio.CancelScope(shield=True):
                await fail_query(db, row, interrupted=True)
            raise
        except Exception as exc:
            await fail_query(db, row)
            raise HTTPException(
                503,
                {
                    "message": (
                        "Query could not complete. Check runtime readiness; no "
                        "sample answer was substituted."
                    ),
                    "query_id": str(row.id),
                },
            ) from exc
        return await present_query(db, row, current_user)
    top_k = request.top_k or settings.RETRIEVAL_TOP_K
    t_start = time.perf_counter()

    chunks = await retrieval_service.retrieve(
        query=request.question, top_k=top_k, db=db
    )
    reranked = await reranking_service.rerank(query=request.question, chunks=chunks)

    confidence = sum(c.relevance_score for c in reranked) / max(len(reranked), 1)

    should_refuse, refusal_reason = refusal_service.should_refuse(
        query=request.question,
        chunks=reranked,
        confidence=confidence,
    )

    scores = [
        {
            "chunk_id": str(c.id),
            "document_id": str(c.document_id),
            "score": c.relevance_score,
        }
        for c in reranked
    ]

    conversation_memory, memory_enabled, memory_context = await _prepare_request_memory(
        request, db
    )

    if should_refuse:
        latency_ms = int((time.perf_counter() - t_start) * 1000)
        trace = RetrievalTrace(
            query_embedding_dim=settings.EMBEDDING_DIMENSIONS,
            vector_results=retrieval_service.last_vector_count,
            keyword_results=retrieval_service.last_keyword_count,
            reranked_results=len(reranked),
            final_context_chunks=0,
            confidence=confidence,
            latency_ms=latency_ms,
            scores=scores,
        )

        query_record = Query(
            question=request.question,
            answer=None,
            refused=True,
            confidence=confidence,
            retrieval_trace=trace.model_dump(),
        )
        db.add(query_record)
        if memory_enabled and request.conversation_id:
            await conversation_memory.append(
                str(request.conversation_id),
                {
                    "role": "assistant",
                    "content": refusal_reason or "Insufficient grounded evidence.",
                },
            )
        await db.commit()
        await db.refresh(query_record)
        await audit_trail.record(
            actor_id="request",
            action="create",
            resource_type="query",
            resource_id=str(query_record.id),
            metadata={"refused": True},
        )

        return QueryResponse(
            id=query_record.id,
            question=request.question,
            answer=None,
            sources=[],
            retrieval_trace=trace,
            refused=True,
            confidence=query_record.confidence,
            token_usage=None,
            created_at=query_record.created_at,
        )

    generation_context = [chunk.content for chunk in reranked]
    # Conversation turns never take the position of numbered source evidence.
    answer, token_usage = await generation_service.generate_answer(
        query=request.question,
        context=generation_context,
        sources=[],
    )

    latency_ms = int((time.perf_counter() - t_start) * 1000)

    cost_tracker.record_usage(
        model=settings.LLM_MODEL,
        token_usage=token_usage,
        latency_ms=latency_ms,
        workspace_id=get_request_context().workspace_id,
    )

    citations = await citation_service.assemble_citations(
        chunks=reranked, answer=answer
    )

    trace = RetrievalTrace(
        query_embedding_dim=settings.EMBEDDING_DIMENSIONS,
        vector_results=retrieval_service.last_vector_count,
        keyword_results=retrieval_service.last_keyword_count,
        reranked_results=len(reranked),
        final_context_chunks=len(reranked),
        confidence=confidence,
        latency_ms=latency_ms,
        scores=scores,
    )

    query_record = Query(
        question=request.question,
        answer=answer,
        sources=[c.model_dump() for c in citations],
        refused=False,
        confidence=confidence,
        token_usage=token_usage,
        retrieval_trace=trace.model_dump(),
    )
    db.add(query_record)
    if memory_enabled and request.conversation_id:
        await conversation_memory.append(
            str(request.conversation_id),
            {"role": "assistant", "content": answer},
        )
    await db.commit()
    await db.refresh(query_record)
    await audit_trail.record(
        actor_id="request",
        action="create",
        resource_type="query",
        resource_id=str(query_record.id),
        metadata={"refused": False},
    )

    return QueryResponse(
        id=query_record.id,
        question=request.question,
        answer=answer,
        sources=citations,
        retrieval_trace=trace,
        refused=False,
        confidence=confidence,
        token_usage=token_usage,
        created_at=query_record.created_at,
    )


@router.post("/queries/stream")
async def stream_query(  # noqa: C901 - legacy and connected SSE compatibility adapter
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> StreamingResponse:
    """Stream a grounded answer token by token via Server-Sent Events.

    Retrieves relevant chunks, checks for refusal, then streams the LLM
    response. After streaming completes, saves the full answer to the database.
    """
    if settings.AUTH_ENABLED and not settings.connected:
        raise HTTPException(
            503,
            (
                "Configure explicit connected embedding and generation "
                "modes before using authenticated queries."
            ),
        )
    if settings.connected:
        from app.services.connected_query import (
            begin_query,
            fail_query,
            finish_query,
            prepare_answer,
            present_query,
        )

        row = await begin_query(db, request, current_user)

        terminal = False

        async def finish_connected() -> None:
            nonlocal terminal
            # Persist the final application outcome atomically. A later network
            # disconnect cannot turn an already completed execution into failure.
            with anyio.CancelScope(shield=True):
                await finish_query(db, row, current_user)
                terminal = True

        async def finalize_interrupted() -> None:
            nonlocal terminal
            if not terminal:
                with anyio.CancelScope(shield=True):
                    await fail_query(db, row, interrupted=True)
                    terminal = True

        async def connected_events() -> AsyncGenerator[str, None]:
            nonlocal terminal
            try:
                await prepare_answer(db, row, request, current_user)
                if row.refused:
                    await finish_connected()
                    payload = (await present_query(db, row, current_user)).model_dump(
                        mode="json"
                    )
                    yield encode_sse(
                        {"type": "refused", "reason": row.refusal_reason, **payload}
                    )
                else:
                    # Presentation must not flush the uncommitted answer and
                    # hold a SQLite write lock across streaming yield points.
                    with db.no_autoflush:
                        prepared = await present_query(db, row, current_user)
                    for token in (prepared.answer or "").splitlines(keepends=True):
                        # Reader/provider inference and every stream yield can
                        # outlive a permission grant. Never stream raw row text;
                        # recheck SQL scope before each further body fragment.
                        with db.no_autoflush:
                            checked = await present_query(db, row, current_user)
                        if checked.evidence_access == "restricted":
                            break
                        yield encode_sse({"type": "token", "content": token})
                        await asyncio.sleep(0)
                    await finish_connected()
                    payload = (await present_query(db, row, current_user)).model_dump(
                        mode="json"
                    )
                    yield encode_sse(
                        {
                            "type": "citations",
                            "sources": payload["sources"],
                            "retrieval_trace": payload["retrieval_trace"],
                        }
                    )
                    # Emitting citations is another yield boundary. Its body
                    # cannot authorize a later terminal answer after revocation.
                    payload = (await present_query(db, row, current_user)).model_dump(
                        mode="json"
                    )
                    yield f"data: {json.dumps({'type': 'done', **payload})}\n\n"
            except (asyncio.CancelledError, GeneratorExit):
                await finalize_interrupted()
                raise
            except Exception:
                if not terminal:
                    with anyio.CancelScope(shield=True):
                        await fail_query(db, row)
                        terminal = True
                yield encode_sse(
                    {
                        "type": "error",
                        "message": "Query failed; check runtime readiness and retry.",
                        "query_id": str(row.id),
                    }
                )

        from app.services.query_stream import QueryStreamingResponse

        return QueryStreamingResponse(connected_events(), finalize_interrupted)
    top_k = request.top_k or settings.RETRIEVAL_TOP_K
    t_start = time.perf_counter()

    chunks = await retrieval_service.retrieve(
        query=request.question, top_k=top_k, db=db
    )
    reranked = await reranking_service.rerank(query=request.question, chunks=chunks)

    confidence = sum(c.relevance_score for c in reranked) / max(len(reranked), 1)

    should_refuse, refusal_reason = refusal_service.should_refuse(
        query=request.question,
        chunks=reranked,
        confidence=confidence,
    )

    scores = [
        {
            "chunk_id": str(c.id),
            "document_id": str(c.document_id),
            "score": c.relevance_score,
        }
        for c in reranked
    ]

    conversation_memory, memory_enabled, memory_context = await _prepare_request_memory(
        request, db
    )

    async def _event_stream() -> AsyncGenerator[str, None]:
        if should_refuse:
            latency_ms = int((time.perf_counter() - t_start) * 1000)
            trace = RetrievalTrace(
                query_embedding_dim=settings.EMBEDDING_DIMENSIONS,
                vector_results=retrieval_service.last_vector_count,
                keyword_results=retrieval_service.last_keyword_count,
                reranked_results=len(reranked),
                final_context_chunks=0,
                confidence=confidence,
                latency_ms=latency_ms,
                scores=scores,
            )

            query_record = Query(
                question=request.question,
                answer=None,
                refused=True,
                confidence=confidence,
                retrieval_trace=trace.model_dump(),
            )
            db.add(query_record)
            if memory_enabled and request.conversation_id:
                await conversation_memory.append(
                    str(request.conversation_id),
                    {
                        "role": "assistant",
                        "content": refusal_reason or "Insufficient grounded evidence.",
                    },
                )
            await db.commit()
            await db.refresh(query_record)
            await audit_trail.record(
                actor_id="request",
                action="create",
                resource_type="query",
                resource_id=str(query_record.id),
                metadata={"refused": True, "streaming": True},
            )

            refused_payload = {
                "type": "refused",
                "reason": refusal_reason,
                "retrieval_trace": trace.model_dump(),
            }
            yield f"data: {json.dumps(refused_payload)}\n\n"
            return

        accumulated_tokens: list[str] = []
        token_usage: dict[str, int] = {}

        generation_context = [chunk.content for chunk in reranked]
        async for event in generation_service.stream_answer(
            query=request.question,
            context=generation_context,
            sources=[],
        ):
            if event["type"] == "token":
                accumulated_tokens.append(event["content"])
                yield f"data: {json.dumps(event)}\n\n"
            elif event["type"] == "error":
                yield f"data: {json.dumps(event)}\n\n"
                return
            elif event["type"] == "done":
                token_usage = event.get("token_usage", {})

        answer = "".join(accumulated_tokens)
        latency_ms = int((time.perf_counter() - t_start) * 1000)
        citations = await citation_service.assemble_citations(
            chunks=reranked, answer=answer
        )

        trace = RetrievalTrace(
            query_embedding_dim=settings.EMBEDDING_DIMENSIONS,
            vector_results=retrieval_service.last_vector_count,
            keyword_results=retrieval_service.last_keyword_count,
            reranked_results=len(reranked),
            final_context_chunks=len(reranked),
            confidence=confidence,
            latency_ms=latency_ms,
            scores=scores,
        )

        query_record = Query(
            question=request.question,
            answer=answer,
            sources=[c.model_dump() for c in citations],
            refused=False,
            confidence=confidence,
            token_usage=token_usage,
            retrieval_trace=trace.model_dump(),
        )
        db.add(query_record)
        if memory_enabled and request.conversation_id:
            await conversation_memory.append(
                str(request.conversation_id),
                {"role": "assistant", "content": answer},
            )
        await db.commit()
        await db.refresh(query_record)
        await audit_trail.record(
            actor_id="request",
            action="create",
            resource_type="query",
            resource_id=str(query_record.id),
            metadata={"refused": False, "streaming": True},
        )

        citations_payload = {
            "type": "citations",
            "sources": [c.model_dump() for c in citations],
            "retrieval_trace": trace.model_dump(),
        }
        yield f"data: {json.dumps(citations_payload)}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'token_usage': token_usage})}\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@router.get("/queries", response_model=QueryListResponse)
async def list_queries(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
    conversation_id: uuid.UUID | None = None,
) -> QueryListResponse:
    """List query history with pagination."""
    from app.services.access_control.scope import owned_scope

    predicates = [owned_scope(Query, current_user)]
    if conversation_id:
        predicates.append(Query.conversation_id == conversation_id)
    count_result = await db.execute(
        select(func.count()).select_from(Query).where(*predicates)
    )
    total: int = count_result.scalar() or 0

    result = await db.execute(
        select(Query)
        .where(*predicates)
        .order_by(Query.created_at.desc())
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 100))
    )
    queries = list(result.scalars().all())

    return QueryListResponse(
        queries=[QueryListItem.model_validate(q) for q in queries],
        total=total,
    )


@router.get("/queries/{query_id}", response_model=QueryResponse)
async def get_query(
    query_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> QueryResponse:
    """Retrieve full query details including sources and retrieval trace."""
    from app.services.access_control.scope import owned_scope

    result = await db.execute(
        select(Query).where(Query.id == query_id, owned_scope(Query, current_user))
    )
    query_record = result.scalar_one_or_none()

    if query_record is None:
        raise HTTPException(status_code=404, detail="Query not found")

    from app.services.connected_query import present_query

    return await present_query(db, query_record, current_user)


@router.get("/queries/{query_id}/sources/{citation_index}")
async def get_query_source(
    query_id: uuid.UUID,
    citation_index: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    response = await get_query(query_id, db, current_user)
    if response.evidence_access == "restricted":
        raise HTTPException(
            403, "Source access has changed; recorded evidence is withheld"
        )
    citation = next(
        (
            source
            for source in response.sources
            if source.citation_index == citation_index
        ),
        None,
    )
    if citation is None:
        raise HTTPException(404, "Citation not found")
    return {
        **citation.model_dump(mode="json"),
        "passage": citation.quoted_text,
        "evidence_access": response.evidence_access,
    }
