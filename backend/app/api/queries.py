import json
import time
import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from app.db.session import get_db
from app.models.query import (
    Query,
    QueryListResponse,
    QueryListItem,
    QueryRequest,
    QueryResponse,
    RetrievalTrace,
)
from app.services.retrieval import retrieval_service
from app.services.reranking import reranking_service
from app.services.generation import generation_service
from app.services.citation import citation_service
from app.services.refusal import refusal_service
from app.config import get_settings

router = APIRouter(tags=["queries"])
settings = get_settings()


@router.post("/queries", response_model=QueryResponse)
async def create_query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
) -> QueryResponse:
    """Process a question through the full retrieval-augmented generation pipeline.

    Retrieves relevant chunks, checks for refusal, generates an answer with
    citations, and records the full retrieval trace.
    """
    top_k = request.top_k or settings.RETRIEVAL_TOP_K
    t_start = time.perf_counter()

    chunks = await retrieval_service.retrieve(query=request.question, top_k=top_k, db=db)
    reranked = await reranking_service.rerank(query=request.question, chunks=chunks)

    confidence = sum(c.relevance_score for c in reranked) / max(len(reranked), 1)

    should_refuse, refusal_reason = refusal_service.should_refuse(
        query=request.question,
        chunks=reranked,
        confidence=confidence,
    )

    scores = [
        {"chunk_id": str(c.id), "document_id": str(c.document_id), "score": c.relevance_score}
        for c in reranked
    ]

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
        await db.commit()
        await db.refresh(query_record)

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

    answer, token_usage = await generation_service.generate_answer(
        query=request.question,
        context=[chunk.content for chunk in reranked],
        sources=[],
    )

    latency_ms = int((time.perf_counter() - t_start) * 1000)

    citations = await citation_service.assemble_citations(chunks=reranked, answer=answer)

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
    await db.commit()
    await db.refresh(query_record)

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
async def stream_query(
    request: QueryRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream a grounded answer token by token via Server-Sent Events.

    Retrieves relevant chunks, checks for refusal, then streams the LLM
    response. After streaming completes, saves the full answer to the database.
    """
    top_k = request.top_k or settings.RETRIEVAL_TOP_K
    t_start = time.perf_counter()

    chunks = await retrieval_service.retrieve(query=request.question, top_k=top_k, db=db)
    reranked = await reranking_service.rerank(query=request.question, chunks=chunks)

    confidence = sum(c.relevance_score for c in reranked) / max(len(reranked), 1)

    should_refuse, refusal_reason = refusal_service.should_refuse(
        query=request.question,
        chunks=reranked,
        confidence=confidence,
    )

    scores = [
        {"chunk_id": str(c.id), "document_id": str(c.document_id), "score": c.relevance_score}
        for c in reranked
    ]

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
            await db.commit()
            await db.refresh(query_record)

            yield f"data: {json.dumps({'type': 'refused', 'reason': refusal_reason, 'retrieval_trace': trace.model_dump()})}\n\n"
            return

        accumulated_tokens: list[str] = []
        token_usage: dict[str, int] = {}

        async for event in generation_service.stream_answer(
            query=request.question,
            context=[chunk.content for chunk in reranked],
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
        citations = await citation_service.assemble_citations(chunks=reranked, answer=answer)

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
        await db.commit()
        await db.refresh(query_record)

        yield f"data: {json.dumps({'type': 'citations', 'sources': [c.model_dump() for c in citations], 'retrieval_trace': trace.model_dump()})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'token_usage': token_usage})}\n\n"

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@router.get("/queries", response_model=QueryListResponse)
async def list_queries(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> QueryListResponse:
    """List query history with pagination."""
    count_result = await db.execute(select(func.count()).select_from(Query))
    total: int = count_result.scalar() or 0

    result = await db.execute(
        select(Query).order_by(Query.created_at.desc()).offset(offset).limit(limit)
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
) -> QueryResponse:
    """Retrieve full query details including sources and retrieval trace."""
    result = await db.execute(select(Query).where(Query.id == query_id))
    query_record = result.scalar_one_or_none()

    if query_record is None:
        raise HTTPException(status_code=404, detail="Query not found")

    return QueryResponse.model_validate(query_record)
