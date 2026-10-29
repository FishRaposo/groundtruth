"""Complete compound evidence and reject obvious cross-attribute borrowing."""

from app.config import Settings
from app.models.query import AnswerSpan
from app.services.answer_reader import LocalReader, ReaderSelection

from tests.test_connected_contract import upload

pytest_plugins = ["tests.test_connected_contract"]


def selected(text, raw=None):
    raw = raw or text
    return ReaderSelection(
        AnswerSpan(start=0, end=len(text), text=text),
        {
            "decision": "answer",
            "null_margin": -10.0,
            "raw_span": {
                "start": text.index(raw),
                "end": text.index(raw) + len(raw),
                "text": raw,
            },
            "windows": 1,
        },
    )


def reader_with(monkeypatch, predict):
    reader = LocalReader()
    monkeypatch.setattr(reader, "_load", lambda config: None)
    monkeypatch.setattr(reader, "_context", predict)
    return reader


def test_compound_request_retains_both_document_answers(monkeypatch):
    contexts = ["Orion lockers are assigned by Sam.", "Vela seals last twelve hours."]

    def predict(question, context, config):
        if " and " in question:
            return ReaderSelection(None, {"decision": "no_answer"})
        if "who" in question.lower() and "Orion" in context:
            return selected(context, "Sam")
        if "how long" in question.lower() and "Vela" in context:
            return selected(context, "twelve hours")
        return ReaderSelection(None, {"decision": "no_answer"})

    reader = reader_with(monkeypatch, predict)
    result = reader._read(
        "Who assigns Orion lockers, and how long do Vela seals last?",
        contexts,
        Settings(),
    )
    assert [r.span.text if r.span else None for r in result] == contexts


def test_supported_first_part_cannot_hide_missing_second_part(monkeypatch):
    def predict(question, context, config):
        return (
            selected(context, "Sam")
            if "who" in question.lower()
            else ReaderSelection(None, {"decision": "no_answer"})
        )

    reader = reader_with(monkeypatch, predict)
    result = reader._read(
        "Who assigns Orion lockers, and how much is their insurance?",
        ["Sam assigns Orion lockers."],
        Settings(),
    )
    assert all(r.span is None for r in result)


def test_topic_prefix_is_context_not_an_extra_question(monkeypatch):
    """A leading topic must not cause an unanswerable synthetic first part."""
    text = "Sam assigns Orion lockers. Vela seals last twelve hours."

    def predict(question, context, config):
        if "who" in question.lower():
            return selected(context, "Sam")
        if "how long" in question.lower():
            return selected(context, "twelve hours")
        return ReaderSelection(None, {"decision": "no_answer"})

    result = reader_with(monkeypatch, predict)._read(
        "For Orion lockers, who assigns them, and how long do Vela seals last?",
        [text],
        Settings(),
    )
    assert result[0].span is not None


def test_explicit_requested_list_needs_both_documents(monkeypatch):
    contexts = ["Orion lockers are owned by Sam.", "Orion lockers return to rack R7."]

    def predict(question, context, config):
        if " and " in question:
            return ReaderSelection(None, {"decision": "no_answer"})
        if "owner" in question.lower() and "Sam" in context:
            return selected(context, "Sam")
        if "rack" in question.lower() and "R7" in context:
            return selected(context, "R7")
        return ReaderSelection(None, {"decision": "no_answer"})

    result = reader_with(monkeypatch, predict)._read(
        "For Orion lockers, give me the owner and the return rack.",
        contexts,
        Settings(),
    )
    assert all(item.span is not None for item in result)


def test_need_list_retains_each_requested_document(monkeypatch):
    contexts = ["Orion lockers have twelve slots.", "Orion lockers return to rack R7."]

    def predict(question, context, config):
        if " and " in question:
            return ReaderSelection(None, {"decision": "no_answer"})
        if "capacity" in question.lower() and "twelve" in context:
            return selected(context, "twelve slots")
        if "rack" in question.lower() and "R7" in context:
            return selected(context, "R7")
        return ReaderSelection(None, {"decision": "no_answer"})

    result = reader_with(monkeypatch, predict)._read(
        "I need the Orion locker capacity and the return rack.", contexts, Settings()
    )
    assert all(item.span for item in result)


def test_explicit_topic_does_not_inject_the_previous_question(monkeypatch):
    contexts = ["Sam approves Orion night access.", "Orion night access is on Tuesday."]

    def predict(question, context, config):
        if "who" in question.lower() and "Sam" in context:
            return selected(context, "Sam")
        if "when" in question.lower() and "who" not in question.lower():
            if "Tuesday" in context:
                return selected(context, "Tuesday")
        return ReaderSelection(None, {"decision": "no_answer"})

    result = reader_with(monkeypatch, predict)._read(
        "For Orion night access, who approves, and when is it scheduled?",
        contexts,
        Settings(),
    )
    assert all(item.span for item in result)


def test_person_question_cannot_use_a_schedule_as_its_answer(monkeypatch):
    context = "Orion access is granted on Friday at 09:00."
    reader = reader_with(monkeypatch, lambda q, c, s: selected(c, "Friday at 09:00"))
    assert (
        reader._read("Who grants Orion access?", [context], Settings())[0].span is None
    )


def test_duration_question_cannot_borrow_a_start_clock_time(monkeypatch):
    context = "The Orion station opens at 09:00."
    reader = reader_with(monkeypatch, lambda q, c, s: selected(c, "09:00"))
    assert (
        reader._read("How long is the Orion session?", [context], Settings())[0].span
        is None
    )


def test_operation_schedule_is_not_elapsed_duration(monkeypatch):
    context = "The Orion inspection takes place on Wednesday at 08:00."
    reader = reader_with(monkeypatch, lambda q, c, s: selected(c, "Wednesday at 08:00"))
    assert (
        reader._read(
            "What is the duration of Orion inspection?", [context], Settings()
        )[0].span
        is None
    )


def test_procedure_cannot_be_established_by_appointment_only(monkeypatch):
    context = "Orion inspection is booked for Friday at 09:00."
    reader = reader_with(monkeypatch, lambda q, c, s: selected(c, "Friday at 09:00"))
    assert (
        reader._read(
            "What are the ordered steps for Orion inspection?", [context], Settings()
        )[0].span
        is None
    )


def test_named_entity_scope_rejects_unrelated_lower_document(monkeypatch):
    reader = reader_with(monkeypatch, lambda q, c, s: selected(c))
    result = reader._read(
        "Who assigns Orion lockers?",
        ["Sam assigns Orion lockers.", "Kim assigns Vela lockers."],
        Settings(),
    )
    assert result[0].span is not None and result[1].span is None


def test_money_request_cannot_borrow_mass_from_selected_clause(monkeypatch):
    text = "Staff handle the refill. Each refill is eighty grams."
    reader = reader_with(monkeypatch, lambda q, c, s: selected(c, "eighty grams"))
    result = reader._read("How much does a refill cost?", [text], Settings())
    assert result[0].span is None


def test_explicit_money_source_and_procedural_conjunction_remain_valid(monkeypatch):
    money = "A refill costs $8."
    reader = reader_with(monkeypatch, lambda q, c, s: selected(c, "$8"))
    assert reader._read("How much does a refill cost?", [money], Settings())[0].span
    procedure = "Clear cups, then wipe the table."
    reader = reader_with(monkeypatch, lambda q, c, s: selected(c))
    assert reader._read(
        "How do I clear cups and wipe the table?", [procedure], Settings()
    )[0].span


def test_relation_subject_must_belong_to_selected_rule_clause(monkeypatch):
    text = (
        "The boardroom uses the clean card procedure. "
        "The classroom has a separate checklist."
    )
    reader = reader_with(monkeypatch, lambda q, c, s: selected(c, "clean card"))
    assert (
        reader._read(
            "Does the classroom use the boardroom clean card procedure?",
            [text],
            Settings(),
        )[0].span
        is None
    )


async def test_connected_citation_limit_keeps_every_requested_part(
    real_client, monkeypatch
):
    """Three high-ranked part-one sources cannot crowd out part two."""
    from app.config import get_settings
    from app.services.answer_reader import reader_service

    client, _, _ = real_client
    monkeypatch.setattr(get_settings(), "ANSWER_SELECTION_MODE", "reader")
    docs = [
        await upload(client, text)
        for text in [
            "Orion locker assignment is owned by Sam, weekday schedule.",
            "Orion locker assignment is owned by Sam, weekend schedule.",
            "Orion locker assignment is owned by Sam, holiday schedule.",
            "Orion locker seal duration is twelve hours.",
        ]
    ]

    last_required = []

    async def predictions(question, contexts, config=None):
        # Isolate the model boundary: the fourth ranked candidate supplies a
        # required part which the first three predictions do not establish.
        assert len(contexts) == 4
        last_required.append(contexts[-1])
        return [
            ReaderSelection(
                AnswerSpan(start=0, end=len(text), text=text),
                {
                    "part_count": 2,
                    "covered_parts": [1] if index == 3 else [0],
                    "parts": [{"raw_span": {"start": 0, "end": 5, "text": "Orion"}}],
                },
            )
            for index, text in enumerate(contexts)
        ]

    monkeypatch.setattr(reader_service, "select", predictions)
    response = await client.post(
        "/api/queries",
        json={
            "question": (
                "Who owns Orion locker assignment and how long is the seal duration?"
            ),
            "document_ids": [doc["id"] for doc in docs],
            "retrieval_method": "keyword",
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["outcome"] == "completed"
    assert last_required[0] in result["answer"]
    assert len(result["sources"]) <= 3
    for candidate in result["provenance"]["answer_selection"]["candidates"]:
        assert "text" not in candidate["parts"][0]["raw_span"]
