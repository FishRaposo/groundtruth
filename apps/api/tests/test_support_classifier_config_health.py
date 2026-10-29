"""Public configuration/readiness guards for optional local support inference."""

import pytest
from app.api import health
from app.api.health import runtime_metadata
from app.config import Settings
from app.db.session import get_db
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


def test_support_metadata_is_explicit_and_disabled_by_default():
    assert runtime_metadata().get("evidence_support", {}).get("mode") == "disabled"


@pytest.mark.parametrize("margin", [-1, 5, float("nan"), float("inf")])
def test_support_margin_rejects_outside_development_grid(margin):
    with pytest.raises(ValidationError):
        Settings(SUPPORT_MIN_MARGIN=margin)


def test_support_mode_rejects_implicit_fallback():
    with pytest.raises(ValidationError):
        Settings(ANSWER_SUPPORT_MODE="lexical")


async def test_selected_unavailable_support_returns_actionable_503(monkeypatch):
    settings = Settings(ANSWER_SUPPORT_MODE="local_nli", SUPPORT_MODEL_PATH="")
    monkeypatch.setattr(health, "get_settings", lambda: settings)
    application = FastAPI()
    application.include_router(health.router)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def database():
        async with AsyncSession(engine) as session:
            yield session

    application.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://support-test"
        ) as client:
            response = await client.get("/health/ready")
            assert response.status_code == 503
            detail = response.json()
            assert detail.get("status") == "degraded"
            assert "document_count" in detail and "chunk_count" in detail
            assert detail["checks"]["evidence_support"] == "error"
            assert "SUPPORT_MODEL_PATH" in detail["action"]
            assert detail["runtime"]["evidence_support"]["readiness"] == "error"
            assert "answer_selection" in detail["runtime"]
    finally:
        await engine.dispose()


def test_health_reports_the_selected_complete_evidence_contract(monkeypatch):
    settings = Settings(ANSWER_SELECTION_MODE="reader", ANSWER_SUPPORT_MODE="local_nli")
    monkeypatch.setattr(health, "get_settings", lambda: settings)
    runtime = runtime_metadata()
    assert runtime["answer_selection"]["mode"] == "reader"
    assert runtime["answer_selection"]["contract"] == "requirement-evidence-v2"
    assert runtime["answer_selection"]["reader_contract"] == "reader-parts-v14"
    assert runtime["evidence_support"]["mode"] == "local_nli"
