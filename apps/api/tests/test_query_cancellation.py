"""A cancelled database read must release its cursor before outcome cleanup."""

import asyncio
import uuid

import aiosqlite
import pytest
from app.api.queries import stream_query
from app.models.query import Query, QueryRequest
from app.services.connected_query import fail_query, source_access
from starlette.requests import ClientDisconnect

from tests.test_connected_contract import upload

pytest_plugins = ["tests.test_connected_contract"]


async def test_cancelled_authorization_read_drains_before_interrupted_commit(
    real_client, monkeypatch
):
    client, factory, keys = real_client
    doc = await upload(client)
    response = await client.post(
        "/api/queries",
        json={
            "question": "What staging rollback release applies?",
            "document_ids": [doc["id"]],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    identifier = uuid.UUID(response.json()["id"])
    principal = {"id": keys["owner"], "workspace_id": "ops-a", "is_admin": False}
    entered, release = asyncio.Event(), asyncio.Event()
    native = aiosqlite.Connection._execute
    armed = True

    async def pause_select(connection, operation, *args, **kwargs):
        nonlocal armed
        result = await native(connection, operation, *args, **kwargs)
        if (
            armed
            and getattr(operation, "__qualname__", "") == "Cursor.execute"
            and args
            and str(args[0]).startswith("SELECT documents.id")
        ):
            armed = False
            entered.set()
            await release.wait()
        return result

    async with factory() as db:
        row = await db.get(Query, identifier)
        monkeypatch.setattr(aiosqlite.Connection, "_execute", pause_select)
        task = asyncio.create_task(source_access(db, row, principal))
        try:
            await asyncio.wait_for(entered.wait(), timeout=3)
            task.cancel()
            await asyncio.sleep(0)
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        await fail_query(db, row, interrupted=True)
    async with factory() as db:
        saved = await db.get(Query, identifier)
        assert saved.outcome == "interrupted" and saved.answer is None


async def test_closing_body_at_yield_persists_interrupted_outcome(real_client):
    client, factory, keys = real_client
    await upload(client)
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
        event = await anext(response.body_iterator)
        assert '"type": "token"' in event
        await response.body_iterator.aclose()
    async with factory() as db:
        from sqlalchemy import select

        rows = list((await db.scalars(select(Query))).all())
        assert len(rows) == 1
        assert rows[0].outcome == "interrupted" and rows[0].answer is None


@pytest.mark.parametrize("disconnect_at", ["start", "token", "done"])
async def test_transport_send_failure_finalizes_query(real_client, disconnect_at):
    client, factory, keys = real_client
    await upload(client)
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

        async def receive():
            raise AssertionError("ASGI2.4 uses send failures for disconnects")

        async def send(message):
            if disconnect_at == "start" or (
                message["type"] == "http.response.body"
                and ('"type": "' + disconnect_at + '"').encode()
                in message.get("body", b"")
            ):
                raise OSError("Peer closed the local test connection")

        with pytest.raises(ClientDisconnect):
            await response(
                {"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send
            )
    async with factory() as db:
        from sqlalchemy import select

        rows = list((await db.scalars(select(Query))).all())
        assert len(rows) == 1
        if disconnect_at == "done":
            assert rows[0].outcome == "completed" and rows[0].answer
        else:
            assert rows[0].outcome == "interrupted" and rows[0].answer is None


async def test_direct_cancellation_during_finalizer_persists_interruption(
    real_client, monkeypatch
):
    import app.services.connected_query as connected

    client, factory, keys = real_client
    await upload(client)
    entered, release = asyncio.Event(), asyncio.Event()
    native = connected.fail_query

    async def pause_cleanup(*args, **kwargs):
        entered.set()
        await release.wait()
        return await native(*args, **kwargs)

    monkeypatch.setattr(connected, "fail_query", pause_cleanup)
    async with factory() as db:
        response = await stream_query(
            QueryRequest(
                question="What staging rollback release applies?",
                retrieval_method="keyword",
            ),
            db,
            {"id": keys["owner"], "workspace_id": "ops-a", "is_admin": False},
        )

        async def send(message):
            raise OSError("Peer closed before iteration")

        async def receive():
            await asyncio.Event().wait()

        task = asyncio.create_task(
            response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
        )
        try:
            await asyncio.wait_for(entered.wait(), 3)
            task.cancel()
            await asyncio.sleep(0)
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    async with factory() as db:
        from sqlalchemy import select

        row = await db.scalar(select(Query))
        assert row.outcome == "interrupted" and row.answer is None
