"""Prepared procedure evidence must remain current at each publication boundary.

Inference/retrieval doubles isolate lifecycle races; SQL and ASGI are real.
"""

import json
import uuid

import pytest
from app.api.queries import stream_query
from app.models.chunk import Chunk
from app.models.collection import Collection, collection_documents
from app.models.conversation import Message
from app.models.document import Document
from app.models.query import Query, QueryRequest
from app.services import connected_query
from app.services.document.versioning import DocumentVersionManager
from app.services.retrieval.scoped import RetrievalResult
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from tests.test_procedure_extent import LONG, PRINCIPAL, QUESTION, seed_procedure

pytest_plugins = ["tests.test_connected_contract", "tests.test_procedure_http"]


async def setup_group(db, monkeypatch, mutation):
    a, chunks = await seed_procedure(db)
    b, _ = await seed_procedure(db)
    group = "v56-prepared-procedure"
    for document in (a, b):
        document.metadata_ = {"conflict_group": group}
    for chunk in chunks:
        chunk.metadata["conflict_group"] = group
    payload = {
        "question": QUESTION,
        "document_ids": [str(a.id), str(b.id)],
        "retrieval_method": "keyword",
        "top_k": 1,
        "memory_policy": "disabled",
    }
    collection = None
    if mutation == "new_group_member":
        payload.pop("document_ids")
    if mutation == "collection_membership":
        collection = Collection(name="v56 scope", owner_id="writer")
        db.add(collection)
        await db.flush()
        await db.execute(
            collection_documents.insert(),
            [{"collection_id": collection.id, "document_id": d.id} for d in (a, b)],
        )
        payload["collection_ids"] = [str(collection.id)]
    await db.commit()

    async def retrieved(*args, **kwargs):
        return RetrievalResult(
            chunks[:1], 0, 1, 0.0, "keyword", {"embedding": {"dimension": 32}}
        )

    monkeypatch.setattr(connected_query, "retrieve_scoped", retrieved)

    async def mutate():
        factory = async_sessionmaker(db.bind, expire_on_commit=False)
        async with factory() as external:
            if mutation == "condition":
                await external.execute(
                    update(Document)
                    .where(Document.id == b.id)
                    .values(
                        metadata_={"conflict_group": group, "condition": "exception"}
                    )
                )
            elif mutation == "version":
                changed = LONG.replace(
                    "Do not reopen the transfer after closure.",
                    "Reopen the transfer after closure.",
                )
                target = await external.get(Document, b.id)
                replacements = [
                    Chunk(
                        id=uuid.uuid4(),
                        document_id=b.id,
                        chunk_index=i,
                        content=text,
                        metadata_={"document_version": 2},
                    )
                    for i, text in enumerate([changed[:1292], changed[1171:]])
                ]
                external.add_all(replacements)
                await external.flush()
                await DocumentVersionManager(external).create_version(
                    str(b.id),
                    changed,
                    replacements,
                    workspace_id="ops-a",
                    document=target,
                )
            elif mutation == "new_group_member":
                added, _ = await seed_procedure(external)
                added.metadata_ = {"conflict_group": group}
            else:
                await external.execute(
                    delete(collection_documents).where(
                        collection_documents.c.collection_id == collection.id,
                        collection_documents.c.document_id == b.id,
                    )
                )
            await external.commit()

    return payload, mutate


def events(body):
    return [
        json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")
    ]


async def assert_saved_refusal(db, client, final):
    saved = (await client.get(f"/api/queries/{final['id']}")).json()
    assert saved["outcome"] == "refused" and saved["answer"] is None
    assert saved["sources"] == []
    messages = list(
        (
            await db.scalars(
                select(Message).where(
                    Message.conversation_id == uuid.UUID(final["conversation_id"]),
                    Message.role == "assistant",
                )
            )
        ).all()
    )
    assert messages and all(
        m.content == saved["refusal_reason"] and m.sources == [] for m in messages
    )


@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize(
    "mutation", ["condition", "version", "new_group_member", "collection_membership"]
)
async def test_prepared_procedure_change_never_escapes_first_sse_token(
    procedure_client, monkeypatch, stream, mutation
):
    # Missing prepared-evidence gate leaks the stale full body before refusing.
    client, db = procedure_client
    payload, mutate = await setup_group(db, monkeypatch, mutation)
    prepare = connected_query.prepare_answer

    async def prepare_then_mutate(*args):
        await prepare(*args)
        assert args[1].outcome == "completed", args[1].refusal_reason
        await mutate()

    monkeypatch.setattr(connected_query, "prepare_answer", prepare_then_mutate)
    response = await client.post(
        "/api/queries/stream" if stream else "/api/queries", json=payload
    )
    assert response.status_code == 200, response.text
    output = events(response.text) if stream else []
    final = output[-1] if stream else response.json()
    await assert_saved_refusal(db, client, final)
    assert not [event for event in output if event["type"] == "token"]
    assert not [event for event in output if event["type"] == "citations"]
    assert final["refused"] and final["answer"] is None and final["sources"] == []


@pytest.mark.parametrize("consumed_tokens", [1, 3])
async def test_inspection_change_between_stream_fragments_stops_prepared_output(
    procedure_client, monkeypatch, consumed_tokens
):
    # Checking only once permits later body fragments/citations after a yield.
    client, db = procedure_client
    payload, mutate = await setup_group(db, monkeypatch, "condition")
    response = await stream_query(QueryRequest(**payload), db, PRINCIPAL)
    for _ in range(consumed_tokens):
        first = events(await anext(response.body_iterator))
        assert first[0]["type"] == "token"
    await mutate()
    remaining = events("".join([piece async for piece in response.body_iterator]))
    assert remaining and remaining[-1]["type"] == "refused"
    assert not [e for e in remaining if e["type"] in {"token", "citations"}]
    await assert_saved_refusal(db, client, remaining[-1])


async def test_cancelling_prepared_procedure_stream_remains_interrupted(
    procedure_client, monkeypatch
):
    # A publication guard must not persist completion or terminal status early.
    _, db = procedure_client
    payload, _ = await setup_group(db, monkeypatch, "condition")
    response = await stream_query(QueryRequest(**payload), db, PRINCIPAL)
    assert events(await anext(response.body_iterator))[0]["type"] == "token"
    await response.body_iterator.aclose()
    rows = list((await db.scalars(select(Query))).all())
    assert len(rows) == 1
    assert rows[0].outcome == "interrupted" and rows[0].answer is None
    assert rows[0].sources == []
    assert list((await db.scalars(select(Message))).all()) == []
