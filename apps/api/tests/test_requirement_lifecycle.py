"""Strict evidence stays request-local through real HTTP/SSE persistence."""

import asyncio
import json

from tests.test_connected_contract import upload
from tests.test_requirement_answer_contract import external_models

pytest_plugins = ["tests.test_connected_contract"]


async def test_strict_normal_stream_and_saved_history_agree(real_client, monkeypatch):
    client, _, _ = real_client
    document = await upload(client, "The record steward leads Meridian review.")
    external_models(monkeypatch, lambda question, context: "record steward")
    request = {
        "question": "Who leads Meridian review?",
        "document_ids": [document["id"]],
        "retrieval_method": "keyword",
    }
    normal = await client.post("/api/queries", json=request)
    stream = await client.post("/api/queries/stream", json=request)
    assert normal.status_code == stream.status_code == 200
    events = [
        json.loads(line[6:])
        for line in stream.text.splitlines()
        if line.startswith("data: ")
    ]
    done = next(event for event in events if event["type"] == "done")
    assert done["refused"] is False
    assert done["answer"] == normal.json()["answer"]
    assert done["sources"] == normal.json()["sources"]
    for response in (normal.json(), done):
        saved = (await client.get(f"/api/queries/{response['id']}")).json()
        assert saved["answer"] == response["answer"]
        assert (
            saved["provenance"]["answer_selection"]["requirements"]
            == response["provenance"]["answer_selection"]["requirements"]
        )
        assert saved["outcome"] == "completed"


async def test_concurrent_strict_requests_keep_requirements_and_evidence_separate(
    real_client, monkeypatch
):
    client, _, _ = real_client
    texts = [
        "The record steward leads Meridian review.",
        "The shift clerk leads Juniper audit.",
    ]
    documents = [await upload(client, text) for text in texts]
    external_models(
        monkeypatch,
        lambda question, context: (
            "record steward" if "Meridian" in context else "shift clerk"
        ),
    )
    requests = [
        {
            "question": "Who leads Meridian review?",
            "document_ids": [documents[0]["id"]],
            "retrieval_method": "keyword",
        },
        {
            "question": "Who leads Juniper audit?",
            "document_ids": [documents[1]["id"]],
            "retrieval_method": "keyword",
        },
    ]
    responses = await asyncio.gather(
        *(client.post("/api/queries", json=request) for request in requests)
    )
    for index, response in enumerate(responses):
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["refused"] is False
        assert {source["document_id"] for source in body["sources"]} == {
            documents[index]["id"]
        }
        assert texts[index] in body["answer"] and texts[1 - index] not in body["answer"]
        requirement = body["provenance"]["answer_selection"]["requirements"][0]
        assert requirement["original_text"] == requests[index]["question"]
        assert requirement["input_range"] == {
            "start": 0,
            "end": len(requests[index]["question"]),
        }
        saved = (await client.get(f"/api/queries/{body['id']}")).json()
        assert saved["sources"] == body["sources"]
        assert saved["outcome"] == "completed"


async def test_primary_support_premise_must_be_an_actual_source_window(
    real_client, monkeypatch
):
    from types import SimpleNamespace

    client, _, _ = real_client
    content = "The shift clerk archives Meridian review."
    document = await upload(client, content)
    external_models(monkeypatch, lambda question, context: "shift clerk")

    def fabricated(req, context, start, end):
        return SimpleNamespace(
            rejection=None,
            hypothesis="The shift clerk leads Meridian review.",
            premise="The shift clerk leads Meridian review.",
            value=context[start:end],
            start=start,
            end=end,
            support_start=0,
            support_end=len(context),
            checks=(),
        )

    monkeypatch.setattr("app.services.requirement_answers.support_claim", fabricated)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads Meridian review?",
            "document_ids": [document["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["refused"] is True and body["answer"] is None
    assert body["sources"] == []


async def test_requested_schedule_day_and_time_cannot_succeed_with_day_only(
    real_client, monkeypatch
):
    client, _, _ = real_client
    documents = [
        await upload(client, text)
        for text in [
            "The standard Birch review lasts 12 minutes.",
            "The standard Birch review starts on Mondays.",
        ]
    ]

    def proposed(question, context):
        if "long" in question and "12 minutes" in context:
            return "12 minutes"
        if "day" in question and "Mondays" in context:
            return "Mondays"
        return None

    external_models(monkeypatch, proposed)
    response = await client.post(
        "/api/queries",
        json={
            "question": (
                "For a standard Birch review, supply both its duration "
                "and its scheduled day and time."
            ),
            "document_ids": [doc["id"] for doc in documents],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["refused"] is True
    assert response.json()["answer"] is None


async def test_unrelated_namespaces_are_not_sent_to_the_local_reader(
    real_client, monkeypatch
):
    from app.services.answer_reader import reader_service

    client, _, _ = real_client
    await upload(client, "The record steward leads Meridian review.")
    await upload(client, "The shift clerk leads Juniper review.")
    external_models(
        monkeypatch,
        lambda question, context: "record steward" if "Meridian" in context else None,
    )
    original = reader_service.select_atomic
    queried = []

    async def guarded(question, contexts, config=None):
        queried.extend(contexts)
        if any("Juniper" in context for context in contexts):
            raise RuntimeError("A different named subject reached reader inference")
        return await original(question, contexts, config=config)

    monkeypatch.setattr(reader_service, "select_atomic", guarded)
    response = await client.post(
        "/api/queries",
        json={
            "question": "Who leads Meridian review?",
            "retrieval_method": "keyword",
            "top_k": 5,
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["refused"] is False
    assert "record steward" in response.json()["answer"]
    assert queried and all("Juniper" not in context for context in queried)
    selection = response.json()["provenance"]["answer_selection"]
    assert any(
        item["decision"] == "reader_not_queried_subject_scope"
        for item in selection["candidates"]
    )
