"""In-process ASGI lifecycle only: no sockets, model loading or provider calls."""

import json
import uuid

import pytest
from app.api.deps import get_current_user
from app.config import Settings
from app.db.session import get_db
from app.main import app
from app.models.chunk import Chunk
from app.services.document.versioning import DocumentVersionManager
from app.services.requirement_contract import complete_procedure
from httpx import ASGITransport, AsyncClient

from tests.test_procedure_extent import (
    LONG,
    PRINCIPAL,
    QUESTION,
    external_boundaries,
    seed_procedure,
)

pytest_plugins = ["tests.test_connected_contract"]


@pytest.fixture
async def procedure_client(connected_db, monkeypatch):
    db, _ = connected_db
    config = Settings(
        EMBEDDING_MODE="deterministic",
        EMBEDDING_DIMENSIONS=32,
        GENERATION_MODE="extractive",
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        SUPPORT_MIN_MARGIN=0,
        READER_NULL_THRESHOLD=8,
        RATE_LIMIT_ENABLED=False,
    )
    monkeypatch.setattr("app.services.connected_query.settings", config)
    monkeypatch.setattr("app.api.queries.settings", config)
    external_boundaries(monkeypatch)
    from app.services.answer_support import support_service

    monkeypatch.setattr(support_service, "_error_identity", None)

    async def session():
        yield db

    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_user] = lambda: PRINCIPAL
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client, db
    finally:
        app.dependency_overrides.clear()


def request(document):
    return {
        "question": QUESTION,
        "document_ids": [str(document.id)],
        "retrieval_method": "keyword",
        "top_k": 1,
    }


async def test_complete_normal_stream_history_and_source_quotes(procedure_client):
    client, db = procedure_client
    document, _ = await seed_procedure(db)
    normal = await client.post("/api/queries", json=request(document))
    assert normal.status_code == 200, normal.text
    body = normal.json()
    assert body["outcome"] == "completed", body
    assert (
        body["answer"]
        == "Source extracts (not model-generated):\n\n" + LONG[46:] + " [1] [2]"
    )
    trace = body["retrieval_trace"]
    assert trace["reranked_results"] == 1 and trace["final_context_chunks"] == 2
    assert len(trace["scores"]) == 1
    assert body["sources"][1]["score_status"] == "not_ranked"
    assert body["sources"][1]["relevance_score"] == 0.0
    selection = body["provenance"]["answer_selection"]
    assert selection["contract"] == "requirement-evidence-v2"
    assert complete_procedure(selection["requirements"][0]["procedure_completeness"])
    assert selection["procedure_contexts"][0]["sources"][1]["ranking_score"] is None
    for index, expected in [(1, LONG[:1292]), (2, LONG[1171:])]:
        cited = await client.get(f"/api/queries/{body['id']}/sources/{index}")
        assert cited.status_code == 200
        assert cited.json()["quoted_text"] == cited.json()["passage"] == expected
        assert cited.json()["source_status"] == "current"
    streamed = await client.post("/api/queries/stream", json=request(document))
    events = [
        json.loads(line[6:])
        for line in streamed.text.splitlines()
        if line.startswith("data: ")
    ]
    done = next(event for event in events if event["type"] == "done")
    assert done["answer"] == body["answer"]
    assert done["sources"] == body["sources"]
    saved = (await client.get(f"/api/queries/{body['id']}")).json()
    assert saved["answer"] == body["answer"] and saved["sources"] == body["sources"]


async def test_historical_quotes_survive_version_replacement_and_revocation(
    procedure_client,
):
    client, db = procedure_client
    document, _ = await seed_procedure(db)
    body = (await client.post("/api/queries", json=request(document))).json()
    changed = LONG.replace("archive key", "archive token")
    pieces = [changed[:1292], changed[1171:]]
    chunks = [
        Chunk(
            id=uuid.uuid4(),
            document_id=document.id,
            chunk_index=i,
            content=text,
            metadata_={"document_version": 2},
        )
        for i, text in enumerate(pieces)
    ]
    db.add_all(chunks)
    await db.flush()
    await DocumentVersionManager(db).create_version(
        str(document.id), changed, chunks, workspace_id="ops-a", document=document
    )
    source = (await client.get(f"/api/queries/{body['id']}/sources/2")).json()
    assert source["source_status"] == "superseded"
    assert source["quoted_text"] == LONG[1171:]
    document.owner_id = "someone-else"
    await db.commit()
    withheld = (await client.get(f"/api/queries/{body['id']}")).json()
    assert withheld["evidence_access"] == "restricted"
    assert (
        withheld["answer"] is None
        and withheld["sources"] == []
        and withheld["provenance"] is None
    )
    assert (await client.get(f"/api/queries/{body['id']}/sources/2")).status_code == 403


async def test_revocation_during_proofs_cannot_publish_complete_method(
    procedure_client, monkeypatch
):
    from app.services.answer_support import SupportAssessment, support_service

    client, db = procedure_client
    document, _ = await seed_procedure(db)

    async def revoke(pairs, config=None):
        if pairs:
            document.owner_id = "someone-else"
            await db.commit()
        return [
            SupportAssessment("entailment", (-5.0, 5.0, -5.0), 10.0, True, 12)
            for _ in pairs
        ]

    monkeypatch.setattr(support_service, "assess", revoke)
    response = await client.post("/api/queries", json=request(document))
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] != "completed"
    assert body["answer"] is None and body["sources"] == []


async def test_content_budget_is_an_ordinary_persisted_refusal(
    procedure_client, monkeypatch
):
    from app.services.answer_support import SupportInputBudgetExceeded, support_service

    client, db = procedure_client
    document, _ = await seed_procedure(db)

    async def over_budget(pairs, config=None):
        if pairs:
            raise SupportInputBudgetExceeded("Required content exceeds 512", (513,))
        return []

    monkeypatch.setattr(support_service, "assess", over_budget)
    response = await client.post("/api/queries", json=request(document))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "refused" and body["answer"] is None
    selection = body["provenance"]["answer_selection"]
    assert selection["requirements"][0]["reason"] == "procedure_support_budget_exceeded"
    assert selection["evidence_support"]["readiness"] != "error"
    assert (await client.get(f"/api/queries/{body['id']}")).json()[
        "outcome"
    ] == "refused"


async def test_current_curation_change_during_proofs_refuses(
    procedure_client, monkeypatch
):
    from app.services.answer_support import SupportAssessment, support_service

    client, db = procedure_client
    document, _ = await seed_procedure(db)

    async def change(pairs, config=None):
        if pairs:
            document.metadata_ = {
                **(document.metadata_ or {}),
                "condition": "exception",
            }
            await db.commit()
        return [
            SupportAssessment("entailment", (-5.0, 5.0, -5.0), 10.0, True, 12)
            for _ in pairs
        ]

    monkeypatch.setattr(support_service, "assess", change)
    response = await client.post("/api/queries", json=request(document))
    assert response.status_code == 200
    assert response.json()["outcome"] == "refused"


async def test_cancellation_publishes_no_completed_procedure(
    procedure_client, monkeypatch
):
    import asyncio

    from app.api.queries import create_query
    from app.models.query import Query, QueryRequest
    from app.services.answer_support import support_service
    from sqlalchemy import select

    client, db = procedure_client
    document, _ = await seed_procedure(db)

    async def cancelled(pairs, config=None):
        if pairs:
            raise asyncio.CancelledError
        return []

    monkeypatch.setattr(support_service, "assess", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await create_query(QueryRequest(**request(document)), db, PRINCIPAL)
    rows = list((await db.scalars(select(Query))).all())
    assert len(rows) == 1 and rows[0].outcome == "interrupted"
    assert rows[0].answer is None and rows[0].sources == []


async def test_existing_narrative_normal_stream_and_sources(
    procedure_client, monkeypatch
):
    from tests.test_procedure_support_plan import NARRATIVE

    client, db = procedure_client
    document, _ = await seed_procedure(db, NARRATIVE, [NARRATIVE])
    external_boundaries(monkeypatch, raw_text="pause the deployment queue")
    payload = {
        **request(document),
        "question": "How do I roll back the staging deployment?",
    }
    response = await client.post("/api/queries", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "completed"
    assert (
        body["answer"]
        == "Source extracts (not model-generated):\n\n" + NARRATIVE + " [1]"
    )
    proof = body["provenance"]["answer_selection"]["requirements"][0][
        "procedure_completeness"
    ]
    assert proof["structure"] == "narrative" and proof["step_count"] is None
    assert complete_procedure(proof)
    assert any(unit["kind"] == "whole_method" for unit in proof["proof_units"])
    source = (await client.get(f"/api/queries/{body['id']}/sources/1")).json()
    assert source["quoted_text"] == NARRATIVE
    streamed = await client.post("/api/queries/stream", json=payload)
    done = next(
        json.loads(line[6:])
        for line in streamed.text.splitlines()
        if line.startswith("data: ") and json.loads(line[6:]).get("type") == "done"
    )
    assert done["answer"] == body["answer"] and done["sources"] == body["sources"]


async def test_genuine_runtime_failure_remains_503_with_current_contract(
    procedure_client, monkeypatch
):
    from app.services.answer_support import SupportUnavailableError, support_service

    client, db = procedure_client
    document, _ = await seed_procedure(db)

    async def unavailable(pairs, config=None):
        raise SupportUnavailableError("Selected runtime unavailable")

    monkeypatch.setattr(support_service, "assess", unavailable)
    response = await client.post("/api/queries", json=request(document))
    assert response.status_code == 503
    query_id = response.json()["detail"]["query_id"]
    saved = (await client.get(f"/api/queries/{query_id}")).json()
    assert saved["outcome"] == "error" and saved["answer"] is None
    assert (
        saved["provenance"]["answer_selection"]["contract"] == "requirement-evidence-v2"
    )


async def test_historical_v1_is_readable_without_retroactive_completeness(
    procedure_client,
):
    from app.models.query import Query

    client, db = procedure_client
    document, chunks = await seed_procedure(db)
    identity = {
        "document_id": str(document.id),
        "chunk_id": str(chunks[0].id),
        "document_version": 1,
        "content_hash": document.content_hash,
    }
    row = Query(
        question=QUESTION,
        answer="Historical source extract",
        outcome="completed",
        owner_id="writer",
        workspace_id="ops-a",
        provenance={
            "answer_selection": {
                "contract": "requirement-evidence-v1",
                "inspected_sources": [identity],
                "requirements": [{"kind": "procedure", "status": "supported"}],
            }
        },
        sources=[
            {
                **identity,
                "document_title": "Historical",
                "content_preview": "This is",
                "relevance_score": 0.9,
                "citation_index": 1,
                "quoted_text": LONG[:1292],
            }
        ],
    )
    db.add(row)
    await db.commit()
    saved = (await client.get(f"/api/queries/{row.id}")).json()
    assert saved["evidence_access"] == "available"
    selection = saved["provenance"]["answer_selection"]
    assert selection["contract"] == "requirement-evidence-v1"
    assert "procedure_completeness" not in selection["requirements"][0]
    assert saved["sources"][0]["score_status"] is None


async def test_v40_normal_post_cannot_publish_stale_opponent_agreement(
    procedure_client, monkeypatch
):
    from app.services.retrieval.scoped import RetrievalResult

    from tests.test_procedure_chunk_cover import configure_late_opponent_change

    client, db = procedure_client
    a, chunks, b, c, state = await configure_late_opponent_change(db, monkeypatch)

    async def retrieved(*args, **kwargs):
        return RetrievalResult(
            chunks[:1], 0, 1, 0.0, "keyword", {"embedding": {"dimension": 32}}
        )

    monkeypatch.setattr("app.services.connected_query.retrieve_scoped", retrieved)
    response = await client.post(
        "/api/queries",
        json={
            "question": QUESTION,
            "document_ids": [str(d.id) for d in (a, b, c)],
            "retrieval_method": "keyword",
            "top_k": 1,
        },
    )
    assert state["changed"] and b.version_number == 2
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] != "completed", (
        "Public POST must not use the stale version-1 opponent agreement"
    )
    assert body["answer"] is None and body["sources"] == []


async def test_v40_publication_rechecks_inputs_after_preparation(
    procedure_client, monkeypatch
):
    from app.models.conversation import Message
    from app.models.query import QueryRequest
    from app.services.connected_query import begin_query, finish_query, prepare_answer
    from app.services.retrieval.scoped import RetrievalResult
    from sqlalchemy import select

    _, db = procedure_client
    a, chunks = await seed_procedure(db)
    b, _ = await seed_procedure(db)
    for document in (a, b):
        document.metadata_ = {
            **(document.metadata_ or {}),
            "conflict_group": "v40-before-publish",
        }
    for chunk in chunks:
        chunk.metadata["conflict_group"] = "v40-before-publish"
    await db.commit()

    async def retrieved(*args, **kwargs):
        return RetrievalResult(
            chunks[:1], 0, 1, 0.0, "keyword", {"embedding": {"dimension": 32}}
        )

    monkeypatch.setattr("app.services.connected_query.retrieve_scoped", retrieved)
    request = QueryRequest(
        question=QUESTION,
        document_ids=[a.id, b.id],
        retrieval_method="keyword",
        top_k=1,
    )
    row = await begin_query(db, request, PRINCIPAL)
    await prepare_answer(db, row, request, PRINCIPAL)
    assert row.outcome == "completed"
    b.metadata_ = {**b.metadata_, "condition": "exception"}
    await finish_query(db, row, PRINCIPAL)
    assert row.outcome == "refused", (
        "A source changed after preparation and before publication"
    )
    assert row.answer is None and row.sources == []
    messages = list(
        (
            await db.scalars(
                select(Message).where(
                    Message.conversation_id == row.conversation_id,
                    Message.role == "assistant",
                )
            )
        ).all()
    )
    assert (
        len(messages) == 1
        and messages[0].content == row.refusal_reason
        and messages[0].sources == []
    )
