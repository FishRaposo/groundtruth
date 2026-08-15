"""Request/workspace context propagation contracts."""

from __future__ import annotations

from app.internal.context import bind_request_context, get_request_context
from app.middleware.request_logging import RequestLoggingMiddleware
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def test_request_context_is_bound_and_reset() -> None:
    assert get_request_context().request_id is None
    with bind_request_context(
        request_id="req-1", workspace_id="ws-1", api_key_id="key-1"
    ):
        context = get_request_context()
        assert context.request_id == "req-1"
        assert context.workspace_id == "ws-1"
        assert context.api_key_id == "key-1"
    assert get_request_context().request_id is None
    assert get_request_context().workspace_id == "default"


async def test_request_logger_propagates_workspace_and_request_id() -> None:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/context")
    async def context_endpoint() -> dict[str, str | None]:
        context = get_request_context()
        return {
            "request_id": context.request_id,
            "workspace_id": context.workspace_id,
        }

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/context",
            headers={"X-Correlation-ID": "req-2", "X-Workspace-ID": "ws-2"},
        )
    assert response.json() == {"request_id": "req-2", "workspace_id": "ws-2"}
    assert response.headers["X-Correlation-ID"] == "req-2"
    assert response.headers["X-Workspace-ID"] == "ws-2"
