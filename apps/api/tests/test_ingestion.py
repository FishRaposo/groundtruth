import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.models.document import Document, DocumentStatus, SourceType
from app.services.ingestion import IngestionService


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
async def test_ingest_document_creates_pending_record(
    service: IngestionService,
) -> None:
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
        mock_chunking.chunk_by_semantic.return_value = ["chunk one", "chunk two"]
        mock_embedding.embed_texts = AsyncMock(
            return_value=[[0.1] * 1536, [0.2] * 1536]
        )

        await service.process_document(doc_id)

        mock_parser.parse.assert_awaited_once()
        mock_chunking.chunk_by_semantic.assert_called_once_with(mock_parsed.content)
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
        mock_chunking.chunk_by_semantic.return_value = ["a", "b", "c"]
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
        mock_chunking.chunk_by_semantic.return_value = ["Short content."]
        mock_embedding.embed_texts = AsyncMock(return_value=[[0.1] * 1536])

        await service.process_document(doc_id)

        assert mock_doc.status == DocumentStatus.READY
        assert mock_session.commit.await_count >= 2


@pytest.mark.asyncio
async def test_process_nonexistent_document_returns_none(
    service: IngestionService,
) -> None:
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
async def test_process_document_sets_error_on_failure(
    service: IngestionService,
) -> None:
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
        assert mock_doc.metadata_["quarantine"] == {
            "reason": "file not found",
            "stage": "parse",
            "source_path": f"data/uploads/{doc_id}/{doc_id}.md",
            "reprocess_with": "reindex_document",
        }


@pytest.mark.asyncio
async def test_process_document_skips_duplicate_content(
    service: IngestionService,
) -> None:
    doc_id = uuid.uuid4()
    existing_id = uuid.uuid4()
    mock_doc = _make_mock_document(doc_id=doc_id, title="copy.md")
    existing = _make_mock_document(doc_id=existing_id, title="original.md")

    document_result = MagicMock()
    document_result.scalar_one_or_none.return_value = mock_doc
    duplicate_result = MagicMock()
    duplicate_result.scalar_one_or_none.return_value = existing

    mock_session = AsyncMock()
    mock_session.execute.side_effect = [document_result, duplicate_result]
    mock_session.commit = AsyncMock()
    session_ctx = _make_async_session(mock_session)

    mock_parser = AsyncMock()
    mock_parsed = MagicMock()
    mock_parsed.content = "same   content"
    mock_parsed.metadata = {"file_type": "markdown"}
    mock_parser.parse.return_value = mock_parsed

    with (
        patch("app.services.ingestion.AsyncSessionLocal", return_value=session_ctx),
        patch("app.services.ingestion.get_parser", return_value=mock_parser),
        patch("app.services.ingestion.embedding_service") as mock_embedding,
    ):
        await service.process_document(doc_id)

    assert mock_doc.status == DocumentStatus.READY
    assert mock_doc.metadata_["duplicate_of"] == str(existing_id)
    assert mock_doc.chunk_count == 0
    mock_embedding.embed_texts.assert_not_called()


@pytest.mark.asyncio
async def test_process_document_enriches_metadata_and_deduplicates_semantic_chunks(
    service: IngestionService,
) -> None:
    doc_id = uuid.uuid4()
    mock_doc = _make_mock_document(doc_id=doc_id, title="people.md")

    document_result = MagicMock()
    document_result.scalar_one_or_none.return_value = mock_doc
    duplicate_result = MagicMock()
    duplicate_result.scalar_one_or_none.return_value = None

    mock_session = AsyncMock()
    mock_session.execute.side_effect = [document_result, duplicate_result]
    mock_session.commit = AsyncMock()
    mock_session.flush = AsyncMock()
    mock_session.add = MagicMock()
    session_ctx = _make_async_session(mock_session)

    mock_parser = AsyncMock()
    mock_parsed = MagicMock()
    mock_parsed.content = "Jane Smith works at Acme. Contact jane@example.com."
    mock_parsed.metadata = {"file_type": "markdown", "page_count": 1}
    mock_parser.parse.return_value = mock_parsed

    with (
        patch("app.services.ingestion.AsyncSessionLocal", return_value=session_ctx),
        patch("app.services.ingestion.get_parser", return_value=mock_parser),
        patch("app.services.ingestion.chunking_service") as mock_chunking,
        patch("app.services.ingestion.embedding_service") as mock_embedding,
    ):
        mock_chunking.chunk_by_semantic.return_value = ["same", " same ", "unique"]
        mock_embedding.embed_texts = AsyncMock(return_value=[[0.1], [0.2]])

        await service.process_document(doc_id)

    mock_chunking.chunk_by_semantic.assert_called_once_with(
        "Jane Smith works at Acme. Contact jane@example.com."
    )
    mock_embedding.embed_texts.assert_awaited_once_with(["same", "unique"])
    assert mock_doc.metadata_["entities"]["emails"] == ["jane@example.com"]
    assert mock_doc.chunk_count == 2
    assert mock_doc.page_count == 1
