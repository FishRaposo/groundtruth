"""Tests for the heuristic RerankingService (term-overlap reranker)."""

import uuid

import pytest
from app.models.chunk import ChunkWithScore
from app.services.reranking.service import RerankingService


def _chunk(content: str, score: float, index: int = 0) -> ChunkWithScore:
    return ChunkWithScore(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content=content,
        chunk_index=index,
        metadata=None,
        relevance_score=score,
    )


@pytest.fixture
def service() -> RerankingService:
    return RerankingService()


async def test_rerank_empty_returns_empty(service: RerankingService) -> None:
    assert await service.rerank("query", []) == []


async def test_rerank_combines_retrieval_and_overlap(
    service: RerankingService,
) -> None:
    # Chunk fully containing query terms beats one with none, given equal base.
    relevant = _chunk("the remote work policy applies", 0.5, 0)
    irrelevant = _chunk("totally different content", 0.5, 1)
    out = await service.rerank("remote work policy", [relevant, irrelevant])
    assert out[0].id == relevant.id


async def test_rerank_score_formula_is_golden(service: RerankingService) -> None:
    # base 0.8, all 3 query terms present -> overlap_ratio 1.0
    # combined = 0.7*0.8 + 0.3*1.0 = 0.86
    chunk = _chunk("remote work policy", 0.8, 0)
    out = await service.rerank("remote work policy", [chunk])
    assert out[0].relevance_score == pytest.approx(0.86)


async def test_rerank_no_overlap_score(service: RerankingService) -> None:
    # base 0.5, no overlap -> combined = 0.7*0.5 + 0.3*0 = 0.35
    chunk = _chunk("unrelated text", 0.5, 0)
    out = await service.rerank("alpha beta gamma", [chunk])
    assert out[0].relevance_score == pytest.approx(0.35)


async def test_rerank_preserves_metadata(service: RerankingService) -> None:
    chunk = _chunk("remote work", 0.5, 7)
    out = await service.rerank("remote work", [chunk])
    assert out[0].chunk_index == 7
    assert out[0].document_id == chunk.document_id


async def test_rerank_output_is_sorted(service: RerankingService) -> None:
    chunks = [
        _chunk("none here", 0.1, 0),
        _chunk("query query query match", 0.9, 1),
        _chunk("partial query", 0.5, 2),
    ]
    out = await service.rerank("query match", chunks)
    scores = [c.relevance_score for c in out]
    assert scores == sorted(scores, reverse=True)
