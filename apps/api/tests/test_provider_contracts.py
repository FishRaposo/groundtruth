"""Contracts for offline/provider-backed generation and embeddings."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from app.internal.provider_contracts import (
    EmbeddingResult,
    GenerationResult,
    OfflineEmbeddingProvider,
    OfflineGenerationProvider,
    UsageMetadata,
)
from app.services.embedding import EmbeddingService
from app.services.generation import GenerationService


class StubGenerationProvider:
    async def complete(
        self, query: str, context: list[str], sources: list[object]
    ) -> GenerationResult:
        return GenerationResult(
            text=f"answer:{query}:{context[0]}",
            provider="stub",
            model="stub-1",
            usage=UsageMetadata(prompt_tokens=2, completion_tokens=3),
        )

    async def stream(
        self, query: str, context: list[str], sources: list[object]
    ) -> AsyncIterator[dict[str, object]]:
        yield {"type": "token", "content": "answer"}
        yield {
            "type": "done",
            "token_usage": {
                "prompt_tokens": 0,
                "completion_tokens": 1,
                "total_tokens": 1,
            },
        }


class StubEmbeddingProvider:
    async def embed(self, texts: list[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=[[float(len(text))] for text in texts],
            provider="stub",
            model="stub-embedding",
            dimensions=1,
        )


def test_usage_metadata_derives_total_tokens() -> None:
    usage = UsageMetadata(prompt_tokens=2, completion_tokens=3)
    assert usage.total_tokens == 5
    assert usage.as_legacy_dict() == {
        "prompt_tokens": 2,
        "completion_tokens": 3,
        "total_tokens": 5,
    }


@pytest.mark.asyncio
async def test_generation_service_accepts_typed_provider_without_wire_change() -> None:
    service = GenerationService(provider=StubGenerationProvider())
    answer, usage = await service.generate_answer("Q", ["context"], [])
    assert answer == "answer:Q:context"
    assert usage == {
        "prompt_tokens": 2,
        "completion_tokens": 3,
        "total_tokens": 5,
    }


@pytest.mark.asyncio
async def test_embedding_service_accepts_typed_provider_without_wire_change() -> None:
    service = EmbeddingService(provider=StubEmbeddingProvider(), cache_enabled=False)
    assert await service.embed_texts(["a", "abcd"]) == [[1.0], [4.0]]


@pytest.mark.asyncio
async def test_offline_generation_is_deterministic_and_preserves_citations() -> None:
    provider = OfflineGenerationProvider()
    first = await provider.complete("Q", ["alpha", "beta"], [])
    second = await provider.complete("Q", ["alpha", "beta"], [])
    assert first == second
    assert "source [1]" in first.text
    assert first.usage.total_tokens == 0


@pytest.mark.asyncio
async def test_offline_embedding_is_deterministic_and_unit_length() -> None:
    provider = OfflineEmbeddingProvider(dimensions=8)
    first = await provider.embed(["stable"])
    second = await provider.embed(["stable"])
    assert first == second
    assert first.dimensions == 8
    assert sum(value * value for value in first.vectors[0]) == pytest.approx(1.0)
