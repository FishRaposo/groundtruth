import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.retrieval import RetrievalService
from app.models.chunk import ChunkWithScore


@pytest.fixture
def service() -> RetrievalService:
    return RetrievalService()


def _make_chunk(chunk_id: uuid.UUID, doc_id: uuid.UUID, index: int) -> ChunkWithScore:
    return ChunkWithScore(
        id=chunk_id,
        document_id=doc_id,
        content=f"Chunk content {index}",
        chunk_index=index,
        metadata=None,
        relevance_score=0.0,
    )


@pytest.mark.asyncio
async def test_retrieve_returns_empty_for_no_documents(service: RetrievalService) -> None:
    with patch.object(service, "hybrid_search", new_callable=AsyncMock, return_value=[]):
        results = await service.retrieve("test query")
        assert results == []


@pytest.mark.asyncio
async def test_hybrid_search_combines_vector_and_keyword(service: RetrievalService) -> None:
    chunk_id_1 = uuid.uuid4()
    chunk_id_2 = uuid.uuid4()
    doc_id = uuid.uuid4()

    vector_results = [(str(chunk_id_1), 0.9)]
    keyword_results = [(str(chunk_id_2), 0.8)]

    mock_chunk_1 = MagicMock()
    mock_chunk_1.id = chunk_id_1
    mock_chunk_1.document_id = doc_id
    mock_chunk_1.content = "Vector result"
    mock_chunk_1.chunk_index = 0
    mock_chunk_1.metadata_ = None

    mock_chunk_2 = MagicMock()
    mock_chunk_2.id = chunk_id_2
    mock_chunk_2.document_id = doc_id
    mock_chunk_2.content = "Keyword result"
    mock_chunk_2.chunk_index = 1
    mock_chunk_2.metadata_ = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_chunk_1, mock_chunk_2]

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.retrieval.service.embedding_service") as mock_embedding,
        patch("app.services.retrieval.service.AsyncSessionLocal", return_value=mock_session),
    ):
        mock_embedding.embed_query = AsyncMock(return_value=[0.1] * 1536)

        with (
            patch.object(service, "similarity_search", new_callable=AsyncMock, return_value=vector_results),
            patch.object(service, "keyword_search", new_callable=AsyncMock, return_value=keyword_results),
        ):
            results = await service.hybrid_search("test query", top_k=5)

            assert len(results) == 2
            assert all(isinstance(r, ChunkWithScore) for r in results)
            assert results[0].relevance_score >= results[1].relevance_score


@pytest.mark.asyncio
async def test_similarity_search_returns_scored_results(service: RetrievalService) -> None:
    chunk_id = uuid.uuid4()
    # Return a row with id + embedding that yields ~0.85 cosine similarity with [0.1]*1536
    mock_row = MagicMock()
    mock_row.id = chunk_id
    mock_row.embedding = [0.1] * 1536

    mock_result = MagicMock()
    mock_result.all.return_value = [mock_row]

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.retrieval.service.AsyncSessionLocal", return_value=mock_session):
        results = await service.similarity_search([0.1] * 1536, top_k=5)

        assert len(results) == 1
        assert results[0][0] == str(chunk_id)
        assert round(results[0][1], 2) == 1.0


@pytest.mark.asyncio
async def test_keyword_search_handles_special_characters(service: RetrievalService) -> None:
    chunk_id = uuid.uuid4()
    mock_row = MagicMock()
    mock_row.id = chunk_id
    mock_row.content = "test query special"

    mock_result = MagicMock()
    mock_result.all.return_value = [mock_row]

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("app.services.retrieval.service.AsyncSessionLocal", return_value=mock_session):
        results = await service.keyword_search("test & query <special>", top_k=5)

        assert len(results) == 1
        assert results[0][0] == str(chunk_id)


@pytest.mark.asyncio
async def test_retrieve_respects_top_k(service: RetrievalService) -> None:
    mock_results = [
        _make_chunk(uuid.uuid4(), uuid.uuid4(), i) for i in range(3)
    ]

    with patch.object(service, "hybrid_search", new_callable=AsyncMock, return_value=mock_results[:3]) as mock_hybrid:
        results = await service.retrieve("test query", top_k=3)
        mock_hybrid.assert_awaited_once_with("test query", 3)
        assert len(results) == 3


@pytest.mark.asyncio
async def test_hybrid_search_with_no_results(service: RetrievalService) -> None:
    with (
        patch("app.services.retrieval.service.embedding_service") as mock_embedding,
        patch.object(service, "similarity_search", new_callable=AsyncMock, return_value=[]),
        patch.object(service, "keyword_search", new_callable=AsyncMock, return_value=[]),
    ):
        mock_embedding.embed_query = AsyncMock(return_value=[0.1] * 1536)
        results = await service.hybrid_search("obscure query", top_k=5)
        assert results == []


@pytest.mark.asyncio
async def test_rrf_fusion_gives_higher_score_to_items_in_both_results(service: RetrievalService) -> None:
    shared_id = str(uuid.uuid4())
    only_vector_id = str(uuid.uuid4())
    only_keyword_id = str(uuid.uuid4())
    doc_id = uuid.uuid4()

    vector_results = [(shared_id, 0.95), (only_vector_id, 0.8)]
    keyword_results = [(shared_id, 0.7), (only_keyword_id, 0.6)]

    def make_mock_chunk(cid_str: str, idx: int) -> MagicMock:
        c = MagicMock()
        c.id = uuid.UUID(cid_str)
        c.document_id = doc_id
        c.content = f"Content {idx}"
        c.chunk_index = idx
        c.metadata_ = None
        return c

    all_chunks = [make_mock_chunk(shared_id, 0), make_mock_chunk(only_vector_id, 1), make_mock_chunk(only_keyword_id, 2)]
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = all_chunks

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with (
        patch("app.services.retrieval.service.embedding_service") as mock_embedding,
        patch("app.services.retrieval.service.AsyncSessionLocal", return_value=mock_session),
        patch.object(service, "similarity_search", new_callable=AsyncMock, return_value=vector_results),
        patch.object(service, "keyword_search", new_callable=AsyncMock, return_value=keyword_results),
    ):
        mock_embedding.embed_query = AsyncMock(return_value=[0.1] * 1536)
        results = await service.hybrid_search("test query", top_k=5)

        scores_by_id = {str(r.id): r.relevance_score for r in results}
        assert scores_by_id[shared_id] > scores_by_id[only_vector_id]
        assert scores_by_id[shared_id] > scores_by_id[only_keyword_id]
