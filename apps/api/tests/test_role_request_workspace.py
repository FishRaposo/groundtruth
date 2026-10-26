"""Original request constraints have independent authority from source workspace."""

import uuid
from copy import deepcopy
from dataclasses import replace

import pytest
from app.models.query import Query
from app.services import requirement_answers

from tests.test_activity_scope_policy import role_models
from tests.test_connected_contract import upload

pytest_plugins = ["tests.test_connected_contract"]


async def answer(real_client, monkeypatch, workspace):
    client, _, _ = real_client
    document = await upload(
        client, "The record steward in workspace ops-a leads Meridian review."
    )
    role_models(monkeypatch)
    plan = requirement_answers.plan_requirements
    # The controller receives an independently captured typed request. A source
    # manifest cannot create or alter this original constraint.
    monkeypatch.setattr(
        requirement_answers,
        "plan_requirements",
        lambda question: tuple(
            replace(item, source_workspace=workspace) for item in plan(question)
        ),
    )
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads ordinary Meridian review sessions?",
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200 and response.json()["refused"] is False, (
        response.text
    )
    return response.json()


@pytest.mark.parametrize("workspace", [None, "ops-a"])
async def test_row_records_original_workspace_independently(
    real_client, monkeypatch, workspace
):
    value = await answer(real_client, monkeypatch, workspace)
    row = value["provenance"]["answer_selection"]["requirements"][0]
    assert "source_workspace" in row
    assert row["source_workspace"] == workspace
    assert row["role_scope_interpretation"]["source_workspace"] == workspace


@pytest.mark.parametrize("mutation", ["missing", "mismatched"])
async def test_nonnull_interpreted_constraint_requires_original_row_authority(
    real_client, monkeypatch, mutation
):
    client, factory, _ = real_client
    value = await answer(real_client, monkeypatch, "ops-a")
    async with factory() as db:
        saved = await db.get(Query, uuid.UUID(value["id"]))
        provenance = deepcopy(saved.provenance)
        row = provenance["answer_selection"]["requirements"][0]
        if mutation == "missing":
            row.pop("source_workspace", None)
        else:
            row["source_workspace"] = "ops-b"
        saved.provenance = provenance
        await db.commit()
    historic = (await client.get(f"/api/queries/{value['id']}")).json()
    assert historic["answer"] is None and historic["provenance"] is None
