from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.embedding import EmbeddingCache, EmbeddingService


class TestEmbeddingCache:
    def test_cache_miss_returns_none(self) -> None:
        cache = EmbeddingCache()
        assert cache.get("nonexistent text") is None

    def test_cache_set_and_get(self) -> None:
        cache = EmbeddingCache()
        vector = [0.1, 0.2, 0.3]
        cache.set("hello world", vector)
        assert cache.get("hello world") == vector

    def test_cache_hit_returns_cached_vector(self) -> None:
        cache = EmbeddingCache()
        cache.set("text", [1.0, 2.0])
        result = cache.get("text")
        assert result == [1.0, 2.0]

    def test_cache_evicts_oldest_when_full(self) -> None:
        cache = EmbeddingCache(max_size=3)
        cache.set("a", [1.0])
        cache.set("b", [2.0])
        cache.set("c", [3.0])
        cache.set("d", [4.0])

        assert cache.get("a") is None
        assert cache.get("b") == [2.0]
        assert cache.get("d") == [4.0]

    def test_cache_move_to_end_on_get(self) -> None:
        cache = EmbeddingCache(max_size=2)
        cache.set("first", [1.0])
        cache.set("second", [2.0])

        cache.get("first")
        cache.set("third", [3.0])

        assert cache.get("first") == [1.0]
        assert cache.get("second") is None

    def test_cache_move_to_end_on_set(self) -> None:
        cache = EmbeddingCache(max_size=2)
        cache.set("first", [1.0])
        cache.set("second", [2.0])

        cache.set("first", [10.0])
        cache.set("third", [3.0])

        assert cache.get("first") == [10.0]
        assert cache.get("second") is None

    def test_cache_clear(self) -> None:
        cache = EmbeddingCache()
        cache.set("text", [1.0])
        cache.clear()
        assert cache.get("text") is None
        assert cache.size == 0

    def test_cache_size_property(self) -> None:
        cache = EmbeddingCache()
        assert cache.size == 0
        cache.set("a", [1.0])
        assert cache.size == 1
        cache.set("b", [2.0])
        assert cache.size == 2

    def test_cache_overwrite_updates_value(self) -> None:
        cache = EmbeddingCache()
        cache.set("key", [1.0])
        cache.set("key", [2.0])
        assert cache.get("key") == [2.0]
        assert cache.size == 1


class TestEmbeddingService:
    @pytest.fixture
    def service(self) -> EmbeddingService:
        with patch("app.services.embedding.settings") as mock_settings:
            mock_settings.EMBEDDING_CACHE_ENABLED = True
            mock_settings.EMBEDDING_BATCH_SIZE = 100
            mock_settings.OPENAI_API_KEY = ""
            mock_settings.EMBEDDING_MODEL = "test-model"
            svc = EmbeddingService()
        return svc

    @pytest.mark.asyncio
    async def test_embed_texts_returns_empty_for_empty_input(self, service: EmbeddingService) -> None:
        result = await service.embed_texts([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_texts_returns_from_cache(self, service: EmbeddingService) -> None:
        service._cache = EmbeddingCache()
        service._cache.set("cached text", [0.5, 0.6])

        with patch("app.services.embedding.settings") as mock_settings:
            mock_settings.EMBEDDING_BATCH_SIZE = 100
            mock_settings.OPENAI_API_KEY = ""
            result = await service.embed_texts(["cached text"])

        assert result == [[0.5, 0.6]]

    @pytest.mark.asyncio
    async def test_embed_query_returns_single_vector(self, service: EmbeddingService) -> None:
        service._cache = None

        with (
            patch("app.services.embedding.settings") as mock_settings,
            patch.object(service, "embed_texts", new_callable=AsyncMock, return_value=[[0.1, 0.2, 0.3]]),
        ):
            mock_settings.EMBEDDING_BATCH_SIZE = 100
            mock_settings.OPENAI_API_KEY = ""
            result = await service.embed_query("test query")

        assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_embed_texts_splits_into_batches(self, service: EmbeddingService) -> None:
        service._cache = None
        texts = ["text1", "text2", "text3", "text4", "text5"]
        batch_vectors = [[float(i)] for i in range(5)]

        with patch("app.services.embedding.settings") as mock_settings:
            mock_settings.EMBEDDING_BATCH_SIZE = 2
            mock_settings.OPENAI_API_KEY = "fake-key"
            mock_settings.EMBEDDING_MODEL = "test-model"
            mock_settings.EMBEDDING_DIMENSIONS = 1

            with patch.object(service, "_embed_openai", new_callable=AsyncMock) as mock_openai:
                mock_openai.side_effect = [batch_vectors[0:2], batch_vectors[2:4], batch_vectors[4:5]]
                result = await service.embed_texts(texts)

        assert len(result) == 5
        assert mock_openai.await_count == 3

    def test_clear_cache_removes_entries(self, service: EmbeddingService) -> None:
        service._cache = EmbeddingCache()
        service._cache.set("a", [1.0])
        service.clear_cache()
        assert service._cache.size == 0

    def test_clear_cache_noop_when_cache_disabled(self) -> None:
        with patch("app.services.embedding.settings") as mock_settings:
            mock_settings.EMBEDDING_CACHE_ENABLED = False
            mock_settings.OPENAI_API_KEY = ""
            mock_settings.EMBEDDING_MODEL = "test-model"
            svc = EmbeddingService()

        svc.clear_cache()
