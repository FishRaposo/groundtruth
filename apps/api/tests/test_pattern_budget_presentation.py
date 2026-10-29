"""A content-discovery budget refusal must not masquerade as revoked access."""

import pytest

from tests.test_connected_contract import upload
from tests.test_requirement_answer_contract import external_models

pytest_plugins = ["tests.test_connected_contract"]


@pytest.mark.parametrize("scope", ["source", "requirement"])
async def test_pattern_budget_refusal_retains_authorized_diagnostics(
    real_client, monkeypatch, scope
):
    client, _, _ = real_client
    actors = ["record steward", "shift clerk", "duty reviewer", "release coordinator"]
    for index in range(7 if scope == "requirement" else 1):
        text = f"Protocol record {index + 1}. " + " ".join(
            f"The {actor} leads Meridian review."
            for actor in actors[: 3 if scope == "requirement" else 4]
        )
        await upload(client, text)
    external_models(monkeypatch, lambda *_: None)
    from app.services import connected_query

    monkeypatch.setattr(
        connected_query,
        "settings",
        connected_query.settings.model_copy(
            update={"ANSWER_PROPOSAL_PROFILE": "qa_plus_source_patterns_v1"}, deep=True
        ),
    )
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads Meridian review?",
            "retrieval_method": "keyword",
            "top_k": 10,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is True and body["answer"] is None
    assert body["evidence_access"] == "available", body
    selection = body["provenance"]["answer_selection"]
    assert any(
        row.get("decision") == f"pattern_{scope}_budget_exceeded"
        for row in selection["pattern_observations"]
    )
    saved = await client.get(f"/api/queries/{body['id']}")
    assert saved.status_code == 200, saved.text
    assert saved.json()["provenance"]["answer_selection"] == selection
