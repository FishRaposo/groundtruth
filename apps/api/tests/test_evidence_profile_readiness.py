"""Mandatory reader failure must fail readiness, including composite discovery."""

import pytest
from app.api import health
from app.config import Settings
from app.db.session import get_db
from app.services.answer_reader import reader_service
from app.services.answer_support import support_service
from app.services.embedding import embedding_service
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


@pytest.mark.parametrize("proposal", ["qa_only_v1", "qa_plus_source_patterns_v1"])
async def test_unavailable_reader_is_503_even_if_support_and_embeddings_are_ready(
    monkeypatch, proposal
):
    config = Settings(
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        ANSWER_PROPOSAL_PROFILE=proposal,
    )
    monkeypatch.setattr(health, "get_settings", lambda: config)

    async def broken_reader(*args, **kwargs):
        raise RuntimeError("Controlled unavailable QA reader")

    async def healthy_support(*args, **kwargs):
        return []

    async def embeddings(*args, **kwargs):
        return [[0.0] * 32]

    monkeypatch.setattr(reader_service, "select", broken_reader)
    monkeypatch.setattr(support_service, "assess", healthy_support)
    monkeypatch.setattr(embedding_service, "embed_texts", embeddings)
    application = FastAPI()
    application.include_router(health.router)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def database():
        async with AsyncSession(engine) as session:
            yield session

    application.dependency_overrides[get_db] = database
    try:
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://readiness-test"
        ) as client:
            response = await client.get("/health/ready")
        assert response.status_code == 503, response.text
        payload = response.json()
        assert payload["checks"]["reader"] == "error"
        assert payload["checks"]["evidence_support"] == "ok"
        assert "READER_MODEL_PATH" in payload["action"]
        assert payload["runtime"]["evidence_profile"]["proposal_profile"] == proposal
    finally:
        await engine.dispose()


pytest_plugins = ["tests.test_connected_contract"]


@pytest.mark.parametrize(
    "question",
    [
        "Hello there",
        " and ".join(["who leads Meridian review"] * 9) + "?",
    ],
)
async def test_empty_or_unsupported_request_cannot_hide_selected_reader_failure(
    real_client, monkeypatch, question
):
    from tests.test_requirement_answer_contract import external_models

    client, _, _ = real_client
    external_models(monkeypatch, lambda *args: None)
    calls = []

    async def unavailable(question, contexts, config=None):
        calls.append(list(contexts))
        raise RuntimeError("Configured local reader is unavailable; controlled test.")

    monkeypatch.setattr(reader_service, "select_atomic", unavailable)
    response = await client.post("/api/queries", json={"question": question})
    assert response.status_code == 503, response.text
    assert calls == [[]]
    identifier = response.json()["detail"]["query_id"]
    saved = await client.get(f"/api/queries/{identifier}")
    assert saved.status_code == 200, saved.text
    assert saved.json()["outcome"] == "error"
    assert saved.json()["refused"] is False
    assert saved.json()["answer"] is None
