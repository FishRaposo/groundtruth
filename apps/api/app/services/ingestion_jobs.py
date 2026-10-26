"""Durable jobs using the existing parser/chunker/embedding pipeline.

Publication is a single database transaction after successful parsing/embedding.
An atomic queued→processing claim prevents duplicate task delivery side effects.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import suppress
from datetime import timedelta
from hashlib import sha256
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
from app.services.document.content_profile import (
    PROFILE,
    PROFILE_KEY,
    canonical_content,
    exact_chunks,
    snapshot_chunk_metadata,
    snapshot_profile,
)
from app.services.document.source_context import (
    INPUT_KEY,
    apply_source_context,
    build_source_context,
    capture_title,
    same_title_input,
    snapshot_title_input,
    validated_snapshot_context,
)
from app.services.document_intelligence import extract_entities
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
    source_title: str | None = None,
    title_origin: str = "accepted_document_title",
) -> IngestionJob:
    if base_version is not None and base_version != document.version_number:
        raise HTTPException(409, "Published version changed; reload before updating")
    captured_metadata = await _job_context(
        db,
        document,
        kind,
        dict(metadata or {}),
        source_title,
        title_origin,
    )
    job = IngestionJob(
        document_id=document.id,
        owner_id=str(principal["id"]),
        workspace_id=document.workspace_id,
        kind=kind,
        base_version=document.version_number or 0,
        source_path=source_path,
        metadata_=captured_metadata or None,
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


async def _job_context(
    db: AsyncSession,
    document: Document,
    kind: str,
    metadata: dict[str, Any],
    title: str | None,
    origin: str,
) -> dict[str, Any]:
    # Reserved proof inputs are created here, never inherited from generic metadata.
    metadata.pop(INPUT_KEY, None)
    metadata.pop("source_context_snapshot", None)
    metadata[PROFILE_KEY] = PROFILE
    if kind in {"restore", "reindex"}:
        version = (
            int(metadata["restore_version"])
            if kind == "restore"
            else document.version_number
        )
        snapshot = await db.scalar(
            select(DocumentVersion).where(
                DocumentVersion.document_id == document.id,
                DocumentVersion.workspace_id == document.workspace_id,
                DocumentVersion.version_number == version,
            )
        )
        metadata[INPUT_KEY] = None
        metadata[PROFILE_KEY] = None
        if snapshot is not None:
            if (
                sha256(snapshot.normalized_content.encode("utf-8")).hexdigest()
                != snapshot.content_hash
            ):
                raise ValueError("Captured snapshot body hash mismatch")
            context = validated_snapshot_context(snapshot)
            metadata[PROFILE_KEY] = snapshot_profile(snapshot)
            metadata[INPUT_KEY] = snapshot_title_input(snapshot)
            metadata["source_context_snapshot"] = {
                "version_number": version,
                "body_hash": snapshot.content_hash,
                "context_hash": context["context_hash"] if context else None,
            }
        elif kind == "restore":
            raise HTTPException(404, "Document version not found")
    elif settings.SOURCE_CONTEXT_MODE == "versioned_title":
        metadata[INPUT_KEY] = capture_title(
            document.title if title is None else title, origin=origin
        )
    return metadata


async def _title_duplicate(
    db: AsyncSession,
    document: Document,
    job: IngestionJob,
    digest: str,
    captured: dict[str, Any] | None,
) -> bool:
    if captured is None or job.kind not in {"upload", "update"} or not job.base_version:
        return False
    snapshot = await db.scalar(
        select(DocumentVersion).where(
            DocumentVersion.document_id == document.id,
            DocumentVersion.workspace_id == document.workspace_id,
            DocumentVersion.version_number == job.base_version,
        )
    )
    return bool(
        snapshot
        and snapshot.content_hash == digest
        and same_title_input(snapshot, captured)
        and snapshot_profile(snapshot) == (job.metadata_ or {}).get(PROFILE_KEY)
    )


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
            captured = (job.metadata_ or {}).get(INPUT_KEY)
            if (
                captured is not None
                or (job.metadata_ or {}).get("source_context_snapshot")
            ) and doc.workspace_id != job.workspace_id:
                raise ValueError("Captured publication workspace changed")
            source_snapshot_context = None
            snapshot = None
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
                    snapshot = await db.scalar(
                        select(DocumentVersion).where(
                            DocumentVersion.document_id == doc.id,
                            DocumentVersion.workspace_id == doc.workspace_id,
                            DocumentVersion.version_number == job.base_version,
                        )
                    )
                    if snapshot is None:
                        raise ValueError("Published immutable snapshot is missing")
                    content = snapshot.normalized_content
                profile = snapshot_profile(snapshot)
                if sha256(
                    content.encode("utf-8")
                ).hexdigest() != snapshot.content_hash or (
                    PROFILE_KEY in metadata and metadata[PROFILE_KEY] != profile
                ):
                    raise ValueError("Captured snapshot body/profile changed")
                pinned = metadata.get("source_context_snapshot")
                if pinned is not None:
                    if snapshot is None:
                        raise ValueError("Captured snapshot is missing")
                    source_snapshot_context = validated_snapshot_context(snapshot)
                    expected_context_hash = (
                        source_snapshot_context["context_hash"]
                        if source_snapshot_context
                        else None
                    )
                    if (
                        pinned["version_number"] != snapshot.version_number
                        or sha256(
                            snapshot.normalized_content.encode("utf-8")
                        ).hexdigest()
                        != pinned["body_hash"]
                        or pinned["body_hash"] != snapshot.content_hash
                        or pinned["context_hash"] != expected_context_hash
                        or snapshot_title_input(snapshot) != captured
                    ):
                        raise ValueError("Captured source snapshot changed")
                    content = snapshot.normalized_content
            else:
                if not job.source_path:
                    raise ValueError("Stored upload missing")
                path = Path(job.source_path).resolve()
                if not path.is_relative_to(Path(settings.STORAGE_ROOT).resolve()):
                    raise ValueError("Stored upload outside configured root")
                parser = get_parser(doc.source_type.value)
                parsed = await parser.parse(str(path))
                content = canonical_content(parsed.content)
                profile = PROFILE
            if not content.strip():
                raise ValueError("No extractable text")
            stage = "chunk"
            job.stage = stage
            await db.commit()
            snapshot_items = []
            if job.kind in {"restore", "reindex"} and snapshot is not None:
                # Neither operation rewrites an immutable chunk manifest. Reindex
                # changes embeddings, not the content revision or its partitions.
                snapshot_items = sorted(
                    snapshot.chunks or [], key=lambda item: item["index"]
                )
                chunks = [item["content"] for item in snapshot_items]
                if any(
                    not isinstance(text, str) or not text or text not in content
                    for text in chunks
                ):
                    raise ValueError("Snapshot chunk is not a literal body passage")
            else:
                chunks = exact_chunks(content, embedding_service.chunk_content(content))
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
            digest = sha256(content.encode("utf-8")).hexdigest()
            duplicate = await _title_duplicate(db, doc, job, digest, captured)
            new_version = (
                job.base_version
                if job.kind == "reindex" or duplicate
                else job.base_version + 1
            )
            # Conditional write both serializes publication and prevents a stale
            # worker replacing newer evidence. Everything below commits once.
            published = await db.execute(
                update(Document)
                .where(
                    Document.id == doc.id,
                    Document.version_number == job.base_version,
                    Document.workspace_id == job.workspace_id,
                )
                .values(version_number=new_version)
            )
            if int(getattr(published, "rowcount", 0)) != 1:
                raise ValueError("Published version changed")
            stored = []
            if not duplicate:
                await db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
                for index, (text, vector) in enumerate(
                    zip(chunks, vectors, strict=True)
                ):
                    chunk_id = uuid.uuid4()
                    if job.kind == "reindex" and snapshot_items[index].get("id"):
                        chunk_id = uuid.UUID(snapshot_items[index]["id"])
                    chunk = Chunk(
                        id=chunk_id,
                        document_id=doc.id,
                        content=text,
                        chunk_index=snapshot_items[index]["index"]
                        if snapshot_items
                        else index,
                        embedding=vector,
                        embedding_vector=vector if len(vector) == 384 else None,
                        metadata_={
                            "embedding_signature": embedding_service.signature,
                            "document_version": new_version,
                            "char_count": len(text),
                            PROFILE_KEY: profile,
                            **(
                                snapshot_chunk_metadata(
                                    snapshot,
                                    snapshot_items[index],
                                    embedding_service.signature,
                                    job.kind,
                                )
                                if snapshot_items
                                else {
                                    "chunking_provenance": {
                                        "method": embedding_service.signature.get(
                                            "chunking"
                                        )
                                    }
                                }
                            ),
                        },
                    )
                    db.add(chunk)
                    stored.append(chunk)
                context = (
                    source_snapshot_context
                    if job.kind == "reindex"
                    else build_source_context(
                        captured,
                        document_id=doc.id,
                        workspace_id=doc.workspace_id,
                        version_number=new_version,
                        body=content,
                        chunks=[
                            {"index": chunk.chunk_index, "content": chunk.content}
                            for chunk in stored
                        ],
                    )
                )
                apply_source_context(stored, context)
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
                doc.chunk_count if duplicate else len(stored),
                DocumentStatus.READY,
            )
            index_signature = (
                (stored[0].metadata_ or {})["embedding_signature"]
                if stored
                else (doc.metadata_ or {}).get("embedding_signature")
            )
            doc.metadata_ = {
                **(doc.metadata_ or {}),
                "normalized_content": content,
                "entities": extract_entities(content),
                "embedding_signature": index_signature,
                PROFILE_KEY: profile,
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
                PROFILE_KEY: profile,
                "embedding_signature": index_signature,
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
