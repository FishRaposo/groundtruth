"""Integration tests for retrieval with SQLite backend."""

import pytest

from app.db.session import AsyncSessionLocal
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.services.retrieval import RetrievalService


@pytest.mark.asyncio
async def test_similarity_search_with_json_embeddings() -> None:
    """Vector similarity search works with JSON-stored embeddings."""
    async with AsyncSessionLocal() as session:
        doc = Document(
            title="test.md",
            status=DocumentStatus.READY,
            source_type="md",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        chunks = [
            Chunk(document_id=doc.id, content="apple banana", chunk_index=0, embedding=[1.0, 0.0, 0.0]),
            Chunk(document_id=doc.id, content="cherry date", chunk_index=1, embedding=[0.0, 1.0, 0.0]),
            Chunk(document_id=doc.id, content="fig grape", chunk_index=2, embedding=[0.0, 0.0, 1.0]),
        ]
        session.add_all(chunks)
        await session.commit()

    service = RetrievalService()
    results = await service.similarity_search([1.0, 0.0, 0.0], top_k=2)

    assert len(results) == 2
    assert results[0][1] == 1.0  # exact match
    # The highest-similarity result should be the chunk with [1.0, 0.0, 0.0]
    top_chunk_id = results[0][0]


@pytest.mark.asyncio
async def test_keyword_search_finds_matches() -> None:
    """Keyword search finds chunks containing query terms."""
    async with AsyncSessionLocal() as session:
        doc = Document(
            title="test.md",
            status=DocumentStatus.READY,
            source_type="md",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        chunks = [
            Chunk(document_id=doc.id, content="machine learning overview", chunk_index=0),
            Chunk(document_id=doc.id, content="deep learning basics", chunk_index=1),
            Chunk(document_id=doc.id, content="data science introduction", chunk_index=2),
        ]
        session.add_all(chunks)
        await session.commit()

    service = RetrievalService()
    results = await service.keyword_search("deep learning", top_k=2)

    assert len(results) == 2
    # "deep learning basics" matches both terms (score 1.0)
    assert results[0][1] == 1.0
    # "machine learning overview" matches "learning" only (score 0.5)
    assert results[1][1] == 0.5
