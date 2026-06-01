"""Prometheus metrics for GroundTruth RAG assistant."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram, generate_latest, REGISTRY


def _get_or_create_metric(metric_cls, name, description, labels=None):
    """Get existing metric or create new one, handling duplicate registration."""
    try:
        if labels:
            return metric_cls(name, description, labels)
        return metric_cls(name, description)
    except ValueError:
        # Metric already registered, retrieve it
        return REGISTRY._names_to_collectors[name]


REQUEST_COUNT = _get_or_create_metric(
    Counter,
    "groundtruth_requests_total",
    "Total requests",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = _get_or_create_metric(
    Histogram,
    "groundtruth_request_duration_seconds",
    "Request latency",
    ["method", "endpoint"],
)

DOCUMENTS_PROCESSED = _get_or_create_metric(
    Counter,
    "groundtruth_documents_processed_total",
    "Documents processed",
    ["status"],
)

QUERIES_EXECUTED = _get_or_create_metric(
    Counter,
    "groundtruth_queries_executed_total",
    "Queries executed",
    ["refused"],
)

CHUNKS_CREATED = _get_or_create_metric(
    Counter,
    "groundtruth_chunks_created_total",
    "Chunks created",
)

EMBEDDINGS_GENERATED = _get_or_create_metric(
    Counter,
    "groundtruth_embeddings_generated_total",
    "Embeddings generated",
)

ACTIVE_DOCUMENTS = _get_or_create_metric(
    Gauge,
    "groundtruth_active_documents",
    "Currently active documents",
)

RETRIEVAL_LATENCY = _get_or_create_metric(
    Histogram,
    "groundtruth_retrieval_duration_seconds",
    "Retrieval stage latency",
    ["stage"],
)


def get_metrics() -> bytes:
    """Return all registered Prometheus metrics in text exposition format.

    Returns:
        Bytes containing the Prometheus text-format metrics payload.
    """
    return generate_latest()


def track_request(method: str, endpoint: str, status_code: int, duration: float) -> None:
    """Record a single HTTP request in both counter and histogram metrics.

    Args:
        method: HTTP method (GET, POST, etc.).
        endpoint: URL path template (without path parameters).
        status_code: HTTP response status code.
        duration: Request duration in seconds.
    """
    REQUEST_COUNT.labels(
        method=method, endpoint=endpoint, status_code=str(status_code)
    ).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=endpoint).observe(duration)


def track_document(status: str) -> None:
    """Increment the document processing counter for a given outcome.

    Args:
        status: Processing result such as "success" or "error".
    """
    DOCUMENTS_PROCESSED.labels(status=status).inc()


def track_query(refused: bool) -> None:
    """Increment the query execution counter.

    Args:
        refused: Whether the query was refused by the guardrails.
    """
    QUERIES_EXECUTED.labels(refused=str(refused)).inc()


def track_retrieval(stage: str, duration: float) -> None:
    """Observe retrieval latency for a specific pipeline stage.

    Args:
        stage: Pipeline stage name (e.g. "vector", "keyword", "rerank").
        duration: Stage duration in seconds.
    """
    RETRIEVAL_LATENCY.labels(stage=stage).observe(duration)
