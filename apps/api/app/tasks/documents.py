"""Document processing Celery tasks.

Handles document ingestion pipeline asynchronously:
1. Text extraction
2. Chunking
3. Embedding generation
4. Indexing
"""

from __future__ import annotations

from typing import Any

from celery import shared_task

from app.db.session import AsyncSessionLocal
from app.models.chunk import Chunk
from app.models.document import Document
from app.parsers import get_parser
from app.services.chunking import ChunkingService
from app.services.embeddings import get_embedding_provider
from app.services.ingestion import ingestion_service


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def process_document_task(self, document_id: str) -> dict[str, Any]:
    """Process a document through the full pipeline.

    Args:
        document_id: Document ID to process.

    Returns:
        Processing result summary.
    """
    import asyncio

    return asyncio.run(_process_document_async(document_id))


async def _process_document_async(document_id: str) -> dict[str, Any]:
    """Delegate worker execution to the canonical ingestion pipeline."""
    import uuid

    from sqlalchemy import select

    identifier = uuid.UUID(document_id)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).where(Document.id == identifier))
        document = result.scalar_one_or_none()
        if document is None:
            return {"error": "Document not found", "document_id": document_id}

    try:
        await ingestion_service.process_document(identifier)
    except Exception as exc:
        return {"error": str(exc), "document_id": document_id}

    async with AsyncSessionLocal() as db:
        refreshed = (
            await db.execute(select(Document).where(Document.id == identifier))
        ).scalar_one_or_none()
        if refreshed is None:
            return {"error": "Document not found", "document_id": document_id}
        return {
            "success": refreshed.status.value == "ready",
            "document_id": document_id,
            "chunk_count": refreshed.chunk_count or 0,
        }


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def extract_text_task(self, document_id: str) -> dict[str, Any]:
    """Extract text from document file.

    Args:
        document_id: Document ID.

    Returns:
        Extraction result with content.
    """
    import asyncio

    return asyncio.run(_extract_text_async(document_id))


async def _extract_text_async(document_id: str) -> dict[str, Any]:
    """Async text extraction."""
    async with AsyncSessionLocal() as db:
        import uuid

        from sqlalchemy import select

        result = await db.execute(
            select(Document).where(Document.id == uuid.UUID(document_id))
        )
        document = result.scalar_one_or_none()

        if not document:
            return {"error": "Document or file not found"}

        try:
            parser = get_parser(document.source_type.value)
            parsed = await parser.parse(ingestion_service._stored_path(document))
            content = parsed.content

            return {
                "success": True,
                "content": content,
                "length": len(content),
            }

        except Exception as e:
            return {"error": str(e)}


@shared_task(bind=True, max_retries=2, default_retry_delay=5)
def chunk_document_task(
    self,
    document_id: str,
    content: str | None = None,
) -> dict[str, Any]:
    """Chunk document content.

    Args:
        document_id: Document ID.
        content: Optional content (if not already on document).

    Returns:
        Chunking result.
    """
    import asyncio

    return asyncio.run(_chunk_document_async(document_id, content))


async def _chunk_document_async(
    document_id: str,
    content: str | None,
) -> dict[str, Any]:
    """Async document chunking."""
    async with AsyncSessionLocal() as db:
        import uuid

        from sqlalchemy import delete, select

        result = await db.execute(
            select(Document).where(Document.id == uuid.UUID(document_id))
        )
        document = result.scalar_one_or_none()

        if not document:
            return {"error": "Document not found"}

        text = content or (document.metadata_ or {}).get("normalized_content")
        if not text:
            return {"error": "No content to chunk"}

        try:
            # Clear existing chunks
            await db.execute(
                delete(Chunk).where(Chunk.document_id == uuid.UUID(document_id))
            )

            # Chunk content
            chunking_service = ChunkingService()
            chunks = chunking_service.chunk_text(text)

            # Create chunk records
            chunk_objects = []
            for idx, chunk_data in enumerate(chunks):
                chunk = Chunk(
                    id=uuid.uuid4(),
                    document_id=uuid.UUID(document_id),
                    content=chunk_data,
                    chunk_index=idx,
                    metadata_={"char_count": len(chunk_data)},
                )
                chunk_objects.append(chunk)
                db.add(chunk)

            document.chunk_count = len(chunk_objects)
            await db.commit()

            return {
                "success": True,
                "chunk_count": len(chunk_objects),
            }

        except Exception as e:
            return {"error": str(e)}


@shared_task(bind=True, max_retries=2, default_retry_delay=10)
def generate_embeddings_task(self, document_id: str) -> dict[str, Any]:
    """Generate embeddings for all chunks.

    Args:
        document_id: Document ID.

    Returns:
        Embedding generation result.
    """
    import asyncio

    return asyncio.run(_generate_embeddings_async(document_id))


async def _generate_embeddings_async(document_id: str) -> dict[str, Any]:
    """Async embedding generation."""
    async with AsyncSessionLocal() as db:
        import uuid

        from sqlalchemy import select

        # Get chunks
        result = await db.execute(
            select(Chunk).where(Chunk.document_id == uuid.UUID(document_id))
        )
        chunks = list(result.scalars().all())

        if not chunks:
            return {"error": "No chunks found"}

        try:
            # Get embedding provider
            provider = get_embedding_provider()

            # Generate embeddings in batches
            batch_size = 100
            for i in range(0, len(chunks), batch_size):
                batch = chunks[i : i + batch_size]
                texts = [chunk.content for chunk in batch]

                embeddings = await provider.embed(texts)

                # Update chunks with embeddings
                for chunk, embedding in zip(batch, embeddings, strict=False):
                    chunk.embedding = embedding

                await db.commit()

            return {
                "success": True,
                "chunk_count": len(chunks),
            }

        except Exception as e:
            return {"error": str(e)}
