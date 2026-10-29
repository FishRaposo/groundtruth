from app.config import Settings
from app.services.answer_reader import LocalReader, ReaderSelection, passage_span


def result(monkeypatch, question, context, raw):
    service = LocalReader()
    start = context.index(raw)
    end = start + len(raw)
    selected = ReaderSelection(
        passage_span(context, start, end),
        {"decision": "answer", "raw_span": {"start": start, "end": end, "text": raw}},
    )
    monkeypatch.setattr(service, "_context", lambda q, c, s: selected)
    return service._parts(question, [context], Settings())[0]


def test_relative_when_does_not_ask_for_clock(monkeypatch):
    selection = result(
        monkeypatch,
        "What airflow rate is required when Aster starts?",
        "Aster starts on Tuesday at 07:30.",
        "07:30",
    )
    print("RELATIVE_WHEN", selection.diagnostics)
    assert selection.span is None, (
        "A relative when clause must not turn the requested airflow attribute "
        "into a clock question"
    )


def test_explicit_repeated_action_token_links_following_explanation(monkeypatch):
    selection = result(
        monkeypatch,
        "What action clears Aster controls?",
        "Press RESET. RESET clears Aster controls.",
        "Press RESET",
    )
    print("REPEATED_ACTION", selection.diagnostics)
    assert selection.span is not None, (
        "An explicit identical RESET action is a valid forward link "
        "even though it is one content token"
    )


def test_interrogative_when_still_allows_clock(monkeypatch):
    selection = result(
        monkeypatch,
        "When does Aster start?",
        "Aster starts on Tuesday at 07:30.",
        "07:30",
    )
    assert selection.span is not None


def test_rely_on_named_person_remains_allowed(monkeypatch):
    selection = result(
        monkeypatch,
        "Who provides Aster support?",
        "We rely on Morgan for Aster support.",
        "Morgan",
    )
    assert selection.span is not None
