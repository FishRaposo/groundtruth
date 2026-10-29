from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.gzip import DEFAULT_EXCLUDED_CONTENT_TYPES, GZipMiddleware
from starlette.types import ExceptionHandler

from app import __version__
from app.api.conversations import router as conversations_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.ingestions import router as ingestions_router
from app.api.keys import router as keys_router
from app.api.metrics import router as metrics_router
from app.api.queries import router as queries_router
from app.api.v1.admin import router as admin_router
from app.api.v1.documents import router as doc_processing_router
from app.api.v1.workflows import router as workflows_router
from app.config import get_settings
from app.core.logging import setup_logging
from app.db.evidence_json import EvidenceArchiveError
from app.db.session import init_db
from app.internal.vendor_core.errors import (
    BaseApplicationError,
    application_error_handler,
)
from app.middleware.metrics import MetricsMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware

settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize database tables and structured logging on startup."""
    setup_logging(log_format=settings.LOG_FORMAT, log_level=settings.LOG_LEVEL)
    await init_db()
    if settings.connected:
        from app.services.ingestion_jobs import interrupt_jobs

        await interrupt_jobs()
    yield


app = FastAPI(
    title="GroundTruth",
    description="A production-minded RAG assistant template",
    version=__version__,
    lifespan=lifespan,
)

app.add_exception_handler(
    BaseApplicationError,
    cast(ExceptionHandler, application_error_handler),
)


@app.exception_handler(EvidenceArchiveError)
async def evidence_archive_error_handler(
    request: Request, exc: EvidenceArchiveError
) -> JSONResponse:
    """An owned corrupt archive cannot become legacy/unknown answer success."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "code": "evidence_integrity_failed",
                "message": (
                    "Recorded evidence is unavailable; answer and source "
                    "content are withheld."
                ),
            }
        },
    )


app.add_middleware(RateLimitMiddleware, default_rate_limit=60)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(
    GZipMiddleware,
    compresslevel=1,
    exclude_content_types=(*DEFAULT_EXCLUDED_CONTENT_TYPES, "text/event-stream"),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api")
app.include_router(keys_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")
app.include_router(ingestions_router, prefix="/api")
app.include_router(queries_router, prefix="/api")
app.include_router(doc_processing_router, prefix="/api/v1")
app.include_router(admin_router, prefix="/api/v1")
app.include_router(workflows_router, prefix="/api/v1")
app.include_router(metrics_router)


@app.get("/")
async def root() -> dict[str, str]:
    """Return basic API information."""
    return {
        "name": "GroundTruth API",
        "version": __version__,
        "docs": "/docs",
    }
