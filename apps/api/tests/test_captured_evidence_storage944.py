"""Lossless storage recognition only; this is not evidence certification."""

import json
from copy import deepcopy

import pytest
from app.db.evidence_json import MARKER, decode_evidence_json, encode_evidence_json
from app.db.session import Base
from app.evidence_policy import reading_version
from app.models.query import Query
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def provenance(profile):
    version = reading_version(profile)
    return {
        "answer_selection": {
            "contract": version.requirement,
            "evidence_profile": {
                "contract": version.evidence_profile,
                "evidence_reading_profile": profile,
            },
            "staged_request_inputs": {
                "contract": version.request_inputs or "staged-request-inputs-v1",
                "UNITONLY_UNASSESSED": "Exact 🧭 source bytes\r\n" * 12000,
            },
        }
    }


@pytest.mark.parametrize("profile", ["contextual_source_v3", "contextual_source_v4"])
def test_actual_sql_roundtrip_keeps_new_and_old_staged_proof_bytes(profile):
    engine = create_engine("sqlite:///:memory:")
    actual = provenance(profile)
    trace = {"provenance": deepcopy(actual)}
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            row = Query(
                question="UNITONLY storage", provenance=actual, retrieval_trace=trace
            )
            db.add(row)
            db.commit()
            identifier = row.id
        with engine.connect() as connection:
            raw = connection.execute(
                text("SELECT provenance,retrieval_trace FROM queries WHERE id=:id"),
                {"id": identifier.hex},
            ).one()
        for serialized, expected, column in zip(
            raw, (actual, trace), ("provenance", "retrieval_trace"), strict=True
        ):
            frame = json.loads(serialized)
            assert frame.get(MARKER) == 1
            assert decode_evidence_json(frame, column=column) == expected
        with Session(engine) as db:
            restored = db.get(Query, identifier)
            assert restored.provenance == actual
            assert restored.retrieval_trace == trace
    finally:
        engine.dispose()


@pytest.mark.parametrize("damage", ["unknown", "mixed_version", "legacy"])
def test_unrecognized_profile_is_not_silently_reclassified_for_storage(damage):
    value = provenance("contextual_source_v4")
    selection = value["answer_selection"]
    if damage == "unknown":
        selection["evidence_profile"]["evidence_reading_profile"] = "future_unknown"
    elif damage == "mixed_version":
        selection["evidence_profile"]["contract"] = "evidence-profile-v8"
    else:
        selection["contract"] = "requirement-evidence-v2"
    assert encode_evidence_json(value, column="provenance") is value
