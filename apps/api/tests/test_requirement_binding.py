"""Selected values must carry the requested relation, units and polarity."""

import pytest
from app.services.answer_requirements import plan_requirements
from app.services.requirement_binding import (
    condition_relation,
    relation_present,
    support_claim,
)


def claim(question, context, value):
    requirement = plan_requirements(question)[0]
    start = context.index(value)
    return support_claim(requirement, context, start, start + len(value))


@pytest.mark.parametrize(
    ("question", "context", "value", "hypothesis"),
    [
        (
            "Who leads Cedar intake?",
            "The duty editor leads Cedar intake.",
            "duty editor",
            "duty editor leads Cedar intake",
        ),
        (
            "Who is the deputy for Cedar intake?",
            "The Cedar intake deputy is the reserve clerk.",
            "reserve clerk",
            "reserve clerk is the deputy for Cedar intake",
        ),
        (
            "How long does Cedar intake last?",
            "Cedar intake lasts 16 minutes.",
            "16",
            "Cedar intake lasts 16 minutes",
        ),
        (
            "What time does Cedar intake start?",
            "Cedar intake starts at 08:45.",
            "08:45",
            "Cedar intake starts at 08:45",
        ),
        (
            "On which day does Cedar intake start?",
            "Cedar intake starts on Tuesday.",
            "Tuesday",
            "Cedar intake starts on Tuesday",
        ),
    ],
)
def test_verification_proposition_preserves_requested_relation(
    question, context, value, hypothesis
):
    result = claim(question, context, value)
    assert result.rejection is None
    assert result.hypothesis == hypothesis
    assert result.value == context[result.start : result.end]
    assert result.value in result.premise


@pytest.mark.parametrize(
    ("question", "context", "value"),
    [
        (
            "What is the participant count for Cedar intake?",
            "Cedar intake lasts 16 minutes.",
            "16 minutes",
        ),
        ("How long does Cedar intake last?", "Cedar intake starts at 08:45.", "08:45"),
        (
            "Who leads Cedar intake?",
            "The duty editor leads Cedar intake; the reserve clerk is its deputy.",
            "reserve clerk",
        ),
        (
            "Who is the deputy for Cedar intake?",
            "The duty editor leads Cedar intake.",
            "duty editor",
        ),
        (
            "Who leads Cedar intake?",
            "The duty editor leads Birch intake. Cedar intake starts at 08:45.",
            "duty editor",
        ),
        (
            "What is the current workload for Cedar intake?",
            "Cedar intake has a duty editor.",
            "duty editor",
        ),
        ("How do I run Cedar intake?", "Cedar intake starts at 08:45.", "08:45"),
        (
            "Who leads Cedar intake?",
            "The former duty editor no longer leads Cedar intake.",
            "duty editor",
        ),
    ],
)
def test_wrong_attribute_relation_or_selected_clause_never_becomes_a_claim(
    question, context, value
):
    result = claim(question, context, value)
    assert result.hypothesis is None and result.rejection


def test_negative_boolean_keeps_negative_action_and_procedure_keeps_order():
    result = claim(
        "May Cedar intake skip the stamp?",
        "Cedar intake must not skip the stamp.",
        "must not skip the stamp",
    )
    assert result.rejection is None
    assert "not skip the stamp" in result.hypothesis
    context = (
        "For Cedar intake, first scan all 4 packets, then hold for 20 minutes, "
        "finally record approval."
    )
    result = claim(
        "How do I run Cedar intake with 4 packets and a 20 minute hold?",
        context,
        context,
    )
    assert result.rejection is None and result.value == context
    assert "4 packets" in result.hypothesis and "20 minutes" in result.hypothesis


def test_offsets_are_validated_and_numeric_units_are_only_literal():
    requirement = plan_requirements("How long does Cedar intake last?")[0]
    for start, end in [(-1, 2), (0, 99), (True, 4), (3, 3)]:
        result = support_claim(requirement, "Cedar", start, end)
        assert (
            result.hypothesis is None
            and result.rejection == "invalid_candidate_offsets"
        )
    result = claim("How long does Cedar intake last?", "Cedar intake lasts 16.", "16")
    assert result.hypothesis is None and result.rejection


def test_unrelated_conditions_are_irrelevant_without_metadata():
    standard = plan_requirements("Who leads the standard Cedar intake?")[0]
    assert (
        condition_relation(
            standard, "For the Cedar exception retest, begin by showing a marker.", {}
        )
        == "irrelevant"
    )
    retest = plan_requirements("How do I run the Cedar exception retest?")[0]
    assert (
        condition_relation(
            retest,
            "For the Cedar exception retest, first scan a marker, then record it.",
            {},
        )
        == "applies"
    )
    assert (
        condition_relation(standard, "For Cedar audit, display a marker.", {})
        == "unknown"
    )


def test_same_clause_different_numeric_fact_is_not_the_requested_count():
    result = claim(
        "What is the participant count for Cedar intake?",
        "Cedar intake lasts 16 minutes and has a participant count of 8.",
        "16",
    )
    assert result.hypothesis is None and result.rejection
    result = claim(
        "What is the participant count for Cedar intake?",
        "Cedar intake has a participant count of 8.",
        "8",
    )
    assert result.rejection is None and "8" in result.hypothesis


def test_prohibition_binds_only_the_prohibited_action():
    question = "What is the prohibition for Cedar intake?"
    result = claim(
        question, "Cedar intake prohibits copying the pass.", "copying the pass"
    )
    assert result.rejection is None
    assert result.hypothesis == "Cedar intake prohibits copying the pass"
    wrong = claim(
        question,
        "Cedar intake allows scanning the pass and prohibits copying the pass.",
        "scanning the pass",
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_leading_space_does_not_invalidate_correct_role_offsets():
    result = claim(
        "Who leads Cedar intake?",
        "Other facts.  The duty editor leads Cedar intake.",
        "duty editor",
    )
    assert result.rejection is None


def test_decimal_duration_and_selected_procedure_block_keep_literal_units():
    result = claim(
        "How long does Cedar intake last?", "Cedar intake lasts 1.5 hours.", "1.5"
    )
    assert result.rejection is None and result.value == "1.5 hours"
    context = (
        "The room has two windows. For Cedar intake, first scan the pass, "
        "then record approval. The building is open."
    )
    value = "For Cedar intake, first scan the pass, then record approval."
    result = claim("How do I run Cedar intake?", context, value)
    assert result.rejection is None


def test_abbreviated_entity_keeps_full_activity_in_the_nli_proposition():
    result = claim(
        "Who is the deputy for Cedar intake?",
        "The Cedar deputy is the reserve clerk.",
        "reserve clerk",
    )
    assert result.rejection is None
    assert result.hypothesis == "reserve clerk is the deputy for Cedar intake"


def test_relation_presence_only_excludes_clear_typed_incompatibility():
    requirement = plan_requirements("What time does Cedar intake start?")[0]
    assert (
        relation_present(requirement, "For Cedar intake, display the orange marker.")
        is False
    )
    assert relation_present(requirement, "Cedar intake starts at 08:45.") is True
    assert (
        relation_present(requirement, "Cedar intake convenes shortly after dawn.")
        is True
    )


def test_coordinated_role_arguments_do_not_borrow_each_other():
    context = (
        "The duty editor leads Cedar intake and the reserve clerk "
        "deputizes for Cedar intake."
    )
    wrong = claim("Who is the deputy for Cedar intake?", context, "duty editor")
    assert wrong.hypothesis is None and wrong.rejection
    correct = claim("Who is the deputy for Cedar intake?", context, "reserve clerk")
    assert correct.rejection is None


def test_immediate_pronoun_prefix_is_part_of_the_nli_premise():
    context = "Cedar intake is a short review. It is led by the duty editor."
    result = claim("Who leads Cedar intake?", context, "duty editor")
    assert result.rejection is None
    assert "Cedar intake is a short review" in result.premise
    assert result.hypothesis == "duty editor leads Cedar intake"
    wrong = claim(
        "Who leads Cedar intake?",
        "Cedar intake is a short review. Birch intake is separate. "
        "It is led by the duty editor.",
        "duty editor",
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_positive_deputy_contrast_does_not_inherit_other_role_negation():
    context = "The Cedar deputy is the reserve clerk, not the duty editor."
    selected = claim("Who is the deputy for Cedar intake?", context, "reserve clerk")
    assert selected.rejection is None
    assert selected.hypothesis == "reserve clerk is the deputy for Cedar intake"
    rejected = claim("Who is the deputy for Cedar intake?", context, "duty editor")
    assert rejected.hypothesis is None and rejected.rejection


def test_weekday_after_start_clock_preserves_literal_plural_day():
    result = claim(
        "On which day does Cedar intake start?",
        "The Cedar intake session starts at 08:45 on Tuesdays.",
        "Tuesdays",
    )
    assert (
        result.rejection is None
        and result.hypothesis == "Cedar intake starts on Tuesdays"
    )


def test_same_clause_competing_entity_cannot_supply_selected_role():
    result = claim(
        "Who leads Cedar intake?",
        "The duty editor leads Birch intake and Cedar intake starts at 08:45.",
        "duty editor",
    )
    assert result.hypothesis is None and result.rejection


def test_procedure_parameters_keep_number_and_unit_together():
    context = "For Cedar intake, first scan 4 forms, then hold for 20 seconds."
    result = claim(
        "How do I run Cedar intake with 4 packets and a 20 minute hold?",
        context,
        context,
    )
    assert (
        result.hypothesis is None and result.rejection == "procedure_parameter_missing"
    )


def test_source_leading_exception_header_cannot_apply_to_standard_work():
    requirement = plan_requirements("Who leads the standard Cedar intake?")[0]
    assert (
        condition_relation(
            requirement, "Exception retest for Cedar intake: first show a marker.", {}
        )
        == "irrelevant"
    )


def test_absent_condition_does_not_impose_a_second_literal_activity_gate():
    requirement = plan_requirements("Who is the deputy for Cedar intake?")[0]
    assert (
        condition_relation(requirement, "The Cedar deputy is the reserve clerk.", {})
        == "applies"
    )
    assert condition_relation(
        requirement, "If the alarm is active, the reserve clerk becomes deputy.", {}
    ) in {"irrelevant", "unknown"}


@pytest.mark.parametrize(
    "block",
    [
        "For Cedar intake, first unlock the cabinet. Next scan 4 packets. "
        "Then hold for 20 minutes. Finally record approval.",
        "Cedar intake: 1. Unlock the cabinet. 2. Scan 4 packets. "
        "3. Hold for 20 minutes. 4. Record approval.",
    ],
)
def test_a_nonnull_step_expands_to_the_complete_contiguous_ordered_block(block):
    result = claim(
        "How do I run Cedar intake with 4 packets and a 20 minute hold?",
        block,
        "Scan 4 packets" if "1." in block else "scan 4 packets",
    )
    assert result.rejection is None
    assert result.value == block
    assert result.start == 0 and result.end == len(block)
    assert "Unlock" in result.value or "unlock" in result.value
    assert "Record approval" in result.value or "record approval" in result.value


def test_ordered_expansion_preserves_an_explicit_prerequisite():
    block = (
        "Before Cedar intake, unlock the cabinet. First scan the pass. "
        "Then record approval."
    )
    result = claim("How do I run Cedar intake?", block, "scan the pass")
    assert result.rejection is None and result.value == block


def test_procedure_expansion_cannot_take_a_step_from_another_entity_or_condition():
    context = (
        "Cedar intake: 1. Unlock the cabinet. 2. Scan the pass. "
        "Birch intake: 1. Raise the gate. 2. Record the seal."
    )
    wrong = claim("How do I run Cedar intake?", context, "Raise the gate")
    assert wrong.hypothesis is None and wrong.rejection
    correct = claim("How do I run Cedar intake?", context, "Scan the pass")
    assert correct.rejection is None and "Birch" not in correct.value
    exception = (
        "For Cedar exception retest, first raise the gate, then record the seal."
    )
    wrong = claim(
        "How do I run the standard Cedar intake?", exception, "raise the gate"
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_ordered_expansion_keeps_missing_step_and_wrong_unit_controls():
    incomplete = "Cedar intake: 1. Unlock the cabinet. 3. Record approval."
    wrong = claim("How do I run Cedar intake?", incomplete, "Unlock the cabinet")
    assert wrong.hypothesis is None and wrong.rejection
    wrong = claim(
        "How do I run Cedar intake with a 20 minute hold?",
        "Cedar intake: 1. Scan the pass. 2. Hold for 20 seconds.",
        "Scan the pass",
    )
    assert wrong.hypothesis is None and wrong.rejection == "procedure_parameter_missing"


def test_generic_wh_claim_preserves_the_requested_attribute_and_relation():
    result = claim(
        "Which fixture is reserved for Cedar intake?",
        "The fixture Juniper is reserved for Cedar intake.",
        "Juniper",
    )
    assert result.rejection is None
    assert result.hypothesis == "Juniper is the fixture reserved for Cedar intake"
    wrong = claim(
        "Which fixture is reserved for Cedar intake?",
        "The fixture Juniper is displayed near Cedar intake.",
        "Juniper",
    )
    assert wrong.hypothesis is None and wrong.rejection


@pytest.mark.parametrize("predicate", ["contains", "consists of"])
def test_quantity_container_relation_keeps_the_counted_noun(predicate):
    result = claim(
        "How many text strings does Cedar intake contain?",
        f"Cedar intake {predicate} 24 text strings.",
        "24 text strings",
    )
    assert result.rejection is None
    assert result.hypothesis == "Cedar intake contains 24 text strings"


def test_maximum_count_cannot_be_replaced_by_an_unqualified_count():
    question = "What is the maximum participant count for Cedar intake?"
    wrong = claim(question, "Cedar intake has a participant count of 8.", "8")
    assert wrong.hypothesis is None and wrong.rejection
    result = claim(question, "Cedar intake has a maximum participant count of 8.", "8")
    assert result.rejection is None
    assert result.hypothesis == "Cedar intake has a maximum of 8 participants"


@pytest.mark.parametrize(
    ("question", "context", "value"),
    [
        (
            "What is the participant count for Maple intake?",
            "Maple intake has 8 kg of material and a participant count of 4.",
            "8",
        ),
        (
            "How long does Maple intake last?",
            "Willow intake lasts 16 minutes and Maple intake starts at 08:45.",
            "16",
        ),
        (
            "What time does Maple intake start?",
            "Willow intake starts at 08:45 and Maple intake lasts 16 minutes.",
            "08:45",
        ),
        (
            "Who leads Maple intake?",
            "The duty editor leads Maple audit.",
            "duty editor",
        ),
        (
            "Who leads Maple intake?",
            "The duty editor leads neither Maple intake nor Willow intake.",
            "duty editor",
        ),
        (
            "How long does Maple intake last?",
            "Maple intake never lasts 16 minutes.",
            "16",
        ),
        (
            "What time does Maple intake start?",
            "Maple intake never starts at 08:45.",
            "08:45",
        ),
        (
            "What is the participant count for Maple intake?",
            "Maple intake never has 8 participants.",
            "8 participants",
        ),
        (
            "Who is the deputy for Maple intake?",
            "The deputy for Maple audit is the reserve clerk.",
            "reserve clerk",
        ),
        (
            "During which hours is Maple intake available?",
            "Maple intake is available from 08:00 to 09:00 "
            "and Willow intake is available from 10:00 to 11:00.",
            "from 10:00 to 11:00",
        ),
        (
            "May Maple intake skip the stamp?",
            "Maple intake must not copy the pass and may skip the stamp.",
            "must not copy the pass and may skip the stamp",
        ),
    ],
)
def test_review_wrong_selected_relation_polarity_entity_or_unit_rejects(
    question, context, value
):
    result = claim(question, context, value)
    assert result.hypothesis is None and result.rejection


@pytest.mark.parametrize(
    "block",
    [
        "Before Maple intake, obtain a permit. Confirm the seal is intact. "
        "For Maple intake, first scan the pass. Then record approval.",
        "For Maple intake, first scan the pass. Then record approval. "
        "Finally sign the log. File the signed log with the office.",
    ],
)
def test_review_complete_procedure_keeps_separated_prerequisites_and_continuations(
    block,
):
    result = claim("How do I run Maple intake?", block, "scan the pass")
    assert result.rejection is None and result.value == block


def test_selected_occurrence_binds_even_when_the_same_number_is_repeated():
    context = "Maple intake has 8 kg of material and a participant count of 8."
    requirement = plan_requirements("What is the participant count for Maple intake?")[
        0
    ]
    wrong_start = context.index("8")
    wrong = support_claim(requirement, context, wrong_start, wrong_start + 1)
    assert wrong.hypothesis is None and wrong.rejection
    correct_start = context.rindex("8")
    correct = support_claim(requirement, context, correct_start, correct_start + 1)
    assert correct.rejection is None


def test_positive_availability_and_action_do_not_inherit_another_clause():
    positive = claim(
        "During which hours is Maple intake available?",
        "Maple intake is available from 08:00 to 09:00.",
        "from 08:00 to 09:00",
    )
    assert positive.rejection is None
    positive = claim(
        "May Maple intake skip the stamp?",
        "Maple intake must not copy the pass and may skip the stamp.",
        "may skip the stamp",
    )
    assert (
        positive.rejection is None
        and positive.hypothesis == "Maple intake may skip the stamp"
    )


def test_selected_action_cannot_drop_its_own_source_negation():
    result = claim(
        "May Maple intake skip the stamp?",
        "Maple intake must not skip the stamp.",
        "skip the stamp",
    )
    assert result.hypothesis is None and result.rejection


def test_negated_prohibition_is_not_a_positive_prohibition():
    result = claim(
        "What is the prohibition for Maple intake?",
        "Maple intake never prohibits copying the pass.",
        "copying the pass",
    )
    assert result.hypothesis is None and result.rejection


def test_mandatory_procedure_continuation_stops_at_another_entity_qualifier():
    block = "For Maple intake, first scan the pass. Then record approval."
    context = block + " Raise the gate for Willow intake."
    result = claim("How do I run Maple intake?", context, "scan the pass")
    assert result.hypothesis is None or result.value == block


def test_development_condition_header_and_canonical_owner_keep_the_full_request():
    context = (
        "This source applies under standard conditions only. "
        "The Alder boundary run owner is the segmentation steward."
    )
    result = claim(
        "Who owns the standard Alder boundary run?", context, "segmentation steward"
    )
    assert result.rejection is None
    assert (
        result.hypothesis
        == "For standard conditions, the segmentation steward is the owner "
        "of the Alder boundary run"
    )
    assert "standard conditions only" in result.premise
    assert "The Alder boundary run owner is the segmentation steward" in result.premise


def test_development_reserved_fixture_can_be_a_named_source_argument():
    result = claim(
        "Which expansion fixture is reserved for Alder?",
        "The owner-only Alder expansion fixture is named amber-set.",
        "amber-set",
    )
    assert result.rejection is None
    assert result.hypothesis == "amber-set is the expansion fixture reserved for Alder"
    wrong = claim(
        "Which expansion fixture is reserved for Alder?",
        "The owner-only Birch expansion fixture is named amber-set.",
        "amber-set",
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_development_negative_imperative_retains_prohibited_operation():
    result = claim(
        "What substitution must not be made to combining marks for an Alder batch?",
        "For an Alder batch, do not replace combining marks with spacing characters.",
        "do not replace combining marks with spacing characters",
    )
    assert result.rejection is None
    assert (
        "must not replace combining marks with spacing characters" in result.hypothesis
    )


def test_generic_transitive_who_keeps_the_actual_verb_and_object():
    result = claim(
        "Who approves harbor repair?", "Mira approves harbor repair.", "Mira"
    )
    assert (
        result.rejection is None and result.hypothesis == "Mira approves harbor repair"
    )
    wrong = claim("Who approves harbor repair?", "Mira approves bridge repair.", "Mira")
    assert wrong.hypothesis is None and wrong.rejection


def test_review_v4_possessive_subject_fragment_is_not_the_responsible_party():
    result = claim(
        "Who approves harbor repair?",
        "Mira's supervisor approves harbor repair.",
        "Mira",
    )
    assert result.hypothesis is None or (
        result.value == "Mira's supervisor"
        and result.hypothesis == "Mira's supervisor approves harbor repair"
    )


@pytest.mark.parametrize(
    "header",
    [
        "This source does not apply under standard conditions.",
        "This source applies under standard conditions only for Willow intake.",
    ],
)
def test_review_v4_condition_header_must_govern_the_requested_activity(header):
    context = header + " The Linden intake owner is the duty editor."
    result = claim("Who owns the standard Linden intake?", context, "duty editor")
    assert result.hypothesis is None and result.rejection


def test_review_v4_prohibited_action_keeps_the_requested_target():
    result = claim(
        "What substitution must not be made to labels for a Linden batch?",
        "For a Linden batch, do not remove approved forms.",
        "do not remove approved forms",
    )
    assert result.hypothesis is None and result.rejection


def test_review_v4_temporal_session_keeps_the_original_activity():
    question = (
        "How long does Linden intake last, and at what time does its session start?"
    )
    requirement = plan_requirements(question)[1]
    context = "The Linden audit session starts at 08:40."
    start = context.index("08:40")
    result = support_claim(requirement, context, start, start + 5)
    assert result.hypothesis is None and result.rejection
    wrong = claim(
        "Who approves harbor repair?", "Mira never approves harbor repair.", "Mira"
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_next_grammar_elapsed_unit_request_cannot_be_answered_in_other_units():
    question = "How many minutes does Alder intake take?"
    correct = claim(question, "Alder intake takes 14 minutes.", "14 minutes")
    assert correct.rejection is None
    wrong = claim(question, "Alder intake takes 14 hours.", "14 hours")
    assert wrong.hypothesis is None and wrong.rejection


@pytest.mark.parametrize(
    ("question", "hypothesis"),
    [
        (
            "What is the name of the Alder expansion fixture?",
            "The name of the Alder expansion fixture is amber-set",
        ),
        (
            "What is the reserved Alder expansion fixture called?",
            "The reserved Alder expansion fixture is called amber-set",
        ),
        (
            "Name the reserved Alder expansion fixture.",
            "amber-set is the reserved Alder expansion fixture",
        ),
    ],
)
def test_next_grammar_identity_questions_preserve_the_complete_requested_descriptor(
    question, hypothesis
):
    correct = claim(
        question,
        "The owner-only Alder expansion fixture is named amber-set.",
        "amber-set",
    )
    assert correct.rejection is None and correct.hypothesis == hypothesis
    wrong = claim(
        question,
        "The owner-only Birch expansion fixture is named amber-set.",
        "amber-set",
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_next_support_range_is_exact_source_clause_and_not_the_nli_header():
    header = "This source applies under standard conditions only. "
    sentence = "The Alder intake owner is the duty editor."
    context = header + sentence + " The office has two doors."
    result = claim("Who owns standard Alder intake?", context, "duty editor")
    assert result.rejection is None
    assert result.support_start is not None and result.support_end is not None
    assert context[result.support_start : result.support_end].strip().rstrip(
        "."
    ) == sentence.rstrip(".")
    assert header.strip() in result.premise


def test_next_prohibition_raw_action_expands_to_its_governing_negative_instruction():
    context = "For Alder intake, do not replace labels with tags."
    result = claim(
        "What substitution must not be made to labels for Alder intake?",
        context,
        "replace labels with tags",
    )
    assert result.rejection is None
    assert result.value == "do not replace labels with tags"
    assert context[result.start : result.end] == result.value
    assert "must not replace labels with tags" in result.hypothesis
    wrong = claim(
        "What substitution must not be made to labels for Alder intake?",
        "For Alder intake, do not copy the pass and replace labels with tags.",
        "replace labels with tags",
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_next_procedure_hypothesis_fronts_real_condition_without_losing_the_block():
    block = "For Alder intake, first scan the pass, then record approval."
    context = "This source applies under standard conditions only. " + block
    result = claim("How do I run standard Alder intake?", context, "scan the pass")
    assert result.rejection is None
    assert (
        result.hypothesis
        == "For standard conditions, the procedure for the Alder intake is: " + block
    )
    assert context[result.support_start : result.support_end] == block


def test_unnumbered_procedure_requires_matching_scope_and_all_steps():
    block = (
        "For a routine restore, pause the deployment, choose the "
        "last verified release, restore the snapshot, and verify "
        "health. Record the release and approval."
    )
    result = claim("How do I perform a routine restore?", block, "restore the snapshot")
    assert result.rejection is None and result.value == block
    wrong = claim(
        "How do I perform a routine restore?",
        block.replace("routine restore", "production reset"),
        "restore the snapshot",
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_support_clause_retains_literal_terminal_punctuation():
    context = "Mira approves harbor repair. The room has two windows."
    result = claim("Who approves harbor repair?", context, "Mira")
    assert result.rejection is None
    assert (
        context[result.support_start : result.support_end]
        == "Mira approves harbor repair."
    )


def test_copular_operand_counts_bind_word_numbers_to_the_correct_operand():
    question = "In Alder, how many glyphs are the marked letter and the letter pair?"
    context = (
        "In Alder, the marked letter is one glyph, while the letter pair is two glyphs."
    )
    first, second = plan_requirements(question)
    start = context.index("one")
    result = support_claim(first, context, start, start + 3)
    assert result.rejection is None and result.value == "one glyph"
    assert "marked letter" in result.hypothesis and "one glyph" in result.hypothesis
    start = context.index("two")
    result = support_claim(second, context, start, start + 3)
    assert result.rejection is None and result.value == "two glyphs"
    assert "letter pair" in result.hypothesis and "two glyphs" in result.hypothesis
    wrong = support_claim(
        second, context, context.index("one"), context.index("one") + 3
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_count_as_boolean_retains_the_predicate_and_polarity():
    question = (
        "For Alder, does a self-reference count as a witness, and "
        "do two duplicated edges count?"
    )
    first, second = plan_requirements(question)
    context = "For Alder, a self-reference counts as a witness."
    start = context.index("counts")
    result = support_claim(first, context, start, len(context) - 1)
    assert result.rejection is None and "counts as a witness" in result.hypothesis
    context = "For Alder, two duplicated edges do not count as a witness."
    start = context.index("do not")
    result = support_claim(second, context, start, len(context) - 1)
    assert result.rejection is None and "do not count as a witness" in result.hypothesis


def test_passive_ownership_and_owner_dependent_deputy_keep_exact_role_targets():
    from app.services.answer_requirements import resolve_requirement

    context = "The standard Alder inspection is owned by the review steward."
    result = claim("Who owns standard Alder inspection?", context, "review steward")
    assert result.rejection is None
    owner, deputy = plan_requirements(
        (
            "Name the owner of standard Alder inspection and the "
            "person-role deputizing for that owner."
        )
    )
    prepared = resolve_requirement(deputy, {owner.id: "review steward"})
    context = "The backup clerk deputizes for the review steward."
    start = context.index("backup clerk")
    result = support_claim(prepared, context, start, start + len("backup clerk"))
    assert (
        result.rejection is None
        and result.hypothesis == "backup clerk deputizes for review steward"
    )
    wrong = support_claim(
        prepared,
        context.replace("review steward", "records auditor"),
        start,
        start + len("backup clerk"),
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_review_v5_unicode_coreference_keeps_literal_antecedent_ranges():
    context = (
        "💠 Notice. Élan intake is a short review. It is led by "
        "the duty editor! Other facts."
    )
    result = claim("Who leads \u00c9lan intake?", context, "duty editor")
    assert result.rejection is None
    expected = "\u00c9lan intake is a short review. It is led by the duty editor!"
    assert context[result.support_start : result.support_end] == expected
    assert "\u00c9lan intake is a short review" in result.premise


@pytest.mark.parametrize(
    ("context", "full_value"),
    [
        ("The Linden inspection is owned by Mira's supervisor.", "Mira's supervisor"),
        (
            "The Linden inspection is owned by the supervisor of Mira.",
            "the supervisor of Mira",
        ),
    ],
)
def test_review_v5_passive_owner_never_claims_a_possessive_fragment(
    context, full_value
):
    result = claim("Who owns Linden inspection?", context, "Mira")
    assert result.hypothesis is None or (
        result.value == full_value and full_value in result.hypothesis
    )


@pytest.mark.parametrize(
    "target", ["the review steward's assistant", "the assistant of the review steward"]
)
def test_review_v5_dependent_deputy_does_not_change_the_owner_target(target):
    from app.services.answer_requirements import resolve_requirement

    owner, deputy = plan_requirements(
        (
            "Name the owner of Linden inspection and the person-role "
            "deputizing for that owner."
        )
    )
    resolved = resolve_requirement(deputy, {owner.id: "review steward"})
    context = "The backup clerk deputizes for " + target + "."
    start = context.index("backup clerk")
    result = support_claim(resolved, context, start, start + len("backup clerk"))
    assert result.hypothesis is None and result.rejection


@pytest.mark.parametrize(
    "context",
    [
        "For Linden, the label for a self-reference counts as a witness.",
        "For Linden, a self-reference counts as a witness archive.",
    ],
)
def test_review_v5_count_as_binds_complete_subject_and_target(context):
    result = claim(
        "For Linden, does a self-reference count as a witness?",
        context,
        "counts as a witness",
    )
    assert result.hypothesis is None and result.rejection


@pytest.mark.parametrize(
    "context",
    [
        (
            "For Linden intake, first select the red profile, then "
            "scan the pass, finally write the result to the audit "
            "ledger."
        ),
        (
            "For Linden intake, first select the blue profile, then "
            "scan the pass, finally record approval."
        ),
    ],
)
def test_review_v5_original_procedure_configuration_and_destination_are_required(
    context,
):
    question = (
        "Give the complete ordered procedure for Linden intake "
        "with the blue profile, including writing the result to "
        "the audit ledger."
    )
    result = claim(question, context, "scan the pass")
    assert result.hypothesis is None and result.rejection


def test_review_v5_original_procedure_configuration_and_destination_positive():
    question = (
        "Give the complete ordered procedure for Linden intake "
        "with the blue profile, including writing the result to "
        "the audit ledger."
    )
    context = (
        "For Linden intake, first select the blue profile, then "
        "scan the pass, finally write the result to the audit "
        "ledger."
    )
    result = claim(question, context, "scan the pass")
    assert result.rejection is None


def test_observed_procedure_markers_cannot_restart_inside_an_instruction():
    block = (
        "Alder audit: 1. Open the bundle. 2. Select the next "
        "entry. 3. Record the first repeated label. 4. Save the "
        "witness."
    )
    result = claim("How do I run Alder audit?", block, "Select the next entry")
    assert result.rejection is None and result.value == block


def test_exact_full_subject_expansion_keeps_source_coordinates():
    context = "Mira's supervisor approves harbor repair."
    result = claim("Who approves harbor repair?", context, "Mira")
    assert result.rejection is None and result.value == "Mira's supervisor"
    assert context[result.start : result.end] == result.value
    assert result.hypothesis == "Mira's supervisor approves harbor repair"


def test_existing_phrasal_rollback_question_uses_a_complete_scoped_procedure():
    question = "How do I roll back the staging deployment?"
    block = (
        "For a staging rollback, pause the deployment queue, "
        "select the last verified release, restore the snapshot, "
        "and verify health before opening traffic. Record the "
        "release and approval."
    )
    result = claim(question, block, "pause the deployment queue")
    assert result.rejection is None and result.value == block
    assert "roll back the staging deployment" in result.hypothesis
    wrong = claim(
        question,
        block.replace("staging rollback", "production rollback"),
        "pause the deployment queue",
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_observed_possessive_schedule_and_each_weekday_keep_activity_binding():
    context = "Alder's standard cycle audit begins at 14:35 each Wednesday."
    clock = claim(
        "What time does the standard Alder cycle audit start?", context, "14:35"
    )
    day = claim(
        "On which day does the standard Alder cycle audit start?", context, "Wednesday"
    )
    assert clock.rejection is None and day.rejection is None
    wrong = claim(
        "On which day does the standard Alder intake start?", context, "Wednesday"
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_observed_possessive_record_deputy_is_not_a_competing_activity():
    question = (
        "Who is responsible for standard Alder coefficient "
        "records, and who is the record deputy?"
    )
    requirement = plan_requirements(question)[1]
    context = "Alder's record deputy is the packet editor."
    start = context.index("packet editor")
    result = support_claim(requirement, context, start, start + len("packet editor"))
    assert result.rejection is None


def test_procedure_hypothesis_retains_unsimplified_requested_parameter_clause():
    question = (
        "Give the ordered procedure for Alder intake, including "
        "its profile and destination."
    )
    context = (
        "For Alder intake, first select the blue profile, then "
        "write the result to the audit ledger."
    )
    result = claim(question, context, "select the blue profile")
    assert result.rejection is None
    assert "including its profile and destination" in result.hypothesis


@pytest.mark.parametrize(
    "action", ["use the blue profile", "deny permission to use the blue profile"]
)
def test_procedure_conditions_have_independent_minimal_contiguous_proofs(action):
    context = (
        f"For Linden intake, first {action}, "
        "then scan the pass, finally record approval."
    )
    result = claim(
        "Give the complete procedure for Linden intake with the blue profile.",
        context,
        "scan the pass",
    )
    assert result.rejection is None
    assert result.checks
    check = next(
        c for c in result.checks if c.name.startswith("procedure_configuration")
    )
    assert check.premise in context and action in check.premise
    assert (
        check.hypothesis
        == "The instructions for Linden intake require using the blue profile."
    )
    assert context not in check.hypothesis


def test_procedure_action_target_is_the_actual_governing_argument():
    question = "How do I back up Linden records?"
    wrong = claim(
        question,
        "For Linden backup, back up the audit index, "
        "scan the records catalog, verify the checksum.",
        "verify the checksum",
    )
    assert wrong.hypothesis is None and wrong.rejection
    context = (
        "For Linden backup, back up the records, verify the checksum, record approval."
    )
    correct = claim(question, context, "verify the checksum")
    assert correct.rejection is None
    requirement = plan_requirements(question)[0]
    assert condition_relation(requirement, context, {}) == "applies"
    assert condition_relation(
        requirement, context, {"condition": "the alarm is active"}
    ) in {"unknown", "irrelevant"}


def test_colonheaded_rollback_keeps_constraints_and_stops_next_topic():
    block = (
        "Staging rollback: pause the deployment queue, "
        "select the last healthy image, and run the staging smoke test "
        "before resuming traffic. The approval owner is the release captain. "
        "The observation window is 12 minutes. "
        "Never use this procedure for production."
    )
    context = (
        block + " Production rollback: contact the production commander, "
        "request approval, record the ticket."
    )
    result = claim(
        "How do I roll back the staging deployment?",
        context,
        "pause the deployment queue",
    )
    assert result.rejection is None and result.value == block
    assert context[result.support_start : result.support_end] == block
    assert "Never use this procedure for production" in result.value
    assert any(check.name == "procedure_action_target" for check in result.checks)
    assert all(check.premise in context for check in result.checks)


def test_activity_carrier_abbreviations_keep_full_hypotheses():
    deputy = claim(
        "Who is the deputy for standard Alder boundary run?",
        "The Alder boundary deputy is the corpus librarian.",
        "corpus librarian",
    )
    assert (
        deputy.rejection is None and "standard Alder boundary run" in deputy.hypothesis
    )
    context = "The standard Alder boundary session starts at 11:20 on Tuesdays."
    clock = claim(
        "What time does standard Alder boundary pass start?", context, "11:20"
    )
    day = claim(
        "On which day does standard Alder boundary pass start?", context, "Tuesdays"
    )
    assert clock.rejection is None and day.rejection is None
    assert "standard Alder boundary pass" in clock.hypothesis
    wrong = claim("Who leads Alder intake?", "The editor leads Alder audit.", "editor")
    assert wrong.hypothesis is None and wrong.rejection


def test_generic_property_relevance_does_not_turn_another_condition_into_a_conflict():
    requirement = plan_requirements("Which expansion fixture is reserved for Alder?")[0]
    context = (
        "For an Alder run tagged violet-overflow, "
        "split each joined pair into two output groups."
    )
    assert relation_present(requirement, context) is False
    assert (
        condition_relation(
            requirement, context, {"condition": "an Alder run tagged violet-overflow"}
        )
        != "applies"
    )
    for value in ["amber-set", "mauve-set"]:
        context = f"The Alder expansion fixture is named {value}."
        assert relation_present(requirement, context) is True
        assert condition_relation(requirement, context, {}) == "applies"


@pytest.mark.parametrize(
    ("question", "context", "value", "topic", "expected"),
    [
        (
            "Which years have an extra day?",
            "Leap years have an extra day.",
            "Leap years",
            "years",
            "Leap years have an extra day",
        ),
        (
            "What is Iris's label for bundle AX?",
            "Iris's label for bundle AX is cyan.",
            "cyan",
            "Iris's label for bundle AX",
            "Iris's label for bundle AX is cyan",
        ),
        (
            "What code corresponds to payload 1010?",
            "The code QZ corresponds to payload 1010.",
            "QZ",
            "payload 1010",
            "The code QZ corresponds to payload 1010",
        ),
    ],
)
def test_generic_relation_dispatcher_preserves_complete_worker_relation(
    question, context, value, topic, expected
):
    from dataclasses import replace

    # Planner integration has a separate owner; this isolates dispatcher wiring.
    requirement = replace(
        plan_requirements(question)[0],
        kind="generic",
        relation="generic",
        topic=topic,
        anchors=(),
    )
    start = context.index(value)
    result = support_claim(requirement, context, start, start + len(value))
    assert result.rejection is None and result.hypothesis == expected


def test_primary_header_context_is_an_actual_contiguous_source_window():
    context = (
        "These facts apply under standard conditions. "
        "The room contains eight chairs. "
        "The Iris review owner is the duty clerk."
    )
    result = claim("Who owns standard Iris review?", context, "duty clerk")
    assert result.rejection is None
    assert result.premise in context
    assert "standard conditions" in result.premise
    assert "standard conditions" in result.hypothesis


def test_configuration_proof_limit_refuses_instead_of_silently_losing_a_condition():
    profiles = [f"the shade{chr(97 + i)} profile" for i in range(9)]
    question = (
        "Give the complete procedure for Iris intake with "
        + " and ".join(profiles)
        + "."
    )
    context = (
        "For Iris intake, first "
        + ", then ".join("use " + p for p in profiles)
        + ", finally record approval."
    )
    result = claim(question, context, "record approval")
    assert result.hypothesis is None and result.rejection == "procedure_proof_limit"


def test_governing_phrasal_action_cannot_be_replaced_by_a_local_prohibition():
    context = (
        "For Iris backup, never back up the records, "
        "verify the checksum, record approval."
    )
    result = claim("How do I back up Iris records?", context, "verify the checksum")
    assert result.hypothesis is None and result.rejection


def test_configuration_article_variation_cannot_remove_supplementary_proof():
    result = claim(
        "Give the complete procedure for Iris intake with the blue profile.",
        "For Iris intake, first use blue profile, "
        "then scan the pass, finally record approval.",
        "scan the pass",
    )
    assert result.rejection is None
    assert len(result.checks) == 1
    assert (
        result.checks[0].hypothesis
        == "The instructions for Iris intake require using the blue profile."
    )


def test_ordered_procedure_uses_the_same_governing_action_target_guard():
    context = (
        "For Iris backup, first back up the audit index, "
        "then scan the records catalog, finally verify the checksum."
    )
    result = claim("How do I back up Iris records?", context, "verify the checksum")
    assert result.hypothesis is None and result.rejection


def test_action_goal_proof_uses_one_governing_sentence_without_discarding_recipe():
    first = (
        "Test clearout: pause cache writes, remove stored entries, "
        "and verify the test state."
    )
    block = (
        first + " The approval owner is the duty editor. "
        "Never use this procedure for production."
    )
    result = claim("How do I clear out the test cache?", block, "pause cache writes")
    assert result.rejection is None and result.value == block
    check = next(c for c in result.checks if c.name == "procedure_action_target")
    assert check.premise == first
    assert (
        check.hypothesis == "The instructions describe how to clear out the test cache."
    )
    assert result.premise == block
    assert "Never use this procedure for production." in result.hypothesis


def test_minimal_goal_window_retains_the_governing_instruction_negation():
    first = (
        "Test clearout: never delete cache backups, "
        "stop cache writes, and verify the test state."
    )
    block = first + " The approval owner is the duty editor."
    result = claim("How do I clear out the test cache?", block, "verify the test state")
    assert result.rejection is None
    check = next(c for c in result.checks if c.name == "procedure_action_target")
    assert check.premise == first and "never delete" in check.premise


def test_explicit_applicable_procedure_prohibition_cannot_be_cut_from_goal_proof():
    block = (
        "Test clearout: pause cache writes, remove stored entries, "
        "and verify the test state. Never use this procedure for test."
    )
    result = claim("How do I clear out the test cache?", block, "pause cache writes")
    assert (
        result.hypothesis is None and result.rejection == "procedure_scope_prohibited"
    )


def test_numbered_colon_section_keeps_parameters_and_prohibitions_before_next_heading():
    block = (
        "Quartz intake: 1. Scan the pass. 2. Record approval. "
        "The observation window is 14 minutes. Never open the outer gate."
    )
    context = block + " Willow intake: 1. Scan a different pass. 2. Contact the deputy."
    result = claim(
        "Give the complete procedure for Quartz intake.", context, "Scan the pass"
    )
    assert result.rejection is None and result.value == block
    assert context[result.support_start : result.support_end] == block
    assert "14 minutes" in result.value and "Never open the outer gate." in result.value


def test_numbered_minimal_goal_window_skips_list_marker_periods():
    block = (
        "Test clearout: 1. Pause cache writes. 2. Remove stored entries. "
        "3. Verify the test state. The observation window is 14 minutes."
    )
    result = claim("How do I clear out the test cache?", block, "Pause cache writes")
    assert result.rejection is None
    check = next(c for c in result.checks if c.name == "procedure_action_target")
    assert check.premise == "Test clearout: 1. Pause cache writes."
    assert result.value == block


def test_numbered_section_continuation_retains_its_preceding_prerequisite():
    block = (
        "Before Quartz intake, check the stamp. "
        "Quartz intake: 1. Scan the pass. 2. Record approval. "
        "The observation window is 14 minutes. Never open the outer gate."
    )
    result = claim(
        "Give the complete procedure for Quartz intake.", block, "Scan the pass"
    )
    assert result.rejection is None and result.value == block


def test_same_procedure_prohibition_for_named_other_scope_remains_in_complete_section():
    block = (
        "Quartz intake: 1. Scan the pass. 2. Record approval. "
        "The observation window is 14 minutes. Never use this procedure for Willow."
    )
    result = claim(
        "Give the complete procedure for Quartz intake.", block, "Scan the pass"
    )
    assert result.rejection is None and result.value == block


@pytest.mark.parametrize(
    ("question", "sentence", "selected"),
    [
        (
            "How long does standard Alder intake last?",
            "A standard Alder intake lasts 17 minutes.",
            "17 minutes",
        ),
        (
            "On which day does standard Alder intake start?",
            "A standard Alder intake starts on Tuesdays.",
            "Tuesdays",
        ),
    ],
)
def test_complete_scoped_scalar_clause_does_not_borrow_unnecessary_header(
    question, sentence, selected
):
    context = (
        "These facts apply under standard conditions. The room has eight chairs. "
        + sentence
    )
    result = claim(question, context, selected)
    assert result.rejection is None and result.premise == sentence.rstrip(".")
    assert "standard Alder intake" in result.hypothesis


def test_abbreviated_scalar_still_requires_its_actual_contiguous_condition_header():
    context = (
        "These facts apply under standard conditions. The room has eight chairs. "
        "Alder intake lasts 17 minutes."
    )
    result = claim("How long does standard Alder intake last?", context, "17 minutes")
    assert result.rejection is None and result.premise in context
    assert result.premise.startswith("These facts apply under standard conditions.")
    assert "standard Alder intake" in result.hypothesis
    negative = claim(
        "How long does standard Alder intake last?",
        "A standard Alder intake does not last 17 minutes.",
        "17 minutes",
    )
    assert negative.hypothesis is None and negative.rejection


@pytest.mark.parametrize(
    ("kind", "question", "source", "selected", "expected"),
    [
        (
            "start_time",
            "At what time does standard Alder sequencing session open each week?",
            "The standard Alder sequencing session opens on Wednesdays at 09:40.",
            "09:40",
            "standard Alder sequencing session opens at 09:40",
        ),
        (
            "weekday",
            "On which day does standard Alder sequencing session open each week?",
            "The standard Alder sequencing session opens at 09:40 every Wednesday.",
            "Wednesday",
            "standard Alder sequencing session opens on Wednesday",
        ),
    ],
)
def test_open_schedule_preserves_requested_temporal_predicate(
    kind, question, source, selected, expected
):
    from dataclasses import replace

    requirement = replace(
        plan_requirements(question)[0],
        kind=kind,
        relation="opens",
        topic="standard Alder sequencing session",
        anchors=("alder",),
    )
    start = source.index(selected)
    result = support_claim(requirement, source, start, start + len(selected))
    assert result.rejection is None and result.hypothesis == expected


@pytest.mark.parametrize("predicate", ["occupies", "runs for"])
def test_elapsed_duration_source_predicates_are_not_confused_with_other_units(
    predicate,
):
    source = f"A standard Alder review {predicate} 19 minutes."
    result = claim("How long does standard Alder review last?", source, "19")
    assert (
        result.rejection is None
        and result.hypothesis == "standard Alder review lasts 19 minutes"
    )
    wrong = claim(
        "How long does standard Alder review last?",
        source.replace("minutes", "pixels"),
        "19",
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_belongs_to_ownership_binds_the_complete_role():
    result = claim(
        "Who owns Alder calendar sequencing?",
        "Alder calendar sequencing belongs to the calendar keeper.",
        "calendar keeper",
    )
    assert (
        result.rejection is None
        and result.hypothesis == "calendar keeper owns Alder calendar sequencing"
    )


def test_dependent_deputy_accepts_only_its_authorized_namespace_on_exact_owner_role():
    from app.services.answer_requirements import resolve_requirement

    reqs = plan_requirements(
        "Name the owner of Alder review and the person-role deputizing for that owner."
    )
    requirement = resolve_requirement(reqs[1], {reqs[0].id: "review steward"})
    source = "The backup clerk deputizes for the Alder review steward."
    start = source.index("backup clerk")
    result = support_claim(requirement, source, start, start + len("backup clerk"))
    assert (
        result.rejection is None
        and result.hypothesis == "backup clerk deputizes for the Alder review steward"
    )
    wrong = source.replace("Alder", "Willow")
    result = support_claim(requirement, wrong, start, start + len("backup clerk"))
    assert result.hypothesis is None and result.rejection


def test_count_as_binds_namespace_and_retains_typed_witness_description():
    result = claim(
        "For Alder, does a self-loop count as a cycle witness?",
        "A Alder self-loop is a cycle witness of one edge.",
        "one edge",
    )
    assert result.rejection is None
    assert result.hypothesis == "For Alder, a self-loop counts as a cycle witness"


def test_count_as_shared_namespace_and_directional_adjective_keep_negative_fact():
    source = (
        "A Alder self-loop is a cycle witness of one edge; "
        "two parallel edges in the same direction alone are not a cycle witness."
    )
    result = claim(
        "For Alder, do two same-direction parallel edges alone "
        "count as a cycle witness?",
        source,
        "not",
    )
    assert result.rejection is None
    assert (
        result.hypothesis == "For Alder, two same-direction parallel edges alone "
        "do not count as a cycle witness"
    )
    assert result.premise in source and "Alder" in result.premise


def test_full_scoped_procedure_value_is_the_minimal_premise_with_all_original_facets():
    context = (
        "These facts apply under standard conditions. The owner is the duty clerk. "
        "Complete standard procedure: 1. Open the Alder fixture. "
        "2. Select the blue profile. 3. Export the result to the audit ledger."
    )
    result = claim(
        "Give the complete ordered procedure for standard Alder intake, "
        "including fixture, profile and destination.",
        context,
        "Open the Alder fixture",
    )
    assert result.rejection is None and result.premise == result.value
    assert "including fixture, profile and destination" in result.hypothesis
    assert result.value.startswith("Complete standard procedure:")


def test_minimal_procedure_cannot_discard_explicit_other_activity_in_its_heading():
    context = (
        "Standard Alder audit procedure: 1. Open the Alder fixture. "
        "2. Select the blue profile. 3. Record approval."
    )
    result = claim(
        "Give the complete procedure for standard Alder intake.",
        context,
        "Open the Alder fixture",
    )
    assert result.hypothesis is None and result.rejection


def test_minimal_procedure_retains_its_earlier_applicable_governing_prohibition():
    context = (
        "Never use this procedure for standard Alder intake. "
        "Complete standard procedure: 1. Open the Alder fixture. "
        "2. Select the blue profile. 3. Record approval."
    )
    result = claim(
        "Give the complete procedure for standard Alder intake.",
        context,
        "Open the Alder fixture",
    )
    assert (
        result.hypothesis is None and result.rejection == "procedure_scope_prohibited"
    )


@pytest.mark.parametrize("namespace", ["staging", "Alder"])
def test_passive_modal_condition_uses_only_worker_validated_adjacent_source_range(
    namespace,
):
    question = f"What must be paused before restoring the {namespace} snapshot?"
    pair = (
        f"Pause the deployment queue. Restore the {namespace} snapshot "
        "and verify all health checks."
    )
    source = pair + " The unrelated room has eight chairs."
    result = claim(question, source, "the deployment queue")
    assert result.rejection is None
    assert (
        result.hypothesis == "the deployment queue must be paused before "
        f"restoring the {namespace} snapshot"
    )
    assert result.premise == pair
    assert source[result.support_start : result.support_end] == pair
    assert result.value == "the deployment queue"
    wrong = source.replace(f"the {namespace} snapshot", "the Willow snapshot")
    result = claim(question, wrong, "the deployment queue")
    assert result.hypothesis is None and result.rejection


def test_passive_modal_condition_cannot_borrow_a_negative_or_nonadjacent_instruction():
    question = "What must be paused before restoring the staging snapshot?"
    for source in [
        "Never pause the deployment queue. Restore the staging snapshot.",
        "Pause the deployment queue. Audit a different record. "
        "Restore the staging snapshot.",
    ]:
        result = claim(question, source, "the deployment queue")
        assert result.hypothesis is None and result.rejection


@pytest.mark.parametrize(
    ("scope", "polarity", "blocked"),
    [
        ("standard Meridian review", "prohibited", True),
        ("standard Meridian audit", "prohibited", False),
        ("standard Meridian review", "not prohibited", False),
    ],
)
def test_minimal_procedure_respects_preceding_scoped_instructions_below_restriction(
    scope, polarity, blocked
):
    source = (
        f"For {scope}, the instructions below are {polarity}. "
        "Complete standard procedure: 1. Open the Meridian fixture. 2. Record approval."
    )
    result = claim(
        "Give the complete procedure for standard Meridian review.",
        source,
        "Open the Meridian fixture",
    )
    if blocked:
        assert (
            result.hypothesis is None
            and result.rejection == "procedure_scope_prohibited"
        )
    else:
        assert result.rejection is None


def test_requested_ordinary_condition_keeps_actual_header_and_full_activity():
    source = (
        "These facts apply under standard conditions. "
        "Alder calendar sequencing belongs to the calendar keeper."
    )
    result = claim(
        "Who owns ordinary Alder calendar sequencing?", source, "calendar keeper"
    )
    assert result.rejection is None
    assert (
        result.hypothesis
        == "For ordinary conditions, the calendar keeper is the owner "
        "of the Alder calendar sequencing"
    )
    assert result.premise == source.rstrip(".")


def test_explicit_requested_record_deputy_modifier_is_not_dropped():
    source = (
        "These facts apply under standard sessions. "
        "Alder's record deputy is the packet editor."
    )
    result = claim(
        "Who is the record deputy for standard Alder coefficient records?",
        source,
        "packet editor",
    )
    assert result.rejection is None
    assert (
        result.hypothesis
        == "For standard conditions, the packet editor is the record deputy "
        "for the Alder coefficient records"
    )


def test_dependent_possessive_deputy_question_keeps_its_requested_role_relation():
    from app.services.answer_requirements import resolve_requirement

    owner, deputy = plan_requirements(
        "Which role owns standard Alder review, and which role is that owner's deputy?"
    )
    req = resolve_requirement(deputy, {owner.id: "the review steward"})
    source = "The card checker is the Alder review steward's deputy."
    start = source.index("card checker")
    result = support_claim(req, source, start, start + len("card checker"))
    assert result.rejection is None
    assert result.hypothesis == "card checker is the Alder review steward's deputy"


def test_scheduled_clock_weekday_binds_without_inventing_a_different_activity():
    source = (
        "The standard Alder nullable ordering run is scheduled for 15:40 on Tuesdays."
    )
    result = claim(
        "On which day does standard Alder nullable ordering run start?",
        source,
        "Tuesdays",
    )
    assert result.rejection is None
    assert (
        result.hypothesis == "standard Alder nullable ordering run starts on Tuesdays"
    )
    wrong = source.replace("ordering run", "ordering audit")
    result = claim(
        "On which day does standard Alder nullable ordering run start?",
        wrong,
        "Tuesdays",
    )
    assert result.hypothesis is None and result.rejection


def test_gerund_prohibition_request_binds_full_negative_instruction_and_parameters():
    source = (
        "For a standard Alder packet, do not omit zero coefficients "
        "between nonzero terms."
    )
    result = claim(
        "Give the rule against omitting coefficients for standard Alder packet.",
        source,
        "omit zero coefficients",
    )
    assert result.rejection is None
    assert result.value == "do not omit zero coefficients between nonzero terms"
    assert (
        result.hypothesis
        == "standard Alder packet must not omit zero coefficients between nonzero terms"
    )
    wrong = claim(
        "Give the rule against omitting coefficients for standard Alder packet.",
        source.replace("coefficients", "labels"),
        "omit zero labels",
    )
    assert wrong.hypothesis is None and wrong.rejection


@pytest.mark.parametrize(
    ("question", "source", "value", "expected"),
    [
        (
            "In Alder, is an empty string a null key or a non-null key?",
            "In Alder, an empty string is a non-null key.",
            "non-null key",
            "In Alder, an empty string is a non-null key",
        ),
        (
            "In Alder, is an empty string a synonym for null?",
            "In Alder, an empty string is not a synonym for null.",
            "not",
            "In Alder, an empty string is not a synonym for null",
        ),
    ],
)
def test_boolean_copular_classification_preserves_full_subject_scope_and_polarity(
    question, source, value, expected
):
    result = claim(question, source, value)
    assert result.rejection is None and result.hypothesis == expected
    wrong = claim(
        question, source.replace("empty string", "label for an empty string"), value
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_boolean_copular_unknown_class_is_not_assumed_to_be_a_requested_alternative():
    result = claim(
        "In Alder, is an empty string a null key or a non-null key?",
        "In Alder, an empty string is an audit key.",
        "audit key",
    )
    assert result.hypothesis is None and result.rejection


def test_prepared_factual_boolean_keeps_negative_actual_verb_and_source_antecedent():
    requirements = plan_requirements(
        "What is Alder's label for AX, and does this symbolic puzzle "
        "describe a biological sample?"
    )
    req = requirements[1]
    source = (
        "Alder is a symbolic puzzle only; it does not describe a biological sample."
    )
    start = source.index("a biological sample")
    result = support_claim(req, source, start, start + len("a biological sample"))
    assert result.rejection is None
    assert (
        result.hypothesis
        == "Alder symbolic puzzle does not describe a biological sample"
    )
    assert result.premise in source and result.premise.startswith("Alder is")


def test_conditional_passive_boolean_keeps_every_operand_and_negative_classification():
    question = (
        "In Alder, is a ring that touches longitude 180 degrees without crossing split?"
    )
    source = (
        "Alder treats a ring touching longitude 180 degrees "
        "without crossing it as one unsplit ring."
    )
    result = claim(question, source, "one unsplit ring")
    assert result.rejection is None
    assert (
        result.hypothesis == "In Alder, a ring that touches longitude 180 degrees "
        "without crossing is not split"
    )
    wrong = claim(
        question, source.replace("180 degrees", "170 degrees"), "one unsplit ring"
    )
    assert wrong.hypothesis is None and wrong.rejection


def test_nonnull_scalar_normalization_precedes_relation_scope_range():
    question = "What is Alder's label for bundle AX?"
    source = (
        "Alder is a symbolic guide: its label for bundle AX is cyan, "
        "and it does not describe a parcel."
    )
    selected = "cyan, and it does not describe a parcel"
    result = claim(question, source, selected)
    assert result.rejection is None and result.value == "cyan"
    assert source[result.start : result.end] == "cyan"
    assert result.premise in source and "Alder" in result.premise
    wrong = claim(question, source, "bundle AX is " + selected)
    assert wrong.hypothesis is None and wrong.rejection


def test_unresolved_copular_it_cannot_claim_another_namespace_definition():
    requirements = plan_requirements(
        "In Ibis, is an empty string a null key or a non-null key, "
        "and is it a synonym for null?"
    )
    req = requirements[1]
    source = (
        "In Willow, an empty string is a non-null key; it is not a synonym for null."
    )
    start = source.index("not")
    result = support_claim(req, source, start, start + 3)
    assert result.hypothesis is None and result.rejection


def test_factual_boolean_positive_and_wrong_object_controls_keep_actual_relation():
    from dataclasses import replace

    question = "Does Alder describe a biological sample?"
    # This isolates binding; standalone arbitrary Does-topic planning remains
    # outside this worker's ownership. The prepared compound path is above.
    req = replace(
        plan_requirements(question)[0],
        topic="Alder",
        anchors=("alder",),
        kind="boolean",
    )
    source = "Alder does describe a biological sample."
    start = source.index("a biological sample")
    positive = support_claim(req, source, start, start + len("a biological sample"))
    assert (
        positive.rejection is None
        and positive.hypothesis == "Alder does describe a biological sample"
    )
    source = "Alder does not describe a storage sample."
    start = source.index("a storage sample")
    wrong = support_claim(req, source, start, start + len("a storage sample"))
    assert wrong.hypothesis is None and wrong.rejection
