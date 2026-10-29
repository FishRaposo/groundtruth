"""Quantity propositions must retain the selected number's local relation."""

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


def bind(
    source,
    selected,
    *,
    question="How many signed forms does ordinary Maple intake receive?",
    topic="ordinary Maple intake",
    noun="signed forms",
    relation="quantity",
    kind="quantity",
):
    start = source.index(selected)
    req = Requirement(
        "r1",
        question,
        0,
        len(question),
        question,
        kind,
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
    "verb, source_verb",
    [
        ("receive", "receives"),
        ("hold", "holds"),
        ("provide", "provides"),
        ("retain", "retains"),
    ],
)
def test_explicit_transitive_count_keeps_verb_subject_and_whole_noun(verb, source_verb):
    source = f"Each ordinary Maple intake {source_verb} 18 signed forms."
    result, reason = quantity_hypothesis(
        bind(
            source,
            "18",
            question=f"How many signed forms does ordinary Maple intake {verb}?",
        )
    )
    assert reason is None
    assert result == f"ordinary Maple intake {source_verb} 18 signed forms"


@pytest.mark.parametrize(
    "source, selected",
    [
        ("ordinary Maple intake holds 18 signed forms.", "18"),
        ("ordinary Maple intake's deputy receives 18 signed forms.", "18"),
        ("The deputy of ordinary Maple intake receives 18 signed forms.", "18"),
        ("ordinary Maple intake does not receive 18 signed forms.", "18"),
        ("ordinary Maple intake no longer receives 18 signed forms.", "18"),
        ("ordinary Maple intake receives up to 18 signed forms.", "18"),
        ("ordinary Maple intake receives 18 unsigned forms.", "18"),
        ("ordinary Maple intake receives 18 kg and its signed forms count is 4.", "18"),
        ("ordinary Maple intake receives 18. Later it receives signed forms.", "18"),
        (
            "ordinary Maple intake receives 18 signed forms for exception conditions.",
            "18",
        ),
        ("exception Maple intake receives 18 signed forms.", "18"),
    ],
)
def test_unbound_or_different_count_never_yields_proposition(source, selected):
    hypothesis, reason = quantity_hypothesis(bind(source, selected))
    assert hypothesis is None and reason


def test_number_selection_cannot_borrow_a_later_counted_noun():
    value = bind(
        "Maple intake has 8 kg of material and a participant count of 4.",
        "8",
        question="What is the participant count for Maple intake?",
        topic="Maple intake",
        noun="participant",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


@pytest.mark.parametrize(
    "source",
    [
        "Maple intake has a maximum participant count of 8.",
        "Maple intake allows at most 8 participants.",
    ],
)
def test_maximum_count_is_distinct_from_actual_count(source):
    maximum = bind(
        source,
        "8",
        question="What is the maximum participant count for Maple intake?",
        topic="Maple intake",
        noun="participant",
        relation="maximum_count",
    )
    hypothesis, reason = quantity_hypothesis(maximum)
    assert (
        reason is None and hypothesis == "Maple intake has a maximum of 8 participants"
    )
    actual = bind(
        source,
        "8",
        question="What is the participant count for Maple intake?",
        topic="Maple intake",
        noun="participant",
    )
    hypothesis, reason = quantity_hypothesis(actual)
    assert hypothesis is None and reason


def test_unqualified_count_is_not_a_maximum():
    hypothesis, reason = quantity_hypothesis(
        bind(
            "Maple intake has a participant count of 8.",
            "8",
            question="What is the maximum participant count for Maple intake?",
            topic="Maple intake",
            noun="participant",
            relation="maximum_count",
        )
    )
    assert hypothesis is None and reason


def test_explicit_passive_count_preserves_recipient():
    question = "How many signed forms are provided to ordinary Maple intake?"
    source = "18 signed forms are provided to ordinary Maple intake."
    hypothesis, reason = quantity_hypothesis(bind(source, "18", question=question))
    assert reason is None
    assert hypothesis == "18 signed forms are provided to ordinary Maple intake"


def test_unicode_offsets_bind_literal_selected_number():
    source = "💠 Élan intake receives 18 signed forms."
    # A heading is outside the supplied clause, retaining character offsets.
    value = bind(
        source,
        "18",
        topic="Élan intake",
        question="How many signed forms does Élan intake receive?",
    )
    value = Binding(
        value.req,
        source,
        value.value,
        source[2:-1],
        value.topic,
        value.start,
        value.end,
        2,
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None and hypothesis == "Élan intake receives 18 signed forms"
    assert source[value.start : value.end] == "18"


def test_operand_word_count_keeps_exact_operand():
    value = bind(
        "In Alder, the marked letter is one glyph.",
        "one",
        question="How many glyphs is the marked letter?",
        topic="In Alder, the marked letter",
        noun="glyphs",
        relation="operand_count",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert (
        reason is None and "marked letter" in hypothesis and "one glyph" in hypothesis
    )


@pytest.mark.parametrize(
    "kind, relation", [("boolean", "count_as"), ("duration", "duration")]
)
def test_other_fact_types_never_become_quantities(kind, relation):
    hypothesis, reason = quantity_hypothesis(
        bind(
            "ordinary Maple intake receives 18 signed forms.",
            "18",
            kind=kind,
            relation=relation,
        )
    )
    assert hypothesis is None and reason


@pytest.mark.parametrize("verb", ["receive", "hold", "retain"])
def test_request_relation_exposes_actual_transitive_verb(verb):
    from app.services import requirement_quantities

    relation = getattr(requirement_quantities, "question_relation", lambda q: None)
    assert (
        relation(f"How many signed forms does ordinary Maple intake {verb}?")
        == f"quantity:{verb}"
    )
    hypothesis, reason = quantity_hypothesis(
        bind(
            f"ordinary Maple intake {verb}s 18 signed forms.",
            "18",
            relation=f"quantity:{verb}",
            question=f"How many signed forms does ordinary Maple intake {verb}?",
        )
    )
    assert (
        reason is None
        and hypothesis == f"ordinary Maple intake {verb}s 18 signed forms"
    )


def test_passive_relation_exposes_participle_and_accepts_matching_source():
    from app.services import requirement_quantities

    question = "How many signed forms are provided to ordinary Maple intake?"
    relation = getattr(requirement_quantities, "question_relation", lambda q: None)
    assert relation(question) == "quantity:provided"
    hypothesis, reason = quantity_hypothesis(
        bind(
            "18 signed forms are provided to ordinary Maple intake.",
            "18",
            question=question,
            relation="quantity:provided",
        )
    )
    assert (
        reason is None
        and hypothesis == "18 signed forms are provided to ordinary Maple intake"
    )


def test_nominal_count_can_inherit_same_subject_across_one_conjunction():
    source = "Maple intake has 8 kg of material and a participant count of 8."
    value = bind(
        source,
        "8",
        question="What is the participant count for Maple intake?",
        topic="Maple intake",
        noun="participant",
    )
    from dataclasses import replace

    start = source.rindex("8")
    value = replace(
        value, start=start, end=start + 1, clause_start=source.index("and") + 3
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None and hypothesis == "Maple intake has 8 participants"


def test_other_subject_cannot_supply_an_implicit_count():
    from dataclasses import replace

    source = "Willow intake has 8 kg of material and a participant count of 8."
    value = bind(
        source,
        "8",
        question="What is the participant count for Maple intake?",
        topic="Maple intake",
        noun="participant",
    )
    start = source.rindex("8")
    value = replace(
        value, start=start, end=start + 1, clause_start=source.index("and") + 3
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


def test_implicit_count_cannot_skip_an_intervening_subject():
    from dataclasses import replace

    source = (
        "Maple intake has 8 kg and Willow intake has 3 kg and a participant count of 8."
    )
    value = bind(
        source,
        "8",
        question="What is the participant count for Maple intake?",
        topic="Maple intake",
        noun="participant",
    )
    start = source.rindex("8")
    value = replace(
        value, start=start, end=start + 1, clause_start=source.rindex("and") + 3
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


@pytest.mark.parametrize(
    "source_verb", ["holds", "contains", "carries", "includes", "has"]
)
def test_container_count_binds_descriptive_subject_modifiers_and_requested_relation(
    source_verb,
):
    value = bind(
        f"A standard Alder sequencing packet {source_verb} 13 year cards.",
        "13",
        question="How many year cards does a standard Alder packet hold?",
        topic="standard Alder packet",
        noun="year cards",
        relation="quantity:hold",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None
    assert hypothesis == "standard Alder packet holds 13 year cards"


@pytest.mark.parametrize("source_verb", ["holds", "carries", "includes"])
def test_nominal_container_quantity_can_use_current_containment_predicates(source_verb):
    value = bind(
        f"A standard Alder batch {source_verb} 12 polygon rings.",
        "12",
        question="How many polygon rings are in a standard Alder batch?",
        topic="standard Alder batch",
        noun="polygon rings",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None
    assert hypothesis == f"standard Alder batch {source_verb} 12 polygon rings"


@pytest.mark.parametrize(
    "subject",
    [
        "standard Alder deputy packet",
        "standard Alder owner's packet",
        "standard Alder exception packet",
        "standard Alder former packet",
        "standard Alder Orchard packet",
        "standard Alder packet's coordinator",
        "ordinary Alder sequencing packet",
    ],
)
def test_descriptive_subject_matching_never_changes_entity_condition_or_role(subject):
    value = bind(
        f"A {subject} holds 13 year cards.",
        "13",
        question="How many year cards does a standard Alder packet hold?",
        topic="standard Alder packet",
        noun="year cards",
        relation="quantity:hold",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


@pytest.mark.parametrize(
    "source_verb,requested",
    [("receives", "hold"), ("owns", "hold"), ("contains", "receive")],
)
def test_container_synonyms_never_replace_transfer_or_ownership(source_verb, requested):
    value = bind(
        f"A standard Alder packet {source_verb} 13 year cards.",
        "13",
        question=f"How many year cards does a standard Alder packet {requested}?",
        topic="standard Alder packet",
        noun="year cards",
        relation=f"quantity:{requested}",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


def test_unqualified_permission_is_not_observed_cardinality():
    value = bind(
        "A standard Alder packet allows 13 year cards.",
        "13",
        question="How many year cards are in a standard Alder packet?",
        topic="standard Alder packet",
        noun="year cards",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


def test_explicit_count_preserves_plural_source_predicate():
    value = bind(
        "Standard Alder packets receive 13 year cards.",
        "13",
        question="How many year cards do standard Alder packets receive?",
        topic="standard Alder packets",
        noun="year cards",
        relation="quantity:receive",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert (
        reason is None and hypothesis == "standard Alder packets receive 13 year cards"
    )


@pytest.mark.parametrize("selected", ["24", "24 text strings"])
def test_natural_count_proposition_uses_one_count_and_full_literal_unit(selected):
    value = bind(
        "A standard Alder batch consists of 24 text strings.",
        selected,
        question="How many text strings go into a standard Alder batch?",
        topic="standard Alder batch",
        noun="text strings",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None
    assert hypothesis == "standard Alder batch consists of 24 text strings"


@pytest.mark.parametrize("selected", ["8", "8 participants"])
def test_natural_maximum_proposition_preserves_limit_and_counted_noun(selected):
    value = bind(
        "Maple intake allows at most 8 participants.",
        selected,
        question="What is the maximum participant count for Maple intake?",
        topic="Maple intake",
        noun="participant",
        relation="maximum_count",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None
    assert hypothesis == "Maple intake has a maximum of 8 participants"


@pytest.mark.parametrize(
    "number,unit",
    [
        ("1", "participant"),
        ("8", "participants"),
        ("one", "participant"),
        ("two", "participants"),
    ],
)
def test_natural_nominal_count_uses_the_explicit_source_count_noun(number, unit):
    value = bind(
        f"Maple intake has a participant count of {number}.",
        number,
        question="What is the participant count for Maple intake?",
        topic="Maple intake",
        noun="participant",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None and hypothesis == f"Maple intake has {number} {unit}"


def test_natural_proposition_keeps_explicit_requested_container_relation():
    value = bind(
        "Cedar intake consists of 24 text strings.",
        "24",
        question="How many text strings does Cedar intake contain?",
        topic="Cedar intake",
        noun="text strings",
        relation="quantity:contain",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None and hypothesis == "Cedar intake contains 24 text strings"


def test_scoped_provided_count_keeps_provided_in_the_hypothesis():
    value = bind(
        "A standard Alder layout sheet contains 22 payload rows.",
        "22",
        question=(
            "For a standard Alder layout sheet, how many payload rows are provided?"
        ),
        topic="standard Alder layout sheet",
        noun="payload rows",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None
    assert hypothesis == "22 payload rows are provided for standard Alder layout sheet"


def test_a_different_passive_action_is_not_proposed_from_container_cardinality():
    value = bind(
        "A standard Alder layout sheet contains 22 payload rows.",
        "22",
        question=(
            "For a standard Alder layout sheet, how many payload rows are destroyed?"
        ),
        topic="standard Alder layout sheet",
        noun="payload rows",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


@pytest.mark.parametrize("relation", ["selected_count", "other_count"])
def test_dependent_count_relations_never_invent_an_omitted_noun(relation):
    value = bind(
        "A standard Alder batch contains 24 text strings.",
        "24",
        question="How many do those and the others have?",
        topic="standard Alder batch",
        noun="",
        relation=relation,
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


@pytest.mark.parametrize("selected", ["one", "one unsplit ring"])
def test_remaining_count_binds_the_literal_cardinal_and_full_conditional_argument(
    selected,
):
    value = bind(
        (
            "Alder treats a ring touching longitude 180 degrees without "
            "crossing it as one unsplit ring."
        ),
        selected,
        question="how many rings remain?",
        noun="rings",
        topic="a ring that touches longitude 180 degrees without crossing in Alder",
        relation="quantity:remain",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None
    assert hypothesis == (
        "For a ring that touches longitude 180 degrees without crossing in Alder, "
        "one unsplit ring remains"
    )


@pytest.mark.parametrize(
    "number",
    (
        "zero one two three four five six seven eight nine ten "
        "eleven twelve thirteen fourteen fifteen sixteen seventeen "
        "eighteen nineteen twenty"
    ).split(),
)
def test_remaining_count_retains_source_cardinal_words(number):
    noun = "ring" if number == "one" else "rings"
    value = bind(
        (
            "Alder treats a ring touching longitude 180 degrees "
            f"without crossing it as {number} unsplit {noun}."
        ),
        number,
        question="how many rings remain?",
        noun="rings",
        topic="a ring that touches longitude 180 degrees without crossing in Alder",
        relation="quantity:remain",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None
    assert f"{number} unsplit {noun}" in hypothesis
    assert hypothesis.endswith("remains" if number == "one" else "remain")


@pytest.mark.parametrize("number", ["0", "1", "2", "18", "20"])
def test_remaining_count_keeps_digit_arguments(number):
    value = bind(
        (
            "Alder treats a ring touching longitude 180 degrees "
            f"without crossing it as {number} unsplit rings."
        ),
        number,
        question="how many rings remain?",
        noun="rings",
        topic="a ring that touches longitude 180 degrees without crossing in Alder",
        relation="quantity:remain",
    )
    from dataclasses import replace

    start = value.context.rindex(f"as {number}") + 3
    value = replace(value, start=start, end=start + len(number))
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None and f"{number} unsplit rings" in hypothesis


@pytest.mark.parametrize(
    "source,selected",
    [
        (
            (
                "Willow treats a ring touching longitude 180 degrees without "
                "crossing it as one unsplit ring."
            ),
            "one",
        ),
        (
            (
                "Alder's deputy treats a ring touching longitude 180 degrees "
                "without crossing it as one unsplit ring."
            ),
            "one",
        ),
        (
            "Alder treats a ring crossing longitude 180 degrees as one unsplit ring.",
            "one",
        ),
        (
            (
                "Alder treats a ring touching longitude 170 degrees without "
                "crossing it as one unsplit ring."
            ),
            "one",
        ),
        (
            (
                "Alder does not treat a ring touching longitude 180 degrees "
                "without crossing it as one unsplit ring."
            ),
            "one",
        ),
        (
            (
                "Alder no longer treats a ring touching longitude 180 "
                "degrees without crossing it as one unsplit ring."
            ),
            "one",
        ),
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as one additional ring."
            ),
            "one",
        ),
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as one aggregate ring."
            ),
            "one",
        ),
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as one minute."
            ),
            "one",
        ),
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as a ring."
            ),
            "a ring",
        ),
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as no rings."
            ),
            "no",
        ),
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as one of the rings."
            ),
            "one",
        ),
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as profile one ring."
            ),
            "one",
        ),
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as the first one ring."
            ),
            "one",
        ),
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as eighteen unsplit rings."
            ),
            "eight",
        ),
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as 18 unsplit rings."
            ),
            "8",
        ),
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as one unsplit ring."
            ),
            "one unsplit",
        ),
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as 1.5 unsplit rings."
            ),
            "1",
        ),
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as at most one unsplit ring."
            ),
            "one",
        ),
    ],
)
def test_remaining_count_never_borrows_entity_condition_unit_or_partial_number(
    source, selected
):
    value = bind(
        source,
        selected,
        question="how many rings remain?",
        noun="rings",
        topic="a ring that touches longitude 180 degrees without crossing in Alder",
        relation="quantity:remain",
    )
    if selected.isdigit():
        from dataclasses import replace

        start = source.rindex(selected)
        value = replace(value, start=start, end=start + len(selected))
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


def test_remaining_count_can_use_an_explicit_conditional_remains_clause():
    value = bind(
        (
            "For a ring touching longitude 180 degrees without crossing "
            "it in Alder, one closed ring remains."
        ),
        "one",
        question="how many rings remain?",
        noun="rings",
        topic="a ring that touches longitude 180 degrees without crossing in Alder",
        relation="quantity:remain",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None and hypothesis.endswith("one closed ring remains")


def test_remaining_count_cannot_be_replaced_by_an_unqualified_container_count():
    value = bind(
        "Alder contains one unsplit ring.",
        "one",
        question="how many rings remain?",
        noun="rings",
        topic="Alder",
        relation="quantity:remain",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


@pytest.mark.parametrize("start,end", [(None, None), (0, 0), (-1, 2)])
def test_remaining_count_does_not_turn_missing_or_invalid_raw_spans_into_candidates(
    start, end
):
    from dataclasses import replace

    value = bind(
        (
            "Alder treats a ring touching longitude 180 degrees without "
            "crossing it as one unsplit ring."
        ),
        "one",
        question="how many rings remain?",
        noun="rings",
        topic="a ring that touches longitude 180 degrees without crossing in Alder",
        relation="quantity:remain",
    )
    value = replace(value, start=start, end=end)
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


def test_remaining_count_keeps_unicode_source_offsets():
    source = (
        "💠 Notice. Alder treats a ring touching longitude 180 "
        "degrees without crossing it as one unsplit ring."
    )
    value = bind(
        source,
        "one",
        question="how many rings remain?",
        noun="rings",
        topic="a ring that touches longitude 180 degrees without crossing in Alder",
        relation="quantity:remain",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None and hypothesis.endswith("one unsplit ring remains")
    assert source[value.start : value.end] == "one"


@pytest.mark.parametrize(
    "source,selected",
    [
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as twenty-one unsplit rings."
            ),
            "twenty",
        ),
        (
            (
                "Alder treats a ring touching longitude 180 degrees without "
                "crossing it as twenty one unsplit rings."
            ),
            "twenty",
        ),
    ],
)
def test_remaining_count_does_not_truncate_an_unsupported_compound_cardinal(
    source, selected
):
    value = bind(
        source,
        selected,
        question="how many rings remain?",
        noun="rings",
        topic="a ring that touches longitude 180 degrees without crossing in Alder",
        relation="quantity:remain",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


def test_remaining_count_does_not_mistake_one_conjunct_for_the_aggregate_result():
    source = (
        "Alder treats a ring touching longitude 180 degrees without crossing it "
        "as one unsplit ring and two additional rings."
    )
    value = bind(
        source,
        "one",
        question="how many rings remain?",
        noun="rings",
        topic="a ring that touches longitude 180 degrees without crossing in Alder",
        relation="quantity:remain",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


# Literal immutable development chunk; selected boundaries were recorded by QA.
_RECORDED_CAPACITY_CHUNK = (
    "This is an invented Copper sparse triplets worksheet convention. "
    "Ordinary worksheets carry no amber triangle. An ordinary Copper "
    "sparse triplets session lasts 14 minutes. An ordinary Copper "
    "sparse triplets session may accept at most 9 triplet records. The "
    "sample illustration contains 29 columns; that illustration does "
    "not set session capacity. Do not add values at duplicate "
    "coordinates. The following complete procedure applies to ordinary "
    "worksheets with no amber triangle. Step 1. Copy the row number, "
    "column number, and value into separate boxes. Step 2. Remove "
    "records whose value is zero, keeping the remaining values "
    "unchanged. Step 3. Arrange the remaining records by ascending row "
    "number and then ascending column number. Step 4. Write duplicate "
    "coordinates on the review line instead of combining their values."
)


@pytest.mark.parametrize("start,end", [(233, 234), (233, 250), (225, 234)])
def test_recorded_maximum_count_binds_modal_acceptance_and_full_source_unit(start, end):
    source = _RECORDED_CAPACITY_CHUNK
    selected = source[start:end]
    value = bind(
        source,
        selected,
        question=(
            "For ordinary Copper sparse triplets, provide the maximum number of"
            " triplet records"
        ),
        topic="ordinary Copper sparse triplets",
        noun="triplet records",
        relation="maximum_count",
    )
    assert (value.start, value.end) == (start, end)
    hypothesis, reason = quantity_hypothesis(value)
    assert reason is None
    assert hypothesis == (
        "An ordinary Copper sparse triplets session may accept "
        "at most 9 triplet records"
    )


@pytest.mark.parametrize(
    "question,noun,relation",
    [
        ("What is the ordinary Maple intake session capacity?", "", "capacity_count"),
        (
            "Give the ordinary capacity in numeral cards.",
            "numeral cards",
            "capacity_count",
        ),
        (
            "How many numeral cards may one ordinary Maple intake session accept?",
            "numeral cards",
            "maximum_count:accept",
        ),
    ],
)
def test_capacity_and_explicit_acceptance_requests_preserve_source_upper_bound(
    question, noun, relation
):
    value = bind(
        "An ordinary Maple intake session may accept at most 8 numeral cards.",
        "8",
        question=question,
        topic="ordinary Maple intake session",
        noun=noun,
        relation=relation,
    )
    assert quantity_hypothesis(value) == (
        "An ordinary Maple intake session may accept at most 8 numeral cards",
        None,
    )


@pytest.mark.parametrize(
    "predicate",
    [
        "may accept up to",
        "can accept no more than",
        "accepts a maximum of",
        "has a capacity of",
        "has a maximum capacity of",
    ],
)
def test_capacity_preserves_the_literal_governing_limit_predicate(predicate):
    source = f"An ordinary Maple intake session {predicate} 8 numeral cards."
    value = bind(
        source,
        "8 numeral cards",
        question="What is the ordinary Maple intake session capacity?",
        topic="ordinary Maple intake session",
        noun="",
        relation="capacity_count",
    )
    assert quantity_hypothesis(value) == (source[:-1], None)


@pytest.mark.parametrize(
    "source,selected,noun,relation,question",
    [
        (
            "An ordinary Maple intake session lasts 8 minutes.",
            "8",
            "",
            "capacity_count",
            "What is session capacity?",
        ),
        (
            "The sample illustration contains 8 numeral cards.",
            "8",
            "",
            "capacity_count",
            "What is session capacity?",
        ),
        (
            "An ordinary Maple intake session contains 8 numeral cards.",
            "8",
            "",
            "capacity_count",
            "What is session capacity?",
        ),
        (
            "An ordinary Maple intake session receives 8 numeral cards.",
            "8",
            "",
            "capacity_count",
            "What is session capacity?",
        ),
        (
            "An ordinary Maple intake session may accept 8 numeral cards.",
            "8",
            "",
            "capacity_count",
            "What is session capacity?",
        ),
        (
            "An ordinary Maple intake session may accept at most 8 unsigned forms.",
            "8",
            "numeral cards",
            "maximum_count",
            "What is the maximum number of numeral cards?",
        ),
        (
            (
                "An ordinary Maple intake session may accept at most 8 numeral "
                "cards for exceptional cases."
            ),
            "8",
            "numeral cards",
            "maximum_count",
            "What is the maximum number of numeral cards?",
        ),
        (
            "An exceptional Maple intake session may accept at most 8 numeral cards.",
            "8",
            "",
            "capacity_count",
            "What is session capacity?",
        ),
        (
            (
                "The deputy of an ordinary Maple intake session may accept at most "
                "8 numeral cards."
            ),
            "8",
            "",
            "capacity_count",
            "What is session capacity?",
        ),
        (
            "An ordinary Maple intake session may not accept at most 8 numeral cards.",
            "8",
            "",
            "capacity_count",
            "What is session capacity?",
        ),
        (
            (
                "An ordinary Maple intake session formerly could accept at most 8 "
                "numeral cards."
            ),
            "8",
            "",
            "capacity_count",
            "What is session capacity?",
        ),
        (
            "An ordinary Maple intake session may accept at most 8 numeral cards.",
            "8",
            "",
            "quantity",
            "How many?",
        ),
        (
            "An ordinary Maple intake session may accept at most 8 numeral cards.",
            "8",
            "",
            "capacity_count",
            "How many do other years have?",
        ),
        (
            "An ordinary Maple intake session may accept at most 8 numeral cards.",
            "8",
            "numeral cards",
            "quantity",
            "How many numeral cards does ordinary Maple intake session have?",
        ),
        (
            "An ordinary Maple intake session may accept at most 8 numeral cards.",
            "8",
            "numeral cards",
            "maximum_count:accept",
            "How many numeral cards may one exceptional Maple intake session accept?",
        ),
        (
            "An ordinary Maple intake session may receive at most 8 numeral cards.",
            "8",
            "numeral cards",
            "maximum_count:accept",
            "How many numeral cards may one ordinary Maple intake session accept?",
        ),
        (
            "An ordinary Maple intake session may accept at most 18 numeral cards.",
            "8",
            "",
            "capacity_count",
            "What is session capacity?",
        ),
        (
            "An ordinary Maple intake session may accept at most 8.5 numeral cards.",
            "8",
            "",
            "capacity_count",
            "What is session capacity?",
        ),
        (
            (
                "An ordinary Maple intake session may accept at most twenty-one "
                "numeral cards."
            ),
            "twenty",
            "",
            "capacity_count",
            "What is session capacity?",
        ),
        (
            (
                "An ordinary Maple intake session may accept at most 8 numeral "
                "cards and two additional cards."
            ),
            "8",
            "",
            "capacity_count",
            "What is session capacity?",
        ),
        (
            (
                "An ordinary Maple intake session may accept at most 8 kg and then "
                "4 numeral cards."
            ),
            "8",
            "numeral cards",
            "maximum_count",
            "What is the maximum number of numeral cards?",
        ),
        (
            (
                "An ordinary Maple intake session may accept at most 8. Later it "
                "receives numeral cards."
            ),
            "8",
            "",
            "capacity_count",
            "What is session capacity?",
        ),
    ],
)
def test_capacity_never_borrows_other_units_profiles_or_unbounded_counts(
    source, selected, noun, relation, question
):
    value = bind(
        source,
        selected,
        question=question,
        topic="ordinary Maple intake session",
        noun=noun,
        relation=relation,
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


def test_modal_acceptance_relation_is_exposed_without_erasing_permission():
    from app.services.requirement_quantities import question_relation

    assert (
        question_relation(
            "How many numeral cards may one ordinary Maple intake session accept?"
        )
        == "maximum_count:accept"
    )


def test_capacity_keeps_unicode_offsets_and_whole_governed_cardinal_word():
    source = (
        "Élan note. An ordinary Maple intake session may accept "
        "at most eight numeral cards."
    )
    value = bind(
        source,
        "eight",
        question="What is session capacity?",
        topic="ordinary Maple intake session",
        noun="",
        relation="capacity_count",
    )
    assert value.start == 63
    assert quantity_hypothesis(value) == (
        "An ordinary Maple intake session may accept at most eight numeral cards",
        None,
    )


@pytest.mark.parametrize("connector", ["or", "plus"])
def test_capacity_cannot_hide_a_disjunctive_or_additional_source_unit(connector):
    source = (
        "An ordinary Maple intake session may accept at most 8 numeral cards "
        f"{connector} tokens."
    )
    value = bind(
        source,
        "8",
        question="What is session capacity?",
        topic="ordinary Maple intake session",
        noun="",
        relation="capacity_count",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason


@pytest.mark.parametrize("verb", ["receive", "own", "hold"])
def test_bounded_acceptance_does_not_answer_a_different_requested_count_action(verb):
    value = bind(
        "An ordinary Maple intake session may accept at most 8 numeral cards.",
        "8",
        question=f"How many numeral cards does ordinary Maple intake session {verb}?",
        topic="ordinary Maple intake session",
        noun="numeral cards",
        relation="maximum_count",
    )
    hypothesis, reason = quantity_hypothesis(value)
    assert hypothesis is None and reason
