"""API tests for the cost-summary metrics endpoint."""

import pytest
import pytest_asyncio
from app.main import app
from app.services.cost_tracking import cost_tracker
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def _reset_tracker() -> None:
    cost_tracker.reset()
    yield
    cost_tracker.reset()


@pytest.mark.asyncio
async def test_cost_summary_empty(client: AsyncClient) -> None:
    response = await client.get("/api/metrics/cost")
    assert response.status_code == 200
    data = response.json()
    assert data["workspaces"] == {}
    assert data["total"]["total_requests"] == 0


@pytest.mark.asyncio
async def test_cost_summary_after_record(client: AsyncClient) -> None:
    cost_tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=100,
        completion_tokens=50,
        latency_ms=120.0,
        workspace="ws1",
    )
    response = await client.get("/api/metrics/cost")
    assert response.status_code == 200
    data = response.json()
    assert "ws1" in data["workspaces"]
    assert data["total"]["total_requests"] == 1
    assert data["total"]["total_tokens"] == 150


@pytest.mark.asyncio
async def test_cost_summary_filtered_by_workspace(client: AsyncClient) -> None:
    cost_tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=10,
        completion_tokens=5,
        latency_ms=10.0,
        workspace="ws1",
    )
    cost_tracker.record(
        model="gpt-4o-mini",
        prompt_tokens=20,
        completion_tokens=10,
        latency_ms=10.0,
        workspace="ws2",
    )
    response = await client.get("/api/metrics/cost?workspace=ws1")
    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] == 1
    assert data["total_tokens"] == 15
