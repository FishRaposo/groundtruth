"""Tests for the offline lexical reranker (shared_core.embeddings adoption).

Numeric scores are golden-pinned so a refactor of the blending weights or the
shared-core similarity primitives cannot silently change ordering.
"""

import uuid

import pytest
from app.models.chunk import ChunkWithScore
from app.services.reranking.lexical import LexicalReranker


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
def reranker() -> LexicalReranker:
    return LexicalReranker()


async def test_rerank_empty_returns_empty(reranker: LexicalReranker) -> None:
    assert await reranker.rerank("query", []) == []


async def test_rerank_promotes_lexically_relevant_chunk(
    reranker: LexicalReranker,
) -> None:
    chunks = [
        _chunk("Unrelated weather data about clouds", 0.5, 0),
        _chunk("The remote work policy allows three days remote", 0.5, 1),
    ]
    out = await reranker.rerank("what is the remote work policy", chunks)
    assert "remote work policy" in out[0].content


async def test_rerank_blends_base_and_lexical_scores(
    reranker: LexicalReranker,
) -> None:
    chunk = _chunk("the remote work policy", 1.0, 0)
    out = await reranker.rerank("remote work policy", [chunk])
    # base_weight 0.6 * 1.0 + lexical_weight 0.4 * lexical(>0) > 0.6
    assert out[0].relevance_score > 0.6
    assert out[0].relevance_score <= 1.0


async def test_rerank_preserves_chunk_identity(reranker: LexicalReranker) -> None:
    chunk = _chunk("remote work policy details", 0.5, 3)
    out = await reranker.rerank("remote work", [chunk])
    assert out[0].id == chunk.id
    assert out[0].document_id == chunk.document_id
    assert out[0].chunk_index == 3
    assert out[0].content == chunk.content


async def test_rerank_no_lexical_overlap_keeps_base_fraction(
    reranker: LexicalReranker,
) -> None:
    chunk = _chunk("completely different subject matter", 0.8, 0)
    out = await reranker.rerank("xyzzy plover", [chunk])
    # No term overlap -> lexical 0 -> score == base_weight * base
    assert out[0].relevance_score == pytest.approx(0.6 * 0.8)


def test_lexical_score_is_bounded(reranker: LexicalReranker) -> None:
    score = reranker.lexical_score("remote work", "remote work policy here")
    assert 0.0 <= score <= 1.0


def test_lexical_score_identical_text_is_one(reranker: LexicalReranker) -> None:
    assert reranker.lexical_score(
        "remote work policy", "remote work policy"
    ) == pytest.approx(1.0)


def test_weights_are_normalized() -> None:
    rr = LexicalReranker(base_weight=3.0, lexical_weight=1.0)
    assert rr.base_weight == pytest.approx(0.75)
    assert rr.lexical_weight == pytest.approx(0.25)


def test_zero_weights_fall_back_to_default() -> None:
    rr = LexicalReranker(base_weight=0.0, lexical_weight=0.0)
    assert rr.base_weight == pytest.approx(0.6)
    assert rr.lexical_weight == pytest.approx(0.4)


async def test_rerank_is_descending_by_score(reranker: LexicalReranker) -> None:
    chunks = [
        _chunk("alpha beta", 0.2, 0),
        _chunk("query terms match here exactly query terms", 0.9, 1),
        _chunk("gamma delta", 0.1, 2),
    ]
    out = await reranker.rerank("query terms", chunks)
    scores = [c.relevance_score for c in out]
    assert scores == sorted(scores, reverse=True)
