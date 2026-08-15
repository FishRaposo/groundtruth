import os
import uuid
from typing import Any

from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.parsers import get_parser
from app.services.chunking import chunking_service
from app.services.document_intelligence import (
    content_hash,
    deduplicate_chunks,
    extract_entities,
    normalize_content,
    select_canonical_duplicate,
)
from app.services.embedding import embedding_service


class IngestionService:
    """Orchestrates the full document ingestion pipeline.

    The pipeline consists of six stages:
    1. Parse — Extract structured content from the raw file
    2. Deduplicate — Hash documents and skip repeated content
    3. Enrich — Extract deterministic entity metadata
    4. Chunk — Split semantically and discard repeated chunks
    5. Embed — Generate vector embeddings for each chunk
    6. Store — Persist chunks and embeddings to the database
    """

    async def ingest_document(
        self,
        file_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> Document:
        """Create a document record and start the ingestion pipeline.

        Args:
            file_path: Path to the uploaded file on disk.
            metadata: Optional additional metadata to attach to the document.

        Returns:
            The created Document record with pending status.
        """
        async with AsyncSessionLocal() as session:
            document = Document(
                title=file_path.split("/")[-1],
                status=DocumentStatus.PENDING,
                metadata_=metadata,
            )
            session.add(document)
            await session.commit()
            await session.refresh(document)

        await self.process_document(document.id)
        return document

    @staticmethod
    def _stored_path(document: Document) -> str:
        """Resolve the on-disk path for a document's uploaded file.

        Files are stored under ``data/uploads/{id}/{id}{ext}`` where the
        extension is derived from (but the only part reused from) the original
        title. The raw title is never used directly in the path, mirroring the
        sanitization in the upload handler so traversal is impossible here too.
        """
        _, ext = os.path.splitext(document.title)
        return f"data/uploads/{document.id}/{document.id}{ext.lower()}"

    async def process_document(self, document_id: uuid.UUID) -> None:
        """Run the full ingestion pipeline for a document.

        Parses the file, chunks the content, generates embeddings,
        and stores everything in the database.

        Args:
            document_id: UUID of the document to process.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()
            if document is None:
                return

            document.status = DocumentStatus.PROCESSING
            await session.commit()

            stage = "parse"
            try:
                parser = get_parser(document.source_type.value)
                parsed = await parser.parse(self._stored_path(document))

                normalized_content = normalize_content(parsed.content)
                document.content_hash = content_hash(normalized_content)

                duplicate_result = await session.execute(
                    select(Document).where(
                        Document.content_hash == document.content_hash,
                        Document.id != document.id,
                    )
                )
                duplicate = select_canonical_duplicate(duplicate_result.scalars().all())
                if duplicate is not None:
                    document.metadata_ = {
                        **(document.metadata_ or {}),
                        "duplicate_of": str(duplicate.id),
                    }
                    document.chunk_count = 0
                    document.status = DocumentStatus.READY
                    await session.commit()
                    return

                stage = "enrich"
                parsed_metadata = dict(parsed.metadata or {})
                document.metadata_ = {
                    **(document.metadata_ or {}),
                    **parsed_metadata,
                    "entities": extract_entities(normalized_content),
                }
                page_count = parsed_metadata.get("page_count")
                if isinstance(page_count, int):
                    document.page_count = page_count

                stage = "chunk"
                chunks = deduplicate_chunks(
                    chunking_service.chunk_by_semantic(normalized_content)
                )

                stage = "embed"
                embeddings = await embedding_service.embed_texts(chunks)

                stage = "store"
                for idx, (content, embedding) in enumerate(
                    zip(chunks, embeddings, strict=False)
                ):
                    chunk_record = Chunk(
                        document_id=document.id,
                        content=content,
                        chunk_index=idx,
                        metadata_={"char_count": len(content)},
                    )
                    session.add(chunk_record)
                    await session.flush()
                    chunk_record.embedding = embedding

                document.chunk_count = len(chunks)
                document.status = DocumentStatus.READY
                await session.commit()

            except Exception as exc:
                document.status = DocumentStatus.ERROR
                document.metadata_ = {
                    **(document.metadata_ or {}),
                    "error": str(exc),
                    "quarantine": {
                        "reason": str(exc),
                        "stage": stage,
                        "source_path": self._stored_path(document),
                        "reprocess_with": "reindex_document",
                    },
                }
                await session.commit()
                raise

    async def delete_document(self, document_id: uuid.UUID) -> None:
        """Remove a document and all associated chunks from the database.

        Args:
            document_id: UUID of the document to delete.
        """
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
            await session.delete(
                (
                    await session.execute(
                        select(Document).where(Document.id == document_id)
                    )
                ).scalar_one()
            )
            await session.commit()

    async def reindex_document(self, document_id: uuid.UUID) -> None:
        """Delete existing chunks and re-run the ingestion pipeline.

        Args:
            document_id: UUID of the document to re-index.
        """
        async with AsyncSessionLocal() as session:
            await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()
            if document is not None:
                document.status = DocumentStatus.PENDING
            await session.commit()

        await self.process_document(document_id)


ingestion_service = IngestionService()
