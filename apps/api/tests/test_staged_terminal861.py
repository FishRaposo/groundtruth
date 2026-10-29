"""In-flight terminal protocol: actual SQLite/generator, UNITONLY inference."""

import json
import uuid

import pytest
from app.api.queries import stream_query
from app.models.conversation import Conversation, Message
from app.models.document import Document
from app.models.query import Query, QueryRequest
from app.services.procedure_evidence import check_read_set
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.test_procedure_extent import PRINCIPAL
from tests.test_procedure_stream_publication import events, setup_group

pytest_plugins = ["tests.test_connected_contract", "tests.test_procedure_http"]


async def citations(response):
    seen = []
    while True:
        value = events(await anext(response.body_iterator))
        seen.extend(value)
        if any(event["type"] == "citations" for event in value):
            return seen


async def read_set(db):
    row = await db.scalar(select(Query))
    captured = row.provenance["answer_selection"]["procedure_read_set"]
    request = QueryRequest(
        question=row.question,
        document_ids=captured["document_ids"],
        collection_ids=captured["collection_ids"],
    )
    return await check_read_set(db, PRINCIPAL, request, captured)


async def test_857_actual_sql_condition_after_citations_refuses_terminal_done(
    procedure_client, monkeypatch
):
    _, db = procedure_client
    payload, mutate = await setup_group(db, monkeypatch, "condition")
    response = await stream_query(QueryRequest(**payload), db, PRINCIPAL)
    seen = await citations(response)
    assert any(event["type"] == "token" for event in seen)
    await mutate()
    checked = await read_set(db)
    assert checked["consistent"] is False, checked
    remaining = events("".join([part async for part in response.body_iterator]))
    assert remaining and remaining[-1]["type"] == "refused", remaining
    assert remaining[-1]["answer"] is None and remaining[-1]["sources"] == []
    row = await db.scalar(select(Query))
    assert row.outcome == "refused" and row.answer is None and row.sources == []
    saved = list((await db.scalars(select(Message))).all())
    assert len(saved) == 2
    assert saved[1].role == "assistant" and saved[1].content == row.refusal_reason
    assert saved[1].sources == []


async def test_close_after_citations_is_interrupted_without_completed_memory(
    procedure_client, monkeypatch
):
    _, db = procedure_client
    payload, _ = await setup_group(db, monkeypatch, "condition")
    response = await stream_query(QueryRequest(**payload), db, PRINCIPAL)
    await citations(response)
    assert list((await db.scalars(select(Message))).all()) == []
    await response.body_iterator.aclose()
    await response.body_iterator.aclose()
    row = await db.scalar(select(Query))
    assert row.outcome == "interrupted" and row.answer is None and row.sources == []
    assert list((await db.scalars(select(Message))).all()) == []
    conversation = await db.get(Conversation, row.conversation_id)
    assert conversation.message_count == 0 and conversation.total_tokens == 0


@pytest.mark.parametrize(
    "mutation", ["condition", "version", "new_group_member", "revoked"]
)
async def test_late_sql_changes_refuse_without_stale_answer_or_memory(
    procedure_client, monkeypatch, mutation
):
    _, db = procedure_client
    payload, mutate = await setup_group(
        db, monkeypatch, "condition" if mutation == "revoked" else mutation
    )
    response = await stream_query(QueryRequest(**payload), db, PRINCIPAL)
    await citations(response)
    if mutation == "revoked":
        factory = async_sessionmaker(db.bind, expire_on_commit=False)
        async with factory() as external:
            await external.execute(
                update(Document)
                .where(Document.id == uuid.UUID(payload["document_ids"][1]))
                .values(owner_id="revoked-owner")
            )
            await external.commit()
    else:
        await mutate()
    assert not (await read_set(db))["consistent"]
    remaining = events("".join([part async for part in response.body_iterator]))
    assert [event["type"] for event in remaining] == ["refused"]
    final = remaining[0]
    assert final["refused"] and final["answer"] is None and final["sources"] == []
    row = await db.scalar(select(Query))
    assert row.outcome == "refused" and row.answer is None
    messages = list((await db.scalars(select(Message))).all())
    assert len(messages) == 2
    assistant = next(message for message in messages if message.role == "assistant")
    assert assistant.content == row.refusal_reason and assistant.sources == []
    await response.body_iterator.aclose()
    assert len(list((await db.scalars(select(Message))).all())) == 2


async def test_citations_send_failure_interrupts_and_does_not_append_memory(
    procedure_client, monkeypatch
):
    from starlette.requests import ClientDisconnect

    _, db = procedure_client
    payload, _ = await setup_group(db, monkeypatch, "condition")
    response = await stream_query(QueryRequest(**payload), db, PRINCIPAL)

    async def receive():
        raise AssertionError("ASGI2.4 uses actual send failures")

    async def send(message):
        if message[
            "type"
        ] == "http.response.body" and b'"type": "citations"' in message.get(
            "body", b""
        ):
            raise OSError("UNITONLY861 transport closed at citations")

    with pytest.raises(ClientDisconnect):
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    row = await db.scalar(select(Query))
    assert row.outcome == "interrupted" and row.answer is None and row.sources == []
    assert list((await db.scalars(select(Message))).all()) == []


async def test_final_sql_failure_records_error_without_completed_memory(
    procedure_client, monkeypatch
):
    _, db = procedure_client
    payload, _ = await setup_group(db, monkeypatch, "condition")
    response = await stream_query(QueryRequest(**payload), db, PRINCIPAL)
    await citations(response)

    async def broken_read(*args):
        raise RuntimeError("UNITONLY861 private SQL failure detail")

    # The generator owns the function imported when stream_query was called;
    # inject the actual SQL session read boundary instead of a successful API.
    monkeypatch.setattr(db, "scalars", broken_read)
    remaining = events("".join([part async for part in response.body_iterator]))
    assert [event["type"] for event in remaining] == ["error"]
    assert "private SQL" not in json.dumps(remaining)
    monkeypatch.undo()
    row = await db.scalar(select(Query))
    assert row.outcome == "error" and row.answer is None and row.sources == []
    assert list((await db.scalars(select(Message))).all()) == []


async def test_success_finalizes_once_and_later_source_edits_do_not_rewrite_history(
    procedure_client, monkeypatch
):
    from app.services import connected_query

    _, db = procedure_client
    payload, mutate = await setup_group(db, monkeypatch, "condition")
    native_prepare = connected_query.prepare_answer
    native_finish = connected_query.finish_query
    calls = {"prepare": 0, "finish": 0}

    async def prepare(*args):
        calls["prepare"] += 1
        return await native_prepare(*args)

    async def finish(*args):
        calls["finish"] += 1
        return await native_finish(*args)

    monkeypatch.setattr(connected_query, "prepare_answer", prepare)
    monkeypatch.setattr(connected_query, "finish_query", finish)
    response = await stream_query(QueryRequest(**payload), db, PRINCIPAL)
    seen = await citations(response)
    # No app-side commit or conversation mutation has happened at this yield.
    with db.no_autoflush:
        assert list((await db.scalars(select(Message))).all()) == []
    remaining = events("".join([part async for part in response.body_iterator]))
    assert [event["type"] for event in remaining] == ["done"]
    assert remaining[0]["outcome"] == "completed" and remaining[0]["answer"]
    assert calls == {"prepare": 1, "finish": 1}
    assert seen[-1]["sources"] == remaining[0]["sources"]
    await response.body_iterator.aclose()
    await response.body_iterator.aclose()
    row = await db.scalar(select(Query))
    original = row.answer
    assert len(list((await db.scalars(select(Message))).all())) == 2
    conversation = await db.get(Conversation, row.conversation_id)
    assert conversation.message_count == 2
    await mutate()
    await response.body_iterator.aclose()
    await db.refresh(row)
    assert row.outcome == "completed" and row.answer == original
    assert len(list((await db.scalars(select(Message))).all())) == 2


async def test_late_acl_without_semantic_read_set_withholds_terminal_answer(
    real_client,
):
    from tests.test_connected_contract import upload

    client, factory, keys = real_client
    document = await upload(client)
    principal = {"id": keys["owner"], "workspace_id": "ops-a", "is_admin": False}
    async with factory() as db:
        response = await stream_query(
            QueryRequest(
                question="What staging rollback release applies?",
                retrieval_method="keyword",
            ),
            db,
            principal,
        )
        await citations(response)
        async with factory() as external:
            doc = await external.get(Document, uuid.UUID(document["id"]))
            doc.owner_id = keys["reader"]
            await external.commit()
        remaining = events("".join([part async for part in response.body_iterator]))
        assert [event["type"] for event in remaining] == ["error"]
        assert "answer" not in remaining[0] and "sources" not in remaining[0]
    async with factory() as db:
        row = await db.scalar(select(Query))
        assert row.outcome == "error" and row.answer is None and row.sources == []
        assert list((await db.scalars(select(Message))).all()) == []
