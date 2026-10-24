"""Health check endpoints for load balancers, readiness, and liveness probes."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.models.chunk import Chunk
from app.models.document import Document


def runtime_metadata() -> dict[str, Any]:
    from app.services.answer_reader import reader_service
    from app.services.embedding import embedding_service

    settings = get_settings()
    return {
        "answer_selection": reader_service.metadata(),
        "embedding": embedding_service.signature,
        "generation_mode": settings.GENERATION_MODE,
        "ingestion_mode": settings.INGESTION_MODE,
        "persistence": "sqlite"
        if settings.DATABASE_URL.startswith("sqlite")
        else "postgresql",
        "authentication": "api-key"
        if settings.AUTH_ENABLED
        else "single-user-development",
        "pricing_provenance": "unknown; local extraction uses no provider",
        "scope": "local application; hosted multi-user authentication unverified",
    }


router = APIRouter(tags=["health"])

_START_TIME: float = time.monotonic()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Return basic health status for load balancer probes.

    Returns:
        A dictionary with status, version, and uptime information.
    """
    uptime = time.monotonic() - _START_TIME
    return {
        "status": "healthy",
        "version": "0.1.0",
        "uptime_seconds": round(uptime, 2),
        "runtime": runtime_metadata(),
    }


@router.get("/health/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Return readiness status including database, pgvector, and embedding checks.

    Args:
        db: Async database session injected by FastAPI.

    Returns:
        A dictionary with readiness status, individual check results, and counts.
    """
    checks: dict[str, str] = {}
    document_count: int = 0
    chunk_count: int = 0

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    try:
        if db.get_bind().dialect.name != "postgresql":
            checks["pgvector"] = "unavailable"
        else:
            result = await db.execute(
                text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
            )
            checks["pgvector"] = "ok" if result.scalar() else "not_installed"
    except Exception:
        checks["pgvector"] = "unavailable"  # Expected for SQLite/offline mode

    try:
        from app.services.embedding import embedding_service

        await embedding_service.embed_texts(["health check probe"])
        checks["embeddings"] = "ok"
    except Exception:
        checks["embeddings"] = "error"

    if get_settings().ANSWER_SELECTION_MODE == "reader":
        try:
            from app.services.answer_reader import reader_service

            await reader_service.select("What is the readiness probe?", [])
            checks["reader"] = "ok"
        except Exception:
            checks["reader"] = "error"

    # In offline mode, only database + embeddings matter
    if checks.get("pgvector") == "unavailable":
        all_ok = (
            checks.get("database") == "ok"
            and checks.get("embeddings") == "ok"
            and checks.get("reader", "ok") == "ok"
        )
    else:
        all_ok = all(v == "ok" for v in checks.values())

    try:
        doc_result = await db.execute(select(func.count()).select_from(Document))
        document_count = doc_result.scalar() or 0
    except Exception:
        pass

    try:
        chunk_result = await db.execute(select(func.count()).select_from(Chunk))
        chunk_count = chunk_result.scalar() or 0
    except Exception:
        pass

    return {
        "status": "ready" if all_ok else "degraded",
        "checks": checks,
        "document_count": document_count,
        "chunk_count": chunk_count,
        "runtime": runtime_metadata(),
    }


@router.get("/health/live")
async def liveness_check() -> dict[str, str]:
    """Return liveness status without any database dependency.

    Returns:
        A minimal dictionary confirming the process is alive.
    """
    return {"status": "alive"}
