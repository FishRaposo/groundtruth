from app.services.reader_questions import mismatch_reason, question_parts


def test_nominal_list_preserves_postposed_topic_qualifier():
    orion = question_parts("Give me the opening time and the closing time for Orion.")
    vela = question_parts("Give me the opening time and the closing time for Vela.")
    print("POSTPOSED_TOPIC", {"orion": orion, "vela": vela})
    assert orion[0].question != vela[0].question, (
        "Opening-time subquestion lost the explicitly requested entity"
    )


def test_responsible_party_can_be_a_weekday_shift_team():
    text = "The Monday shift supervisor approves Orion access."
    raw = "The Monday shift supervisor"
    start = text.index(raw)
    actual = mismatch_reason(
        "Who approves Orion access?", text, start, start + len(raw)
    )
    print("WEEKDAY_OWNER", actual)
    assert actual is None


def test_procedure_can_include_a_required_clock_time():
    text = "At 09:00, isolate the line, inspect the valve, then record the result."
    actual = mismatch_reason(
        "What are the steps for Orion inspection?", text, 0, len(text)
    )
    print("TIMED_PROCEDURE", actual)
    assert actual is None


def test_price_question_can_ask_for_a_cause_not_a_quantity():
    text = "Stock availability changes the price."
    raw = "Stock availability"
    actual = mismatch_reason("What condition changes the price?", text, 0, len(raw))
    print("PRICE_CAUSE", actual)
    assert actual is None


def test_missing_orion_opening_cannot_be_borrowed_from_vela(monkeypatch):
    from app.config import Settings
    from app.models.query import AnswerSpan
    from app.services.answer_reader import LocalReader, ReaderSelection

    contexts = ["Vela opens at ten.", "Orion closes at seventeen."]
    reader = LocalReader()

    def predict(question, context, config):
        if "opening" in question and context.startswith("Vela"):
            raw = "ten"
        elif "closing" in question and context.startswith("Orion"):
            raw = "seventeen"
        else:
            return ReaderSelection(None, {})
        start = context.index(raw)
        return ReaderSelection(
            AnswerSpan(start=0, end=len(context), text=context),
            {
                "decision": "answer",
                "raw_span": {"start": start, "end": start + len(raw), "text": raw},
            },
        )

    monkeypatch.setattr(reader, "_context", predict)
    result = reader._parts(
        "Give me the opening time and the closing time for Orion.", contexts, Settings()
    )
    print(
        "CROSS_ENTITY_NOMINAL_ANSWER",
        [item.span.text if item.span else None for item in result],
    )
    assert all(item.span is None for item in result), (
        "Missing requested Orion opening time was replaced by Vela opening evidence"
    )
