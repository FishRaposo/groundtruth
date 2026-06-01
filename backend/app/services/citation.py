import re
import uuid

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.document import Document
from app.models.chunk import ChunkWithScore
from app.models.query import SourceCitation


class CitationService:
    """Assembles and validates source citations for generated answers.

    Matches citation markers in the answer text (e.g. [1], [2]) to
    the corresponding retrieved chunks and produces structured citations.
    """

    async def assemble_citations(
        self,
        chunks: list[ChunkWithScore],
        answer: str,
    ) -> list[SourceCitation]:
        """Build source citations from retrieved chunks and the generated answer.

        Matches numbered citation markers in the answer text to chunks
        by their position order.

        Args:
            chunks: The retrieved chunks used during generation.
            answer: The generated answer text containing citation markers.

        Returns:
            A list of SourceCitation objects linked to the answer.
        """
        citations: list[SourceCitation] = []

        citation_pattern = re.compile(r"\[(\d+)\]")
        matches = citation_pattern.findall(answer)
        referenced_indices = set(int(m) for m in matches)

        for chunk in chunks:
            citation_index = chunk.chunk_index + 1
            if citation_index not in referenced_indices and referenced_indices:
                continue

            document_title = await self._get_document_title(chunk.document_id)
            preview = chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content

            citations.append(
                SourceCitation(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_title=document_title,
                    content_preview=preview,
                    relevance_score=chunk.relevance_score,
                    citation_index=citation_index,
                )
            )

        return citations

    async def format_citation(
        self,
        chunk: ChunkWithScore,
        index: int,
    ) -> SourceCitation:
        """Create a single SourceCitation from a chunk and index.

        Args:
            chunk: The chunk to cite.
            index: The citation index number.

        Returns:
            A formatted SourceCitation object.
        """
        document_title = await self._get_document_title(chunk.document_id)
        preview = chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content
        return SourceCitation(
            chunk_id=chunk.id,
            document_id=chunk.document_id,
            document_title=document_title,
            content_preview=preview,
            relevance_score=chunk.relevance_score,
            citation_index=index,
        )

    async def _get_document_title(self, document_id: uuid.UUID) -> str:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Document.title).where(Document.id == document_id)
            )
            row = result.scalar_one_or_none()
            return row if row else "Unknown Document"

    def validate_citations(
        self,
        answer: str,
        citations: list[SourceCitation],
    ) -> bool:
        """Verify that all citation markers in the answer have corresponding sources.

        Args:
            answer: The generated answer text.
            citations: The assembled source citations.

        Returns:
            True if all citation markers have matching citations.
        """
        citation_pattern = re.compile(r"\[(\d+)\]")
        matches = citation_pattern.findall(answer)
        referenced_indices = set(int(m) for m in matches)
        available_indices = {c.citation_index for c in citations}
        return referenced_indices.issubset(available_indices)


citation_service = CitationService()
