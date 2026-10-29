from app.config import Settings
from app.services.answer_reader import LocalReader, ReaderSelection, passage_span


def selected(context, raw):
    start = context.index(raw)
    end = start + len(raw)
    return ReaderSelection(
        passage_span(context, start, end),
        {
            "decision": "answer",
            "null_margin": -9,
            "raw_span": {"start": start, "end": end, "text": raw},
        },
    )


def evaluate(monkeypatch, question, context, raw):
    service = LocalReader()
    monkeypatch.setattr(service, "_context", lambda q, c, s: selected(c, raw))
    return service._parts(question, [context], Settings())[0]


def test_nonspatial_rely_on_person_is_not_rejected_as_location(monkeypatch):
    result = evaluate(
        monkeypatch,
        "Who provides Aster support?",
        "We rely on Morgan for Aster support.",
        "Morgan",
    )
    print("RELY_ON_DIAGNOSTICS", result.diagnostics)
    assert result.span is not None, (
        "The preposition on in rely on introduces a responsible person, "
        "not a spatial object"
    )


def test_repeated_subject_explanation_can_follow_supporting_instruction(monkeypatch):
    context = "Press the green button. The green button resets Aster controls."
    result = evaluate(
        monkeypatch,
        "What action resets Aster controls?",
        context,
        "Press the green button",
    )
    print("REPEATED_SUBJECT_DIAGNOSTICS", result.diagnostics)
    assert result.span is not None, (
        "Later explicit explanation binds the same green button to Aster controls "
        "without a demonstrative pronoun"
    )


def test_temporal_modifier_does_not_change_requested_physical_attribute(monkeypatch):
    context = "Aster purge is scheduled on Tuesday at 07:30."
    result = evaluate(
        monkeypatch,
        "What airflow rate is required during the scheduled Aster purge?",
        context,
        "07:30",
    )
    print("PHYSICAL_ATTRIBUTE_DIAGNOSTICS", result.diagnostics)
    assert result.span is None, (
        "Mentioning scheduled in the subject does not ask for a clock time"
    )
