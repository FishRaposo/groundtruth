"""Connected records disclose source-pattern discovery without inventing QA use."""

import uuid
from copy import deepcopy

from app.models.query import Query

from tests.test_connected_contract import upload
from tests.test_requirement_answer_contract import external_models

pytest_plugins = ["tests.test_connected_contract"]


async def pattern_answer(real_client, monkeypatch):
    client, _, _ = real_client
    document = await upload(client, "The record steward leads Meridian review.")
    external_models(monkeypatch, lambda *_: None)
    from app.services import connected_query

    config = connected_query.settings.model_copy(
        update={"ANSWER_PROPOSAL_PROFILE": "qa_plus_source_patterns_v1"}, deep=True
    )
    monkeypatch.setattr(connected_query, "settings", config)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads Meridian review?",
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["refused"] is False, response.text
    return response.json(), document


async def test_pattern_success_retains_actual_qa_null_and_captured_profile_in_history(
    real_client, monkeypatch
):
    client, _, _ = real_client
    body, _ = await pattern_answer(real_client, monkeypatch)
    selection = body["provenance"]["answer_selection"]
    assert (
        selection.get("evidence_profile", {}).get("proposal_profile")
        == "qa_plus_source_patterns_v1"
    )
    assert selection["proposals"] and selection["selected_proposal_ids"]
    assert all(p["origin"] == "source_pattern" for p in selection["proposals"])
    assert all(p.get("null_margin") is None for p in selection["proposals"])
    assert selection["qa_observations"]
    assert all(
        observation["span"] is None for observation in selection["qa_observations"]
    )
    assert all(
        observation["diagnostics"]["decision"] == "no_answer"
        for observation in selection["qa_observations"]
    )
    assert selection["discovery_lineage"]["status"] == "recorded"
    from app.services import connected_query

    monkeypatch.setattr(
        connected_query,
        "settings",
        connected_query.settings.model_copy(
            update={"ANSWER_PROPOSAL_PROFILE": "qa_only_v1"}, deep=True
        ),
    )
    saved = (await client.get(f"/api/queries/{body['id']}")).json()
    assert saved["answer"] == body["answer"]
    assert saved["provenance"]["answer_selection"] == selection


async def test_forged_qa_origin_on_saved_pattern_cannot_keep_certified_answer(
    real_client, monkeypatch
):
    client, factory, _ = real_client
    body, _ = await pattern_answer(real_client, monkeypatch)
    async with factory() as db:
        row = await db.get(Query, uuid.UUID(body["id"]))
        value = deepcopy(row.provenance)
        selection = value["answer_selection"]
        # This mutation claims the abstaining reader accepted the pattern.
        selection.setdefault("proposals", [{"origin": "source_pattern"}])[0][
            "origin"
        ] = "qa_reader"
        row.provenance = value
        await db.commit()
    saved = await client.get(f"/api/queries/{body['id']}")
    assert saved.status_code == 200, saved.text
    assert saved.json()["answer"] is None
    assert saved.json()["sources"] == []
    assert saved.json()["provenance"] is None
