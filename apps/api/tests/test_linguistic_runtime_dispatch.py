"""UNITONLY retained real parser captures; no inference/quality claim."""

from copy import deepcopy

import pytest
from app.config import Settings
from app.models.query import QueryRequest
from app.services import request_parser, requirement_answers
from app.services.answer_requirements import plan_requirements

from tests.test_dependency_frames import actual
from tests.test_linguistic_reading_profile import CONTROLS

pytest_plugins = ["tests.test_connected_contract"]


def config():
    return Settings(**CONTROLS, REQUEST_PARSER_MODE="local_dependency")


def test_synchronous_library_planner_cannot_impersonate_local_dependency_capture():
    with pytest.raises(ValueError, match="capture"):
        plan_requirements(
            "How long is the Copper check?", reading_profile="contextual_source_v2"
        )


async def test_unresolved_actual_capture_refuses_before_retrieval_or_model_support(
    monkeypatch,
):
    question, captured = actual("engineering-unknown-why")
    calls = []

    async def fake_capture(text, settings):
        calls.append(text)
        assert settings.REQUEST_PARSER_MODE == "local_dependency"
        return deepcopy(captured)

    async def forbidden(*args, **kwargs):
        pytest.fail("An incomplete request must not reach retrieval or QA/NLI")

    monkeypatch.setattr(request_parser, "capture_async", fake_capture)
    monkeypatch.setattr(requirement_answers, "_find_scoped_witnesses", forbidden)
    result = await requirement_answers.select_requirement_answer(
        None,
        QueryRequest(question=question),
        None,
        [],
        config(),
        validate_current=forbidden,
    )
    assert calls == [question]
    assert result.reason and "unresolved" in result.reason.lower()
    assert not result.chunks and not result.candidates
    assert result.request_plan["resolved_request"] is False
    assert result.request_plan["unresolved"]
    assert result.request_capture == captured


async def test_configured_parser_asset_failure_remains_execution_error(monkeypatch):
    async def unavailable(*args, **kwargs):
        raise request_parser.RequestParserReadinessError("Missing pinned assets")

    monkeypatch.setattr(request_parser, "capture_async", unavailable)
    with pytest.raises(request_parser.RequestParserReadinessError, match="Missing"):
        await requirement_answers.select_requirement_answer(
            None,
            QueryRequest(question="Who leads the Copper review?"),
            None,
            [],
            config(),
            validate_current=unavailable,
        )


async def test_invalid_parser_capture_is_an_execution_error_not_refusal(monkeypatch):
    async def invalid(*args, **kwargs):
        return {"contract": "forged"}

    monkeypatch.setattr(request_parser, "capture_async", invalid)
    with pytest.raises(request_parser.InvalidCapture):
        await requirement_answers.select_requirement_answer(
            None,
            QueryRequest(question="Who leads the Copper review?"),
            None,
            [],
            config(),
            validate_current=invalid,
        )


async def test_readiness_reports_missing_parser_without_fallback(monkeypatch):
    from app.api import health
    from fastapi import Response

    monkeypatch.setattr(health, "get_settings", config)

    async def unavailable(*args, **kwargs):
        raise request_parser.RequestParserReadinessError("Missing pinned assets")

    monkeypatch.setattr(request_parser, "capture_async", unavailable)
    checks = await health._request_parser_readiness()
    assert checks == {"request_parser": "error"}
    response = Response()
    payload = health._readiness_response({"checks": checks}, response)
    assert response.status_code == 503
    assert "REQUEST_PARSER_MODEL_PATH" in payload["action"]


def test_health_discloses_parser_mode_without_host_paths(monkeypatch):
    from app.api import health

    monkeypatch.setattr(health, "get_settings", config)
    parser = health.runtime_metadata()["request_parser"]
    assert parser["mode"] == "local_dependency"
    assert parser["revision"] == "en_core_web_sm-3.8.0"
    assert parser["support_or_permissions"] == "NOT_ASSESSED"
    assert not any("path" in key for key in parser)


async def test_linguistic_execution_failure_is_not_a_fake_permission_revocation(
    connected_db, monkeypatch
):
    from app.evidence_policy import resolve_evidence_policy
    from app.models.query import Query
    from app.services import connected_query

    db, _ = connected_db
    settings = config()
    monkeypatch.setattr(connected_query, "settings", settings)
    row = Query(
        question="Who leads the Copper review?",
        owner_id="writer",
        workspace_id="ops-a",
        outcome="processing",
        sources=[],
    )
    db.add(row)
    await db.commit()
    row._request_evidence_policy = resolve_evidence_policy(settings)
    await connected_query.fail_query(db, row)
    result = await connected_query.present_query(
        db, row, {"id": "writer", "workspace_id": "ops-a", "is_admin": False}
    )
    assert result.outcome == "error"
    assert result.answer is None and not result.sources
    assert result.evidence_access != "restricted"
    assert "execution failed" in result.refusal_reason.lower()
