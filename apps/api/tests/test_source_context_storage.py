"""Immutable title context publication and lifecycle contracts."""

import copy
import hashlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.config import get_settings
from app.db.session import Base
from app.models.chunk import Chunk
from app.models.document import Document, DocumentVersion, SourceType
from app.models.ingestion import IngestionJob
from app.services.document import source_context
from app.services.document.versioning import DocumentVersionManager
from app.services.ingestion_jobs import create_job, process_job
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def context_db(tmp_path, monkeypatch):
    settings = get_settings()
    monkeypatch.setitem(settings.__dict__, "SOURCE_CONTEXT_MODE", "versioned_title")
    monkeypatch.setattr(settings, "STORAGE_ROOT", str(tmp_path))
    fake_embeddings = SimpleNamespace(
        signature={"mode": "test", "dimension": 2},
        chunk_content=lambda body: [body],
        embed_texts=AsyncMock(side_effect=lambda bodies: [[1.0, 0.0] for _ in bodies]),
    )
    monkeypatch.setattr(
        "app.services.ingestion_jobs.embedding_service", fake_embeddings
    )
    monkeypatch.setattr("app.services.embedding.embedding_service", fake_embeddings)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'context.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.services.ingestion_jobs.AsyncSessionLocal", factory)
    async with factory() as db:
        yield db, factory
    await engine.dispose()


async def test_queued_job_captures_accepted_title_before_a_display_rename(context_db):
    db, _ = context_db
    doc = Document(
        title="Original Élan scope",
        source_type=SourceType.TEXT,
        workspace_id="ws-a",
        owner_id="owner",
    )
    db.add(doc)
    await db.commit()
    job = await create_job(db, doc, {"id": "owner"}, source_path="unused.txt")
    assert (job.metadata_ or {}).get("source_context_input", {}).get(
        "title"
    ) == "Original Élan scope"
    doc.title = "Today's different display label"
    await db.commit()
    assert job.metadata_["source_context_input"]["title"] == "Original Élan scope"


async def publish(
    db,
    tmp_path,
    body="The body contains one literal assertion.",
    *,
    doc=None,
    title="Accepted scope",
    source_title=None,
):
    if doc is None:
        doc = Document(
            title=title,
            source_type=SourceType.TEXT,
            workspace_id="ws-a",
            owner_id="owner",
        )
        db.add(doc)
        await db.commit()
    path = tmp_path / f"{uuid.uuid4()}.txt"
    path.write_bytes(body.encode("utf-8"))
    job = await create_job(
        db,
        doc,
        {"id": "owner"},
        source_path=str(path),
        kind="upload" if not doc.version_number else "update",
        source_title=source_title,
    )
    await process_job(job.id)
    db.expunge_all()
    doc = await db.get(Document, doc.id)
    job = await db.get(IngestionJob, job.id)
    assert job.status == "completed", job.error
    snapshot = await db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.version_number == doc.version_number,
        )
    )
    return doc, snapshot, job


def resolved(snapshot, **overrides):
    item = snapshot.chunks[0]
    kwargs = {
        "document_id": str(snapshot.document_id),
        "workspace_id": snapshot.workspace_id,
        "version_number": snapshot.version_number,
        "body_hash": snapshot.content_hash,
        "chunk_index": item["index"],
        "chunk_content": item["content"],
    }
    kwargs.update(overrides)
    resolver = getattr(source_context, "resolve_source_context", lambda *a, **kw: None)
    return resolver(snapshot, **kwargs)


async def test_publication_context_is_bound_to_snapshot_and_body_bytes(
    context_db, tmp_path
):
    db, _ = context_db
    doc, snapshot, _ = await publish(db, tmp_path, title="Élan / scope")
    envelope = resolved(snapshot)
    assert envelope is not None
    assert envelope["title"] == "Élan / scope"
    assert envelope["usage"] == "scope_only"
    assert (
        envelope["body_hash"]
        == hashlib.sha256(snapshot.normalized_content.encode("utf-8")).hexdigest()
    )
    assert snapshot.content_hash == doc.content_hash == envelope["body_hash"]
    doc.title = "Renamed later"
    await db.commit()
    assert resolved(snapshot)["title"] == "Élan / scope"


async def test_context_only_change_creates_revision_but_exact_repeat_deduplicates(
    context_db, tmp_path
):
    db, _ = context_db
    doc, first, _ = await publish(db, tmp_path, title="First context")
    old_chunks = copy.deepcopy(first.chunks)
    doc, second, _ = await publish(db, tmp_path, doc=doc, source_title="Second context")
    assert second.version_number == 2 and second.content_hash == first.content_hash
    assert resolved(first)["title"] == "First context"
    assert resolved(second)["title"] == "Second context"
    doc, repeated, job = await publish(
        db, tmp_path, doc=doc, source_title="Second context"
    )
    assert repeated.version_number == job.version_number == 2
    assert first.chunks == old_chunks


async def test_connected_restore_and_reindex_preserve_snapshot_title_not_display(
    context_db, tmp_path
):
    db, _ = context_db
    doc, first, _ = await publish(db, tmp_path, title="Historical scope")
    original = copy.deepcopy(first.chunks)
    doc, _, _ = await publish(
        db, tmp_path, "A changed body.", doc=doc, source_title="Changed scope"
    )
    doc.title = "Current display only"
    await db.commit()
    job = await create_job(
        db,
        doc,
        {"id": "owner"},
        source_path=None,
        kind="restore",
        metadata={"restore_version": 1},
    )
    await process_job(job.id)
    db.expunge_all()
    doc = await db.get(Document, doc.id)
    restored = await db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc.id, DocumentVersion.version_number == 3
        )
    )
    assert resolved(restored)["title"] == "Historical scope"
    restored_bytes = copy.deepcopy(restored.chunks)
    job = await create_job(db, doc, {"id": "owner"}, source_path=None, kind="reindex")
    await process_job(job.id)
    db.expunge_all()
    restored_again = await db.get(DocumentVersion, restored.id)
    assert restored_again.chunks == restored_bytes
    assert (await db.get(Document, doc.id)).version_number == 3
    assert resolved(restored_again)["title"] == "Historical scope"
    assert (await db.get(DocumentVersion, first.id)).chunks == original


async def test_library_versioning_and_restore_rebind_known_context(
    context_db, tmp_path
):
    db, _ = context_db
    doc, first, _ = await publish(db, tmp_path, title="Original library scope")
    manager = DocumentVersionManager(db)
    doc.title = "Next scope"
    second = await manager.create_version(
        str(doc.id),
        "New body.",
        [Chunk(document_id=doc.id, content="New body.", chunk_index=0)],
        workspace_id="ws-a",
    )
    assert resolved(second)["title"] == "Next scope"
    await manager.restore_version(str(doc.id), 1, workspace_id="ws-a")
    restored = await db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc.id, DocumentVersion.version_number == 3
        )
    )
    assert resolved(restored)["title"] == "Original library scope"
    assert resolved(first)["version_number"] == 1
    assert resolved(restored)["version_number"] == 3


async def test_library_title_only_update_is_not_body_hash_deduplicated(context_db):
    db, _ = context_db
    doc = Document(title="One title", source_type=SourceType.TEXT, workspace_id="ws-a")
    db.add(doc)
    await db.commit()
    manager = DocumentVersionManager(db)
    first = await manager.create_version(
        str(doc.id),
        "Body.",
        [Chunk(document_id=doc.id, content="Body.", chunk_index=0)],
        workspace_id="ws-a",
    )
    doc.title = "Two title"
    second = await manager.create_version(
        str(doc.id),
        "Body.",
        [Chunk(document_id=doc.id, content="Body.", chunk_index=0)],
        workspace_id="ws-a",
    )
    assert second.version_number == 2 and first.version_number == 1


@pytest.mark.parametrize("restore_path", ["connected", "library"])
async def test_legacy_unknown_context_is_never_backfilled_on_restore(
    context_db, tmp_path, monkeypatch, restore_path
):
    db, _ = context_db
    monkeypatch.setattr(get_settings(), "SOURCE_CONTEXT_MODE", "body")
    doc, first, _ = await publish(
        db, tmp_path, title="Historical display was not captured"
    )
    assert resolved(first) is None
    monkeypatch.setattr(get_settings(), "SOURCE_CONTEXT_MODE", "versioned_title")
    doc.title = "Today's unrelated title"
    await db.commit()
    if restore_path == "connected":
        job = await create_job(
            db,
            doc,
            {"id": "owner"},
            source_path=None,
            kind="restore",
            metadata={"restore_version": 1},
        )
        await process_job(job.id)
        db.expunge_all()
    else:
        await DocumentVersionManager(db).restore_version(
            str(doc.id), 1, workspace_id="ws-a"
        )
    restored = await db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc.id, DocumentVersion.version_number == 2
        )
    )
    assert restored is not None and resolved(restored) is None
    assert all("source_context" not in item["metadata"] for item in restored.chunks)


@pytest.mark.parametrize(
    "field,value",
    [
        ("document_id", str(uuid.uuid4())),
        ("workspace_id", "ws-b"),
        ("version_number", 999),
        ("body_hash", "0" * 64),
        ("chunk_index", 99),
        ("chunk_content", "Unpublished text"),
    ],
)
async def test_resolver_rejects_cross_scope_or_unpublished_chunk(
    context_db, tmp_path, field, value
):
    db, _ = context_db
    _, snapshot, _ = await publish(db, tmp_path)
    assert resolved(snapshot) is not None
    assert resolved(snapshot, **{field: value}) is None


@pytest.mark.parametrize(
    "field",
    [
        "title",
        "title_hash",
        "body_hash",
        "context_hash",
        "chunk_manifest_hash",
        "usage",
    ],
)
async def test_corrupt_snapshot_context_cannot_be_resolved(context_db, tmp_path, field):
    db, _ = context_db
    _, snapshot, _ = await publish(db, tmp_path)
    assert resolved(snapshot) is not None
    data = copy.deepcopy(snapshot.chunks)
    data[0]["metadata"]["source_context"][field] = "corrupt"
    snapshot.chunks = data
    assert resolved(snapshot) is None


@pytest.mark.parametrize(
    "title", ["", " ", "x" * 513, "bad\ntitle", "C:/absolute/title", "/absolute/title"]
)
async def test_unsafe_accepted_title_is_rejected_before_job_creation(context_db, title):
    db, _ = context_db
    doc = Document(title=title, source_type=SourceType.TEXT, workspace_id="ws-a")
    db.add(doc)
    await db.commit()
    with pytest.raises(ValueError, match="Title"):
        await create_job(db, doc, {"id": "owner"}, source_path="unused.txt")


@pytest.fixture
async def title_client(context_db, monkeypatch):
    from app.api.deps import get_current_user
    from app.db.session import get_db
    from app.main import app
    from httpx import ASGITransport, AsyncClient

    settings = get_settings()
    for key, value in {
        "EMBEDDING_MODE": "deterministic",
        "GENERATION_MODE": "extractive",
        "INGESTION_MODE": "inline",
        "RATE_LIMIT_ENABLED": False,
    }.items():
        monkeypatch.setattr(settings, key, value)
    _, factory = context_db

    async def database():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "owner",
        "workspace_id": "ws-a",
        "is_admin": False,
    }
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


async def test_single_upload_declares_title_before_first_publication(
    title_client, context_db
):
    response = await title_client.post(
        "/api/documents/upload",
        files={"files": ("neutral.txt", b"A body assertion.", "text/plain")},
        data={"title": "Actual author scope"},
    )
    assert response.status_code == 200, response.text
    identifier = response.json()["documents"][0]["id"]
    db, _ = context_db
    snapshot = await db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == uuid.UUID(identifier)
        )
    )
    assert resolved(snapshot)["title"] == "Actual author scope"
    assert resolved(snapshot)["origin"] == "declared_title"


async def test_same_body_update_accepts_new_declared_title(title_client, context_db):
    first = await title_client.post(
        "/api/documents/upload",
        files={"files": ("neutral.txt", b"A body assertion.", "text/plain")},
        data={"title": "Scope one"},
    )
    identifier = first.json()["documents"][0]["id"]
    response = await title_client.post(
        f"/api/v1/documents/{identifier}/versions",
        files={"file": ("neutral.txt", b"A body assertion.", "text/plain")},
        data={"title": "Scope two"},
    )
    assert response.status_code == 200, response.text
    db, _ = context_db
    snapshots = list(
        (
            await db.scalars(
                select(DocumentVersion)
                .where(DocumentVersion.document_id == uuid.UUID(identifier))
                .order_by(DocumentVersion.version_number)
            )
        ).all()
    )
    assert [resolved(snapshot)["title"] for snapshot in snapshots] == [
        "Scope one",
        "Scope two",
    ]


@pytest.mark.parametrize("title", ["", "unsafe\ntext", "x" * 513, "C:/private/path"])
async def test_declared_title_errors_are_bounded_before_publication(
    title_client, context_db, title
):
    response = await title_client.post(
        "/api/documents/upload",
        files={"files": ("neutral.txt", b"A body assertion.", "text/plain")},
        data={"title": title},
    )
    assert response.status_code == 422
    db, _ = context_db
    assert not list((await db.scalars(select(Document))).all())


async def test_single_title_cannot_be_applied_ambiguously_to_a_batch(
    title_client, context_db
):
    response = await title_client.post(
        "/api/documents/upload",
        files=[
            ("files", ("one.txt", b"One body.", "text/plain")),
            ("files", ("two.txt", b"Two body.", "text/plain")),
        ],
        data={"title": "Ambiguous title"},
    )
    assert response.status_code == 422
    db, _ = context_db
    assert not list((await db.scalars(select(Document))).all())


async def test_capture_hashes_are_retry_stable_and_ignore_chunk_row_ids(
    context_db, tmp_path
):
    db, _ = context_db
    _, snapshot, _ = await publish(db, tmp_path)
    captured = source_context.capture_title("Accepted scope")
    first = source_context.build_source_context(
        captured,
        document_id=snapshot.document_id,
        workspace_id="ws-a",
        version_number=1,
        body=snapshot.normalized_content,
        chunks=snapshot.chunks,
    )
    changed = copy.deepcopy(snapshot.chunks)
    changed[0]["id"] = str(uuid.uuid4())
    second = source_context.build_source_context(
        captured,
        document_id=snapshot.document_id,
        workspace_id="ws-a",
        version_number=1,
        body=snapshot.normalized_content,
        chunks=changed,
    )
    assert first == second


async def test_failed_job_retry_uses_original_capture_even_after_mode_and_title_change(
    context_db, tmp_path, monkeypatch
):
    db, _ = context_db
    doc = Document(
        title="Accepted before failure",
        source_type=SourceType.TEXT,
        workspace_id="ws-a",
        owner_id="owner",
    )
    db.add(doc)
    await db.commit()
    path = tmp_path / "not-yet-written.txt"
    job = await create_job(db, doc, {"id": "owner"}, source_path=str(path))
    await process_job(job.id)
    db.expunge_all()
    job = await db.get(IngestionJob, job.id)
    doc = await db.get(Document, doc.id)
    assert job.status == "error"
    doc.title = "Later mutable display"
    monkeypatch.setattr(get_settings(), "SOURCE_CONTEXT_MODE", "body")
    path.write_bytes(b"A body assertion.")
    job.status, job.active_slot, job.attempt = "queued", str(doc.id), job.attempt + 1
    await db.commit()
    await process_job(job.id)
    db.expunge_all()
    snapshot = await db.scalar(
        select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
    )
    assert resolved(snapshot)["title"] == "Accepted before failure"


async def test_title_mode_reindex_does_not_backfill_legacy_unknown(
    context_db, tmp_path, monkeypatch
):
    db, _ = context_db
    monkeypatch.setattr(get_settings(), "SOURCE_CONTEXT_MODE", "body")
    doc, first, _ = await publish(db, tmp_path)
    original = copy.deepcopy(first.chunks)
    monkeypatch.setattr(get_settings(), "SOURCE_CONTEXT_MODE", "versioned_title")
    doc.title = "Unobserved historical scope"
    await db.commit()
    job = await create_job(db, doc, {"id": "owner"}, source_path=None, kind="reindex")
    await process_job(job.id)
    db.expunge_all()
    snapshot = await db.get(DocumentVersion, first.id)
    assert snapshot.chunks == original and resolved(snapshot) is None
    assert (await db.get(Document, doc.id)).version_number == 1


async def test_legacy_title_mode_captures_a_durable_job_before_parser_work(
    context_db, monkeypatch
):
    from app.services.ingestion import IngestionService

    db, factory = context_db
    monkeypatch.setattr("app.services.ingestion.AsyncSessionLocal", factory)
    parser = SimpleNamespace(
        parse=AsyncMock(
            return_value=SimpleNamespace(content="Literal body.", metadata={})
        )
    )
    monkeypatch.setattr("app.services.ingestion.get_parser", lambda kind: parser)
    monkeypatch.setattr(
        "app.services.ingestion.embedding_service",
        SimpleNamespace(embed_texts=AsyncMock(return_value=[[1.0, 0.0]])),
    )
    dispatched = []

    async def hold_job(identifier):
        dispatched.append(identifier)

    monkeypatch.setattr("app.services.ingestion_jobs.dispatch_job", hold_job)
    doc = Document(
        title="Semantic scope without extension",
        source_type=SourceType.TEXT,
        owner_id="owner",
        workspace_id="ws-a",
        metadata_={"_upload_extension": ".txt"},
    )
    db.add(doc)
    await db.commit()
    await IngestionService().process_document(doc.id)
    job = await db.scalar(
        select(IngestionJob).where(IngestionJob.document_id == doc.id)
    )
    assert job is not None and job.status == "queued"
    assert (
        job.metadata_["source_context_input"]["title"]
        == "Semantic scope without extension"
    )
    assert dispatched == [job.id]
    parser.parse.assert_not_called()


async def test_opted_in_legacy_ingestion_does_not_fabricate_a_caller_identity(
    context_db, monkeypatch
):
    from app.services.ingestion import IngestionService

    db, factory = context_db
    monkeypatch.setattr("app.services.ingestion.AsyncSessionLocal", factory)
    monkeypatch.setattr(
        "app.services.ingestion.get_parser",
        lambda kind: SimpleNamespace(
            parse=AsyncMock(return_value=SimpleNamespace(content="Body.", metadata={}))
        ),
    )
    monkeypatch.setattr(
        "app.services.ingestion.embedding_service",
        SimpleNamespace(embed_texts=AsyncMock(return_value=[[1.0, 0.0]])),
    )
    doc = Document(
        title="Accepted scope", source_type=SourceType.TEXT, workspace_id="ws-a"
    )
    db.add(doc)
    await db.commit()
    with pytest.raises(ValueError, match="owner"):
        await IngestionService().process_document(doc.id)
    assert (
        await db.scalar(select(IngestionJob).where(IngestionJob.document_id == doc.id))
        is None
    )


async def test_legacy_reindex_of_known_context_uses_existing_snapshot(
    context_db, tmp_path, monkeypatch
):
    from app.services.ingestion import IngestionService

    db, factory = context_db
    doc, first, _ = await publish(db, tmp_path, title="Known original context")
    monkeypatch.setattr(get_settings(), "SOURCE_CONTEXT_MODE", "body")
    monkeypatch.setattr("app.services.ingestion.AsyncSessionLocal", factory)
    called = []

    async def hold_job(identifier):
        called.append(identifier)

    monkeypatch.setattr("app.services.ingestion_jobs.dispatch_job", hold_job)
    service = IngestionService()
    monkeypatch.setattr(service, "process_document", AsyncMock())
    await service.reindex_document(doc.id)
    job = await db.scalar(
        select(IngestionJob).where(
            IngestionJob.document_id == doc.id, IngestionJob.kind == "reindex"
        )
    )
    assert job is not None and called == [job.id]
    assert job.metadata_["source_context_input"]["title"] == "Known original context"
    service.process_document.assert_not_called()
    assert resolved(first)["title"] == "Known original context"


async def test_rename_between_job_acceptance_and_worker_start_does_not_change_evidence(
    context_db, tmp_path
):
    db, _ = context_db
    doc = Document(
        title="Accepted title",
        source_type=SourceType.TEXT,
        workspace_id="ws-a",
        owner_id="owner",
    )
    db.add(doc)
    await db.commit()
    path = tmp_path / "body.txt"
    path.write_bytes(b"Literal body.")
    job = await create_job(db, doc, {"id": "owner"}, source_path=str(path))
    doc.title = "Renamed before worker loads the document"
    await db.commit()
    await process_job(job.id)
    db.expunge_all()
    snapshot = await db.scalar(
        select(DocumentVersion).where(DocumentVersion.document_id == doc.id)
    )
    assert resolved(snapshot)["title"] == "Accepted title"


async def test_reindex_preserves_snapshot_partitions_and_source_context(
    context_db, tmp_path, monkeypatch
):
    from unittest.mock import Mock

    import app.services.ingestion_jobs as jobs
    from app.services.retrieval.scoped import retrieve_scoped

    db, _ = context_db
    monkeypatch.setattr(
        jobs.embedding_service,
        "chunk_content",
        lambda body: ["First sentence.", "Second sentence."],
    )
    doc, first, _ = await publish(db, tmp_path, body="First sentence. Second sentence.")
    original = copy.deepcopy(first.chunks)
    rechunker = Mock(return_value=["Merged replacement."])
    before_embeddings = jobs.embedding_service.embed_texts.await_count
    monkeypatch.setattr(
        jobs.embedding_service,
        "chunk_content",
        rechunker,
    )
    job = await create_job(db, doc, {"id": "owner"}, source_path=None, kind="reindex")
    await process_job(job.id)
    db.expunge_all()
    snapshot = await db.get(DocumentVersion, first.id)
    chunks = list(
        (
            await db.scalars(
                select(Chunk)
                .where(Chunk.document_id == doc.id)
                .order_by(Chunk.chunk_index)
            )
        ).all()
    )
    rechunker.assert_not_called()
    assert jobs.embedding_service.embed_texts.await_count == before_embeddings + 1
    assert snapshot.chunks == original and snapshot.version_number == 1
    assert snapshot.normalized_content == "First sentence. Second sentence."
    assert [str(chunk.id) for chunk in chunks] == [item["id"] for item in original]
    assert [chunk.content for chunk in chunks] == [item["content"] for item in original]
    assert all(
        resolved(snapshot, chunk_index=chunk.chunk_index, chunk_content=chunk.content)
        is not None
        for chunk in chunks
    )
    assert resolved(snapshot)["title"] == "Accepted scope"
    retrieved = await retrieve_scoped(
        db,
        "sentence",
        principal={"id": "owner", "workspace_id": "ws-a"},
        document_ids=[doc.id],
        method="keyword",
        top_k=10,
    )
    assert {chunk.content for chunk in retrieved.chunks} == {
        item["content"] for item in original
    }


async def test_inconsistent_chunk_copies_fail_context_verification(
    context_db, tmp_path, monkeypatch
):
    import app.services.ingestion_jobs as jobs

    db, _ = context_db
    monkeypatch.setattr(
        jobs.embedding_service,
        "chunk_content",
        lambda body: ["First sentence.", "Second sentence."],
    )
    _, snapshot, _ = await publish(
        db, tmp_path, body="First sentence. Second sentence."
    )
    assert resolved(snapshot) is not None
    data = copy.deepcopy(snapshot.chunks)
    data[1]["metadata"].pop("source_context")
    snapshot.chunks = data
    assert resolved(snapshot) is None


async def test_body_mode_cannot_be_opted_in_by_reserved_job_metadata(
    context_db, monkeypatch
):
    db, _ = context_db
    monkeypatch.setattr(get_settings(), "SOURCE_CONTEXT_MODE", "body")
    doc = Document(
        title="Display only",
        source_type=SourceType.TEXT,
        workspace_id="ws-a",
        owner_id="owner",
    )
    db.add(doc)
    await db.commit()
    job = await create_job(
        db,
        doc,
        {"id": "owner"},
        source_path="unused.txt",
        metadata={
            "source_context_input": source_context.capture_title("Unaccepted context"),
            "source_context_snapshot": {"version_number": 9},
        },
    )
    assert "source_context_input" not in (job.metadata_ or {})
    assert "source_context_snapshot" not in (job.metadata_ or {})


async def test_resolver_requires_integer_version_identity_not_boolean(
    context_db, tmp_path
):
    db, _ = context_db
    _, snapshot, _ = await publish(db, tmp_path)
    assert resolved(snapshot, version_number=True) is None


@pytest.mark.parametrize("kind", ["restore", "reindex"])
async def test_restore_and_reindex_keep_exact_existing_body_representation(
    context_db, kind
):
    db, _ = context_db
    body = "First exact line.\nSecond exact line."
    doc = Document(
        title="Captured context",
        source_type=SourceType.TEXT,
        workspace_id="ws-a",
        owner_id="owner",
    )
    db.add(doc)
    await db.commit()
    first = await DocumentVersionManager(db).create_version(
        str(doc.id),
        body,
        [Chunk(document_id=doc.id, chunk_index=0, content=body)],
        workspace_id="ws-a",
    )
    original = copy.deepcopy(first.chunks)
    job = await create_job(
        db,
        doc,
        {"id": "owner"},
        source_path=None,
        kind=kind,
        metadata={"restore_version": 1} if kind == "restore" else None,
    )
    await process_job(job.id)
    db.expunge_all()
    doc = await db.get(Document, doc.id)
    completed = await db.get(IngestionJob, job.id)
    assert completed.status == "completed", completed.error
    assert doc.version_number == (2 if kind == "restore" else 1)
    current = await db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == doc.id,
            DocumentVersion.version_number == doc.version_number,
        )
    )
    assert current.normalized_content == body
    assert doc.content_hash == current.content_hash == first.content_hash
    assert (await db.get(DocumentVersion, first.id)).chunks == original
    assert resolved(current)["title"] == "Captured context"


def test_each_context_envelope_keeps_only_a_compact_chunk_manifest_digest():
    captured = source_context.capture_title("Accepted scope")
    context = source_context.build_source_context(
        captured,
        document_id=uuid.uuid4(),
        workspace_id="ws-a",
        version_number=1,
        body="First. Second.",
        chunks=[{"index": 0, "content": "First."}, {"index": 1, "content": "Second."}],
    )
    assert "chunks" not in context
    assert context["chunk_count"] == 2
    assert len(context["chunk_manifest_hash"]) == 64


async def test_explicit_null_context_is_corruption_not_legacy_absence(
    context_db, tmp_path
):
    db, _ = context_db
    _, snapshot, _ = await publish(db, tmp_path)
    assert source_context.validated_snapshot_context(snapshot) is not None
    chunks = copy.deepcopy(snapshot.chunks)
    chunks[0]["metadata"]["source_context"] = None
    snapshot.chunks = chunks
    with pytest.raises(ValueError, match="context"):
        source_context.validated_snapshot_context(snapshot)
    assert resolved(snapshot) is None


async def test_late_workspace_change_cannot_rebind_a_captured_publication(
    context_db, tmp_path
):
    db, _ = context_db
    doc = Document(
        title="Accepted in original workspace",
        source_type=SourceType.TEXT,
        workspace_id="ws-a",
        owner_id="owner",
    )
    db.add(doc)
    await db.commit()
    path = tmp_path / "body.txt"
    path.write_bytes(b"Literal body.")
    job = await create_job(db, doc, {"id": "owner"}, source_path=str(path))
    doc.workspace_id = "ws-b"
    await db.commit()
    await process_job(job.id)
    db.expunge_all()
    completed = await db.get(IngestionJob, job.id)
    assert completed.status == "error"
    assert not list((await db.scalars(select(DocumentVersion))).all())


async def test_workspace_race_during_embedding_cannot_publish_a_misbound_snapshot(
    context_db, tmp_path, monkeypatch
):
    import app.services.ingestion_jobs as jobs
    from sqlalchemy import update

    db, factory = context_db
    doc = Document(
        title="Captured before work",
        source_type=SourceType.TEXT,
        workspace_id="ws-a",
        owner_id="owner",
    )
    db.add(doc)
    await db.commit()
    path = tmp_path / "body.txt"
    path.write_bytes(b"Literal body.")
    job = await create_job(db, doc, {"id": "owner"}, source_path=str(path))

    async def move_while_embedding(bodies):
        async with factory() as other:
            await other.execute(
                update(Document)
                .where(Document.id == doc.id)
                .values(workspace_id="ws-b")
            )
            await other.commit()
        return [[1.0, 0.0] for _ in bodies]

    monkeypatch.setattr(jobs.embedding_service, "embed_texts", move_while_embedding)
    await process_job(job.id)
    db.expunge_all()
    completed = await db.get(IngestionJob, job.id)
    assert completed.status == "error"
    assert not list((await db.scalars(select(DocumentVersion))).all())
