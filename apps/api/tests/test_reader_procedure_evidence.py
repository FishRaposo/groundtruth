"""Sequence formatting can rank accepted procedure evidence above a booking."""

from app.config import get_settings
from app.models.query import AnswerSpan
from app.services.answer_reader import LocalReader, ReaderSelection, reader_service
from app.services.reader_questions import mismatch_reason
from app.services.reader_support import procedure_features
from app.services.reader_witnesses import select_witness_cover

from tests.test_connected_contract import upload

pytest_plugins = ["tests.test_connected_contract"]


async def test_ordered_steps_prefer_accepted_procedure_over_booking(
    real_client, monkeypatch
):
    client, _, _ = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")
    procedure = (
        "Nova seal inspection: First, isolate the console. Next, inspect the seal. "
        "Then, photograph its edges. Finally, sign the inspection card."
    )
    booking = (
        "Nova seal inspection is booked on Tuesday at 09:20. "
        "Return the card to drawer Q8 after the session."
    )
    docs = [await upload(client, text) for text in (procedure, booking)]
    local = LocalReader()

    def prediction(question, context, config):
        ordered = "First," in context
        raw = "isolate the console" if ordered else "Return the card to drawer Q8"
        start = context.index(raw)
        return ReaderSelection(
            AnswerSpan(start=0, end=len(context), text=context),
            {
                "decision": "answer",
                "null_margin": -4 if ordered else -10,
                "raw_span": {"start": start, "end": start + len(raw), "text": raw},
            },
        )

    monkeypatch.setattr(local, "_context", prediction)

    async def select(question, contexts, config=None):
        return local._parts(question, contexts, config or get_settings())

    monkeypatch.setattr(reader_service, "select", select)
    response = await client.post(
        "/api/queries",
        json={
            "question": "What are the steps for Nova seal inspection?",
            "document_ids": [document["id"] for document in docs],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    row = response.json()
    assert row["outcome"] == "completed"
    assert procedure in row["answer"]
    assert "drawer Q8" not in row["answer"]


def test_clock_interval_cannot_establish_requested_count():
    text = "Nova stocktaking is scheduled from 09:20 to 10:30."
    raw = "09:20 to 10:30"
    start = text.index(raw)
    assert (
        mismatch_reason(
            "What is the official box count for Nova?", text, start, start + len(raw)
        )
        is not None
    )


def test_clock_interval_remains_valid_for_a_when_question():
    text = "Nova stocktaking is scheduled from 09:20 to 10:30."
    raw = "09:20 to 10:30"
    start = text.index(raw)
    assert (
        mismatch_reason(
            "When is Nova stocktaking scheduled?", text, start, start + len(raw)
        )
        is None
    )


def test_unmarked_procedure_keeps_existing_accepted_evidence_behavior():
    features = procedure_features(
        "How do I inspect Nova seals?", "Isolate the console. Inspect the seal."
    )
    assert features["requested"] is True
    assert features["explicit_sequence"] is False
    span = AnswerSpan(start=0, end=4, text="text")
    selection = ReaderSelection(
        span,
        {
            "part_count": 1,
            "covered_parts": [0],
            "parts": [{"index": 0, "null_margin": -5, "procedure_evidence": features}],
        },
    )
    assert select_witness_cover([selection]).indices == (0,)


def test_numbered_sequence_does_not_change_a_nonprocedural_request():
    features = procedure_features(
        "When is Nova inspection?", "1. Isolate the console.\n2. Inspect the seal."
    )
    assert features["explicit_sequence"] is True
    assert features["requested"] is False


def test_null_optional_legacy_features_keep_margin_compatibility():
    span = AnswerSpan(start=0, end=4, text="text")
    selections = [
        ReaderSelection(
            span,
            {
                "part_count": 1,
                "covered_parts": [0],
                "parts": [
                    {"index": 0, "null_margin": score, "procedure_evidence": None}
                ],
            },
        )
        for score in (-1, -9)
    ]
    assert select_witness_cover(selections).indices == (1,)


def test_bulleted_sequence_survives_ingestion_whitespace_normalization():
    from app.services.document_intelligence import normalize_content

    canonical = normalize_content(
        "Nova seal inspection:\n- Isolate the console.\n"
        "- Inspect the seal.\n- Photograph its edges."
    )
    start = canonical.index("Isolate")
    result = procedure_features(
        "What are the steps for Nova seal inspection?",
        canonical,
        start=start,
        end=start + len("Isolate the console"),
        anchors=("nova",),
    )
    assert result["selected_sequence"] is True
