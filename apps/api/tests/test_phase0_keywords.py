"""Whole-word content evidence for legacy retrieval and reranking."""

import uuid

import pytest
from app.db.session import Base
from app.models.chunk import Chunk, ChunkWithScore
from app.models.document import Document, DocumentStatus, SourceType
from app.services.reranking import RerankingService
from app.services.retrieval import RetrievalService
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def test_keyword_search_requires_content_words(monkeypatch):
    from app.services.retrieval import service

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(service, "AsyncSessionLocal", factory)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            doc = Document(
                title="policy.md",
                source_type=SourceType.MARKDOWN,
                status=DocumentStatus.READY,
            )
            session.add(doc)
            await session.flush()
            row = Chunk(
                document_id=doc.id,
                chunk_index=0,
                content="Be careful: refunds are issued within 5 business days.",
            )
            session.add(row)
            await session.commit()
            row_id = str(row.id)
        search = RetrievalService()
        assert await search.keyword_search("What are the salary bands?", 5) == []
        assert await search.keyword_search("care", 5) == []
        assert await search.keyword_search("Refund business day?", 5) == [(row_id, 1.0)]
    finally:
        await engine.dispose()


async def test_reranking_does_not_treat_function_words_or_substrings_as_evidence():
    chunk = ChunkWithScore(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=0,
        content="Be careful: refunds are issued within 5 business days.",
        relevance_score=0.5,
        metadata=None,
    )
    reranker = RerankingService()
    for question in ("What are the salary bands?", "care"):
        [ranked] = await reranker.rerank(question, [chunk])
        assert ranked.relevance_score == pytest.approx(0.35)
    [ranked] = await reranker.rerank("Refund business day?", [chunk])
    assert ranked.relevance_score == pytest.approx(0.65)
