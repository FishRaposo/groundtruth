"""Tests for citation grounding evaluation through the vendored judge."""

import uuid

import pytest
from app.models.query import SourceCitation
from app.services.evaluation.citation_scoring import CitationEvaluator


def _citation(index: int) -> SourceCitation:
    return SourceCitation(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Doc",
        content_preview="preview",
        relevance_score=0.9,
        citation_index=index,
    )


@pytest.fixture
def evaluator() -> CitationEvaluator:
    return CitationEvaluator()


async def test_answer_with_citation_passes(evaluator: CitationEvaluator) -> None:
    result = await evaluator.evaluate("Policy is X [1].", [_citation(1)])
    assert result.passed is True
    assert result.score == 1.0


async def test_answer_without_citation_fails(evaluator: CitationEvaluator) -> None:
    result = await evaluator.evaluate("Policy is X.", [])
    assert result.passed is False
    assert result.score == 0.0


async def test_min_citations_threshold() -> None:
    evaluator = CitationEvaluator(min_citations=2)
    one = await evaluator.evaluate("Only [1] here.", [_citation(1)])
    assert one.passed is False
    two = await evaluator.evaluate("Both [1] and [2].", [_citation(1), _citation(2)])
    assert two.passed is True


async def test_dangling_markers_detected(evaluator: CitationEvaluator) -> None:
    result = await evaluator.evaluate("See [1] and [2].", [_citation(1)])
    assert result.metadata["resolved_markers"] == [1]
    assert result.metadata["dangling_markers"] == [2]
    assert result.metadata["all_resolved"] is False


async def test_all_markers_resolved(evaluator: CitationEvaluator) -> None:
    result = await evaluator.evaluate("See [1] and [2].", [_citation(1), _citation(2)])
    assert result.metadata["dangling_markers"] == []
    assert result.metadata["all_resolved"] is True


async def test_duplicate_markers_counted_once(evaluator: CitationEvaluator) -> None:
    result = await evaluator.evaluate("See [1], [1], [1].", [_citation(1)])
    assert result.metadata["markers"] == [1]
    assert result.passed is True


async def test_no_citations_provided_treats_markers_as_dangling(
    evaluator: CitationEvaluator,
) -> None:
    result = await evaluator.evaluate("See [1] and [2].", None)
    assert result.metadata["dangling_markers"] == [1, 2]


async def test_score_helper(evaluator: CitationEvaluator) -> None:
    assert await evaluator.score("Grounded [1].", [_citation(1)]) == 1.0
    assert await evaluator.score("Ungrounded.", []) == 0.0


async def test_to_dict_serializes_result(evaluator: CitationEvaluator) -> None:
    result = await evaluator.evaluate("Grounded [1].", [_citation(1)])
    payload = evaluator.to_dict(result)
    assert payload["passed"] is True
    assert payload["score"] == 1.0
    assert payload["judge"] == "citation"
    assert "metadata" in payload
