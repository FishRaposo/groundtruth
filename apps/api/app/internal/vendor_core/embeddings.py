# Vendored from FishRaposo/operator-shared-core v1.3.0.
# Source commit: dbf276a7708da65b55e1f10b35af634b300d1f07.
"""Embedding-vector abstraction: providers, cache, and similarity helpers.

An ``EmbeddingProvider`` ABC + factory, an OpenAI provider and a deterministic
offline hash fallback (so demos/tests run with no API key), a gateway client built
on the internal ``BaseHTTPClient``, an LRU content-hash cache, and the pure
similarity ladder (cosine, TF cosine, Jaccard). Heavy deps (numpy,
sentence-transformers) are optional and dynamically imported.
"""

import hashlib
import math
import re
import struct
from abc import ABC, abstractmethod
from collections import Counter, OrderedDict
from typing import Any, Optional, Sequence

from pydantic import BaseModel

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _unwrap(value: Any) -> Optional[str]:
    """Extract plaintext from a pydantic SecretStr, or return the value as-is."""
    if value is None:
        return None
    if hasattr(value, "get_secret_value"):
        return value.get_secret_value()
    return value


class EmbeddingResult(BaseModel):
    """A single embedding vector with its model and dimensionality."""

    vector: list[float]
    model: str
    dimensions: int = 0


class EmbeddingProvider(ABC):
    """Abstract embedding provider."""

    @abstractmethod
    async def embed(self, text: str) -> EmbeddingResult: ...

    async def embed_batch(self, texts: list[str]) -> list[EmbeddingResult]:
        return [await self.embed(text) for text in texts]


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Embeddings via the OpenAI API (openai installed in the consuming service)."""

    def __init__(
        self, api_key: Optional[str] = None, model: str = "text-embedding-3-small"
    ) -> None:
        self.api_key = _unwrap(api_key)
        self.model = model

    async def embed(self, text: str) -> EmbeddingResult:
        try:
            import openai  # type: ignore
        except ImportError:
            raise ImportError(
                "openai module is not installed. Install it via 'pip install openai'."
            ) from None
        client = openai.AsyncOpenAI(api_key=self.api_key)
        response = await client.embeddings.create(model=self.model, input=text)
        vector = list(response.data[0].embedding)
        return EmbeddingResult(vector=vector, model=self.model, dimensions=len(vector))


class HashFallbackProvider(EmbeddingProvider):
    """Deterministic offline embeddings (sha256 -> seeded vector) for tests/demos."""

    def __init__(self, model: str = "hash-fallback", dimensions: int = 384) -> None:
        self.model = model
        self.dimensions = dimensions

    async def embed(self, text: str) -> EmbeddingResult:
        return EmbeddingResult(
            vector=_hash_vector(text, self.dimensions),
            model=self.model,
            dimensions=self.dimensions,
        )


def _hash_vector(text: str, dimensions: int) -> list[float]:
    vector: list[float] = []
    counter = 0
    while len(vector) < dimensions:
        digest = hashlib.sha256(f"{text}:{counter}".encode("utf-8")).digest()
        for offset in range(0, len(digest), 4):
            if len(vector) >= dimensions:
                break
            (raw,) = struct.unpack(">I", digest[offset : offset + 4])
            vector.append((raw / 0xFFFFFFFF) * 2.0 - 1.0)
        counter += 1
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def get_embedding_provider(
    *,
    api_key: Optional[str] = None,
    model: str = "text-embedding-3-small",
    offline: bool = False,
) -> EmbeddingProvider:
    """Return an OpenAI provider when a key is present, else the offline fallback."""
    if offline or not _unwrap(api_key):
        return HashFallbackProvider()
    return OpenAIEmbeddingProvider(api_key=api_key, model=model)


class EmbeddingClient:
    """Client for an OpenAI-compatible embeddings gateway (/v1/embeddings)."""

    def __init__(self, gateway_url: str, model: str = "text-embedding-3-small") -> None:
        self.gateway_url = gateway_url.rstrip("/")
        self.model = model

    async def embed(self, text: str) -> list[float]:
        from app.internal.vendor_core.clients import BaseHTTPClient

        client = BaseHTTPClient(base_url=self.gateway_url)
        try:
            response = await client.post(
                "/v1/embeddings", json={"model": self.model, "input": text}
            )
            data = response.json()
            return list(data["data"][0]["embedding"])
        finally:
            await client.close()


class EmbeddingCache:
    """LRU cache keyed on ``(model, sha256(text))``."""

    def __init__(self, maxsize: int = 1024) -> None:
        self.maxsize = maxsize
        self._store: "OrderedDict[str, list[float]]" = OrderedDict()

    def _key(self, model: str, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{model}:{digest}"

    def get(self, model: str, text: str) -> Optional[list[float]]:
        key = self._key(model, text)
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def put(self, model: str, text: str, vector: list[float]) -> None:
        key = self._key(model, text)
        self._store[key] = vector
        self._store.move_to_end(key)
        while len(self._store) > self.maxsize:
            self._store.popitem(last=False)


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity between two vectors (numpy-accelerated when available)."""
    try:
        import numpy as np  # type: ignore

        va = np.asarray(a, dtype=float)
        vb = np.asarray(b, dtype=float)
        denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
        if denom == 0.0:
            return 0.0
        return float(np.dot(va, vb) / denom)
    except ImportError:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return dot / (na * nb)


def tfidf_cosine(a: str, b: str) -> float:
    """Token-frequency cosine similarity between two strings."""
    ta, tb = _tokenize(a), _tokenize(b)
    if not ta or not tb:
        return 0.0
    ca, cb = Counter(ta), Counter(tb)
    vocab = set(ca) | set(cb)
    dot = sum(ca[t] * cb[t] for t in vocab)
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def jaccard_similarity(a: str, b: str) -> float:
    """Jaccard similarity over the token sets of two strings."""
    sa, sb = set(_tokenize(a)), set(_tokenize(b))
    if not sa and not sb:
        return 1.0
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)
