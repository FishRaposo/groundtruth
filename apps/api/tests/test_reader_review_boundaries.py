from app.config import Settings
from app.models.query import AnswerSpan
from app.services.answer_reader import LocalReader, ReaderSelection
from app.services.reader_questions import mismatch_reason, question_parts


def selected(context, raw):
    start = context.index(raw)
    return ReaderSelection(
        AnswerSpan(start=0, end=len(context), text=context),
        {
            "decision": "answer",
            "raw_span": {"start": start, "end": start + len(raw), "text": raw},
        },
    )


def test_middle_pronoun_does_not_inherit_future_entity(monkeypatch):
    question = (
        "Who approves Orion access, and how long is it valid, "
        "and who approves Vela access?"
    )
    contexts = [
        "Sam approves Orion access. Orion access is valid for eleven minutes.",
        "Kim approves Vela access.",
    ]
    reader = LocalReader()

    def predict(question, context, config):
        if "how long" in question.lower() and "Orion" in context:
            return selected(context, "eleven minutes")
        if "who" in question.lower():
            return selected(context, "Sam" if "Orion" in context else "Kim")
        return ReaderSelection(None, {})

    monkeypatch.setattr(reader, "_context", predict)
    result = reader._parts(question, contexts, Settings())
    print("MIDDLE_PARTS", question_parts(question))
    assert any(item.span for item in result), (
        "Complete two-document answer rejected: middle pronoun inherited "
        "both Orion and future Vela anchors"
    )


def test_pronoun_continuation_preserves_qualifying_subject():
    night = question_parts(
        "Who approves night access to Orion, and how long is it valid?"
    )
    day = question_parts("Who approves day access to Orion, and how long is it valid?")
    print("CONTINUATIONS", {"night": night[1].question, "day": day[1].question})
    assert night[1].question != day[1].question, (
        "Distinct durations become identical subquestions "
        "after dropping night/day qualifier"
    )


def test_price_mention_does_not_require_a_monetary_answer():
    text = "Sam approves the insured value."
    start = text.index("Sam")
    actual = mismatch_reason("Who approves the insured value?", text, start, start + 3)
    print("VALUE_AUTHORITY_REASON", actual)
    assert actual is None


def test_money_span_may_include_valid_per_hour_unit():
    text = "Orion access costs eight dollars per hour."
    raw = "eight dollars per hour"
    start = text.index(raw)
    actual = mismatch_reason(
        "What does Orion access cost?", text, start, start + len(raw)
    )
    print("RATE_PRICE_REASON", actual)
    assert actual is None


def test_explicit_relation_may_be_supported_by_local_pronoun():
    text = "The classroom has new starters. It uses the clean card procedure."
    raw = "the clean card procedure"
    start = text.index(raw)
    actual = mismatch_reason(
        "Does the classroom use the clean card procedure?",
        text,
        start,
        start + len(raw),
    )
    print("RELATION_PRONOUN_REASON", actual)
    assert actual is None
