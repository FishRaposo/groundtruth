"""Independent bounded procedure-prior and interval probes; no model."""

import pytest
from app.config import get_settings
from app.services.answer_reader import (
    LocalReader,
    ReaderSelection,
    passage_span,
    reader_service,
)
from app.services.reader_questions import mismatch_reason
from app.services.reader_support import procedure_features

from tests.test_connected_contract import upload

pytest_plugins = ["tests.test_connected_contract"]


async def test_unrelated_sequence_for_other_subject_cannot_promote_booking(
    real_client, monkeypatch
):
    client, _, _ = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")
    procedure = (
        "Orion valve inspection: Isolate the console. Inspect the seal. "
        "Photograph its edges. Sign the inspection card."
    )
    booking = (
        "Orion valve inspection is booked on Tuesday at 09:20. Return the "
        "card to drawer Q8 after the session.\n\nOffice closing: First, lock"
        " the desk. Next, turn off the lights."
    )
    docs = [await upload(client, text) for text in (procedure, booking)]
    local = LocalReader()

    def prediction(question, context, config):
        actual = "Isolate the console" in context
        raw = "Isolate the console" if actual else "Return the card to drawer Q8"
        start = context.index(raw)
        span = passage_span(context, start, start + len(raw))
        if not actual:
            assert procedure_features(question, context)["explicit_sequence"] is True
        return ReaderSelection(
            span,
            {
                "decision": "answer",
                "null_margin": -10 if actual else -1,
                "raw_span": {"start": start, "end": start + len(raw), "text": raw},
            },
        )

    monkeypatch.setattr(local, "_context", prediction)

    async def predictions(question, contexts, config=None):
        return local._parts(question, contexts, config or get_settings())

    monkeypatch.setattr(reader_service, "select", predictions)
    response = await client.post(
        "/api/queries",
        json={
            "question": "What are the steps for Orion valve inspection?",
            "document_ids": [d["id"] for d in docs],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "completed"
    assert procedure in body["answer"], body["answer"]
    assert "drawer Q8" not in body["answer"]


@pytest.mark.parametrize(
    "raw",
    ["09:20 to 10:30", "09:20–10:30", "09:20 - 10:30", "Tuesday from 09:20 to 10:30"],
)
def test_time_range_rejects_count_but_preserves_when(raw):
    text = "Orion inspection is scheduled " + raw + "."
    start = text.index(raw)
    assert (
        mismatch_reason(
            "What is the official box count for Orion?", text, start, start + len(raw)
        )
        is not None
    )
    assert (
        mismatch_reason(
            "When is Orion inspection scheduled?", text, start, start + len(raw)
        )
        is None
    )


def test_elapsed_range_cannot_be_inferred_from_schedule():
    text = "Orion inspection is scheduled from 09:20 to 10:30."
    raw = "09:20 to 10:30"
    start = text.index(raw)
    assert (
        mismatch_reason("What is its elapsed time?", text, start, start + len(raw))
        == "start_clock_is_not_elapsed_duration"
    )


def test_long_procedure_with_range_is_not_rejected_as_exact_time():
    text = (
        "First, inspect Orion. Next, wait from 09:20 to 10:30. Finally, "
        "log the inspection."
    )
    assert (
        mismatch_reason("What are the steps for Orion inspection?", text, 0, len(text))
        is None
    )


async def test_ingested_numbered_procedure_keeps_sequence_preference(
    real_client, monkeypatch
):
    client, _, _ = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")
    question = "What are the steps for Orion valve inspection?"
    numbered = (
        "Orion valve inspection:\n1. Isolate the console.\n2. Inspect the "
        "seal.\n3. Photograph its edges."
    )
    booking = (
        "Orion valve inspection is booked on Tuesday at 09:20. Return the "
        "card to drawer Q8 after the session."
    )
    assert procedure_features(question, numbered)["explicit_sequence"] is True
    docs = [await upload(client, text) for text in (numbered, booking)]
    local = LocalReader()
    observed = []

    def prediction(question, context, config):
        actual = "Isolate the console" in context
        raw = "Isolate the console" if actual else "Return the card to drawer Q8"
        start = context.index(raw)
        if actual:
            observed.append(procedure_features(question, context))
        return ReaderSelection(
            passage_span(context, start, start + len(raw)),
            {
                "decision": "answer",
                "null_margin": -2 if actual else -10,
                "raw_span": {"start": start, "end": start + len(raw), "text": raw},
            },
        )

    monkeypatch.setattr(local, "_context", prediction)

    async def predictions(question, contexts, config=None):
        return local._parts(question, contexts, config or get_settings())

    monkeypatch.setattr(reader_service, "select", predictions)
    response = await client.post(
        "/api/queries",
        json={
            "question": question,
            "document_ids": [d["id"] for d in docs],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "completed"
    assert "Isolate the console" in body["answer"], {
        "answer": body["answer"],
        "actual_ingested_features": observed,
    }
    assert "drawer Q8" not in body["answer"]
