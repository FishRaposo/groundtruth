"""Reauthorize diagnostic candidates even when no citation was selected."""

import json
import uuid

import pytest
from app.config import get_settings
from app.models.document import Document
from app.models.query import AnswerSpan, Query
from app.services.answer_reader import ReaderSelection, reader_service

from tests.test_connected_contract import upload

pytest_plugins = ["tests.test_connected_contract"]


@pytest.mark.parametrize("mode", ["all-null", "selected-plus-null", "conflict"])
async def test_revoked_diagnostic_is_withheld_across_history(
    real_client, monkeypatch, mode
):
    client, factory, keys = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")
    private = await upload(client, "The observatory telescope inventory is classified.")
    public = await upload(
        client, "Observatory telescope maintenance takes eleven minutes."
    )
    if mode == "conflict":
        async with factory() as db:
            for document_id in [private["id"], public["id"]]:
                doc = await db.get(Document, uuid.UUID(document_id))
                doc.metadata_ = {**doc.metadata_, "conflict_group": "observatory"}
            # Ingestion carries curated groups on immutable chunk metadata.
            from app.models.chunk import Chunk
            from sqlalchemy import select

            for chunk in (await db.scalars(select(Chunk))).all():
                chunk.metadata_ = {
                    **(chunk.metadata_ or {}),
                    "conflict_group": "observatory",
                }
            await db.commit()

    async def reader(question, contexts, config=None):
        return [
            ReaderSelection(
                AnswerSpan(start=0, end=len(text), text=text)
                if mode == "conflict"
                or mode == "selected-plus-null"
                and "eleven" in text
                else None,
                {"decision": "answer", "null_margin": 8.5},
            )
            for text in contexts
        ]

    monkeypatch.setattr(reader_service, "select", reader)
    response = await client.post(
        "/api/queries",
        json={
            "question": "How long is observatory telescope maintenance?",
            "document_ids": [private["id"], public["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == (
        "completed" if mode == "selected-plus-null" else "refused"
    )
    assert len(result["retrieval_trace"]["scores"]) == 2
    async with factory() as db:
        doc = await db.get(Document, uuid.UUID(private["id"]))
        doc.owner_id = keys["reader"]
        await db.commit()
    for path in [
        f"/api/queries/{result['id']}",
        f"/api/conversations/{result['conversation_id']}",
    ]:
        saved = await client.get(path)
        assert saved.status_code == 200
        assert private["id"] not in saved.text
        body = saved.json()
        row = body["queries"][0] if "queries" in body else body
        assert row["evidence_access"] == "restricted"
        assert row["provenance"] is None and row["retrieval_trace"] is None
        assert row["answer"] is None and row["sources"] == []
    # The raw immutable record is retained; only its presentation is withheld.
    async with factory() as db:
        raw = await db.get(Query, uuid.UUID(result["id"]))
        assert raw.provenance == result["provenance"]
        from app.models.query import QueryRequest
        from app.services.connected_query import scoped_memory

        memory = await scoped_memory(
            db,
            Query(id=uuid.uuid4(), conversation_id=raw.conversation_id),
            QueryRequest(question="Continue", memory_policy="recent"),
            {"id": keys["owner"], "workspace_id": "ops-a", "is_admin": False},
        )
        assert memory == []


@pytest.mark.parametrize("damage", ["missing-trace", "malformed-id", "unmapped-chunk"])
async def test_unverifiable_reader_diagnostic_mapping_fails_closed(
    real_client, monkeypatch, damage
):
    import copy

    client, factory, _ = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")

    async def reader(question, contexts, config=None):
        return [ReaderSelection(None, {"decision": "no_answer"}) for _ in contexts]

    monkeypatch.setattr(reader_service, "select", reader)
    doc = await upload(client, "The telescope inventory is classified.")
    response = await client.post(
        "/api/queries",
        json={
            "question": "How long is telescope maintenance?",
            "document_ids": [doc["id"]],
            "retrieval_method": "keyword",
        },
    )
    result = response.json()
    assert response.status_code == 200 and result["refused"]
    async with factory() as db:
        row = await db.get(Query, uuid.UUID(result["id"]))
        if damage == "missing-trace":
            row.retrieval_trace = None
        elif damage == "malformed-id":
            trace = copy.deepcopy(row.retrieval_trace)
            trace["scores"][0]["document_id"] = "not-a-document-id"
            row.retrieval_trace = trace
        else:
            provenance = copy.deepcopy(row.provenance)
            provenance["answer_selection"]["candidates"][0]["chunk_id"] = str(
                uuid.uuid4()
            )
            row.provenance = provenance
        await db.commit()
    saved = await client.get(f"/api/queries/{result['id']}")
    assert saved.status_code == 200
    assert saved.json()["evidence_access"] == "restricted"
    assert saved.json()["provenance"] is None


async def test_null_candidate_revoked_during_reader_is_withheld_from_sse(
    real_client, monkeypatch
):
    from app.api.queries import stream_query
    from app.models.query import QueryRequest

    client, factory, keys = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")
    private = await upload(client, "The telescope inventory is classified.")

    async def reader(question, contexts, config=None):
        async with factory() as db:
            doc = await db.get(Document, uuid.UUID(private["id"]))
            doc.owner_id = keys["reader"]
            await db.commit()
        return [ReaderSelection(None, {"decision": "no_answer"}) for _ in contexts]

    monkeypatch.setattr(reader_service, "select", reader)
    async with factory() as db:
        response = await stream_query(
            QueryRequest(
                question="How long is telescope maintenance?",
                document_ids=[private["id"]],
                retrieval_method="keyword",
            ),
            db,
            {"id": keys["owner"], "workspace_id": "ops-a", "is_admin": False},
        )
        body = "".join([piece async for piece in response.body_iterator])
    event = next(
        json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")
    )
    assert private["id"] not in body
    assert event["evidence_access"] == "restricted" and event["provenance"] is None
