"""GroundTruth-owned provider contracts and offline/OpenAI adapters.

The public services keep their historical tuple/list return values. These typed
contracts carry additive provider metadata internally and make deterministic
offline behavior injectable in tests and portfolio evidence.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class UsageMetadata:
    """Normalized token usage returned by a generation provider."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.total_tokens is None:
            object.__setattr__(
                self, "total_tokens", self.prompt_tokens + self.completion_tokens
            )

    def as_legacy_dict(self) -> dict[str, int]:
        """Return the API's existing token-usage wire shape."""
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": int(self.total_tokens or 0),
        }


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Structured provider completion result."""

    text: str
    provider: str
    model: str
    usage: UsageMetadata = UsageMetadata()
    fallback_path: str | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    """Structured embedding result for a batch."""

    vectors: list[list[float]]
    provider: str
    model: str
    dimensions: int
    usage: UsageMetadata = UsageMetadata()
    fallback_path: str | None = None


class GenerationProvider(Protocol):
    """Provider-neutral grounded completion interface."""

    async def complete(
        self, query: str, context: list[str], sources: list[object]
    ) -> GenerationResult: ...

    def stream(
        self, query: str, context: list[str], sources: list[object]
    ) -> AsyncIterator[dict[str, object]]: ...


class EmbeddingProvider(Protocol):
    """Provider-neutral batch embedding interface."""

    async def embed(self, texts: list[str]) -> EmbeddingResult: ...


def _offline_answer(context: list[str]) -> str:
    if not context:
        return (
            "I don't have sufficient information in the provided documents "
            "to answer this question. Please upload relevant documents or "
            "rephrase your query."
        )
    parts = []
    for index, chunk in enumerate(context, 1):
        excerpt = chunk[:200] + "..." if len(chunk) > 200 else chunk
        parts.append(f"According to source [{index}]: {excerpt}")
    return "Based on the retrieved context:\n\n" + "\n\n".join(parts)


class OfflineGenerationProvider:
    """Credential-free deterministic generation used by the default demo."""

    async def complete(
        self, query: str, context: list[str], sources: list[object]
    ) -> GenerationResult:
        del query, sources
        return GenerationResult(
            text=_offline_answer(context), provider="offline", model="deterministic"
        )

    async def stream(
        self, query: str, context: list[str], sources: list[object]
    ) -> AsyncIterator[dict[str, object]]:
        result = await self.complete(query, context, sources)
        words = result.text.split(" ")
        for word in words:
            yield {"type": "token", "content": word + " "}
            await asyncio.sleep(0.01)
        yield {
            "type": "done",
            "token_usage": UsageMetadata(completion_tokens=len(words)).as_legacy_dict(),
        }


class OfflineEmbeddingProvider:
    """Stable SHA-256-seeded unit vectors with no model download."""

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        vectors: list[list[float]] = []
        for text in texts:
            seed = int(hashlib.sha256(text.encode()).hexdigest(), 16)
            rng = random.Random(seed)
            vector = [rng.gauss(0.0, 1.0) for _ in range(self.dimensions)]
            magnitude = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / magnitude for value in vector])
        return EmbeddingResult(
            vectors=vectors,
            provider="offline",
            model="sha256-hash",
            dimensions=self.dimensions,
            fallback_path="hash",
        )


class OpenAIGenerationProvider:
    """Bounded-retry adapter around an OpenAI-compatible async client."""

    def __init__(self, client: Any, model: str, system_prompt: str, attempts: int = 3):
        self.client = client
        self.model = model
        self.system_prompt = system_prompt
        self.attempts = max(1, attempts)

    async def complete(
        self, query: str, context: list[str], sources: list[object]
    ) -> GenerationResult:
        del sources
        prompt = _numbered_prompt(query, context)
        response: Any = None
        for attempt in range(self.attempts):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_tokens=1024,
                )
                break
            except Exception:
                if attempt + 1 == self.attempts:
                    raise
                await asyncio.sleep(0)
        usage = getattr(response, "usage", None)
        return GenerationResult(
            text=(response.choices[0].message.content or "").strip(),
            provider="openai-compatible",
            model=self.model,
            usage=UsageMetadata(
                prompt_tokens=getattr(usage, "prompt_tokens", 0),
                completion_tokens=getattr(usage, "completion_tokens", 0),
                total_tokens=getattr(usage, "total_tokens", None),
            ),
        )

    async def stream(
        self, query: str, context: list[str], sources: list[object]
    ) -> AsyncIterator[dict[str, object]]:
        del sources
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": _numbered_prompt(query, context)},
            ],
            temperature=0.1,
            max_tokens=1024,
            stream=True,
        )
        completion_tokens = 0
        async for chunk in stream:
            if chunk.choices and (content := chunk.choices[0].delta.content):
                completion_tokens += 1
                yield {"type": "token", "content": content}
        yield {
            "type": "done",
            "token_usage": UsageMetadata(
                completion_tokens=completion_tokens
            ).as_legacy_dict(),
        }


class OpenAIEmbeddingProvider:
    """Bounded-retry OpenAI embedding adapter."""

    def __init__(
        self, client: Any, model: str, dimensions: int, attempts: int = 3
    ) -> None:
        self.client = client
        self.model = model
        self.dimensions = dimensions
        self.attempts = max(1, attempts)

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        response: Any = None
        for attempt in range(self.attempts):
            try:
                response = await self.client.embeddings.create(
                    input=texts, model=self.model, dimensions=self.dimensions
                )
                break
            except Exception:
                if attempt + 1 == self.attempts:
                    raise
                await asyncio.sleep(0)
        return EmbeddingResult(
            vectors=[item.embedding for item in response.data],
            provider="openai-compatible",
            model=self.model,
            dimensions=self.dimensions,
        )


def _numbered_prompt(query: str, context: list[str]) -> str:
    context_text = "\n\n".join(
        f"[{index}] {chunk}" for index, chunk in enumerate(context, 1)
    )
    return f"Context:\n{context_text}\n\nQuestion: {query}\n\nAnswer:"
