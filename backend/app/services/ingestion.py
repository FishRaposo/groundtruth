import uuid
from typing import Any

from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus
from app.services.chunking import chunking_service
from app.services.embedding import embedding_service
from app.parsers import get_parser


class IngestionService:
    """Orchestrates the full document ingestion pipeline.

    The pipeline consists of four stages:
    1. Parse — Extract structured content from the raw file
    2. Chunk — Split the content into retrievable segments
    3. Embed — Generate vector embeddings for each chunk
    4. Store — Persist chunks and embeddings to the database
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

            try:
                parser = get_parser(document.source_type.value)
                parsed = await parser.parse(f"data/uploads/{document.id}/{document.title}")

                chunks = chunking_service.chunk_text(parsed.content)

                embeddings = await embedding_service.embed_texts(chunks)

                for idx, (content, embedding) in enumerate(zip(chunks, embeddings)):
                    chunk_record = Chunk(
                        document_id=document.id,
                        content=content,
                        chunk_index=idx,
                        metadata_={"char_count": len(content)},
                    )
                    session.add(chunk_record)
                    await session.flush()
                    chunk_record.embedding = embedding

                document.status = DocumentStatus.READY
                await session.commit()

            except Exception as exc:
                document.status = DocumentStatus.ERROR
                document.metadata_ = {**(document.metadata_ or {}), "error": str(exc)}
                await session.commit()
                raise

    async def delete_document(self, document_id: uuid.UUID) -> None:
        """Remove a document and all associated chunks from the database.

        Args:
            document_id: UUID of the document to delete.
        """
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(Chunk).where(Chunk.document_id == document_id)
            )
            await session.delete(
                (await session.execute(select(Document).where(Document.id == document_id))).scalar_one()
            )
            await session.commit()

    async def reindex_document(self, document_id: uuid.UUID) -> None:
        """Delete existing chunks and re-run the ingestion pipeline.

        Args:
            document_id: UUID of the document to re-index.
        """
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(Chunk).where(Chunk.document_id == document_id)
            )
            result = await session.execute(
                select(Document).where(Document.id == document_id)
            )
            document = result.scalar_one_or_none()
            if document is not None:
                document.status = DocumentStatus.PENDING
            await session.commit()

        await self.process_document(document_id)


ingestion_service = IngestionService()
