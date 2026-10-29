"Explicit negative scope and relative deadlines cannot establish other facts."

import uuid

import pytest
from app.config import get_settings
from app.models.chunk import Chunk
from app.models.document import Document
from app.services.answer_reader import (
    LocalReader,
    ReaderSelection,
    passage_span,
    reader_service,
)
from app.services.reader_questions import mismatch_reason
from sqlalchemy import select

from tests.test_connected_contract import upload

pytest_plugins = ["tests.test_connected_contract"]


def test_review_duration_cannot_be_a_reservation_cutoff():
    source = (
        "The Aurora coordinator accepts reservations until four "
        "days before the session."
    )
    raw = "four days"
    start = source.index(raw)
    assert (
        mismatch_reason(
            "How long does the Aurora review take?", source, start, start + len(raw)
        )
        is not None
    )


def test_explicit_advance_deadline_question_keeps_its_valid_interval():
    source = (
        "The Aurora coordinator accepts reservations until four "
        "days before the session."
    )
    start = source.index("four days")
    assert (
        mismatch_reason(
            "How long before the Aurora session must I reserve?",
            source,
            start,
            start + 9,
        )
        is None
    )


def test_actual_wait_duration_with_after_qualifier_is_not_a_deadline():
    source = "The Aurora reviewer waits four days after cleaning the fixture."
    start = source.index("four days")
    assert (
        mismatch_reason(
            "How long does the Aurora reviewer wait?", source, start, start + 9
        )
        is None
    )


def test_explicit_outside_scope_statement_rejects_unrelated_exception():
    source = (
        "For the Aurora exception, attach the marker to the "
        "inner edge. This exception is outside the standard "
        "review procedure."
    )
    start = source.index("inner edge")
    assert (
        mismatch_reason(
            "What are the steps for the Aurora standard review?",
            source,
            start,
            start + 10,
        )
        is not None
    )


def test_exception_question_is_not_blocked_by_its_own_scope_statement():
    source = (
        "For the Aurora exception, attach the marker to the "
        "inner edge. This exception is outside the standard "
        "review procedure."
    )
    start = source.index("inner edge")
    assert (
        mismatch_reason(
            "Where should I attach the marker for the Aurora exception?",
            source,
            start,
            start + 10,
        )
        is None
    )


def test_exception_disclaimer_does_not_discard_other_supported_clause():
    source = (
        "Aurora review takes 18 minutes. For the Aurora "
        "exception, attach the marker to the inner edge. This "
        "exception is outside the standard review procedure."
    )
    start = source.index("18 minutes")
    assert (
        mismatch_reason("How long is the Aurora review?", source, start, start + 10)
        is None
    )


@pytest.mark.parametrize("selected_occurrence", ["edge", "continuation"])
async def test_curated_conflicts_keep_their_own_scope(
    real_client, monkeypatch, selected_occurrence
):
    client, factory, _ = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")
    texts = [
        "The Aurora standard review takes 18 minutes.",
        (
            "For the Aurora exception, attach the marker to the "
            "inner edge. This exception is outside the standard "
            "review procedure."
        ),
        (
            "For the Aurora exception, attach the marker to the "
            "outer edge. This exception is outside the standard "
            "review procedure."
        ),
    ]
    texts = [
        text + " This instruction applies to the same current practice run."
        if "exception" in text
        else text
        for text in texts
    ]
    documents = [await upload(client, text) for text in texts]
    async with factory() as db:
        for document in documents[1:]:
            row = await db.get(Document, uuid.UUID(document["id"]))
            row.metadata_ = {**row.metadata_, "conflict_group": "aurora-exception"}
        for chunk in (await db.scalars(select(Chunk))).all():
            if str(chunk.document_id) in {d["id"] for d in documents[1:]}:
                chunk.metadata_ = {
                    **(chunk.metadata_ or {}),
                    "conflict_group": "aurora-exception",
                }
        await db.commit()
    local = LocalReader()

    def prediction(question, context, config):
        raw = (
            "18 minutes"
            if "18 minutes" in context
            else "inner edge"
            if "inner edge" in context
            else "outer edge"
        )
        if selected_occurrence == "continuation" and "exception" in context:
            raw = "same current practice run"
        start = context.index(raw)
        return ReaderSelection(
            passage_span(context, start, start + len(raw)),
            {
                "decision": "answer",
                "null_margin": -10.0,
                "raw_span": {"start": start, "end": start + len(raw)},
            },
        )

    monkeypatch.setattr(local, "_context", prediction)

    async def selections(question, contexts, config=None):
        return local._parts(question, contexts, config or get_settings())

    monkeypatch.setattr(reader_service, "select", selections)
    for question, outcome in [
        ("How long is the Aurora standard review procedure?", "completed"),
        ("Which edge is required for the Aurora exception?", "refused"),
    ]:
        response = await client.post(
            "/api/queries",
            json={
                "question": question,
                "document_ids": [d["id"] for d in documents],
                "retrieval_method": "keyword",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["outcome"] == outcome, response.text
        if outcome == "completed":
            assert "18 minutes" in response.json()["answer"]


def test_physical_outside_location_is_not_a_procedural_scope_exclusion():
    source = (
        "Wait in the courtyard. This courtyard is outside the standard review room."
    )
    start = source.index("courtyard")
    assert (
        mismatch_reason(
            "Where should I wait for the standard review?", source, start, start + 9
        )
        is None
    )


def test_repeated_duration_is_bound_to_its_selected_occurrence():
    source = (
        "The Aurora reviewer works four days and takes reservations "
        "until four days before the session."
    )
    first = source.index("four days")
    second = source.rindex("four days")
    question = "How long does the Aurora reviewer work?"
    assert mismatch_reason(question, source, first, first + 9) is None
    assert mismatch_reason(question, source, second, second + 9) is not None


def test_linked_instruction_retains_its_explicit_excluded_scope():
    source = (
        "For the Aurora exception, attach the marker to the inner edge. "
        "This exception is outside the standard review procedure. "
        "This instruction applies to the same current practice run."
    )
    raw = "same current practice run"
    start = source.index(raw)
    assert (
        mismatch_reason(
            "What are the steps for the Aurora standard review?",
            source,
            start,
            start + len(raw),
        )
        is not None
    )


def test_new_named_subject_breaks_scope_inheritance():
    source = (
        "For the Aurora exception, attach the marker to the inner edge. "
        "This exception is outside the standard review procedure. "
        "This instruction for Borealis review takes 18 minutes."
    )
    start = source.index("18 minutes")
    assert (
        mismatch_reason("How long is the Borealis review?", source, start, start + 10)
        is None
    )


def test_own_exception_question_keeps_linked_instruction_for_conflict_review():
    source = (
        "For the Aurora exception, attach the marker to the inner edge. "
        "This exception is outside the standard review procedure. "
        "This instruction applies to the same current practice run."
    )
    start = source.index("same current practice run")
    assert (
        mismatch_reason(
            "Which instruction applies to the Aurora exception?",
            source,
            start,
            start + 25,
        )
        is None
    )


def test_single_letter_new_subject_breaks_exclusion_inheritance():
    source = (
        "For the Aurora exception, attach the marker to the inner edge. "
        "This exception is outside the standard review procedure. "
        "This instruction for X review takes 18 minutes."
    )
    start = source.index("18 minutes")
    assert (
        mismatch_reason("How long is the X review?", source, start, start + 10) is None
    )


def test_lettered_instruction_reference_retains_its_existing_scope():
    source = (
        "For the Aurora exception, attach the marker to the inner edge. "
        "This exception is outside the standard review procedure. "
        "This instruction applies to the same current practice run as instruction B."
    )
    raw = "same current practice run"
    start = source.index(raw)
    assert (
        mismatch_reason(
            "What are the steps for the Aurora standard review?",
            source,
            start,
            start + len(raw),
        )
        is not None
    )
