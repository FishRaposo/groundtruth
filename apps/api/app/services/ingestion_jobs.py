"""Durable jobs using the existing parser/chunker/embedding pipeline.

Publication is a single database transaction after successful parsing/embedding.
An atomic queued→processing claim prevents duplicate task delivery side effects.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import suppress
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.chunk import Chunk
from app.models.document import Document, DocumentStatus, DocumentVersion
from app.models.ingestion import IngestionJob
from app.parsers import get_parser
from app.services.access_control.scope import Principal
from app.services.audit import audit_trail
from app.services.document_intelligence import (
    content_hash,
    deduplicate_chunks,
    extract_entities,
    normalize_content,
)
from app.services.embedding import embedding_service
from app.utils.time import utc_now

settings = get_settings()


async def create_job(
    db: AsyncSession,
    document: Document,
    principal: Principal,
    *,
    source_path: str | None,
    kind: str = "upload",
    base_version: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> IngestionJob:
    if base_version is not None and base_version != document.version_number:
        raise HTTPException(409, "Published version changed; reload before updating")
    job = IngestionJob(
        document_id=document.id,
        owner_id=str(principal["id"]),
        workspace_id=document.workspace_id,
        kind=kind,
        base_version=document.version_number or 0,
        source_path=source_path,
        metadata_=metadata,
        active_slot=str(document.id),
    )
    db.add(job)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            409, "This document already has an active ingestion"
        ) from exc
    return job


async def dispatch_job(job_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(IngestionJob, job_id)
        if job is None or job.status != "queued":
            return
        expected_attempt = job.attempt
    if settings.INGESTION_MODE == "inline":
        from app.services.ingestion import ingestion_service

        await ingestion_service.process_ingestion_job(job_id)
    elif settings.INGESTION_MODE == "queued":
        try:
            # Dispatch through the configured app: a bare shared_task.delay()
            # binds to Celery's implicit default app, which has no task_routes
            # and would publish to the unconsumed "celery" queue.
            from app.core.celery import celery_app

            celery_app.send_task(
                "app.tasks.documents.process_ingestion_task", args=[str(job_id)]
            )
        except Exception:
            await mark_failed(
                job_id,
                "queue",
                (
                    "The ingestion queue is unavailable. Retry explicitly when "
                    "the worker/broker is available."
                ),
                attempt=expected_attempt,
            )
    else:
        await mark_failed(
            job_id,
            "configuration",
            "Unknown INGESTION_MODE; use inline or queued.",
            attempt=expected_attempt,
        )


async def mark_failed(
    identifier: uuid.UUID,
    stage: str,
    message: str,
    *,
    claim_token: str | None = None,
    attempt: int | None = None,
) -> None:
    async with AsyncSessionLocal() as db:
        job = await db.get(IngestionJob, identifier)
        if not job or attempt is None:
            return
        predicates = [IngestionJob.id == identifier, IngestionJob.attempt == attempt]
        if claim_token:
            predicates.extend(
                [
                    IngestionJob.status == "processing",
                    IngestionJob.claim_token == claim_token,
                    IngestionJob.attempt == attempt,
                ]
            )
        else:
            predicates.append(IngestionJob.status == "queued")
        history = [
            *(job.metadata_ or {}).get("attempt_history", []),
            {
                "attempt": job.attempt,
                "status": "error",
                "stage": stage,
                "error": message,
                "finished_at": utc_now().isoformat(),
            },
        ]
        updated = await db.execute(
            update(IngestionJob)
            .where(*predicates)
            .values(
                status="error",
                stage=stage,
                error=message,
                active_slot=None,
                lease_expires_at=None,
                metadata_={**(job.metadata_ or {}), "attempt_history": history},
            )
        )
        if int(getattr(updated, "rowcount", 0)) != 1:
            await db.rollback()
            return
        doc = await db.get(Document, job.document_id)
        if doc and not doc.version_number:
            doc.status = DocumentStatus.ERROR
        await db.commit()


async def process_job(identifier: uuid.UUID) -> None:  # noqa: C901 - guarded publication
    token = str(uuid.uuid4())
    async with AsyncSessionLocal() as db:
        claimed = await db.execute(
            update(IngestionJob)
            .where(IngestionJob.id == identifier, IngestionJob.status == "queued")
            .values(
                status="processing",
                stage="parse",
                claim_token=token,
                lease_expires_at=utc_now() + timedelta(seconds=30),
            )
        )
        await db.commit()
        if int(getattr(claimed, "rowcount", 0)) != 1:
            return
        job = await db.get(IngestionJob, identifier)
        assert job is not None
        claimed_attempt = job.attempt
        doc = await db.get(Document, job.document_id)
        if doc is None:
            return
        stage = "parse"
        heartbeat = asyncio.create_task(heartbeat_lease(identifier, token))
        try:
            if job.kind in {"restore", "reindex"}:
                metadata = job.metadata_ or {}
                if job.kind == "restore":
                    snapshot = await db.scalar(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == doc.id,
                            DocumentVersion.version_number
                            == int(metadata["restore_version"]),
                            DocumentVersion.workspace_id == doc.workspace_id,
                        )
                    )
                    if snapshot is None:
                        raise ValueError("Snapshot not found")
                    content = snapshot.normalized_content
                else:
                    content = str((doc.metadata_ or {}).get("normalized_content", ""))
            else:
                if not job.source_path:
                    raise ValueError("Stored upload missing")
                path = Path(job.source_path).resolve()
                if not path.is_relative_to(Path(settings.STORAGE_ROOT).resolve()):
                    raise ValueError("Stored upload outside configured root")
                parser = get_parser(doc.source_type.value)
                parsed = await parser.parse(str(path))
                content = normalize_content(parsed.content)
            content = normalize_content(content)
            if not content.strip():
                raise ValueError("No extractable text")
            stage = "chunk"
            job.stage = stage
            await db.commit()
            chunks = deduplicate_chunks(embedding_service.chunk_content(content))
            if not chunks:
                raise ValueError("No chunks")
            stage = "embed"
            job.stage = stage
            await db.commit()
            vectors = await embedding_service.embed_texts(chunks)
            if len(vectors) != len(chunks) or any(
                len(vector) != embedding_service.signature["dimension"]
                for vector in vectors
            ):
                raise ValueError("Embedding output shape mismatch")
            stage = "publish"
            valid_claim = await db.execute(
                update(IngestionJob)
                .where(
                    IngestionJob.id == identifier,
                    IngestionJob.claim_token == token,
                    IngestionJob.status == "processing",
                    IngestionJob.attempt == claimed_attempt,
                    IngestionJob.lease_expires_at > utc_now(),
                    IngestionJob.active_slot == str(doc.id),
                )
                .values(stage="publish")
            )
            if int(getattr(valid_claim, "rowcount", 0)) != 1:
                await db.rollback()
                return
            new_version = (
                job.base_version if job.kind == "reindex" else job.base_version + 1
            )
            # Conditional write both serializes publication and prevents a stale
            # worker replacing newer evidence. Everything below commits once.
            published = await db.execute(
                update(Document)
                .where(
                    Document.id == doc.id, Document.version_number == job.base_version
                )
                .values(version_number=new_version)
            )
            if int(getattr(published, "rowcount", 0)) != 1:
                raise ValueError("Published version changed")
            digest = content_hash(content)
            await db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
            stored = []
            for index, (text, vector) in enumerate(zip(chunks, vectors, strict=True)):
                chunk = Chunk(
                    id=uuid.uuid4(),
                    document_id=doc.id,
                    content=text,
                    chunk_index=index,
                    embedding=vector,
                    embedding_vector=vector if len(vector) == 384 else None,
                    metadata_={
                        "embedding_signature": embedding_service.signature,
                        "document_version": new_version,
                        "char_count": len(text),
                    },
                )
                db.add(chunk)
                stored.append(chunk)
            await db.flush()
            if job.kind != "reindex":
                db.add(
                    DocumentVersion(
                        document_id=doc.id,
                        workspace_id=doc.workspace_id,
                        version_number=new_version,
                        content_hash=digest,
                        normalized_content=content,
                        chunks=[
                            {
                                "id": str(chunk.id),
                                "content": chunk.content,
                                "index": chunk.chunk_index,
                                "metadata": chunk.metadata_,
                            }
                            for chunk in stored
                        ],
                        change_summary=f"{job.kind} publication",
                    )
                )
            doc.version_number, doc.content_hash, doc.chunk_count, doc.status = (
                new_version,
                digest,
                len(stored),
                DocumentStatus.READY,
            )
            doc.metadata_ = {
                **(doc.metadata_ or {}),
                "normalized_content": content,
                "entities": extract_entities(content),
                "embedding_signature": embedding_service.signature,
            }
            job.status, job.stage, job.version_number, job.error, job.active_slot = (
                "completed",
                "published",
                new_version,
                None,
                None,
            )
            job.metadata_ = {
                **(job.metadata_ or {}),
                "attempt_history": [
                    *(job.metadata_ or {}).get("attempt_history", []),
                    {
                        "attempt": claimed_attempt,
                        "status": "completed",
                        "stage": "published",
                        "error": None,
                        "finished_at": utc_now().isoformat(),
                    },
                ],
            }
            job.lease_expires_at = None
            await audit_trail.record(
                actor_id=job.owner_id,
                action=job.kind,
                resource_type="document",
                resource_id=str(doc.id),
                workspace_id=doc.workspace_id,
                metadata={"job_id": str(job.id), "version": new_version},
                db=db,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            safe_reason = {
                "parse": "The file could not be parsed into usable text.",
                "chunk": "The content could not be divided into valid chunks.",
                "embed": (
                    "Configured embeddings are unavailable or incompatible. "
                    "Check runtime readiness."
                ),
                "publish": (
                    "Atomic publication failed or the published version changed."
                ),
            }[stage]
            await mark_failed(
                identifier,
                stage,
                safe_reason,
                claim_token=token,
                attempt=claimed_attempt,
            )
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat


async def heartbeat_lease(identifier: uuid.UUID, token: str) -> None:
    while True:
        await asyncio.sleep(5)
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    update(IngestionJob)
                    .where(
                        IngestionJob.id == identifier,
                        IngestionJob.claim_token == token,
                        IngestionJob.status == "processing",
                    )
                    .values(lease_expires_at=utc_now() + timedelta(seconds=30))
                )
                await db.commit()
        except Exception:
            return


async def interrupt_jobs() -> None:
    async with AsyncSessionLocal() as db:
        now = utc_now()
        expired = list(
            (
                await db.scalars(
                    select(IngestionJob).where(
                        IngestionJob.status == "processing",
                        IngestionJob.lease_expires_at < now,
                    )
                )
            ).all()
        )
        for job in expired:
            message = (
                "The worker lease expired before confirmed publication. "
                "Retry explicitly; no automatic dispatch occurred."
            )
            history = [
                *(job.metadata_ or {}).get("attempt_history", []),
                {
                    "attempt": job.attempt,
                    "status": "interrupted",
                    "stage": "interrupted",
                    "error": message,
                    "finished_at": now.isoformat(),
                },
            ]
            await db.execute(
                update(IngestionJob)
                .where(
                    IngestionJob.id == job.id,
                    IngestionJob.status == "processing",
                    IngestionJob.claim_token == job.claim_token,
                    IngestionJob.attempt == job.attempt,
                    IngestionJob.lease_expires_at < now,
                )
                .values(
                    status="interrupted",
                    stage="interrupted",
                    active_slot=None,
                    error=message,
                    metadata_={**(job.metadata_ or {}), "attempt_history": history},
                )
            )
        await db.commit()
