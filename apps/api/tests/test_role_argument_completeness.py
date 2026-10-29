"""Whole role arguments must be nominal designators, not recognized prefixes."""

import pytest

from tests.test_activity_scope_policy import role_models
from tests.test_connected_contract import upload
from tests.test_role_scope_classification import classify

pytest_plugins = ["tests.test_connected_contract"]


@pytest.mark.parametrize(
    "tail",
    [
        "following a separate appointment",
        "once separately appointed",
        "assuming a separate nomination",
        "despite a separate nomination being necessary",
        "under a subsequent appointment",
        "for an additional appointment",
        "afterward",
        "contingent on nomination by another supervisor",
    ],
)
def test_role_designator_must_consume_whole_copular_value(tail):
    result = classify(
        "For Meridian review sessions, the lead is the duty supervisor " + tail + "."
    )
    assert result["complete"] is False, result


@pytest.mark.parametrize(
    "value",
    [
        "the duty supervisor",
        "the senior records supervisor",
        "the shift clerk",
        "the deputy records steward",
        "the chief operations officer",
        "Maya Chen",
        "the Director of Operations",
        "the record steward in workspace ops-a",
    ],
)
def test_complete_nominal_role_arguments_remain_supported(value):
    result = classify(f"For Meridian review sessions, the lead is {value}.")
    assert result["complete"] is True, result


@pytest.mark.parametrize(
    "tail", ["once separately appointed", "following a separate appointment"]
)
async def test_public_conditional_role_value_is_refused_and_stays_refused_in_history(
    real_client, monkeypatch, tail
):
    client, _, _ = real_client
    document = await upload(
        client, f"For Meridian review sessions, the lead is the duty supervisor {tail}."
    )
    role_models(monkeypatch)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads ordinary Meridian review sessions?",
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is True and body["answer"] is None, body
    saved = (await client.get(f"/api/queries/{body['id']}")).json()
    assert saved["refused"] is True and saved["answer"] is None
