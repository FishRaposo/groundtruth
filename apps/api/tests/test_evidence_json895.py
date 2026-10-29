"""UNITONLY partial framing and raw JSON driver-boundary regressions."""

import copy
import itertools
import json

import pytest
from app.db import evidence_json as codec
from app.models.query import Query
from sqlalchemy import create_engine, select, text
from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg
from sqlalchemy.orm import Session

from tests.test_evidence_json888 import history_client as history_client
from tests.test_evidence_json888 import large_provenance


@pytest.mark.parametrize("column", ["provenance", "retrieval_trace"])
@pytest.mark.parametrize(
    "removed",
    list(
        itertools.combinations(
            ["column", "encoding", "raw_bytes", "sha256", "payload"], 2
        )
    ),
)
def test_partial_frame_three_remaining_fields_cannot_become_legacy(column, removed):
    original = large_provenance()
    if column == "retrieval_trace":
        original = {"provenance": original}
    value = codec.encode_evidence_json(original, column=column)
    del value[codec.MARKER]
    for key in removed:
        del value[key]
    if removed == ("encoding", "payload"):
        # Root898: erasing all codec signals is identical to old checksum data.
        # New898 HTTP controls retain unknown verification and foreign404 scope.
        assert codec.decode_evidence_json(value, column=column) is value
        assert codec.encode_evidence_json(copy.deepcopy(value), column=column) == value
        return
    with pytest.raises(codec.EvidenceArchiveError):
        codec.decode_evidence_json(value, column=column)


def test_postgresql_select_preserves_raw_json_before_asyncpg_decode():
    # JSON driver codecs otherwise discard duplicate object keys before ORM code.
    dialect = PGDialect_asyncpg()
    compiled = str(
        select(Query.provenance, Query.retrieval_trace).compile(dialect=dialect)
    )
    assert "CAST(queries.provenance AS TEXT)" in compiled
    assert "CAST(queries.retrieval_trace AS TEXT)" in compiled
    assert "->>" in str(
        select(Query.provenance["legacy"].as_string()).compile(dialect=dialect)
    )


@pytest.mark.parametrize("column", ["provenance", "retrieval_trace"])
@pytest.mark.parametrize(
    "field", [codec.MARKER, "column", "encoding", "raw_bytes", "sha256", "payload"]
)
def test_duplicate_frame_fields_rejected_through_actual_sql(column, field, tmp_path):
    from app.db.session import Base

    value = large_provenance()
    if column == "retrieval_trace":
        value = {"provenance": value}
    frame = codec.encode_evidence_json(value, column=column)
    raw = "{" + json.dumps(field) + ":null," + json.dumps(frame)[1:]
    engine = create_engine("sqlite:///" + (tmp_path / "duplicate.sqlite").as_posix())
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            row = Query(question="UNITONLY-895")
            session.add(row)
            session.commit()
            ident = row.id
        with engine.begin() as connection:
            connection.execute(
                text(f"UPDATE queries SET {column}=:raw WHERE id=:id"),
                {"raw": raw, "id": ident.hex},
            )
        with Session(engine) as session, pytest.raises(codec.EvidenceArchiveError):
            session.get(Query, ident)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "legacy",
    [
        {
            "column": "amount",
            "encoding": "utf-8",
            "raw_bytes": 100,
            "sha256": "not-an-archive",
        },
        {"column": "amount", "encoding": "utf-8", "payload": {"old": True}},
        {"column": "provenance", "unitonly": True},
        {"column": "provenance", "encoding": "utf-8", "payload": "generic text"},
        {"column": "retrieval_trace", "encoding": "utf-8", "raw_bytes": 100},
        {"sha256": "a" * 64, "raw_bytes": 100},
        {"encoding": "gzip+base64", "note": "an ordinary legacy annotation"},
    ],
)
def test_generic_legacy_metadata_is_not_reserved_framing(legacy):
    assert codec.decode_evidence_json(legacy, column="provenance") is legacy
    assert (
        codec.encode_evidence_json(copy.deepcopy(legacy), column="provenance") == legacy
    )


async def test_both_corrupt_columns_own_safe503_foreign404(history_client):
    from app.api.deps import get_current_user
    from app.main import app

    client, factory = history_client
    for column in ("provenance", "retrieval_trace"):
        value = large_provenance()
        if column == "retrieval_trace":
            value = {"provenance": value}
        damaged = codec.encode_evidence_json(value, column=column)
        del damaged[codec.MARKER]
        del damaged["payload"]
        async with factory() as session:
            row = Query(
                question="UNITONLY-895",
                answer="UNITONLY-SECRET-895",
                owner_id="UNITONLY-owner",
                workspace_id="unit-space",
                sources=[],
                refused=False,
            )
            session.add(row)
            await session.commit()
            ident = row.id
            await session.execute(
                text(f"UPDATE queries SET {column}=:raw WHERE id=:id"),
                {"raw": json.dumps(damaged), "id": ident.hex},
            )
            await session.commit()
        for owner, status in (("UNITONLY-foreign", 404), ("UNITONLY-owner", 503)):
            app.dependency_overrides[get_current_user] = lambda owner=owner: {
                "id": owner,
                "workspace_id": "unit-space",
                "is_admin": False,
            }
            result = await client.get(f"/api/queries/{ident}")
            assert result.status_code == status
            assert "UNITONLY-SECRET-895" not in result.text


@pytest.mark.parametrize("column", ["provenance", "retrieval_trace"])
def test_shared_raw_decoder_preserves_legacy_duplicates_and_rejects_frames(column):
    # Plain JSON keeps pre-existing last-value semantics, including nested JSON.
    raw = '{"column":"generic","column":"other","nested":{"k":1,"k":2}}'
    assert codec.load_evidence_json(raw, column=column) == {
        "column": "other",
        "nested": {"k": 2},
    }
    original = large_provenance()
    if column == "retrieval_trace":
        original = {"provenance": original}
    frame = codec.encode_evidence_json(original, column=column)
    assert codec.load_evidence_json(json.dumps(frame), column=column) == original
    duplicate = '{"' + codec.MARKER + '":999,' + json.dumps(frame)[1:]
    with pytest.raises(codec.EvidenceArchiveError):
        codec.load_evidence_json(duplicate, column=column)


async def test_installed_asyncpg_codec_is_lossy_but_text_projection_processor_is_not():
    # Exercise installed SQLAlchemy codec setup without any PostgreSQL connection.
    class Capture:
        async def set_type_codec(self, name, **settings):
            self.name = name
            self.settings = settings

    connection = Capture()
    adapter = type("Adapter", (), {"_connection": connection})()
    dialect = PGDialect_asyncpg()
    await dialect.setup_asyncpg_json_codec(adapter)
    assert connection.name == "json"
    frame = codec.encode_evidence_json(large_provenance(), column="provenance")
    raw = '{"' + codec.MARKER + '":999,' + json.dumps(frame)[1:]
    assert connection.settings["decoder"](raw.encode())[codec.MARKER] == 1
    adapted_type = Query.__table__.c.provenance.type.dialect_impl(dialect)
    processor = adapted_type.result_processor(dialect, None)
    with pytest.raises(codec.EvidenceArchiveError):
        processor(raw)
    assert processor(json.dumps(frame)) == large_provenance()
    assert str(Query.__table__.c.provenance.type.compile(dialect=dialect)) == "JSON"


@pytest.mark.parametrize("raw", [None, "null", '"UNITONLY"', "42", "false", "[]"])
def test_text_projection_preserves_plain_json_scalars(raw, tmp_path):
    from app.db.session import Base

    engine = create_engine("sqlite:///" + (tmp_path / "plain.sqlite").as_posix())
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            row = Query(question="UNITONLY-895-scalars")
            session.add(row)
            session.commit()
            ident = row.id
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE queries SET provenance=:raw WHERE id=:id"),
                {"raw": raw, "id": ident.hex},
            )
            stored = connection.scalar(
                text("SELECT provenance FROM queries WHERE id=:id"),
                {"id": ident.hex},
            )
        with Session(engine) as session:
            restored = session.get(Query, ident)
            assert restored.provenance == (json.loads(raw) if raw is not None else None)
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT provenance FROM queries WHERE id=:id"),
                    {"id": ident.hex},
                )
                == stored
            )
    finally:
        engine.dispose()
