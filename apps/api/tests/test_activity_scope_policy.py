"""Approved activity-role interpretation stays explicit and exception-scoped.

Real SQLite/parser/ASGI; permissive external model doubles do not certify NLI.
"""

import pytest

from tests.test_connected_contract import upload
from tests.test_requirement_answer_contract import external_models

pytest_plugins = ["tests.test_connected_contract"]


def role_models(monkeypatch):
    def select(question, context):
        values = (
            ["duty supervisor", "record steward"]
            if "leads" in question
            else ["session witness", "shift clerk"]
        )
        return next((value for value in values if value in context), None)

    external_models(monkeypatch, select)
    from app.services import connected_query

    config = connected_query.settings.model_copy(
        update={"ROLE_SCOPE_POLICY": "ordinary_session_activity_v1"}, deep=True
    )
    monkeypatch.setattr(connected_query, "settings", config)


async def test_ordinary_session_uses_documented_activity_roles_with_scope_disclosure(
    real_client, monkeypatch
):
    client, _, _ = real_client
    documents = [
        await upload(client, "The record steward leads Meridian review."),
        await upload(client, "The shift clerk is the deputy for Meridian review."),
    ]
    role_models(monkeypatch)
    response = await client.post(
        "/api/queries",
        json={
            "question": (
                "For an ordinary Meridian review session, "
                "identify the lead and the deputy."
            ),
            "document_ids": [document["id"] for document in documents],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is False, body.get("refusal_reason")
    assert "record steward" in body["answer"] and "shift clerk" in body["answer"]
    assert "activity" in body["answer"].casefold()
    selection = body["provenance"]["answer_selection"]
    interpreted = [
        r for r in selection["requirements"] if r.get("role_scope_interpretation")
    ]
    assert len(interpreted) == 2
    assert all(
        r["role_scope_interpretation"]["activity_scope"] == "Meridian review"
        for r in interpreted
    )
    assert selection["role_scope_read_set"]["complete"] is True
    saved = (await client.get(f"/api/queries/{body['id']}")).json()
    assert saved["answer"] == body["answer"]
    assert saved["provenance"]["answer_selection"] == selection


async def test_activity_policy_does_not_reinterpret_responsibility_as_leadership(
    real_client, monkeypatch
):
    client, _, _ = real_client
    document = await upload(client, "The record steward owns Meridian review.")
    role_models(monkeypatch)
    response = await client.post(
        "/api/queries",
        json={
            "question": "For an ordinary Meridian review session, who is responsible?",
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["refused"] is True


async def test_content_source_budget_failure_is_refusal_not_runtime_substitution(
    real_client, monkeypatch
):
    from app.services import procedure_evidence

    client, _, _ = real_client
    document = await upload(client, "The record steward leads Meridian review.")
    role_models(monkeypatch)

    async def rejected(*args):
        raise procedure_evidence.ProcedureRejected(
            "procedure_projection_budget_exceeded"
        )

    monkeypatch.setattr(procedure_evidence, "resolve_version", rejected)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads ordinary Meridian review sessions?",
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["refused"] is True and response.json()["answer"] is None


async def test_curated_general_activity_fact_cannot_override_explicit_session(
    real_client, monkeypatch
):
    import uuid

    from app.models.document import Document

    client, factory, _ = real_client
    activity = await upload(client, "The record steward leads Meridian review.")
    direct = await upload(
        client, "For Meridian review sessions, the lead is the duty supervisor."
    )
    async with factory() as db:
        for item in (activity, direct):
            document = await db.get(Document, uuid.UUID(item["id"]))
            document.metadata_ = {"conflict_group": "declared role scopes"}
        await db.commit()
    role_models(monkeypatch)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads ordinary Meridian review sessions?",
            "document_ids": [activity["id"], direct["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["refused"] is False, response.text
    assert "record steward" not in response.json()["answer"]


async def test_unaccepted_opposing_explicit_session_cannot_disappear(
    real_client, monkeypatch
):
    client, _, _ = real_client
    first = await upload(
        client, "For Meridian review sessions, the lead is the duty supervisor."
    )
    second = await upload(client, "The reserve officer leads Meridian review sessions.")
    role_models(monkeypatch)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads ordinary Meridian review sessions?",
            "document_ids": [first["id"], second["id"]],
            "retrieval_method": "keyword",
            "top_k": 1,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["refused"] is True
    assert response.json()["answer"] is None


@pytest.mark.parametrize(
    "direct_scope", ["Meridian review sessions", "ordinary Meridian review sessions"]
)
async def test_explicit_session_assignment_precedes_activity_role(
    real_client, monkeypatch, direct_scope
):
    client, _, _ = real_client
    activity = await upload(client, "The record steward leads Meridian review.")
    direct = await upload(
        client, f"For {direct_scope}, the lead is the duty supervisor."
    )
    role_models(monkeypatch)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads ordinary Meridian review sessions?",
            "document_ids": [activity["id"], direct["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    value = response.json()
    assert value["refused"] is False
    assert "duty supervisor" in value["answer"]
    assert "record steward" not in value["answer"]
    interpreted = value["provenance"]["answer_selection"]["requirements"][0][
        "role_scope_interpretation"
    ]
    assert interpreted["effective_scope"] == "session"
    assert interpreted["activity_fallback"] is False


async def test_unparsed_session_nomination_cannot_be_erased_by_qa_null(
    real_client, monkeypatch
):
    client, _, _ = real_client
    activity = await upload(client, "The record steward leads Meridian review.")
    restriction = await upload(
        client, "Meridian review. Each session requires a separate lead nomination."
    )
    role_models(monkeypatch)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads ordinary Meridian review sessions?",
            "document_ids": [activity["id"], restriction["id"]],
            "retrieval_method": "keyword",
            "top_k": 1,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["refused"] is True
    assert response.json()["answer"] is None


async def test_literal_policy_cannot_answer_session_with_activity_only(
    real_client, monkeypatch
):
    from app.services import connected_query

    client, _, _ = real_client
    activity = await upload(client, "The record steward leads Meridian review.")
    role_models(monkeypatch)
    monkeypatch.setattr(connected_query.settings, "ROLE_SCOPE_POLICY", "literal_v1")
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads ordinary Meridian review sessions?",
            "document_ids": [activity["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["refused"] is True
    assert response.json()["answer"] is None


async def test_permissive_models_cannot_bridge_activity_ownership_to_session(
    real_client, monkeypatch
):
    from app.services import connected_query

    client, _, _ = real_client
    document = await upload(client, "The record steward owns Meridian review.")
    external_models(monkeypatch, lambda question, text: "record steward")
    monkeypatch.setattr(
        connected_query.settings, "ROLE_SCOPE_POLICY", "ordinary_session_activity_v1"
    )
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who owns ordinary Meridian review sessions?",
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["refused"] is True
