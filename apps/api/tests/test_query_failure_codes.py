"""Real SQLite/ASGI failure persistence; explicit UNITONLY fault injection."""

import json

import pytest
from app.services import connected_query
from app.services.contextual_source_proof import SourceGuardError

pytest_plugins = ["tests.test_connected_contract"]


@pytest.mark.parametrize("streaming", [False, True], ids=["normal", "sse"])
@pytest.mark.parametrize("integrity", [False, True], ids=["runtime", "integrity"])
async def test_query_errors_keep_safe_category_in_response_and_history(
    real_client, monkeypatch, streaming, integrity
):
    client, _, _ = real_client
    marker = "UNITONLY_private_exception_detail_must_not_be_exposed"

    async def fail(*args, **kwargs):
        raise (SourceGuardError if integrity else RuntimeError)(marker)

    monkeypatch.setattr(connected_query, "prepare_answer", fail)
    response = await client.post(
        "/api/queries/stream" if streaming else "/api/queries",
        json={"question": "A synthetic runtime failure."},
    )
    code = "evidence_integrity_failed" if integrity else "query_execution_failed"
    assert marker not in response.text
    if streaming:
        events = [
            json.loads(line.removeprefix("data: "))
            for line in response.text.splitlines()
            if line.startswith("data: ")
        ]
        assert not any(e.get("type") in {"done", "token"} for e in events)
        errors = [e for e in events if e.get("type") == "error"]
        assert len(errors) == 1
        detail = errors[0]
    else:
        assert response.status_code == 503
        detail = response.json()["detail"]
    assert detail["code"] == code
    history = await client.get(f"/api/queries/{detail['query_id']}")
    assert history.status_code == 200 and marker not in history.text
    saved = history.json()
    assert saved["outcome"] == "error" and saved["answer"] is None
    assert saved["sources"] == []
    assert saved["provenance"]["execution_failure"]["code"] == code
    if integrity:
        assert "integrity" in saved["refusal_reason"].lower()
