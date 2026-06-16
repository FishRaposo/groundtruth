"""Regression test for EnhancedRetrievalService ChunkWithScore construction.

EnhancedRetrievalService previously built ChunkWithScore(score=...), but the
model field is ``relevance_score``; that would raise a ValidationError. This
pins the corrected kwarg and guards against the old field name regressing.
"""

import inspect
import re
import uuid

import pytest
from app.models.chunk import ChunkWithScore
from app.services.retrieval import enhanced as enhanced_module
from pydantic import ValidationError


def test_chunk_with_score_uses_relevance_score_not_score() -> None:
    chunk = ChunkWithScore(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        content="hello",
        chunk_index=0,
        metadata=None,
        relevance_score=0.5,
    )
    assert chunk.relevance_score == 0.5

    # The old kwarg must not silently work (extra fields are not the score).
    with pytest.raises(ValidationError):
        ChunkWithScore(
            id=uuid.uuid4(),
            document_id=uuid.uuid4(),
            content="hello",
            chunk_index=0,
            metadata=None,
            score=0.5,  # type: ignore[call-arg]
        )


def test_enhanced_module_no_longer_constructs_with_score_kwarg() -> None:
    # Guard the source so the dead-code service cannot reintroduce the bare
    # score= kwarg (the negative lookbehind excludes relevance_score=score).
    src = inspect.getsource(enhanced_module)
    assert re.search(r"(?<!relevance_)score=score", src) is None
    assert "relevance_score=score" in src
