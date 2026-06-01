"""Integration tests for generation service offline mode."""

import pytest

from app.services.generation import GenerationService


@pytest.mark.asyncio
async def test_simulated_generation_returns_answer() -> None:
    """Simulated generation produces a deterministic answer when no API key."""
    service = GenerationService()
    answer, usage = await service.generate_answer(
        query="What is AI?",
        context=["AI stands for Artificial Intelligence."],
        sources=[],
    )
    assert "Artificial Intelligence" in answer
    assert usage["total_tokens"] == 0


@pytest.mark.asyncio
async def test_simulated_generation_refuses_empty_context() -> None:
    """Simulated generation refuses when no context is provided."""
    service = GenerationService()
    answer, usage = await service.generate_answer(
        query="What is AI?",
        context=[],
        sources=[],
    )
    assert "don't have sufficient information" in answer.lower()


@pytest.mark.asyncio
async def test_simulated_stream_yields_tokens() -> None:
    """Simulated streaming yields tokens and done event."""
    service = GenerationService()
    events = []
    async for event in service.stream_answer(
        query="What is AI?",
        context=["AI stands for Artificial Intelligence."],
        sources=[],
    ):
        events.append(event)

    assert len(events) > 2
    assert events[0]["type"] == "token"
    assert events[-1]["type"] == "done"
    assert events[-1]["token_usage"]["completion_tokens"] > 0
