from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import math
import random
from collections import OrderedDict
from pathlib import Path
from typing import Any

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings
from app.internal.provider_contracts import EmbeddingProvider

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
    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        cache_enabled: bool | None = None,
    ) -> None:
        self._model: Any = None
        self._client: Any = None
        self._provider = provider
        self._cache: EmbeddingCache | None = None
        should_cache = (
            settings.EMBEDDING_CACHE_ENABLED if cache_enabled is None else cache_enabled
        )
        if should_cache:
            self._cache = EmbeddingCache()

    def _get_client(self) -> Any:
        if self._client is None and settings.OPENAI_API_KEY:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    def _get_model(self) -> Any:
        if self._model is None:
            module = importlib.import_module("sentence_transformers")
            if settings.EMBEDDING_MODE == "local":
                if not settings.LOCAL_MODEL_PATH:
                    raise RuntimeError(
                        (
                            "Local model is not configured. Run python -m "
                            "app.model_setup and set LOCAL_MODEL_PATH."
                        )
                    )
                root = Path(settings.LOCAL_MODEL_PATH).resolve()
                manifest = json.loads(
                    (root / "groundtruth-model.json").read_text(encoding="utf-8")
                )
                if (
                    manifest.get("model") != "sentence-transformers/all-MiniLM-L6-v2"
                    or manifest.get("revision")
                    != "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
                    or settings.LOCAL_MODEL_REVISION != manifest["revision"]
                ):
                    raise RuntimeError(
                        "Local model manifest does not match the pinned model revision."
                    )
                from app.model_setup import FILES

                if set(manifest.get("files", {})) != set(FILES):
                    raise RuntimeError("Local model manifest is incomplete.")
                for filename, digest in manifest["files"].items():
                    path = (root / filename).resolve()
                    if (
                        not path.is_relative_to(root)
                        or hashlib.sha256(path.read_bytes()).hexdigest() != digest
                    ):
                        raise RuntimeError("Local model file integrity check failed.")
                self._model = module.SentenceTransformer(
                    settings.LOCAL_MODEL_PATH,
                    device="cpu",
                    local_files_only=True,
                    trust_remote_code=False,
                    model_kwargs={"use_safetensors": True},
                )
                if self._model.get_sentence_embedding_dimension() != 384:
                    raise RuntimeError(
                        (
                            "Local model has incompatible embedding "
                            "dimensions; expected 384."
                        )
                    )
            else:
                self._model = module.SentenceTransformer(
                    settings.LOCAL_EMBEDDING_MODEL,
                    local_files_only=True,
                    trust_remote_code=False,
                )
        return self._model

    @property
    def signature(self) -> dict[str, Any]:
        from app.services.document.content_profile import LITERAL_CHUNKING

        mode = (
            settings.EMBEDDING_MODE
            if isinstance(settings.EMBEDDING_MODE, str)
            else "legacy"
        )
        return {
            "mode": mode,
            "model": "sentence-transformers/all-MiniLM-L6-v2"
            if mode == "local"
            else "sha256-gaussian"
            if mode == "deterministic"
            else settings.EMBEDDING_MODEL,
            "revision": settings.LOCAL_MODEL_REVISION if mode == "local" else "1",
            "dimension": 384 if mode == "local" else settings.EMBEDDING_DIMENSIONS,
            "chunking": "minilm-tokenizer-v1"
            if mode == "local"
            else LITERAL_CHUNKING
            if mode == "deterministic"
            else "legacy-semantic-v1",
        }

    def _cache_key(self, text: str) -> str:
        return (
            text if self.signature["mode"] == "legacy" else str(self.signature) + text
        )

    def chunk_content(self, content: str) -> list[str]:
        if settings.EMBEDDING_MODE == "deterministic":
            from app.services.document.content_profile import literal_windows

            return literal_windows(content, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
        if settings.EMBEDDING_MODE != "local":
            from app.services.chunking import chunking_service

            return chunking_service.chunk_by_semantic(content)
        model = self._get_model()
        tokenizer = model.tokenizer
        limit = min(int(model.max_seq_length), 256) - 2
        # Offsets retain exact original passages rather than reconstructed text.
        encoded = tokenizer(
            content,
            add_special_tokens=False,
            return_offsets_mapping=True,
            truncation=False,
        )
        offsets = encoded["offset_mapping"]
        stride = max(1, limit - 24)
        chunks = []
        for start in range(0, len(offsets), stride):
            window = offsets[start : start + limit]
            if window:
                chunks.append(content[window[0][0] : window[-1][1]])
            if start + limit >= len(offsets):
                break
        return chunks

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        results: list[list[float] | None] = [None] * len(texts)
        to_embed_indices: list[int] = []
        to_embed_texts: list[str] = []

        if self._cache is not None:
            for i, text in enumerate(texts):
                cached = self._cache.get(self._cache_key(text))
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
            batch = to_embed_texts[batch_start : batch_start + batch_size]
            batch_embeddings = await self._embed_batch(batch)
            all_embeddings.extend(batch_embeddings)

        for idx, embedding in zip(to_embed_indices, all_embeddings, strict=False):
            results[idx] = embedding
            if self._cache is not None:
                self._cache.set(self._cache_key(texts[idx]), embedding)

        return results  # type: ignore[return-value]

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        if self._provider is not None:
            return (await self._provider.embed(texts)).vectors
        mode = self.signature["mode"]
        if mode == "deterministic":
            return [self._hash_embedding(text) for text in texts]
        if mode == "local":
            return await self._embed_local(texts)
        if mode != "legacy":
            raise RuntimeError(
                "Unknown EMBEDDING_MODE; choose local, deterministic or legacy."
            )
        if settings.OPENAI_API_KEY:
            return await self._embed_openai(texts)
        return await self._embed_local(texts)

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
        except Exception as exc:
            if settings.EMBEDDING_MODE == "local":
                raise RuntimeError(
                    (
                        "Configured local embeddings are unavailable. Check "
                        "LOCAL_MODEL_PATH and install the embeddings extra; no "
                        "fallback was used."
                    )
                ) from exc
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
