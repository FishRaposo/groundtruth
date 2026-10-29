"""Health check endpoints for load balancers, readiness, and liveness probes."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.evidence_policy import resolve_evidence_policy
from app.models.chunk import Chunk
from app.models.document import Document


def runtime_metadata() -> dict[str, Any]:
    from app.services.answer_reader import reader_service
    from app.services.answer_support import support_service
    from app.services.embedding import embedding_service
    from app.services.request_parser import metadata as parser_metadata

    settings = get_settings()
    reader = reader_service.metadata(config=settings)
    if (
        settings.ANSWER_SELECTION_MODE == "reader"
        and settings.ANSWER_SUPPORT_MODE == "local_nli"
    ):
        reader = {
            **reader,
            "reader_contract": reader["contract"],
            "contract": resolve_evidence_policy(settings).requirement_contract,
        }
    return {
        "answer_selection": reader,
        "evidence_support": support_service.metadata(settings),
        "request_parser": parser_metadata(settings),
        "evidence_profile": {
            **resolve_evidence_policy(settings).record(),
            "qualification": "Readiness does not establish answer quality.",
        },
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


async def _support_readiness() -> dict[str, str]:
    settings = get_settings()
    if settings.ANSWER_SUPPORT_MODE != "local_nli":
        return {}
    try:
        from app.services.answer_support import support_service

        await support_service.assess([], settings)
        return {"evidence_support": "ok"}
    except Exception:
        return {"evidence_support": "error"}


async def _request_parser_readiness() -> dict[str, str]:
    settings = get_settings()
    if settings.REQUEST_PARSER_MODE != "local_dependency":
        return {}
    try:
        from app.services.request_parser import capture_async

        await capture_async("a", settings)
        return {"request_parser": "ok"}
    except Exception:
        return {"request_parser": "error"}


def _readiness_response(payload: dict[str, Any], response: Response) -> dict[str, Any]:
    actions = []
    if payload["checks"].get("request_parser") == "error":
        actions.append(
            "Install groundtruth[request-parser]; run "
            "python -m app.request_parser_setup "
            "with an explicit model directory and set REQUEST_PARSER_MODEL_PATH."
        )
    if payload["checks"].get("reader") == "error":
        actions.append(
            "Install groundtruth[reader]; download the pinned reader explicitly "
            "and check READER_MODEL_PATH and READER_MODEL_REVISION."
        )
    if payload["checks"].get("evidence_support") == "error":
        actions.append(
            "Install groundtruth[support]; run python -m app.support_setup "
            "--directory <model-directory>; set SUPPORT_MODEL_PATH "
            "and the pinned SUPPORT_MODEL_REVISION."
        )
    if any(
        payload["checks"].get(key) == "error"
        for key in (
            "database",
            "embeddings",
            "reader",
            "evidence_support",
            "request_parser",
        )
    ):
        response.status_code = 503
    if actions:
        payload["action"] = " ".join(actions)
    return payload


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
async def readiness_check(
    response: Response, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
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

            await reader_service.select(
                "What is the readiness probe?", [], config=get_settings()
            )
            checks["reader"] = "ok"
        except Exception:
            checks["reader"] = "error"

    checks.update(await _support_readiness())
    checks.update(await _request_parser_readiness())

    # In offline mode, only database + embeddings matter
    if checks.get("pgvector") == "unavailable":
        all_ok = (
            checks.get("database") == "ok"
            and checks.get("embeddings") == "ok"
            and checks.get("reader", "ok") == "ok"
            and checks.get("evidence_support", "ok") == "ok"
            and checks.get("request_parser", "ok") == "ok"
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

    return _readiness_response(
        {
            "status": "ready" if all_ok else "degraded",
            "checks": checks,
            "document_count": document_count,
            "chunk_count": chunk_count,
            "runtime": runtime_metadata(),
        },
        response,
    )


@router.get("/health/live")
async def liveness_check() -> dict[str, str]:
    """Return liveness status without any database dependency.

    Returns:
        A minimal dictionary confirming the process is alive.
    """
    return {"status": "alive"}
