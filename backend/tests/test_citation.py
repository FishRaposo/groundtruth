import uuid
from unittest.mock import AsyncMock

import pytest
from app.services.citation import CitationService
from app.models.chunk import ChunkWithScore
from app.models.query import SourceCitation


@pytest.fixture
def service() -> CitationService:
    service = CitationService()
    service._get_document_title = AsyncMock(return_value="Test Document")
    return service


@pytest.fixture
def sample_chunks() -> list[ChunkWithScore]:
    return [
        ChunkWithScore(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            content="Employees may work remotely up to 3 days per week with manager approval.",
            chunk_index=0,
            metadata=None,
            relevance_score=0.94,
        ),
        ChunkWithScore(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            content="Remote work arrangements must be documented in the HR system.",
            chunk_index=1,
            metadata=None,
            relevance_score=0.87,
        ),
    ]


async def test_assemble_citations_creates_citations(
    service: CitationService, sample_chunks: list[ChunkWithScore]
) -> None:
    answer = "According to [1], employees may work remotely."
    citations = await service.assemble_citations(sample_chunks, answer)

    assert len(citations) == 1
    assert isinstance(citations[0], SourceCitation)
    assert citations[0].citation_index == 1
    assert citations[0].chunk_id == sample_chunks[0].id
    assert citations[0].document_id == sample_chunks[0].document_id
    assert citations[0].relevance_score == 0.94
    assert citations[0].document_title == "Test Document"
    assert "Employees may work remotely" in citations[0].content_preview


async def test_assemble_citations_includes_all_referenced(
    service: CitationService, sample_chunks: list[ChunkWithScore]
) -> None:
    answer = "According to [1] and [2], employees may work remotely."
    citations = await service.assemble_citations(sample_chunks, answer)

    assert len(citations) == 2
    indices = {c.citation_index for c in citations}
    assert indices == {1, 2}
    assert citations[0].chunk_id == sample_chunks[0].id
    assert citations[1].chunk_id == sample_chunks[1].id


async def test_format_citation_produces_valid_citation(
    service: CitationService, sample_chunks: list[ChunkWithScore]
) -> None:
    citation = await service.format_citation(sample_chunks[0], 1)
    assert citation.citation_index == 1
    assert citation.relevance_score == 0.94


async def test_format_citation_truncates_long_content(service: CitationService) -> None:
    long_chunk = ChunkWithScore(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="x" * 300,
        chunk_index=0,
        metadata=None,
        relevance_score=0.8,
    )
    citation = await service.format_citation(long_chunk, 1)
    assert citation.content_preview.endswith("...")
    assert len(citation.content_preview) == 203


def test_validate_citations_detects_valid_references(service: CitationService) -> None:
    answer = "According to [1], employees can work remotely."
    citations = [
        SourceCitation(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_title="Test",
            content_preview="test",
            relevance_score=0.9,
            citation_index=1,
        )
    ]
    assert service.validate_citations(answer, citations) is True


def test_validate_citations_detects_missing_references(service: CitationService) -> None:
    answer = "According to [1] and [2], employees can work remotely."
    citations = [
        SourceCitation(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_title="Test",
            content_preview="test",
            relevance_score=0.9,
            citation_index=1,
        )
    ]
    assert service.validate_citations(answer, citations) is False


def test_validate_citations_with_no_markers(service: CitationService) -> None:
    answer = "Employees can work remotely."
    citations = [
        SourceCitation(
            chunk_id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            document_title="Test",
            content_preview="test",
            relevance_score=0.9,
            citation_index=1,
        )
    ]
    assert service.validate_citations(answer, citations) is True


async def test_assemble_citations_with_empty_chunks(service: CitationService) -> None:
    answer = "No references here."
    citations = await service.assemble_citations([], answer)
    assert citations == []


async def test_assemble_citations_skips_unreferenced_chunks(
    service: CitationService, sample_chunks: list[ChunkWithScore]
) -> None:
    answer = "According to [2], remote work must be documented."
    citations = await service.assemble_citations(sample_chunks, answer)

    assert len(citations) == 1
    assert citations[0].citation_index == 2
    assert citations[0].chunk_id == sample_chunks[1].id
