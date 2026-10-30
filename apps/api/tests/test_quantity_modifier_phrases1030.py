"""Literal counted noun phrases with source modifiers must bind (1030 repair).

The proposal layer carries the whole literal counted argument ("5 candidate
sites"), while requests extract a shorter attribute ("candidate"). A source
phrase is a compatible counted argument only when the requested attribute's
words align in order inside it (the head may differ by plural stem) and every
extra word is a plain noun modifier — never a quantity modifier, relation or
boundary word. Propositions quote the literal counted text; NLI still decides.
"""

from dataclasses import dataclass

import pytest
from app.services.answer_requirements import Requirement
from app.services.requirement_quantities import quantity_hypothesis


@dataclass(frozen=True)
class Binding:
    req: Requirement
    context: str
    value: str
    premise: str
    topic: str
    start: int
    end: int
    clause_start: int


def bind(source, selected, *, topic, noun, question=None, relation="quantity"):
    start = source.index(selected)
    question = question or f"The {noun} count of {topic} is needed."
    req = Requirement(
        "r1",
        question,
        0,
        len(question),
        question,
        "quantity",
        topic,
        (),
        relation=relation,
        attribute=noun,
    )
    return Binding(
        req,
        source,
        selected,
        source.strip(".!"),
        topic,
        start,
        start + len(selected),
        0,
    )


@pytest.mark.parametrize(
    "subject, verb, counted, noun",
    [
        (
            "A Mauve Field nearest-site worksheet",
            "contains",
            "5 candidate sites",
            "candidate",
        ),
        (
            "A Tern Clock event ledger",
            "contains",
            "10 synthetic event cards",
            "event cards",
        ),
        (
            "An Opal State silent-transition drill",
            "uses",
            "7 named automaton states",
            "state",
        ),
        (
            "A Jade Path pointer transcription sheet",
            "contains",
            "3 property-name segments",
            "segment",
        ),
        (
            "An Amber Ring focus rehearsal",
            "uses",
            "9 enabled menu wedges",
            "enabled wedges",
        ),
        (
            "A Violet Bus channel patch",
            "contains",
            "6 silent virtual channels",
            "channel",
        ),
        (
            "A Bronze Box hierarchy refit",
            "includes",
            "8 leaf bounding boxes",
            "leaf-box",
        ),
        (
            "An Ivory Cube face labeling set",
            "contains",
            "6 square image faces",
            "faces",
        ),
        (
            "An Olive Zone serial exercise",
            "includes",
            "5 synthetic zone records",
            "record",
        ),
    ],
)
def test_modified_counted_phrase_binds_literal_argument(subject, verb, counted, noun):
    source = f"{subject} {verb} {counted}."
    topic = subject.split(" ", 1)[1]
    result, reason = quantity_hypothesis(bind(source, counted, topic=topic, noun=noun))
    assert reason is None
    assert result == f"{topic} {verb} {counted}"


@pytest.mark.parametrize(
    "subject, verb, counted, topic, noun",
    [
        (
            "A Jade Path pointer transcription sheet",
            "contains",
            "3 property-name segments",
            "Jade Path pointer transcription",
            "segment",
        ),
        (
            "An Ivory Cube face labeling set",
            "contains",
            "6 square image faces",
            "Ivory Cube face labeling",
            "faces",
        ),
        (
            "A Rose Atlas gutter fill fixture",
            "contains",
            "3 gutter tiles",
            "Rose Atlas gutter fill",
            "gutter tiles",
        ),
    ],
)
def test_generic_artifact_head_subject_binds(subject, verb, counted, topic, noun):
    source = f"{subject} {verb} {counted}."
    result, reason = quantity_hypothesis(bind(source, counted, topic=topic, noun=noun))
    assert reason is None
    assert result == f"{topic} {verb} {counted}"


def test_non_generic_head_still_rejects():
    source = (
        "A Jade Path pointer transcription review contains 3 property-name segments."
    )
    result, reason = quantity_hypothesis(
        bind(
            source,
            "3 property-name segments",
            topic="Jade Path pointer transcription",
            noun="segment",
        )
    )
    assert result is None
    assert reason is not None


def test_bare_number_value_binds_modified_phrase():
    source = "A Mauve Field nearest-site worksheet contains 5 candidate sites."
    result, reason = quantity_hypothesis(
        bind(source, "5", topic="Mauve Field nearest-site worksheet", noun="candidate")
    )
    assert reason is None
    assert result == "Mauve Field nearest-site worksheet contains 5 candidate sites"


@pytest.mark.parametrize(
    "counted, noun",
    [
        ("5 additional candidate sites", "candidate"),
        ("5 extra candidate sites", "candidate"),
        ("5 former candidate sites", "candidate"),
        ("43 additional work slots", "work slots"),
        ("5 previous candidate sites", "candidate"),
        ("5 candidate sites and 3 extra forms", "candidate"),
    ],
)
def test_modifier_blacklist_still_rejects(counted, noun):
    source = f"A Mauve Field nearest-site worksheet contains {counted}."
    result, reason = quantity_hypothesis(
        bind(
            source,
            counted,
            topic="Mauve Field nearest-site worksheet",
            noun=noun,
        )
    )
    assert result is None
    assert reason is not None


def test_requested_attribute_longer_than_source_phrase_still_rejects():
    source = "A Violet Bus channel patch contains 6 channels."
    result, reason = quantity_hypothesis(
        bind(
            source,
            "6 channels",
            topic="Violet Bus channel patch",
            noun="silent virtual channels",
        )
    )
    assert result is None
    assert reason is not None
