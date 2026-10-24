"""Real SQLite regressions for the connected application boundaries."""

import asyncio
import hashlib
import json
import uuid

import pytest
from app.api.deps import get_current_user
from app.config import get_settings
from app.db.session import Base, get_db
from app.main import app
from app.models.api_key import ApiKey
from app.models.chunk import Chunk
from app.models.collection import Collection, CollectionShare, collection_documents
from app.models.document import Document, DocumentStatus, SourceType
from app.models.query import Query
from app.services.document.versioning import DocumentVersionManager
from app.services.retrieval.service import RetrievalService
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest.fixture
async def connected_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session, factory
    await engine.dispose()


async def test_retrieval_uses_injected_session_and_document_filter(
    connected_db, monkeypatch
):
    session, factory = connected_db
    docs = [
        Document(
            title=f"doc{i}", source_type=SourceType.TEXT, status=DocumentStatus.READY
        )
        for i in range(2)
    ]
    session.add_all(docs)
    await session.flush()
    session.add_all(
        [
            Chunk(
                document_id=doc.id,
                content="rollback staging deploy",
                chunk_index=0,
                embedding=[1.0, 0.0],
            )
            for doc in docs
        ]
    )
    await session.commit()
    monkeypatch.setattr("app.services.retrieval.service.AsyncSessionLocal", factory)
    results = await RetrievalService().retrieve(
        "rollback", filters={"document_id": str(docs[0].id)}, db=session
    )
    assert results and {chunk.document_id for chunk in results} == {docs[0].id}


async def test_unclassified_query_is_not_visible_to_ordinary_reader(connected_db):
    session, _ = connected_db
    row = Query(
        question="private historic question",
        answer="private historical answer",
        sources=[],
        token_usage={},
    )
    session.add(row)
    await session.commit()

    async def db_override():
        yield session

    app.dependency_overrides[get_db] = db_override
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "reader",
        "workspace_id": "default",
        "is_admin": False,
    }
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(f"/api/queries/{row.id}")
            assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()


async def test_restore_regenerates_embeddings(connected_db):
    session, _ = connected_db
    doc = Document(
        title="Rollback", source_type=SourceType.TEXT, status=DocumentStatus.READY
    )
    session.add(doc)
    await session.commit()
    manager = DocumentVersionManager(session)
    await manager.create_version(
        str(doc.id),
        "rollback staging",
        [Chunk(document_id=doc.id, content="rollback staging", chunk_index=0)],
    )
    await manager.restore_version(str(doc.id), 1)
    chunks = list(
        (await session.scalars(select(Chunk).where(Chunk.document_id == doc.id))).all()
    )
    assert chunks and all(chunk.embedding for chunk in chunks)


@pytest.fixture
async def real_client(tmp_path, monkeypatch):
    settings = get_settings()
    for key, value in {
        "EMBEDDING_MODE": "deterministic",
        "GENERATION_MODE": "extractive",
        "INGESTION_MODE": "inline",
        "EMBEDDING_DIMENSIONS": 32,
        "AUTH_ENABLED": True,
        "RATE_LIMIT_ENABLED": False,
        "STORAGE_ROOT": str(tmp_path / "uploads"),
    }.items():
        monkeypatch.setattr(settings, key, value)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.services.ingestion_jobs.AsyncSessionLocal", factory)

    async def get_session():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = get_session
    keys = {}
    async with factory() as db:
        for alias, workspace, admin in [
            ("owner", "ops-a", False),
            ("reader", "ops-a", False),
            ("admin", "ops-a", True),
            ("other", "ops-b", True),
        ]:
            key = ApiKey(
                name=alias,
                key_hash=hashlib.sha256(alias.encode()).hexdigest(),
                key_prefix=alias,
                is_admin=admin,
                metadata_={
                    "workspace_id": workspace,
                    "organization_id": "org-a",
                    "group_ids": ["operators"],
                },
            )
            db.add(key)
            await db.flush()
            keys[alias] = str(key.id)
        await db.commit()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-API-Key": "owner"},
        ) as client:
            yield client, factory, keys
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def upload(
    client,
    text=(
        "Staging rollback uses release R42. Verify deployment "
        "health before resuming traffic."
    ),
):
    response = await client.post(
        "/api/documents/upload", files={"files": ("rollback.txt", text, "text/plain")}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ingestions"][0]["status"] == "completed", payload
    return payload["documents"][0]


async def test_real_upload_query_sources_versions_and_revocation(real_client):
    client, factory, keys = real_client
    doc = await upload(client)
    assert doc["status"] == "ready" and doc["version_number"] == 1
    identifier = doc["id"]
    assert (
        await client.get(
            f"/api/documents/{identifier}", headers={"X-API-Key": "reader"}
        )
    ).status_code == 404
    assert (
        await client.get(
            f"/api/documents/{identifier}",
            headers={"X-API-Key": "other", "X-Workspace-ID": "ops-a"},
        )
    ).status_code == 404
    async with factory() as db:
        collection = Collection(
            name="Public runbooks", owner_id=keys["owner"], is_public="public"
        )
        db.add(collection)
        await db.flush()
        await db.execute(
            collection_documents.insert().values(
                collection_id=collection.id, document_id=uuid.UUID(identifier)
            )
        )
        await db.commit()
        collection_id = collection.id
    body = {
        "question": "What release does staging rollback use?",
        "document_ids": [identifier],
        "retrieval_method": "keyword",
    }
    result = await client.post(
        "/api/queries", json=body, headers={"X-API-Key": "reader"}
    )
    assert result.status_code == 200, result.text
    saved = result.json()
    assert "R42" in saved["answer"] and saved["sources"][0]["document_version"] == 1
    assert saved["retrieval_trace"]["keyword_results"] == 1
    assert saved["provenance"]["embedding"]["mode"] == "deterministic"
    source = (
        await client.get(
            f"/api/queries/{saved['id']}/sources/1", headers={"X-API-Key": "reader"}
        )
    ).json()
    assert source["content_hash"] == doc["content_hash"] and "R42" in source["passage"]
    assert (
        await client.delete(
            f"/api/documents/{identifier}", headers={"X-API-Key": "reader"}
        )
    ).status_code == 404
    update = await client.post(
        f"/api/v1/documents/{identifier}/versions?base_version=1",
        files={
            "file": (
                "rollback.txt",
                "Staging rollback uses release R43. Verify staging health.",
                "text/plain",
            )
        },
    )
    assert update.status_code == 200 and update.json()["version_number"] == 2, (
        update.text
    )
    historical = (
        await client.get(
            f"/api/queries/{saved['id']}/sources/1", headers={"X-API-Key": "reader"}
        )
    ).json()
    assert (
        "R42" in historical["passage"] and historical["source_status"] == "superseded"
    )
    restored = await client.post(f"/api/v1/documents/{identifier}/versions/1/restore")
    assert restored.json()["new_version"] == 3, restored.text
    async with factory() as db:
        collection = await db.get(Collection, collection_id)
        collection.is_public = "private"
        await db.commit()
    restricted = (
        await client.get(f"/api/queries/{saved['id']}", headers={"X-API-Key": "reader"})
    ).json()
    assert (
        restricted["evidence_access"] == "restricted"
        and restricted["answer"] is None
        and restricted["sources"] == []
    )
    memory = (
        await client.get(
            f"/api/conversations/{saved['conversation_id']}",
            headers={"X-API-Key": "reader"},
        )
    ).json()
    assert "R42" not in json.dumps(memory)
    assert (
        await client.get(f"/api/queries/{saved['id']}", headers={"X-API-Key": "owner"})
    ).status_code == 404


async def test_stream_normal_parity_filters_and_memory_not_numbered_evidence(
    real_client,
):
    client, factory, _ = real_client
    doc = await upload(client)
    body = {
        "question": "Staging rollback release?",
        "document_ids": [doc["id"]],
        "retrieval_method": "keyword",
    }
    normal = (await client.post("/api/queries", json=body)).json()
    streamed = await client.post(
        "/api/queries/stream",
        json={
            **body,
            "conversation_id": normal["conversation_id"],
            "memory_policy": "recent",
        },
    )
    events = [
        json.loads(line[6:])
        for line in streamed.text.splitlines()
        if line.startswith("data: ")
    ]
    done = next(event for event in events if event["type"] == "done")
    assert done["answer"] == normal["answer"] and done["sources"] == normal["sources"]
    assert (
        "Conversation history" not in done["answer"]
        and done["sources"][0]["citation_index"] == 1
    )
    empty = (
        await client.post("/api/queries", json={**body, "document_ids": []})
    ).json()
    assert empty["refused"] and empty["retrieval_trace"]["keyword_results"] == 0
    unknown = (
        await client.post(
            "/api/queries",
            json={
                "question": "What is the moon cheese procurement budget?",
                "retrieval_method": "keyword",
            },
        )
    ).json()
    assert unknown["refused"]


async def test_failed_update_preserves_published_version_and_retry_is_explicit(
    real_client, monkeypatch
):
    client, factory, _ = real_client
    doc = await upload(client)
    failed = await client.post(
        f"/api/v1/documents/{doc['id']}/versions",
        files={"file": ("rollback.txt", b"", "text/plain")},
    )
    assert failed.json()["status"] == "error"
    current = (await client.get(f"/api/documents/{doc['id']}")).json()
    assert current["status"] == "ready" and current["version_number"] == 1
    job_id = failed.json()["ingestion_id"]
    retry = await client.post(f"/api/ingestions/{job_id}/retry")
    assert retry.json()["attempt"] == 2 and retry.json()["status"] == "error"
    from app.services.ingestion_jobs import process_job

    await process_job(uuid.UUID(job_id))
    assert (await client.get(f"/api/documents/{doc['id']}")).json()[
        "version_number"
    ] == 1
    oversized = await client.post(
        "/api/documents/upload",
        files={"files": ("large.txt", b"x" * (10 * 1024 * 1024 + 1), "text/plain")},
    )
    assert oversized.status_code == 413


async def test_authentication_is_not_disabled_by_testing_environment(real_client):
    client, _, _ = real_client
    missing = await client.get("/api/identity", headers={"X-API-Key": "not-a-key"})
    assert missing.status_code == 401


async def test_durable_admin_usage_preserves_legacy_keys_with_unknown_cost(real_client):
    client, _, _ = real_client
    await upload(client)
    result = await client.post(
        "/api/queries",
        json={"question": "Staging rollback release?", "retrieval_method": "keyword"},
    )
    assert result.status_code == 200
    response = await client.get("/api/v1/admin/usage", headers={"X-API-Key": "admin"})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["estimated_cost"] is None and payload["total_cost"] is None
    assert payload["total_requests"] == 1 and payload["input_tokens"] > 0
    assert {
        "output_tokens",
        "p50_latency_ms",
        "p95_latency_ms",
        "p99_latency_ms",
        "error_rate",
        "cost_by_model",
        "cost_by_prompt_version",
    } <= payload.keys()


async def test_authenticated_legacy_http_never_uses_unscoped_library_execution(
    real_client, monkeypatch
):
    client, _, _ = real_client
    doc = await upload(client)
    monkeypatch.setattr(get_settings(), "EMBEDDING_MODE", "legacy")
    monkeypatch.setattr(get_settings(), "GENERATION_MODE", "legacy")
    for path in (
        "/api/documents",
        f"/api/documents/{doc['id']}",
        f"/api/v1/documents/{doc['id']}/versions",
        "/api/v1/workflows/definitions",
        "/api/queries",
        "/api/conversations",
    ):
        response = await client.get(path)
        assert response.status_code == 503, (path, response.text)
    query = await client.post("/api/queries", json={"question": "Staging rollback?"})
    assert query.status_code == 503


async def test_new_keyword_query_cannot_promote_unclassified_legacy_evidence(
    real_client,
):
    client, factory, keys = real_client
    async with factory() as db:
        doc = Document(
            title="Unclassified legacy runbook",
            source_type=SourceType.TEXT,
            status=DocumentStatus.READY,
            workspace_id="ops-a",
            owner_id=None,
            version_number=0,
            content_hash=None,
        )
        db.add(doc)
        await db.flush()
        chunk = Chunk(
            document_id=doc.id,
            content="Staging rollback pauses deployment queue.",
            chunk_index=0,
            embedding=None,
            metadata_=None,
        )
        db.add(chunk)
        await db.flush()
        historic = Query(
            question="Old staging question",
            answer="Old recorded source extract",
            owner_id=keys["admin"],
            workspace_id="ops-a",
            sources=[
                {
                    "chunk_id": str(chunk.id),
                    "document_id": str(doc.id),
                    "document_title": doc.title,
                    "content_preview": chunk.content,
                    "relevance_score": 1.0,
                    "citation_index": 1,
                    "document_version": 0,
                    "content_hash": None,
                    "quoted_text": None,
                    "source_status": "current",
                }
            ],
            provenance={"generation_mode": "extractive"},
        )
        db.add(historic)
        await db.commit()
        doc_id, query_id = str(doc.id), str(historic.id)
    headers = {"X-API-Key": "admin"}
    result = await client.post(
        "/api/queries",
        headers=headers,
        json={
            "question": "Staging rollback deployment queue?",
            "document_ids": [doc_id],
            "retrieval_method": "keyword",
        },
    )
    assert result.status_code == 200, result.text
    assert result.json()["refused"] and result.json()["sources"] == []
    historical = (await client.get(f"/api/queries/{query_id}", headers=headers)).json()
    assert historical["evidence_access"] == "unknown"
    assert historical["sources"][0]["source_status"] == "unknown"
    passage = (
        await client.get(f"/api/queries/{query_id}/sources/1", headers=headers)
    ).json()
    assert (
        passage["source_status"] == "unknown"
        and passage["evidence_access"] == "unknown"
    )
    assert (
        await client.get(f"/api/documents/{doc_id}", headers=headers)
    ).status_code == 200
    publication = await client.post(
        f"/api/v1/documents/{doc_id}/versions?base_version=0",
        headers=headers,
        files={
            "file": (
                "legacy.txt",
                "Staging rollback pauses deployment queue.",
                "text/plain",
            )
        },
    )
    assert (
        publication.status_code == 200 and publication.json()["version_number"] == 1
    ), publication.text
    verified = (
        await client.post(
            "/api/queries",
            headers=headers,
            json={
                "question": "Staging rollback deployment queue?",
                "document_ids": [doc_id],
                "retrieval_method": "keyword",
            },
        )
    ).json()
    assert (
        not verified["refused"] and verified["sources"][0]["source_status"] == "current"
    )


async def test_mutated_chunk_cannot_claim_immutable_published_evidence(real_client):
    client, factory, _ = real_client
    doc = await upload(client)
    async with factory() as db:
        chunk = await db.scalar(
            select(Chunk).where(Chunk.document_id == uuid.UUID(doc["id"]))
        )
        chunk.content = (
            "Staging rollback deployment queue must disable all verification checks."
        )
        await db.commit()
    response = await client.post(
        "/api/queries",
        json={
            "question": "Staging rollback deployment queue?",
            "document_ids": [doc["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["refused"] and response.json()["sources"] == []


async def test_workspace_admin_cannot_mint_or_manage_keys_outside_workspace(
    real_client,
):
    client, _, keys = real_client
    headers = {"X-API-Key": "admin"}
    minted = await client.post(
        "/api/keys", headers=headers, json={"name": "Child admin", "is_admin": True}
    )
    assert minted.status_code == 201, minted.text
    identity = (
        await client.get("/api/identity", headers={"X-API-Key": minted.json()["key"]})
    ).json()
    assert identity["workspace_id"] == "ops-a"
    listed = (await client.get("/api/keys", headers=headers)).json()
    assert keys["other"] not in {key["id"] for key in listed["keys"]}
    for method in ("get", "patch", "delete"):
        kwargs = {"json": {"name": "tampered"}} if method == "patch" else {}
        response = await getattr(client, method)(
            f"/api/keys/{keys['other']}", headers=headers, **kwargs
        )
        assert response.status_code == 404, response.text
    assert (
        await client.get("/api/identity", headers={"X-API-Key": "other"})
    ).status_code == 200


async def test_api_restart_retains_queued_and_healthy_worker_claims(real_client):
    from datetime import timedelta

    from app.models.ingestion import IngestionJob
    from app.services.ingestion_jobs import interrupt_jobs, process_job
    from app.utils.time import utc_now

    client, factory, keys = real_client
    docs = [
        await upload(client, text=f"Staging rollback release R{index}")
        for index in range(3)
    ]
    async with factory() as db:
        jobs = []
        for index, doc in enumerate(docs):
            job = IngestionJob(
                document_id=uuid.UUID(doc["id"]),
                owner_id=keys["owner"],
                workspace_id="ops-a",
                status="queued" if index == 0 else "processing",
                stage="embed",
                claim_token=str(uuid.uuid4()),
                active_slot=doc["id"],
                base_version=1,
                lease_expires_at=utc_now() + timedelta(seconds=60)
                if index == 1
                else utc_now() - timedelta(seconds=1),
            )
            db.add(job)
            jobs.append(job)
        await db.commit()
        ids = [job.id for job in jobs]
    await interrupt_jobs()
    async with factory() as db:
        restored = [await db.get(IngestionJob, identifier) for identifier in ids]
        assert [job.status for job in restored] == [
            "queued",
            "processing",
            "interrupted",
        ]
        assert restored[1].active_slot is not None and restored[2].active_slot is None
    await process_job(ids[2])
    assert (await client.get(f"/api/documents/{docs[2]['id']}")).json()[
        "version_number"
    ] == 1


async def test_duplicate_ingestion_delivery_publishes_once(real_client):
    from app.services.ingestion_jobs import create_job, process_job

    client, factory, keys = real_client
    doc = await upload(client)
    async with factory() as db:
        document = await db.get(Document, uuid.UUID(doc["id"]))
        job = await create_job(
            db, document, {"id": keys["owner"]}, source_path=None, kind="reindex"
        )
        identifier = job.id
    await asyncio.gather(process_job(identifier), process_job(identifier))
    current = (await client.get(f"/api/documents/{doc['id']}")).json()
    assert current["version_number"] == 1 and current["chunk_count"] == 1


async def test_document_latest_ingestion_tracks_a_retried_older_job(real_client):
    from app.models.ingestion import IngestionJob

    client, factory, keys = real_client
    doc = await upload(client)
    async with factory() as db:
        older = IngestionJob(
            document_id=uuid.UUID(doc["id"]),
            owner_id=keys["owner"],
            workspace_id="ops-a",
            status="error",
            stage="embed",
            kind="reindex",
            base_version=1,
        )
        db.add(older)
        await db.commit()
        older_id = str(older.id)
    recent = await client.post(f"/api/documents/{doc['id']}/reindex")
    assert recent.json()["status"] == "completed", recent.text
    retry = await client.post(f"/api/ingestions/{older_id}/retry")
    assert retry.json()["status"] == "completed", retry.text
    current = (await client.get(f"/api/documents/{doc['id']}")).json()
    assert current["latest_ingestion"]["id"] == older_id


async def test_late_old_attempt_failure_cannot_fail_explicit_retry(
    real_client, monkeypatch
):
    from app.models.ingestion import IngestionJob
    from app.services.ingestion_jobs import mark_failed

    client, factory, keys = real_client
    doc = await upload(client)
    token = str(uuid.uuid4())
    async with factory() as db:
        job = IngestionJob(
            document_id=uuid.UUID(doc["id"]),
            owner_id=keys["owner"],
            workspace_id="ops-a",
            status="interrupted",
            stage="interrupted",
            claim_token=token,
            base_version=1,
            attempt=1,
        )
        db.add(job)
        await db.commit()
        identifier = job.id

    async def leave_queued(_identifier):
        return None

    monkeypatch.setattr("app.api.ingestions.dispatch_job", leave_queued)
    response = await client.post(f"/api/ingestions/{identifier}/retry")
    assert response.status_code == 200 and response.json()["status"] == "queued"
    await mark_failed(
        identifier, "embed", "Late failure from the old worker", claim_token=token
    )
    await mark_failed(
        identifier,
        "embed",
        "Late failure with an immutable attempt",
        claim_token=token,
        attempt=1,
    )
    async with factory() as db:
        current = await db.get(IngestionJob, identifier)
        assert (
            current.attempt == 2
            and current.status == "queued"
            and current.active_slot == doc["id"]
        )


async def test_late_dispatch_failure_cannot_fail_a_newer_queued_attempt(
    real_client, monkeypatch
):
    from app.models.ingestion import IngestionJob
    from app.services.ingestion_jobs import dispatch_job
    from sqlalchemy import update

    client, factory, keys = real_client
    doc = await upload(client)
    async with factory() as db:
        job = IngestionJob(
            document_id=uuid.UUID(doc["id"]),
            owner_id=keys["owner"],
            workspace_id="ops-a",
            status="queued",
            stage="queued",
            kind="reindex",
            attempt=1,
            base_version=1,
            active_slot=doc["id"],
        )
        db.add(job)
        await db.commit()
        identifier = job.id
    monkeypatch.setattr(get_settings(), "INGESTION_MODE", "queued")
    import threading

    waiting, release = threading.Event(), threading.Event()

    def ambiguous_publish(*_args, **_kwargs):
        waiting.set()
        assert release.wait(timeout=10)
        raise ConnectionError("The original publisher timed out after acceptance")

    monkeypatch.setattr("app.core.celery.celery_app.send_task", ambiguous_publish)

    async def publisher():
        # A separate server thread models a delayed publisher while another
        # request/worker advances the durable attempt in the same database.
        await dispatch_job(identifier)

    task = asyncio.create_task(asyncio.to_thread(lambda: asyncio.run(publisher())))
    assert await asyncio.to_thread(waiting.wait, 5)
    async with factory() as db:
        await db.execute(
            update(IngestionJob)
            .where(IngestionJob.id == identifier)
            .values(attempt=3, status="queued", stage="queued", claim_token=None)
        )
        await db.commit()
    release.set()
    await task
    async with factory() as db:
        current = await db.get(IngestionJob, identifier)
        assert (
            current.status == "queued"
            and current.attempt == 3
            and current.active_slot == doc["id"]
        )


async def test_compound_rollback_question_keeps_exact_source_support(real_client):
    client, _, _ = real_client
    doc = await upload(
        client,
        (
            "Staging rollback: pause the deployment queue and run the "
            "staging smoke test before resuming traffic."
        ),
    )
    response = await client.post(
        "/api/queries",
        json={
            "question": "How do I roll back the staging deployment?",
            "document_ids": [doc["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    assert not response.json()["refused"]
    assert "pause the deployment queue" in response.json()["answer"]


async def test_stream_disconnect_does_not_save_completed_answer(real_client):
    client, factory, _ = real_client
    await upload(
        client,
        "Staging rollback: pause the deployment queue.\n"
        + "\n".join(
            f"Staging verification step {index} checks release health."
            for index in range(20)
        ),
    )
    question = "What staging rollback deployment queue action applies?"
    body = json.dumps({"question": question, "retrieval_method": "keyword"}).encode()
    first_chunk = asyncio.Event()
    request_sent = False

    async def receive():
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await first_chunk.wait()
        return {"type": "http.disconnect"}

    async def send(message):
        if message[
            "type"
        ] == "http.response.body" and b'"type": "token"' in message.get("body", b""):
            first_chunk.set()
            await asyncio.sleep(0)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/queries/stream",
        "raw_path": b"/api/queries/stream",
        "query_string": b"",
        "headers": [
            (b"host", b"test"),
            (b"content-type", b"application/json"),
            (b"x-api-key", b"owner"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("127.0.0.1", 1234),
        "server": ("test", 80),
    }
    await asyncio.wait_for(app(scope, receive, send), timeout=10)
    await asyncio.sleep(0.1)
    async with factory() as db:
        row = await db.scalar(select(Query).where(Query.question == question))
        assert row.outcome == "interrupted" and row.answer is None


@pytest.mark.parametrize(
    "visibility,permission,expired,readable,writable",
    [
        ("organization", None, False, True, False),
        ("private", "read", False, True, False),
        ("private", "write", False, True, True),
        ("private", "read", True, False, False),
    ],
)
async def test_collection_rules_do_not_grant_implicit_writes(
    real_client, visibility, permission, expired, readable, writable
):
    from datetime import timedelta

    from app.utils.time import utc_now

    client, factory, keys = real_client
    doc = await upload(client)
    async with factory() as db:
        collection = Collection(
            name="Scoped collection",
            owner_id=keys["owner"],
            is_public=visibility,
            organization_id="org-a",
        )
        db.add(collection)
        await db.flush()
        await db.execute(
            collection_documents.insert().values(
                collection_id=collection.id, document_id=uuid.UUID(doc["id"])
            )
        )
        if permission:
            db.add(
                CollectionShare(
                    collection_id=collection.id,
                    group_id="operators",
                    permission=permission,
                    created_by=keys["owner"],
                    expires_at=utc_now() - timedelta(seconds=1) if expired else None,
                )
            )
        await db.commit()
    response = await client.get(
        f"/api/documents/{doc['id']}", headers={"X-API-Key": "reader"}
    )
    assert (response.status_code == 200) == readable
    if readable:
        assert response.json()["permissions"]["write"] == writable


async def test_concurrent_requests_keep_counts_and_sources_local(real_client):
    client, _, _ = real_client
    doc = await upload(client)

    async def ask(index):
        response = await client.post(
            "/api/queries",
            json={
                "question": "Staging rollback release?",
                "document_ids": [doc["id"]] if index % 2 else [],
                "retrieval_method": "keyword",
            },
        )
        assert response.status_code == 200, response.text
        return index, response.json()

    results = await asyncio.gather(*(ask(index) for index in range(20)))
    assert len({result["id"] for _, result in results}) == 20
    for index, result in results:
        assert result["retrieval_trace"]["keyword_results"] == (1 if index % 2 else 0)
        assert bool(result["sources"]) == bool(index % 2)


async def test_queue_outage_is_an_error_without_inline_fallback(
    real_client, monkeypatch
):
    client, _, _ = real_client
    settings = get_settings()
    monkeypatch.setattr(settings, "INGESTION_MODE", "queued")

    def unavailable(*_args, **_kwargs):
        raise ConnectionError("private server address must not be exposed")

    monkeypatch.setattr("app.tasks.documents.process_ingestion_task.delay", unavailable)
    result = await client.post(
        "/api/documents/upload",
        files={"files": ("failed.txt", "Staging rollback release R42", "text/plain")},
    )
    payload = result.json()
    assert payload["ingestions"][0]["status"] == "error"
    assert payload["documents"][0]["version_number"] == 0
    assert "private server" not in json.dumps(payload)


async def test_workflow_transition_is_durable_and_single_use(real_client):
    client, factory, keys = real_client
    doc = await upload(client)
    definition = await client.post(
        "/api/v1/workflows/definitions",
        json={
            "name": "Review rollback",
            "steps": [
                {
                    "name": "Operator approval",
                    "approvers": [keys["owner"]],
                    "min_approvals": 1,
                }
            ],
        },
    )
    assert definition.status_code == 200, definition.text
    body = {
        "workflow_definition_id": definition.json()["id"],
        "document_id": doc["id"],
        "trigger_type": "manual",
    }
    result = await client.post("/api/v1/workflows/instances", json=body)
    assert result.status_code == 200, result.text
    workflow = (
        await client.get(f"/api/v1/workflows/instances/{result.json()['id']}")
    ).json()
    approval = {"step_id": workflow["steps"][0]["id"], "action": "approve"}
    accepted = await client.post(
        f"/api/v1/workflows/{workflow['id']}/approve", json=approval
    )
    assert (
        accepted.status_code == 200 and accepted.json()["new_status"] == "approved"
    ), accepted.text
    assert (
        await client.post(f"/api/v1/workflows/{workflow['id']}/approve", json=approval)
    ).status_code == 400
    assert (
        await client.post(f"/api/v1/workflows/instances/{workflow['id']}/cancel")
    ).status_code == 404
    second = (await client.post("/api/v1/workflows/instances", json=body)).json()
    assert (
        await client.post(f"/api/v1/workflows/instances/{second['id']}/cancel")
    ).status_code == 200
    assert (
        await client.post(f"/api/v1/workflows/instances/{second['id']}/cancel")
    ).status_code == 404


async def test_model_missing_or_invalid_never_falls_back(
    real_client, monkeypatch, tmp_path
):
    from app.services.embedding import EmbeddingService

    client, _, _ = real_client
    settings = get_settings()
    monkeypatch.setattr(settings, "EMBEDDING_MODE", "local")
    monkeypatch.setattr(settings, "LOCAL_MODEL_PATH", str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="no fallback"):
        await EmbeddingService(cache_enabled=False).embed_texts(["rollback"])


async def test_generation_failure_is_saved_as_error_not_completed(
    real_client, monkeypatch
):
    client, factory, _ = real_client
    await upload(client)
    monkeypatch.setattr(get_settings(), "GENERATION_MODE", "provider")
    monkeypatch.setattr(get_settings(), "OPENAI_API_KEY", "")
    response = await client.post(
        "/api/queries",
        json={"question": "Staging rollback release?", "retrieval_method": "keyword"},
    )
    assert response.status_code == 503
    identifier = response.json()["detail"]["query_id"]
    saved = (await client.get(f"/api/queries/{identifier}")).json()
    assert saved["outcome"] == "error" and saved["answer"] is None


async def test_sqlite_additive_migration_preserves_unknown_legacy_rows(
    tmp_path, monkeypatch
):
    from app.db.migrate import migrate
    from sqlalchemy import text

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")
    async with engine.begin() as conn:
        await conn.execute(
            text(
                (
                    "CREATE TABLE queries (id CHAR(32) PRIMARY KEY, question "
                    "TEXT NOT NULL, answer TEXT, sources JSON, retrieval_trace "
                    "JSON, refused BOOLEAN NOT NULL DEFAULT 0, confidence "
                    "FLOAT, token_usage JSON, created_at DATETIME NOT NULL "
                    "DEFAULT CURRENT_TIMESTAMP)"
                )
            )
        )
        identifier = uuid.uuid4()
        await conn.execute(
            text(
                (
                    "INSERT INTO queries(id, question, answer) VALUES (:id, "
                    "'original question', 'original answer')"
                )
            ),
            {"id": identifier.hex},
        )
    monkeypatch.setattr("app.db.migrate.async_engine", engine)
    await migrate()
    await migrate()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        row = await db.get(Query, identifier)
        assert (
            row.answer == "original answer"
            and row.owner_id is None
            and row.provenance is None
        )
    await engine.dispose()


async def test_alembic_005_bootstrap_and_later_upgrade_do_not_duplicate_columns(
    tmp_path,
):
    import os
    import subprocess
    import sys
    from pathlib import Path

    path = tmp_path / "migrated.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{path.as_posix()}",
        "OPENAI_API_KEY": "",
        "EMBEDDING_MODE": "legacy",
        "GENERATION_MODE": "legacy",
    }
    api_root = Path(__file__).parents[1]
    commands = [
        [sys.executable, "-m", "alembic", "upgrade", "005"],
        [sys.executable, "-m", "app.db.migrate"],
        [sys.executable, "-m", "alembic", "upgrade", "head"],
    ]
    from sqlalchemy import inspect, text

    legacy_id = uuid.uuid4().hex
    for index, command in enumerate(commands):
        completed = await asyncio.to_thread(
            subprocess.run,
            command,
            env=env,
            cwd=api_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        if index == 0:
            engine = create_async_engine(env["DATABASE_URL"])
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO queries(id, question, answer, refused) "
                        "VALUES (:id, 'Old 005 question', 'Old 005 answer', 0)"
                    ),
                    {"id": legacy_id},
                )
            await engine.dispose()
        elif index == 1:
            engine = create_async_engine(env["DATABASE_URL"])
            async with engine.connect() as connection:
                row = (
                    await connection.execute(
                        text(
                            "SELECT answer, owner_id, provenance "
                            "FROM queries WHERE id=:id"
                        ),
                        {"id": legacy_id},
                    )
                ).one()
                assert tuple(row) == ("Old 005 answer", None, None)
                for table, columns in {
                    "documents": ["owner_id"],
                    "queries": ["owner_id", "workspace_id", "conversation_id"],
                    "conversations": ["owner_id", "workspace_id"],
                }.items():
                    indexes = await connection.run_sync(
                        lambda conn, table=table: {
                            item["name"] for item in inspect(conn).get_indexes(table)
                        }
                    )
                    assert {f"ix_{table}_{column}" for column in columns} <= indexes
            await engine.dispose()
