from app.config import Settings
from app.services.answer_reader import LocalReader, ReaderSelection, passage_span


def predict(context, raw, margin=-9):
    start = context.index(raw)
    end = start + len(raw)
    return ReaderSelection(
        passage_span(context, start, end),
        {
            "decision": "answer",
            "null_margin": margin,
            "raw_span": {"start": start, "end": end, "text": raw},
        },
    )


def run(monkeypatch, question, contexts, model):
    reader = LocalReader()
    monkeypatch.setattr(reader, "_context", model)
    return reader._parts(question, contexts, Settings())


def test_duration_cannot_transfer_between_sibling_entities(monkeypatch):
    context = (
        "Aster training mat reset takes 24 minutes. "
        "The mosaic tray has a depth of 3 centimeters."
    )
    result = run(
        monkeypatch,
        "What is the reset duration for the Aster mosaic tray?",
        [context],
        lambda q, c, s: predict(c, "24 minutes"),
    )
    assert result[0].span is None, (
        "A sibling entity's duration cannot establish the requested tray duration"
    )


def test_requested_physical_attribute_cannot_be_established_by_schedule(monkeypatch):
    context = "Aster glider preflight is scheduled on Tuesday at 07:30."
    result = run(
        monkeypatch,
        "What airflow rate is required for Aster glider preflight?",
        [context],
        lambda q, c, s: predict(c, "07:30"),
    )
    assert result[0].span is None, (
        "An exact opening-clock span cannot establish an airflow measurement"
    )


def test_duration_quantity_form_does_not_turn_opening_clock_into_elapsed_time(
    monkeypatch,
):
    context = "Aster workshop opens on Thursday at 16:10."
    result = run(
        monkeypatch,
        "How many minutes is the Aster workshop?",
        [context],
        lambda q, c, s: predict(c, "16:10"),
    )
    assert result[0].span is None, (
        "Equivalent duration wording must preserve the requested attribute"
    )


def test_wrong_owner_span_cannot_claim_compound_owner_coverage(monkeypatch):
    contexts = [
        "Sora owns Aster sessions.",
        "Aster sessions are booked on Tuesday at 07:30. The kit is stored on shelf K4.",
    ]

    def model(question, context, settings):
        if question.lower().startswith("who"):
            return predict(
                context, "Sora" if context.startswith("Sora") else "shelf K4"
            )
        if context.startswith("Sora"):
            return ReaderSelection(None, {"decision": "no_answer"})
        return predict(context, "Tuesday" if "when" in question else "shelf K4")

    result = run(
        monkeypatch,
        "Who owns Aster sessions, when are they booked, and where is the kit stored?",
        contexts,
        model,
    )
    assert 0 in result[0].diagnostics["covered_parts"]
    assert 0 not in result[1].diagnostics["covered_parts"], (
        "A location cannot make the schedule source replace the owner witness"
    )


def test_matching_entity_duration_remains_supported(monkeypatch):
    context = (
        "Aster training mat reset takes 24 minutes. "
        "The mosaic tray has a depth of 3 centimeters."
    )
    result = run(
        monkeypatch,
        "What is the reset duration for the Aster training mat?",
        [context],
        lambda q, c, s: predict(c, "24 minutes"),
    )
    assert result[0].span is not None


def test_opening_clock_remains_supported_for_schedule_question(monkeypatch):
    context = "Aster workshop opens on Thursday at 16:10."
    result = run(
        monkeypatch,
        "When does the Aster workshop open?",
        [context],
        lambda q, c, s: predict(c, "16:10"),
    )
    assert result[0].span is not None


def test_genuine_multiple_document_support_remains_supported(monkeypatch):
    contexts = [
        "Sora owns Aster sessions.",
        "Aster sessions are booked on Tuesday at 07:30. The kit is stored on shelf K4.",
    ]

    def model(question, context, settings):
        if question.lower().startswith("who"):
            return (
                predict(context, "Sora")
                if context.startswith("Sora")
                else ReaderSelection(None, {"decision": "no_answer"})
            )
        if context.startswith("Sora"):
            return ReaderSelection(None, {"decision": "no_answer"})
        return predict(context, "Tuesday" if "when" in question else "shelf K4")

    result = run(
        monkeypatch,
        "Who owns Aster sessions, when are they booked, and where is the kit stored?",
        contexts,
        model,
    )
    assert all(item.span for item in result)
    assert result[0].diagnostics["covered_parts"] == [0]
    assert result[1].diagnostics["covered_parts"] == [1, 2]


def test_following_explanatory_caption_keeps_the_instruction(monkeypatch):
    context = "Press RESET. This procedure applies to Aster controls."
    result = run(
        monkeypatch,
        "What action is required for Aster controls?",
        [context],
        lambda q, c, s: predict(c, "Press RESET"),
    )
    assert result[0].span is not None


def test_passive_owner_role_is_not_a_spatial_object(monkeypatch):
    context = "Aster checks are owned by the Monday shift supervisor."
    result = run(
        monkeypatch,
        "Who owns Aster checks?",
        [context],
        lambda q, c, s: predict(c, "the Monday shift supervisor"),
    )
    assert result[0].span is not None


def test_elapsed_answer_need_not_contain_a_number(monkeypatch):
    context = "Aster holding lasts overnight."
    result = run(
        monkeypatch,
        "What is the Aster holding duration?",
        [context],
        lambda q, c, s: predict(c, "overnight"),
    )
    assert result[0].span is not None
