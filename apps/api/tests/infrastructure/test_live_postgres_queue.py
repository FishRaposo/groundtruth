"""Actual PostgreSQL/pgvector + Redis + worker acceptance; never a mock gate.

Opt in only against disposable dedicated services. Missing/unusable services
fail when enabled. This host's WSL-free milestone records these tests as skipped.
"""

import asyncio
import hashlib
import os
import socket
import subprocess
import sys
import uuid

import httpx
import pytest
from sqlalchemy import select, text

pytestmark = pytest.mark.skipif(
    os.environ.get("GROUNDTRUTH_INFRASTRUCTURE_TESTS") != "1",
    reason="Dedicated PostgreSQL/Redis services explicitly required",
)


def available_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


async def test_actual_http_worker_postgres_scope_and_indexes(tmp_path):
    from app.config import get_settings
    from app.db.migrate import migrate
    from app.db.session import AsyncSessionLocal
    from app.models.api_key import ApiKey
    from app.models.chunk import Chunk
    from app.models.document import DocumentVersion
    from app.models.ingestion import IngestionJob

    settings = get_settings()
    assert settings.DATABASE_URL.startswith("postgresql"), (
        "Infrastructure flag requires real PostgreSQL"
    )
    assert settings.INGESTION_MODE == "queued" and settings.EMBEDDING_DIMENSIONS == 384
    await migrate()
    raw = f"infrastructure-only-{uuid.uuid4()}"
    workspace = f"test-{uuid.uuid4()}"
    async with AsyncSessionLocal() as db:
        db.add(
            ApiKey(
                name="Infrastructure operator",
                key_hash=hashlib.sha256(raw.encode()).hexdigest(),
                key_prefix="infra",
                is_admin=True,
                metadata_={"workspace_id": workspace},
            )
        )
        await db.commit()
        extension = await db.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname='vector'")
        )
        assert extension
        indexes = list(
            (
                await db.execute(
                    text("SELECT indexname FROM pg_indexes WHERE tablename='chunks'")
                )
            ).scalars()
        )
        assert (
            "ix_chunks_embedding_vector_hnsw" in indexes
            and "ix_chunks_content_fts" in indexes
        )
    port = available_port()
    env = {
        **os.environ,
        "AUTH_ENABLED": "true",
        "RATE_LIMIT_ENABLED": "false",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "STORAGE_ROOT": str(tmp_path / "uploads"),
        "CORS_ORIGINS": f"http://127.0.0.1:{port}",
    }
    api_log = (tmp_path / "api.log").open("w", encoding="utf-8")
    worker_log = (tmp_path / "worker.log").open("w", encoding="utf-8")
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=api_log,
        stderr=subprocess.STDOUT,
    )
    worker = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "celery",
            "-A",
            "app.core.celery.celery_app",
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "--queues=documents",
            "--loglevel=WARNING",
        ],
        env=env,
        stdout=worker_log,
        stderr=subprocess.STDOUT,
    )
    try:
        async with httpx.AsyncClient(
            base_url=f"http://127.0.0.1:{port}", headers={"X-API-Key": raw}, timeout=30
        ) as client:
            for _ in range(120):
                assert api.poll() is None and worker.poll() is None, (
                    "Real API/worker terminated"
                )
                try:
                    if (await client.get("/api/health")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.25)
            else:
                pytest.fail("Real API did not become ready")
            uploaded = await client.post(
                "/api/documents/upload",
                files={
                    "files": (
                        "runbook.txt",
                        "Staging rollback pauses deployment queue. "
                        "Run staging smoke tests before traffic.",
                        "text/plain",
                    )
                },
            )
            assert uploaded.status_code == 200, uploaded.text
            payload = uploaded.json()
            identifier = payload["documents"][0]["id"]
            job_id = payload["ingestions"][0]["id"]
            for _ in range(120):
                job = (await client.get(f"/api/ingestions/{job_id}")).json()
                if job["status"] in {"completed", "error", "interrupted"}:
                    break
                await asyncio.sleep(0.25)
            assert job["status"] == "completed", job
            for method in ["keyword", "vector", "hybrid", "reranked"]:
                answer = await client.post(
                    "/api/queries",
                    json={
                        "question": "Staging rollback deployment queue?",
                        "document_ids": [identifier],
                        "retrieval_method": method,
                    },
                )
                assert answer.status_code == 200, answer.text
                assert (
                    answer.json()["retrieval_trace"]["provenance"]["index"]
                    == "postgresql-pgvector-fts-scoped"
                )
                assert all(
                    item["document_id"] == identifier
                    for item in answer.json()["retrieval_trace"]["scores"]
                )
            from app.core.celery import celery_app

            celery_app.send_task(
                "app.tasks.documents.process_ingestion_task", args=[job_id]
            )
            await asyncio.sleep(1)
            async with AsyncSessionLocal() as db:
                chunks = list(
                    (
                        await db.scalars(
                            select(Chunk).where(
                                Chunk.document_id == uuid.UUID(identifier)
                            )
                        )
                    ).all()
                )
                snapshots = list(
                    (
                        await db.scalars(
                            select(DocumentVersion).where(
                                DocumentVersion.document_id == uuid.UUID(identifier)
                            )
                        )
                    ).all()
                )
                assert chunks and all(
                    len(chunk.embedding_vector) == 384 for chunk in chunks
                )
                assert len(snapshots) == 1
                assert (
                    await db.get(IngestionJob, uuid.UUID(job_id))
                ).status == "completed"
    finally:
        for process in (api, worker):
            process.terminate()
        for process in (api, worker):
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
        api_log.close()
        worker_log.close()
