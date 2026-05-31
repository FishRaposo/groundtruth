import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.services.ingestion import IngestionService
from app.models.document import Document, DocumentStatus, SourceType


@pytest.fixture
def service() -> IngestionService:
    return IngestionService()


def _make_async_session(mock_session: AsyncMock) -> MagicMock:
    ctx_mgr = MagicMock()
    ctx_mgr.__aenter__ = AsyncMock(return_value=mock_session)
    ctx_mgr.__aexit__ = AsyncMock(return_value=False)
    return ctx_mgr


def _make_mock_document(
    doc_id: uuid.UUID | None = None,
    title: str = "test.md",
    source_type: SourceType = SourceType.MARKDOWN,
    status: DocumentStatus = DocumentStatus.PENDING,
) -> MagicMock:
    doc = MagicMock(spec=Document)
    doc.id = doc_id or uuid.uuid4()
    doc.title = title
    doc.source_type = source_type
    doc.status = status
    doc.metadata_ = None
    return doc


@pytest.mark.asyncio
async def test_ingest_document_creates_pending_record(service: IngestionService) -> None:
    assigned_id = uuid.uuid4()

    async def fake_refresh(doc: MagicMock) -> None:
        doc.id = assigned_id

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock(side_effect=fake_refresh)
    session_ctx = _make_async_session(mock_session)

    with (
        patch("app.services.ingestion.AsyncSessionLocal", return_value=session_ctx),
        patch.object(service, "process_document", new_callable=AsyncMock),
    ):
        result = await service.ingest_document("data/uploads/report.md")

        assert result.id == assigned_id
        mock_session.add.assert_called_once()
        assert result.title == "report.md"


@pytest.mark.asyncio
async def test_process_document_parses_and_chunks(service: IngestionService) -> None:
    doc_id = uuid.uuid4()
    mock_doc = _make_mock_document(doc_id=doc_id, title="test.md")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_doc

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()
    session_ctx = _make_async_session(mock_session)

    mock_parser = AsyncMock()
    mock_parsed = MagicMock()
    mock_parsed.content = "This is a test document with some content for chunking."
    mock_parser.parse.return_value = mock_parsed

    with (
        patch("app.services.ingestion.AsyncSessionLocal", return_value=session_ctx),
        patch("app.services.ingestion.get_parser", return_value=mock_parser),
        patch("app.services.ingestion.chunking_service") as mock_chunking,
        patch("app.services.ingestion.embedding_service") as mock_embedding,
    ):
        mock_chunking.chunk_text.return_value = ["chunk one", "chunk two"]
        mock_embedding.embed_texts = AsyncMock(return_value=[[0.1] * 1536, [0.2] * 1536])

        await service.process_document(doc_id)

        mock_parser.parse.assert_awaited_once()
        mock_chunking.chunk_text.assert_called_once_with(mock_parsed.content)
        assert mock_session.add.call_count == 2


@pytest.mark.asyncio
async def test_process_document_generates_embeddings(service: IngestionService) -> None:
    doc_id = uuid.uuid4()
    mock_doc = _make_mock_document(doc_id=doc_id, title="test.md")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_doc

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()
    session_ctx = _make_async_session(mock_session)

    mock_parser = AsyncMock()
    mock_parsed = MagicMock()
    mock_parsed.content = "Embedding test content."
    mock_parser.parse.return_value = mock_parsed

    embeddings = [[0.1] * 1536, [0.2] * 1536, [0.3] * 1536]

    with (
        patch("app.services.ingestion.AsyncSessionLocal", return_value=session_ctx),
        patch("app.services.ingestion.get_parser", return_value=mock_parser),
        patch("app.services.ingestion.chunking_service") as mock_chunking,
        patch("app.services.ingestion.embedding_service") as mock_embedding,
    ):
        mock_chunking.chunk_text.return_value = ["a", "b", "c"]
        mock_embedding.embed_texts = AsyncMock(return_value=embeddings)

        await service.process_document(doc_id)

        mock_embedding.embed_texts.assert_awaited_once_with(["a", "b", "c"])


@pytest.mark.asyncio
async def test_process_document_sets_ready_status(service: IngestionService) -> None:
    doc_id = uuid.uuid4()
    mock_doc = _make_mock_document(doc_id=doc_id, title="test.md")
    mock_doc.status = DocumentStatus.PENDING

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_doc

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()
    session_ctx = _make_async_session(mock_session)

    mock_parser = AsyncMock()
    mock_parsed = MagicMock()
    mock_parsed.content = "Short content."
    mock_parser.parse.return_value = mock_parsed

    with (
        patch("app.services.ingestion.AsyncSessionLocal", return_value=session_ctx),
        patch("app.services.ingestion.get_parser", return_value=mock_parser),
        patch("app.services.ingestion.chunking_service") as mock_chunking,
        patch("app.services.ingestion.embedding_service") as mock_embedding,
    ):
        mock_chunking.chunk_text.return_value = ["Short content."]
        mock_embedding.embed_texts = AsyncMock(return_value=[[0.1] * 1536])

        await service.process_document(doc_id)

        assert mock_doc.status == DocumentStatus.READY
        assert mock_session.commit.await_count >= 2


@pytest.mark.asyncio
async def test_process_nonexistent_document_returns_none(service: IngestionService) -> None:
    fake_id = uuid.uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    session_ctx = _make_async_session(mock_session)

    with patch("app.services.ingestion.AsyncSessionLocal", return_value=session_ctx):
        await service.process_document(fake_id)
        mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_document_sets_error_on_failure(service: IngestionService) -> None:
    doc_id = uuid.uuid4()
    mock_doc = _make_mock_document(doc_id=doc_id, title="test.md")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_doc

    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result
    mock_session.commit = AsyncMock()
    session_ctx = _make_async_session(mock_session)

    mock_parser = AsyncMock()
    mock_parser.parse.side_effect = FileNotFoundError("file not found")

    with (
        patch("app.services.ingestion.AsyncSessionLocal", return_value=session_ctx),
        patch("app.services.ingestion.get_parser", return_value=mock_parser),
    ):
        with pytest.raises(FileNotFoundError):
            await service.process_document(doc_id)

        assert mock_doc.status == DocumentStatus.ERROR
