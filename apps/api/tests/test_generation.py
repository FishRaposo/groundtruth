"""Tests for the offline-first GenerationService (simulation + prompt building)."""

import pytest
from app.services.generation import GenerationService


@pytest.fixture
def service() -> GenerationService:
    return GenerationService()


async def test_generate_answer_offline_returns_simulated(
    service: GenerationService,
) -> None:
    answer, usage = await service.generate_answer(
        query="What is the policy?",
        context=["Employees may work remotely up to three days a week."],
        sources=[],
    )
    assert "source [1]" in answer
    assert "remotely" in answer
    assert usage == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


async def test_generate_answer_empty_context_refuses(
    service: GenerationService,
) -> None:
    answer, _ = await service.generate_answer(query="Q?", context=[], sources=[])
    assert "don't have sufficient information" in answer


async def test_simulate_answer_cites_each_source(service: GenerationService) -> None:
    answer = service._simulate_answer("Q?", ["alpha", "beta", "gamma"])
    assert "source [1]" in answer
    assert "source [2]" in answer
    assert "source [3]" in answer


async def test_simulate_answer_truncates_long_chunk(
    service: GenerationService,
) -> None:
    answer = service._simulate_answer("Q?", ["x" * 500])
    assert "..." in answer


def test_build_prompt_numbers_context(service: GenerationService) -> None:
    prompt = service._build_prompt("My question", ["first", "second"])
    assert "[1] first" in prompt
    assert "[2] second" in prompt
    assert "Question: My question" in prompt


def test_parse_response_strips_whitespace(service: GenerationService) -> None:
    assert service._parse_response("  hello  ") == "hello"


def test_parse_response_handles_empty(service: GenerationService) -> None:
    assert "No answer could be generated" in service._parse_response("   ")


async def test_stream_answer_offline_yields_tokens_then_done(
    service: GenerationService,
) -> None:
    events = [
        event
        async for event in service.stream_answer(
            query="Q?",
            context=["Some grounded context here."],
            sources=[],
        )
    ]
    assert events[-1]["type"] == "done"
    token_events = [e for e in events if e["type"] == "token"]
    assert len(token_events) > 0
    reconstructed = "".join(e["content"] for e in token_events)
    assert "grounded context" in reconstructed


async def test_stream_answer_done_reports_token_usage(
    service: GenerationService,
) -> None:
    events = [
        event
        async for event in service.stream_answer(
            query="Q?", context=["abc def"], sources=[]
        )
    ]
    done = events[-1]
    assert done["type"] == "done"
    assert done["token_usage"]["completion_tokens"] > 0
