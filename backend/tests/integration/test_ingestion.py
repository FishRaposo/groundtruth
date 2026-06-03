"""Integration tests for the document ingestion pipeline with SQLite."""


import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus


@pytest.mark.asyncio
async def test_ingest_document_creates_record() -> None:
    """Ingesting a document creates a pending Document record."""
    async with AsyncSessionLocal() as session:
        doc = Document(
            title="test.md",
            status=DocumentStatus.PENDING,
            source_type="md",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        assert doc.id is not None
        assert doc.title == "test.md"
        assert doc.status == DocumentStatus.PENDING


@pytest.mark.asyncio
async def test_chunk_creation_and_embedding_storage() -> None:
    """Chunks can be created with JSON embedding arrays."""
    async with AsyncSessionLocal() as session:
        doc = Document(
            title="test.md",
            status=DocumentStatus.READY,
            source_type="md",
        )
        session.add(doc)
        await session.commit()
        await session.refresh(doc)

        chunk = Chunk(
            document_id=doc.id,
            content="hello world",
            chunk_index=0,
            embedding=[0.1, 0.2, 0.3],
        )
        session.add(chunk)
        await session.commit()
        await session.refresh(chunk)

        result = await session.execute(
            select(Chunk).where(Chunk.document_id == doc.id)
        )
        fetched = result.scalar_one()
        assert fetched.content == "hello world"
        assert fetched.embedding == [0.1, 0.2, 0.3]
