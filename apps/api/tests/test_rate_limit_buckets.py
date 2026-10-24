"""Deterministic workspace/API-key rate-limit bucket contracts."""

import hashlib

import pytest
from app.config import get_settings
from app.db.session import Base, get_db
from app.main import app
from app.middleware.rate_limit import RateLimitBuckets
from app.models.api_key import ApiKey
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def test_rate_limit_buckets_isolate_workspaces_and_api_keys() -> None:
    buckets = RateLimitBuckets(window_seconds=60)
    assert buckets.check("ws-a", "key-a", limit=1, now=0).allowed is True
    denied = buckets.check("ws-a", "key-a", limit=1, now=1)
    assert denied.allowed is False
    assert denied.retry_after == 59
    assert buckets.check("ws-b", "key-a", limit=1, now=1).allowed is True
    assert buckets.check("ws-a", "key-b", limit=1, now=1).allowed is True


def test_rate_limit_bucket_resets_at_fixed_window_boundary() -> None:
    buckets = RateLimitBuckets(window_seconds=60)
    buckets.check("ws", "key", limit=1, now=59.9)
    decision = buckets.check("ws", "key", limit=1, now=60.0)
    assert decision.allowed is True
    assert decision.remaining == 0
    assert decision.reset_after == 60


@pytest.fixture
async def limited_client(tmp_path, monkeypatch):
    settings = get_settings()
    for key, value in {
        "EMBEDDING_MODE": "deterministic",
        "GENERATION_MODE": "extractive",
        "INGESTION_MODE": "inline",
        "AUTH_ENABLED": True,
        "RATE_LIMIT_ENABLED": True,
        "STORAGE_ROOT": str(tmp_path / "uploads"),
    }.items():
        monkeypatch.setattr(settings, key, value)
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.middleware.rate_limit.AsyncSessionLocal", factory)

    async def get_session():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = get_session
    async with factory() as db:
        db.add(
            ApiKey(
                name="limited",
                key_hash=hashlib.sha256("limited".encode()).hexdigest(),
                key_prefix="limited",
                rate_limit=3,
                metadata_={"workspace_id": "ops-a"},
            )
        )
        await db.commit()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def test_configured_key_rate_limit_is_honored_over_http(limited_client):
    headers = {"X-API-Key": "limited"}
    for _ in range(3):
        response = await limited_client.get("/api/identity", headers=headers)
        assert response.status_code == 200, response.text
    blocked = await limited_client.get("/api/identity", headers=headers)
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Rate limit exceeded"
