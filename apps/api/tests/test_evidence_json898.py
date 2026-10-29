"""UNITONLY legacy checksum compatibility and bounded recognition policy."""

import copy
import json

import pytest
from app.api.deps import get_current_user
from app.db import evidence_json as codec
from app.db.session import Base
from app.main import app
from app.models.query import Query
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from tests.test_evidence_json888 import history_client as history_client
from tests.test_evidence_json888 import large_provenance


@pytest.mark.parametrize("column", ["provenance", "retrieval_trace"])
@pytest.mark.parametrize("encoding", [None, "utf-8"])
async def test_legacy_checksum_owned_history_stays_unknown_not_verified(
    history_client, column, encoding
):
    client, factory = history_client
    legacy = {"column": column, "raw_bytes": 100, "sha256": "a" * 64}
    if encoding is not None:
        legacy["encoding"] = encoding
    if column == "retrieval_trace":
        # A trace must still satisfy the unchanged public RetrievalTrace schema.
        # Exact897 separately covers the sparse checksum dictionary at ORM level.
        legacy.update(
            query_embedding_dim=0,
            vector_results=0,
            keyword_results=0,
            reranked_results=0,
            final_context_chunks=0,
            confidence=0,
            latency_ms=0,
        )
    async with factory() as session:
        row = Query(
            question="UNITONLY-898-LEGACY",
            answer="UNITONLY-898-legacy-answer",
            owner_id="UNITONLY-owner",
            workspace_id="unit-space",
            sources=[],
            refused=False,
            **{column: copy.deepcopy(legacy)},
        )
        session.add(row)
        await session.commit()
        ident = row.id
        before = await session.scalar(
            text(f"SELECT {column} FROM queries WHERE id=:id"), {"id": ident.hex}
        )
    for owner, space in (
        ("UNITONLY-foreign", "unit-space"),
        ("UNITONLY-owner", "other"),
    ):
        app.dependency_overrides[get_current_user] = lambda owner=owner, space=space: {
            "id": owner,
            "workspace_id": space,
            "is_admin": False,
        }
        assert (await client.get(f"/api/queries/{ident}")).status_code == 404
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "UNITONLY-owner",
        "workspace_id": "unit-space",
        "is_admin": False,
    }
    response = await client.get(f"/api/queries/{ident}")
    assert response.status_code == 200
    result = response.json()
    assert result["answer"] == "UNITONLY-898-legacy-answer"
    assert result["execution_mode"] == "unknown"
    assert result.get("answer_selection") is None
    assert result.get("presentation_verification") is None
    async with factory() as session:
        after = await session.scalar(
            text(f"SELECT {column} FROM queries WHERE id=:id"), {"id": ident.hex}
        )
    assert after == before == json.dumps(legacy)


@pytest.mark.parametrize("column", ["provenance", "retrieval_trace"])
def test_signal_erasure_is_ambiguous_legacy_but_gzip_remnants_fail_closed(column):
    value = large_provenance()
    if column == "retrieval_trace":
        value = {"provenance": value}
    frame = codec.encode_evidence_json(value, column=column)
    assert codec.load_evidence_json(json.dumps(frame), column=column) == value
    ambiguous = {key: frame[key] for key in ("column", "raw_bytes", "sha256")}
    assert codec.decode_evidence_json(ambiguous, column=column) is ambiguous
    assert (
        codec.encode_evidence_json(copy.deepcopy(ambiguous), column=column) == ambiguous
    )
    for remnant in (
        {**ambiguous, "encoding": "gzip+base64"},
        {**ambiguous, "payload": frame["payload"]},
    ):
        with pytest.raises(codec.EvidenceArchiveError):
            codec.load_evidence_json(json.dumps(remnant), column=column)


@pytest.mark.parametrize("column", ["provenance", "retrieval_trace"])
def test_legacy_checksum_duplicate_keys_keep_last_value_and_raw_bytes(column, tmp_path):
    raw = (
        '{"column":'
        + json.dumps(column)
        + ',"raw_bytes":1,"raw_bytes":100,"sha256":"'
        + "a" * 64
        + '"}'
    )
    expected = {"column": column, "raw_bytes": 100, "sha256": "a" * 64}
    assert codec.load_evidence_json(raw, column=column) == expected
    engine = create_engine("sqlite:///" + (tmp_path / "legacy.sqlite").as_posix())
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            row = Query(question="UNITONLY-898-duplicates")
            session.add(row)
            session.commit()
            ident = row.id
        with engine.begin() as connection:
            connection.execute(
                text(f"UPDATE queries SET {column}=:raw WHERE id=:id"),
                {"raw": raw, "id": ident.hex},
            )
        with Session(engine) as session:
            assert getattr(session.get(Query, ident), column) == expected
            session.commit()
        with engine.connect() as connection:
            assert (
                connection.scalar(
                    text(f"SELECT {column} FROM queries WHERE id=:id"),
                    {"id": ident.hex},
                )
                == raw
            )
    finally:
        engine.dispose()
