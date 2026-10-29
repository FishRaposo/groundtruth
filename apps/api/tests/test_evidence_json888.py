"""Lossless history storage/HTTP controls; UNITONLY data, no learned inference."""

import base64
import copy
import gzip
import hashlib
import json
import uuid

import pytest
from app.api.deps import get_current_user
from app.db.session import Base, get_db
from app.main import app
from app.models.query import Query
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

MAGIC = "__groundtruth_evidence_json__"


def large_provenance():
    return {
        "generation_mode": "extractive",
        "answer_selection": {
            "contract": "requirement-evidence-v5",
            "evidence_profile": {
                "contract": "evidence-profile-v8",
                "evidence_reading_profile": "contextual_source_v3",
            },
            "staged_request_inputs": {
                "contract": "staged-request-inputs-v1",
                "unitonly": "UNITONLY 🧪 exact bytes\n" * 12000,
            },
        },
    }


def test_actual_query_storage_compresses_large_v3_and_roundtrips(tmp_path):
    from app.db.evidence_json import decode_evidence_json

    engine = create_engine("sqlite:///" + (tmp_path / "history.sqlite").as_posix())
    value = large_provenance()
    trace = {"provenance": copy.deepcopy(value), "unitonly": True}
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            row = Query(question="UNITONLY", provenance=value, retrieval_trace=trace)
            db.add(row)
            db.commit()
            identifier = row.id
        with engine.connect() as connection:
            raw = connection.execute(
                text("SELECT provenance,retrieval_trace FROM queries WHERE id=:id"),
                {"id": identifier.hex},
            ).one()
        assert json.loads(raw[0]).get(MAGIC) == 1
        assert json.loads(raw[1]).get(MAGIC) == 1
        assert decode_evidence_json(json.loads(raw[0]), column="provenance") == value
        assert (
            decode_evidence_json(json.loads(raw[1]), column="retrieval_trace") == trace
        )
        assert len(raw[0].encode()) < len(json.dumps(value).encode()) // 2
        with Session(engine) as db:
            restored = db.get(Query, identifier)
            assert restored.provenance == value
            assert restored.retrieval_trace == trace
            assert restored.provenance is not restored.retrieval_trace["provenance"]
    finally:
        engine.dispose()


@pytest.fixture
async def history_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def database():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "UNITONLY-owner",
        "workspace_id": "unit-space",
        "is_admin": False,
    }
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://unit.test",
        ) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def test_normal_history_json_gzip_keeps_decoded_response(history_client):
    client, factory = history_client
    async with factory() as db:
        row = Query(
            question="UNITONLY",
            answer="UNITONLY legacy answer",
            owner_id="UNITONLY-owner",
            workspace_id="unit-space",
            sources=[],
            provenance={"unitonly": "x" * 5000},
            refused=False,
        )
        db.add(row)
        await db.commit()
        identifier = row.id
    plain = await client.get(
        f"/api/queries/{identifier}", headers={"Accept-Encoding": "identity"}
    )
    zipped = await client.get(
        f"/api/queries/{identifier}", headers={"Accept-Encoding": "gzip"}
    )
    assert plain.status_code == zipped.status_code == 200
    assert zipped.headers.get("content-encoding") == "gzip"
    assert "Accept-Encoding" in zipped.headers.get("vary", "")
    assert zipped.json() == plain.json()
    assert "content-encoding" not in plain.headers


async def test_corrupt_archive_is_safe503_only_after_owned_scope(history_client):
    client, factory = history_client
    async with factory() as db:
        row = Query(
            question="UNITONLY_PRIVATE_QUESTION",
            answer="UNITONLY_PRIVATE_ANSWER",
            owner_id="UNITONLY-owner",
            workspace_id="unit-space",
            sources=[],
            refused=False,
        )
        db.add(row)
        await db.commit()
        identifier = row.id
        await db.execute(
            text("UPDATE queries SET provenance=:value WHERE id=:id"),
            {
                "value": json.dumps(
                    {MAGIC: 999, "payload": "UNITONLY_PRIVATE_ARCHIVE"}
                ),
                "id": identifier.hex,
            },
        )
        await db.commit()
    missing = await client.get(f"/api/queries/{uuid.uuid4()}")
    assert missing.status_code == 404
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "UNITONLY-foreign",
        "workspace_id": "unit-space",
        "is_admin": False,
    }
    foreign = await client.get(f"/api/queries/{identifier}")
    assert foreign.status_code == 404
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "UNITONLY-owner",
        "workspace_id": "other-space",
        "is_admin": False,
    }
    assert (await client.get(f"/api/queries/{identifier}")).status_code == 404
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "UNITONLY-owner",
        "workspace_id": "unit-space",
        "is_admin": False,
    }
    owned = await client.get(f"/api/queries/{identifier}")
    assert owned.status_code == 503
    for token in (
        "UNITONLY_PRIVATE_QUESTION",
        "UNITONLY_PRIVATE_ANSWER",
        "UNITONLY_PRIVATE_ARCHIVE",
    ):
        assert token not in owned.text


def test_self_consistent_nonfinite_archive_is_not_accepted():
    from app.db.evidence_json import EvidenceArchiveError, decode_evidence_json

    value = large_provenance()
    value["unitonly_nonfinite"] = float("nan")
    raw = json.dumps(value).encode()
    archive = {
        MAGIC: 1,
        "column": "provenance",
        "encoding": "gzip+base64",
        "raw_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "payload": base64.b64encode(gzip.compress(raw)).decode(),
    }
    with pytest.raises(EvidenceArchiveError):
        decode_evidence_json(archive, column="provenance")


async def test_malformed_column_json_is_owned_safe503(history_client):
    client, factory = history_client
    async with factory() as db:
        row = Query(
            question="UNITONLY_PRIVATE_BAD_JSON",
            answer="UNITONLY_PRIVATE_BAD_ANSWER",
            owner_id="UNITONLY-owner",
            workspace_id="unit-space",
            sources=[],
        )
        db.add(row)
        await db.commit()
        identifier = row.id
        await db.execute(
            text("UPDATE queries SET provenance=:value WHERE id=:id"),
            {"value": "{not-json", "id": identifier.hex},
        )
        await db.commit()
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "UNITONLY-foreign",
        "workspace_id": "unit-space",
        "is_admin": False,
    }
    assert (await client.get(f"/api/queries/{identifier}")).status_code == 404
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "UNITONLY-owner",
        "workspace_id": "unit-space",
        "is_admin": False,
    }
    response = await client.get(f"/api/queries/{identifier}")
    assert response.status_code == 503
    assert "UNITONLY_PRIVATE" not in response.text and "not-json" not in response.text


def test_legacy_new_and_old_raw_json_bytes_are_unchanged(tmp_path):
    from app.db.evidence_json import decode_evidence_json

    engine = create_engine("sqlite:///" + (tmp_path / "legacy.sqlite").as_posix())
    old_id = uuid.uuid4()
    old_raw = ' { "legacy" : "UNITONLY", "nullable": null } '
    legacy = {
        "answer_selection": {"contract": "requirement-evidence-v4"},
        "unitonly": "🧪" * 40000,
    }
    small = large_provenance()
    small["answer_selection"]["staged_request_inputs"]["unitonly"] = "small"
    try:
        Base.metadata.create_all(engine)
        with engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO queries(id,question,refused,created_at,provenance) "
                    "VALUES(:id,'UNITONLY',1,'2026-10-27 00:00:00',:raw)"
                ),
                {"id": old_id.hex, "raw": old_raw},
            )
        with Session(engine) as db:
            assert db.get(Query, old_id).provenance == {
                "legacy": "UNITONLY",
                "nullable": None,
            }
            assert (
                db.scalar(
                    select(Query.provenance["legacy"].as_string()).where(
                        Query.id == old_id
                    )
                )
                == "UNITONLY"
            )
            db.commit()
            rows = [
                Query(question="UNITONLY", provenance=value)
                for value in (legacy, small, None)
            ]
            db.add_all(rows)
            db.commit()
            ids = [row.id for row in rows]
        with engine.connect() as c:
            assert (
                c.execute(
                    text("SELECT provenance FROM queries WHERE id=:id"),
                    {"id": old_id.hex},
                ).scalar_one()
                == old_raw
            )
            for ident, value in zip(ids, (legacy, small, None), strict=True):
                raw = c.execute(
                    text("SELECT provenance FROM queries WHERE id=:id"),
                    {"id": ident.hex},
                ).scalar_one()
                assert raw == json.dumps(value)
                assert (
                    decode_evidence_json(json.loads(raw), column="provenance") == value
                )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "damage",
    [
        "version",
        "column",
        "encoding",
        "size",
        "oversize",
        "bool_size",
        "sha",
        "base64",
        "truncated",
        "trailing",
        "concatenated",
        "extra",
    ],
)
def test_archive_corruption_never_becomes_plain_legacy(damage):
    from app.db.evidence_json import (
        MAX_JSON_BYTES,
        EvidenceArchiveError,
        decode_evidence_json,
        encode_evidence_json,
    )

    value = encode_evidence_json(large_provenance(), column="provenance")
    if damage == "version":
        value[MAGIC] = 2
    elif damage == "column":
        value["column"] = "retrieval_trace"
    elif damage == "encoding":
        value["encoding"] = "unknown"
    elif damage == "size":
        value["raw_bytes"] -= 1
    elif damage == "oversize":
        value["raw_bytes"] = MAX_JSON_BYTES + 1
    elif damage == "bool_size":
        value["raw_bytes"] = True
    elif damage == "sha":
        value["sha256"] = "0" * 64
    elif damage == "base64":
        value["payload"] = "!invalid"
    elif damage == "extra":
        value["extra"] = "UNITONLY"
    else:
        packed = base64.b64decode(value["payload"])
        packed = (
            packed[:-1]
            if damage == "truncated"
            else packed
            + (b"trailing" if damage == "trailing" else gzip.compress(b"{}"))
        )
        value["payload"] = base64.b64encode(packed).decode()
    with pytest.raises(EvidenceArchiveError):
        decode_evidence_json(value, column="provenance")


def test_bomb_is_bounded_by_declared_size_and_archive_policy(monkeypatch):
    from app.db import evidence_json as codec

    raw = b"x" * (1024 * 1024)
    bomb = {
        MAGIC: 1,
        "column": "provenance",
        "encoding": "gzip+base64",
        "raw_bytes": 8,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "payload": base64.b64encode(gzip.compress(raw)).decode(),
    }
    with pytest.raises(codec.EvidenceArchiveError):
        codec.decode_evidence_json(bomb, column="provenance")
    monkeypatch.setattr(codec, "MAX_JSON_BYTES", 16)
    bomb["raw_bytes"] = 17
    with pytest.raises(codec.EvidenceArchiveError):
        codec.decode_evidence_json(bomb, column="provenance")


def test_swapping_actual_persisted_columns_is_rejected(tmp_path):
    from app.db.evidence_json import EvidenceArchiveError

    engine = create_engine("sqlite:///" + (tmp_path / "swap.sqlite").as_posix())
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            row = Query(
                question="UNITONLY",
                provenance=large_provenance(),
                retrieval_trace={"provenance": large_provenance()},
            )
            db.add(row)
            db.commit()
            ident = row.id
        with engine.begin() as c:
            c.execute(
                text("UPDATE queries SET provenance=retrieval_trace WHERE id=:id"),
                {"id": ident.hex},
            )
        with Session(engine) as db:
            with pytest.raises(EvidenceArchiveError):
                db.get(Query, ident)
    finally:
        engine.dispose()


def test_compressed_pure_output_keeps_independent_verification(monkeypatch):
    # Actual renderer/consumer over UNITONLY graph/NLI fixtures, not real inference.
    from app.db import evidence_json as codec
    from app.services import staged_output as output

    from tests.test_staged_complete_output import complete_fixture

    selection, context = complete_fixture()
    actual = output.build_output(selection, **context)
    selection[output.CERTIFICATE_FIELD] = actual["certificate"]
    monkeypatch.setattr(codec, "MIN_COMPRESS_BYTES", 1)
    provenance = codec.encode_evidence_json(
        {"answer_selection": selection}, column="provenance"
    )
    trace = codec.encode_evidence_json(
        context["query_context"], column="retrieval_trace"
    )
    assert provenance[MAGIC] == trace[MAGIC] == 1
    restored = codec.decode_evidence_json(provenance, column="provenance")[
        "answer_selection"
    ]
    retained = codec.decode_evidence_json(trace, column="retrieval_trace")
    assert output.verify_output(
        restored,
        answer=actual["answer"],
        citations=actual["citations"],
        **{**context, "query_context": retained},
    )
    retained["provenance"]["answer_selection"][output.INPUTS_FIELD]["question"] += (
        " UNITONLY tamper"
    )
    assert not output.verify_output(
        restored,
        answer=actual["answer"],
        citations=actual["citations"],
        **{**context, "query_context": retained},
    )


@pytest.mark.parametrize("channel", ["provenance", "retrieval_trace"])
async def test_encoded_non_cited_planning_body_is_reauthorized(history_client, channel):
    from app.models.document import Document, DocumentStatus, SourceType

    client, factory = history_client
    marker = "UNITONLY_PRIVATE_PLANNING_888"
    async with factory() as db:
        doc = Document(
            title="UNITONLY",
            source_type=SourceType.TEXT,
            status=DocumentStatus.READY,
            owner_id="UNITONLY-owner",
            workspace_id="unit-space",
        )
        db.add(doc)
        await db.flush()
        selection = large_provenance()["answer_selection"]
        selection.update(
            inspected_sources=[], requirements=[], candidates=[], procedure_contexts=[]
        )
        selection["staged_request_inputs"] = {
            "contract": "staged-request-inputs-v1",
            "snapshots": [
                {"identity": {"document_id": str(doc.id)}, "body": marker * 10000}
            ],
            "manifest": {"publications": [{"document_id": str(doc.id)}]},
        }
        value = {"answer_selection": selection}
        row = Query(
            question="UNITONLY",
            owner_id="UNITONLY-owner",
            workspace_id="unit-space",
            refused=True,
            outcome="refused",
            sources=[],
            provenance=value if channel == "provenance" else {},
            retrieval_trace={
                "query_embedding_dim": 32,
                "vector_results": 0,
                "keyword_results": 0,
                "reranked_results": 0,
                "final_context_chunks": 0,
                "confidence": 0,
                "latency_ms": 0,
                "provenance": value,
            }
            if channel == "retrieval_trace"
            else None,
        )
        db.add(row)
        await db.commit()
        identifier = row.id
        doc_id = doc.id
    before = await client.get(f"/api/queries/{identifier}")
    assert before.status_code == 200 and marker in before.text
    async with factory() as db:
        raw = (
            await db.execute(
                text("SELECT " + channel + " FROM queries WHERE id=:id"),
                {"id": identifier.hex},
            )
        ).scalar_one()
        assert json.loads(raw)[MAGIC] == 1
        doc = await db.get(Document, doc_id)
        doc.owner_id = "UNITONLY-foreign"
        await db.commit()
    after = await client.get(f"/api/queries/{identifier}")
    assert after.status_code == 200 and after.json()["evidence_access"] == "restricted"
    assert marker not in after.text and str(doc_id) not in after.text
    assert (
        after.json()["provenance"] is None and after.json()["retrieval_trace"] is None
    )


@pytest.mark.parametrize(
    "media_type,encoded", [("text/event-stream", False), ("application/json", True)]
)
async def test_configured_gzip_preserves_sse_chunks_and_existing_encoding(
    media_type, encoded
):
    from starlette.middleware.gzip import GZipMiddleware

    middleware = next(
        item for item in app.user_middleware if item.cls is GZipMiddleware
    )
    body = b"data: UNITONLY\n\n" * 100
    headers = [(b"content-type", media_type.encode())]
    if encoded:
        headers.append((b"content-encoding", b"gzip"))

    async def endpoint(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": headers})
        await send({"type": "http.response.body", "body": body, "more_body": True})
        await send(
            {
                "type": "http.response.body",
                "body": b"data: done\n\n",
                "more_body": False,
            }
        )

    messages = []

    async def send(message):
        messages.append(copy.deepcopy(message))

    async def receive():
        return {"type": "http.request", "body": b""}

    await GZipMiddleware(endpoint, **middleware.kwargs)(
        {"type": "http", "headers": [(b"accept-encoding", b"gzip")]}, receive, send
    )
    assert [m["body"] for m in messages if m["type"] == "http.response.body"] == [
        body,
        b"data: done\n\n",
    ]
    response_headers = dict(messages[0]["headers"])
    assert response_headers.get(b"content-encoding") == (b"gzip" if encoded else None)


def test_threshold_and_size_policy_boundaries(monkeypatch):
    from app.db import evidence_json as codec

    value = large_provenance()
    body = value["answer_selection"]["staged_request_inputs"]
    body["unitonly"] = ""
    fixed = len(
        json.dumps(
            value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    )
    body["unitonly"] = "x" * (codec.MIN_COMPRESS_BYTES - fixed - 1)
    assert MAGIC not in codec.encode_evidence_json(value, column="provenance")
    body["unitonly"] += "x"
    assert codec.encode_evidence_json(value, column="provenance")[MAGIC] == 1
    monkeypatch.setattr(codec, "MAX_JSON_BYTES", 1024)
    with pytest.raises(codec.EvidenceArchiveError):
        codec.encode_evidence_json(value, column="provenance")


@pytest.mark.parametrize(
    "suffix", [b',"unit":1e999}', b',"unit":Infinity}', b',"unit":1,"unit":2}']
)
def test_coherent_invalid_inner_json_is_rejected(suffix):
    from app.db.evidence_json import EvidenceArchiveError, decode_evidence_json

    raw = json.dumps(large_provenance()).encode()[:-1] + suffix
    archive = {
        MAGIC: 1,
        "column": "provenance",
        "encoding": "gzip+base64",
        "raw_bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "payload": base64.b64encode(gzip.compress(raw)).decode(),
    }
    with pytest.raises(EvidenceArchiveError):
        decode_evidence_json(archive, column="provenance")


@pytest.mark.parametrize("damage", ["missing_marker", "unknown_marker"])
def test_damaged_storage_signature_cannot_downgrade_to_legacy(damage):
    from app.db.evidence_json import (
        EvidenceArchiveError,
        decode_evidence_json,
        encode_evidence_json,
    )

    archive = encode_evidence_json(large_provenance(), column="provenance")
    version = archive.pop(MAGIC)
    if damage == "unknown_marker":
        archive[MAGIC + "_future"] = version
    with pytest.raises(EvidenceArchiveError):
        decode_evidence_json(archive, column="provenance")
