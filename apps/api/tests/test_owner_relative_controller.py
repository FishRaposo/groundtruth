"""Coordinated deputy interpretation retains both scoped source proof edges."""

import pytest

from tests.test_connected_contract import upload
from tests.test_requirement_answer_contract import external_models

pytest_plugins = ["tests.test_connected_contract"]


async def query(client, monkeypatch, deputy_text, owner=True):
    documents = [await upload(client, deputy_text)]
    if owner:
        documents.append(
            await upload(
                client, "The standard Meridian review owner is the record steward."
            )
        )

    def proposal(question, context):
        if "deput" in question.casefold() and "shift clerk" in context:
            return "shift clerk"
        if "owner" in context and "record steward" in context:
            return "record steward"
        return None

    external_models(monkeypatch, proposal)
    result = await client.post(
        "/api/queries",
        json={
            "question": "Who owns standard Meridian review, and who is the deputy?",
            "document_ids": [doc["id"] for doc in documents],
            "retrieval_method": "keyword",
        },
    )
    assert result.status_code == 200, result.text
    return result.json(), documents


async def test_two_document_owner_relative_proof_is_recorded_and_durable(
    real_client, monkeypatch
):
    client, _, _ = real_client
    body, documents = await query(
        client,
        monkeypatch,
        "For standard Meridian review, the record steward's deputy is the shift clerk.",
    )
    assert body["refused"] is False
    assert {s["document_id"] for s in body["sources"]} == {d["id"] for d in documents}
    rows = body["provenance"]["answer_selection"]["requirements"]
    deputy = rows[1]
    assert deputy["interpretation"]["kind"] == "owner_relative_deputy"
    assert deputy["depends_on"] == [rows[0]["id"]]
    assert deputy["interpretation"]["owner_requirement_id"] == rows[0]["id"]
    assert "record steward" in deputy["interpretation"]["resolved_owner"]
    assert deputy["interpretation"]["owner_evidence"]
    assert deputy["interpretation"]["deputy_evidence"]
    saved = (await client.get(f"/api/queries/{body['id']}")).json()
    assert saved["provenance"]["answer_selection"]["requirements"] == rows


async def test_selected_proposals_cover_every_supported_witness(
    real_client, monkeypatch
):
    client, _, _ = real_client
    body, _ = await query(
        client,
        monkeypatch,
        "For standard Meridian review, the record steward's deputy is the shift clerk.",
    )
    assert body["refused"] is False
    selection = body["provenance"]["answer_selection"]
    selected = set(selection["selected_proposal_ids"])
    referenced = {
        proposal["proposal_id"]
        for row in selection["requirements"]
        if row["status"] == "supported"
        for witness in row["witnesses"]
        for proposal in witness["proposals"]
    }
    assert selected == referenced
    saved = (await client.get(f"/api/queries/{body['id']}")).json()
    persisted = saved["provenance"]["answer_selection"]
    assert set(persisted["selected_proposal_ids"]) == selected


@pytest.mark.parametrize(
    "deputy_text,owner",
    [
        (
            "For standard Willow review, "
            "the record steward's deputy is the shift clerk.",
            True,
        ),
        (
            "For standard Meridian review, the accountant's deputy is the shift clerk.",
            True,
        ),
        ("The record steward's personal household deputy is the shift clerk.", True),
        (
            "For standard Meridian review, "
            "the record steward's deputy is the shift clerk.",
            False,
        ),
    ],
)
async def test_owner_relative_join_does_not_supply_missing_or_foreign_edges(
    real_client, monkeypatch, deputy_text, owner
):
    client, _, _ = real_client
    body, _ = await query(client, monkeypatch, deputy_text, owner)
    assert body["refused"] is True and body["answer"] is None
    assert body["sources"] == []
