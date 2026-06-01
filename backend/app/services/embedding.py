from __future__ import annotations

import asyncio
import hashlib
import math
import random
from collections import OrderedDict
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.config import get_settings

settings = get_settings()


class EmbeddingCache:
    """LRU cache for embedding vectors keyed by content hash."""

    def __init__(self, max_size: int = 10000) -> None:
        self._cache: OrderedDict[str, list[float]] = OrderedDict()
        self._max_size = max_size

    def get(self, text: str) -> list[float] | None:
        key = hashlib.sha256(text.encode()).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        return None

    def set(self, text: str, embedding: list[float]) -> None:
        key = hashlib.sha256(text.encode()).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = embedding
        if len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def clear(self) -> None:
        self._cache.clear()

    @property
    def size(self) -> int:
        return len(self._cache)


class EmbeddingService:
    def __init__(self) -> None:
        self._model: Any = None
        self._client: Any = None
        self._cache: EmbeddingCache | None = None
        if settings.EMBEDDING_CACHE_ENABLED:
            self._cache = EmbeddingCache()

    def _get_client(self) -> Any:
        if self._client is None and settings.OPENAI_API_KEY:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(settings.LOCAL_EMBEDDING_MODEL)
        return self._model

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        to_embed_indices: list[int] = []
        to_embed_texts: list[str] = []

        if self._cache is not None:
            for i, text in enumerate(texts):
                cached = self._cache.get(text)
                if cached is not None:
                    results[i] = cached
                else:
                    to_embed_indices.append(i)
                    to_embed_texts.append(text)
        else:
            to_embed_indices = list(range(len(texts)))
            to_embed_texts = texts

        if not to_embed_texts:
            return results  # type: ignore[return-value]

        batch_size = settings.EMBEDDING_BATCH_SIZE
        all_embeddings: list[list[float]] = []

        for batch_start in range(0, len(to_embed_texts), batch_size):
            batch = to_embed_texts[batch_start:batch_start + batch_size]
            if settings.OPENAI_API_KEY:
                batch_embeddings = await self._embed_openai(batch)
            else:
                batch_embeddings = await self._embed_local(batch)
            all_embeddings.extend(batch_embeddings)

        for idx, embedding in zip(to_embed_indices, all_embeddings):
            results[idx] = embedding
            if self._cache is not None:
                self._cache.set(texts[idx], embedding)

        return results  # type: ignore[return-value]

    async def embed_query(self, query: str) -> list[float]:
        results = await self.embed_texts([query])
        return results[0]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        client = self._get_client()
        response = await client.embeddings.create(
            input=texts,
            model=settings.EMBEDDING_MODEL,
            dimensions=settings.EMBEDDING_DIMENSIONS,
        )
        return [item.embedding for item in response.data]

    async def _embed_local(self, texts: list[str]) -> list[list[float]]:
        try:
            model = self._get_model()
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None, lambda: model.encode(texts, convert_to_numpy=True)
            )
            return embeddings.tolist()
        except Exception:
            # Deterministic hash-based fallback when no local model available
            return [self._hash_embedding(t) for t in texts]

    def _hash_embedding(self, text: str) -> list[float]:
        """Generate a deterministic unit-length embedding from text hash.

        Falls back when sentence-transformers is unavailable. Produces
        consistent vectors for identical inputs so caching still works.
        """
        dims = settings.EMBEDDING_DIMENSIONS
        seed = int(hashlib.sha256(text.encode()).hexdigest(), 16)
        rng = random.Random(seed)
        vec = [rng.gauss(0.0, 1.0) for _ in range(dims)]
        magnitude = math.sqrt(sum(v * v for v in vec))
        if magnitude == 0:
            magnitude = 1.0
        return [v / magnitude for v in vec]

    def clear_cache(self) -> None:
        if self._cache is not None:
            self._cache.clear()


embedding_service = EmbeddingService()
