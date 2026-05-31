from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.keys import router as keys_router
from app.api.metrics import router as metrics_router
from app.api.queries import router as queries_router
from app.api.v1.documents import router as doc_processing_router
from app.api.v1.workflows import router as workflows_router
from app.config import get_settings
from app.core.logging import setup_logging
from app.core.metrics import get_metrics
from app.db.session import init_db
from app.middleware.metrics import MetricsMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware

settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None, None]:
    """Initialize database tables and structured logging on startup."""
    setup_logging(log_format=settings.LOG_FORMAT, log_level=settings.LOG_LEVEL)
    await init_db()
    yield


app = FastAPI(
    title="GroundTruth",
    description="A production-minded RAG assistant template",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(RateLimitMiddleware, default_rate_limit=60)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(MetricsMiddleware)
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
app.include_router(queries_router, prefix="/api")
app.include_router(doc_processing_router, prefix="/api/v1")
app.include_router(workflows_router, prefix="/api/v1")
app.include_router(metrics_router)


@app.get("/")
async def root() -> dict[str, str]:
    """Return basic API information."""
    return {
        "name": "GroundTruth API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/metrics")
async def metrics_endpoint() -> Response:
    """Expose Prometheus metrics in text exposition format.

    Returns:
        A plain-text response containing all collected metrics.
    """
    data = get_metrics()
    return Response(content=data, media_type="text/plain; version=0.0.4; charset=utf-8")
    return Response(content=data, media_type="text/plain; version=0.0.4; charset=utf-8")
