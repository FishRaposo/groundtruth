"""Permission-checked inspection and explicit retry of durable ingestions."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.ingestion import IngestionJob
from app.services.access_control.scope import require_document
from app.services.ingestion_jobs import dispatch_job

router = APIRouter(tags=["ingestions"])


@router.get("/ingestions/{identifier}")
async def get_ingestion(
    identifier: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services.ingestion_jobs import interrupt_jobs

    await interrupt_jobs()
    job = await db.get(IngestionJob, identifier, populate_existing=True)
    if job is None:
        raise HTTPException(404, "Ingestion not found")
    await require_document(db, job.document_id, user)
    return job.to_dict()


@router.post("/ingestions/{identifier}/retry")
async def retry_ingestion(
    identifier: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    job = await db.get(IngestionJob, identifier)
    if job is None:
        raise HTTPException(404, "Ingestion not found")
    doc = await require_document(db, job.document_id, user, write=True)
    if job.status not in {"error", "interrupted"}:
        raise HTTPException(409, "Only failed or interrupted ingestion may be retried")
    if job.base_version != doc.version_number:
        raise HTTPException(
            409, "Published version changed; create a new update instead"
        )
    try:
        result = await db.execute(
            update(IngestionJob)
            .where(
                IngestionJob.id == identifier,
                IngestionJob.status.in_(["error", "interrupted"]),
            )
            .values(
                status="queued",
                stage="queued",
                error=None,
                claim_token=None,
                lease_expires_at=None,
                active_slot=str(doc.id),
                attempt=IngestionJob.attempt + 1,
            )
        )
        if int(getattr(result, "rowcount", 0)) != 1:
            raise HTTPException(409, "Ingestion was already retried")
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "Another ingestion is active") from exc
    await dispatch_job(identifier)
    await db.refresh(job)
    return job.to_dict()
