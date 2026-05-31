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
from celery.exceptions import MaxRetriesExceededError

from app.db.session import AsyncSessionLocal
from app.models.document import Document
from app.models.chunk import Chunk
from app.services.parsers import ParserRegistry
from app.services.chunking import ChunkingService
from app.services.embeddings import get_embedding_provider
from app.tasks.webhooks import deliver_webhook_task


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
    """Async implementation of document processing."""
    async with AsyncSessionLocal() as db:
        # Get document
        from sqlalchemy import select
        import uuid
        
        result = await db.execute(
            select(Document).where(Document.id == uuid.UUID(document_id))
        )
        document = result.scalar_one_or_none()
        
        if not document:
            return {"error": "Document not found", "document_id": document_id}
        
        try:
            # Update status
            document.processing_status = "extracting"
            await db.commit()
            
            # Step 1: Extract text
            text = await extract_text_task(document_id)
            
            if not text or text.get("error"):
                document.processing_status = "failed"
                document.processing_error = text.get("error", "Text extraction failed")
                await db.commit()
                return {"error": "Extraction failed", "document_id": document_id}
            
            # Step 2: Chunk document
            document.processing_status = "chunking"
            await db.commit()
            
            chunks = await chunk_document_task(document_id, text["content"])
            
            if not chunks or chunks.get("error"):
                document.processing_status = "failed"
                document.processing_error = chunks.get("error", "Chunking failed")
                await db.commit()
                return {"error": "Chunking failed", "document_id": document_id}
            
            # Step 3: Generate embeddings
            document.processing_status = "embedding"
            await db.commit()
            
            embedding_result = await generate_embeddings_task(document_id)
            
            if not embedding_result or embedding_result.get("error"):
                document.processing_status = "failed"
                document.processing_error = embedding_result.get("error", "Embedding failed")
                await db.commit()
                return {"error": "Embedding failed", "document_id": document_id}
            
            # Success
            document.processing_status = "completed"
            document.processing_error = None
            await db.commit()
            
            # Trigger webhook
            deliver_webhook_task.delay(
                "document.processed",
                {
                    "document_id": document_id,
                    "filename": document.filename,
                    "chunk_count": embedding_result.get("chunk_count", 0),
                },
                document_id,
            )
            
            return {
                "success": True,
                "document_id": document_id,
                "chunk_count": embedding_result.get("chunk_count", 0),
            }
            
        except Exception as e:
            document.processing_status = "failed"
            document.processing_error = str(e)
            await db.commit()
            
            return {"error": str(e), "document_id": document_id}


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
        from sqlalchemy import select
        import uuid
        
        result = await db.execute(
            select(Document).where(Document.id == uuid.UUID(document_id))
        )
        document = result.scalar_one_or_none()
        
        if not document or not document.file_path:
            return {"error": "Document or file not found"}
        
        try:
            # Get appropriate parser
            parser = ParserRegistry.get_parser(document.content_type or "")
            
            # Extract text
            content = parser.parse(document.file_path)
            
            # Update document
            document.content = content
            document.extracted_text_length = len(content)
            await db.commit()
            
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
        from sqlalchemy import select, delete
        import uuid
        
        result = await db.execute(
            select(Document).where(Document.id == uuid.UUID(document_id))
        )
        document = result.scalar_one_or_none()
        
        if not document:
            return {"error": "Document not found"}
        
        text = content or document.content
        if not text:
            return {"error": "No content to chunk"}
        
        try:
            # Clear existing chunks
            await db.execute(
                delete(Chunk).where(Chunk.document_id == uuid.UUID(document_id))
            )
            
            # Chunk content
            chunking_service = ChunkingService()
            chunks = chunking_service.chunk_text(text, document.metadata or {})
            
            # Create chunk records
            chunk_objects = []
            for idx, chunk_data in enumerate(chunks):
                chunk = Chunk(
                    id=uuid.uuid4(),
                    document_id=uuid.UUID(document_id),
                    content=chunk_data["content"],
                    chunk_index=idx,
                    metadata=chunk_data.get("metadata", {}),
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
        from sqlalchemy import select
        import uuid
        
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
                batch = chunks[i:i + batch_size]
                texts = [chunk.content for chunk in batch]
                
                embeddings = await provider.embed(texts)
                
                # Update chunks with embeddings
                for chunk, embedding in zip(batch, embeddings):
                    chunk.embedding = embedding
                
                await db.commit()
            
            return {
                "success": True,
                "chunk_count": len(chunks),
            }
            
        except Exception as e:
            return {"error": str(e)}
