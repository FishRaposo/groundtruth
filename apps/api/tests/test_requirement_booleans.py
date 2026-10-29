"""Pure negative-relation tests; a proposition is not NLI/application acceptance."""

from dataclasses import asdict

import pytest
from app.services.answer_requirements import Requirement, plan_requirements
from app.services.requirement_booleans import negative_boolean_claim


def request(question, topic):
    return Requirement("r1", question, 0, len(question), question, "boolean", topic, ())


def claim(question, topic, context, value):
    start = context.index(value)
    return negative_boolean_claim(
        request(question, topic), context, start, start + len(value)
    )


@pytest.mark.parametrize(
    ("question", "topic", "context", "value", "hypothesis", "kind"),
    [
        (
            "Does Cedar describe a biological sample?",
            "Cedar",
            "Cedar does not describe a biological sample.",
            "does not describe a biological sample",
            "Cedar does not describe a biological sample",
            "factual",
        ),
        (
            "Do Cedar arrays store two rows?",
            "Cedar arrays",
            "Cedar arrays do not store two rows.",
            "Cedar arrays do not store two rows",
            "Cedar arrays do not store two rows",
            "factual",
        ),
        (
            "Does Cedar write an empty record?",
            "Cedar",
            "Cedar writes the zero vector as 0; it does not write an empty record.",
            "it does not write an empty record",
            "Cedar does not write an empty record",
            "factual",
        ),
        (
            "Does Cedar symbolic puzzle describe a biological sample?",
            "Cedar symbolic puzzle",
            "Cedar is a symbolic puzzle only: its transform of ABC is BCA, "
            "and it does not describe a biological sample.",
            "does not describe a biological sample",
            "Cedar symbolic puzzle does not describe a biological sample",
            "factual",
        ),
        (
            "May Cedar use an empty record?",
            "Cedar",
            "Cedar may not use an empty record.",
            "may not use an empty record",
            "Cedar may not use an empty record",
            "permission",
        ),
        (
            "May Cedar use an empty record?",
            "Cedar",
            "Cedar is not permitted to use an empty record.",
            "not permitted to use an empty record",
            "Cedar is not permitted to use an empty record",
            "permission",
        ),
        (
            "May Cedar use an empty record?",
            "Cedar",
            "Cedar is not allowed to use an empty record.",
            "is not allowed to use an empty record",
            "Cedar is not allowed to use an empty record",
            "permission",
        ),
        (
            "Can Cedar use an empty record?",
            "Cedar",
            "Cedar cannot use an empty record.",
            "cannot use an empty record",
            "Cedar cannot use an empty record",
            "capability",
        ),
        (
            "Must Cedar remove zero rows?",
            "Cedar",
            "Cedar must not remove zero rows.",
            "must not remove zero rows",
            "Cedar must not remove zero rows",
            "obligation",
        ),
        (
            "Should Cedar remove zero rows?",
            "Cedar",
            "Cedar should not remove zero rows.",
            "should not remove zero rows",
            "Cedar should not remove zero rows",
            "advice",
        ),
        (
            "For the current batch, does Cedar store two rows?",
            "Cedar",
            "For the current batch, Cedar does not store two rows.",
            "not store two rows",
            "For the current batch, Cedar does not store two rows",
            "factual",
        ),
    ],
)
def test_complete_negative_relation_retains_full_subject_action_object_and_semantics(
    question, topic, context, value, hypothesis, kind
):
    req = request(question, topic)
    before = asdict(req)
    start = context.index(value)
    result = negative_boolean_claim(req, context, start, start + len(value))
    assert result.rejection is None and result.hypothesis == hypothesis
    assert result.relation_kind == kind
    assert context[result.start : result.end] == value
    assert result.support_start is not None and result.support_end is not None
    assert context[result.support_start : result.support_end].endswith(".")
    assert (result.raw_start, result.raw_end) == (start, start + len(value))
    assert asdict(req) == before


def test_exposed_cobalt_nonnull_long_proposal_binds_only_complete_negative_predicate():
    question = (
        "What is Cobalt's complement of ACG, and does this symbolic puzzle "
        "describe a biological sample?"
    )
    req = plan_requirements(question)[1]
    context = (
        "💠 Notice. Cobalt is a symbolic puzzle only: its complement of ACG is TGC, "
        "and it does not describe a biological sample. Cobalt prints labels."
    )
    raw = "does not describe a biological sample. Cobalt prints labels."
    start = context.index(raw)
    result = negative_boolean_claim(req, context, start, len(context))
    assert (
        result.hypothesis
        == "Cobalt symbolic puzzle does not describe a biological sample"
    )
    assert result.rejection is None and result.relation_kind == "factual"
    assert context[result.start : result.end] == "does not describe a biological sample"
    assert (
        context[result.support_start : result.support_end]
        == context[len("💠 Notice. ") : context.index(" Cobalt prints")]
    )
    assert (result.raw_start, result.raw_end) == (start, len(context))


def test_exposed_hollow_factual_writing_convention_does_not_establish_permission():
    req = plan_requirements(
        "How does Hollow represent the zero polynomial, and may it use an empty record?"
    )[1]
    context = (
        "Hollow writes the zero polynomial as a single 0 followed by a period; "
        "it does not write an empty record."
    )
    value = "it does not write an empty record"
    start = context.index(value)
    result = negative_boolean_claim(req, context, start, start + len(value))
    assert result.hypothesis is None
    assert result.rejection == "factual_negative_does_not_establish_permission"


@pytest.mark.parametrize(
    ("question", "topic", "context", "value"),
    [
        (
            "May Cedar use an empty record?",
            "Cedar",
            "Cedar does not use an empty record.",
            "does not use an empty record",
        ),
        (
            "Does Cedar describe a sample?",
            "Cedar",
            "Cedar cannot describe a sample.",
            "cannot describe a sample",
        ),
        (
            "May Cedar use a token?",
            "Cedar",
            "Cedar cannot use a token.",
            "cannot use a token",
        ),
        (
            "Can Cedar use a token?",
            "Cedar",
            "Cedar may not use a token.",
            "may not use a token",
        ),
        (
            "Does Cedar describe a sample?",
            "Cedar",
            "Birch does not describe a sample. Cedar is nearby.",
            "does not describe a sample",
        ),
        (
            "Does Cedar describe a sample?",
            "Cedar",
            "Cedar's supervisor does not describe a sample.",
            "does not describe a sample",
        ),
        (
            "Does Cedar describe a sample?",
            "Cedar",
            "The archive of Cedar does not describe a sample.",
            "does not describe a sample",
        ),
        (
            "Does Cedar describe a sample?",
            "Cedar",
            "Cedar describes a non-biological sample.",
            "non-biological sample",
        ),
        (
            "Does Cedar describe a sample?",
            "Cedar",
            "Cedar does not record a sample.",
            "does not record a sample",
        ),
        (
            "Does Cedar store two rows?",
            "Cedar",
            "Cedar does not store two bytes.",
            "does not store two bytes",
        ),
        (
            "Does Cedar describe a sample?",
            "Cedar",
            "Cedar does not describe a sample archive.",
            "does not describe a sample",
        ),
        (
            "Does Cedar describe a sample?",
            "Cedar",
            "Cedar does not describe a sample.",
            "describe a sample",
        ),
        (
            "Does Cedar describe a sample?",
            "Cedar",
            "Cedar does not describe a sample.",
            "does not",
        ),
        (
            "Does Cedar symbolic puzzle describe a sample?",
            "Cedar symbolic puzzle",
            "Cedar is a symbolic puzzle: Birch describes a card, "
            "and it does not describe a sample.",
            "does not describe a sample",
        ),
        (
            "Does Cedar symbolic puzzle describe a sample?",
            "Cedar symbolic puzzle",
            "Birch is a symbolic puzzle only: its transform of ABC is BCA, "
            "and it does not describe a sample.",
            "does not describe a sample",
        ),
        (
            "Does Cedar current puzzle describe a sample?",
            "Cedar current puzzle",
            "Cedar is a former puzzle only: its transform of ABC is BCA, "
            "and it does not describe a sample.",
            "does not describe a sample",
        ),
        (
            "For the current batch, does Cedar store two rows?",
            "Cedar",
            "For the old batch, Cedar does not store two rows.",
            "does not store two rows",
        ),
        (
            "For the current batch, does Cedar store two rows?",
            "Cedar",
            "Cedar does not store two rows.",
            "does not store two rows",
        ),
        (
            "Does Cedar store two rows and are they approved?",
            "Cedar",
            "Cedar does not store two rows.",
            "does not store two rows",
        ),
        (
            "Does Cedar not describe a sample?",
            "Cedar",
            "Cedar does not describe a sample.",
            "does not describe a sample",
        ),
        (
            "Does Élan describe a sample?",
            "Élan",
            "Élan\u200b does not describe a sample.",
            "does not describe a sample",
        ),
        (
            "Does Cedar describe a sample?",
            "Cedar",
            "Cedar does not describe a sample?",
            "does not describe a sample",
        ),
    ],
)
def test_wrong_subject_relation_modal_units_or_partial_action_has_no_hypothesis(
    question, topic, context, value
):
    result = claim(question, topic, context, value)
    assert result.hypothesis is None and result.rejection
    assert result.support_start is None and result.support_end is None


@pytest.mark.parametrize(
    ("start", "end"), [(None, None), (-1, 5), (0, 999), (True, 5), (4, 4)]
)
def test_absent_or_invalid_raw_proposals_are_never_revived(start, end):
    req = request("Does Cedar describe a sample?", "Cedar")
    result = negative_boolean_claim(
        req, "Cedar does not describe a sample.", start, end
    )
    assert result.hypothesis is None and result.rejection


def test_selected_explicit_subject_uses_its_own_negative_clause():
    context = "Birch does not describe a card; Cedar does not describe a sample."
    result = claim(
        "Does Cedar describe a sample?",
        "Cedar",
        context,
        "Cedar does not describe a sample",
    )
    assert result.hypothesis == "Cedar does not describe a sample"
    assert result.rejection is None


def test_pronoun_does_not_borrow_an_actor_across_an_intervening_clause():
    context = (
        "Cedar records the input; Birch does not store a row; "
        "it does not describe a sample."
    )
    result = claim(
        "Does Cedar describe a sample?",
        "Cedar",
        context,
        "it does not describe a sample",
    )
    assert result.hypothesis is None and result.rejection


def test_explicit_negative_obligation_can_deny_permission_without_rewriting_must():
    context = "Cedar intake must not skip the stamp."
    result = claim(
        "May Cedar intake skip the stamp?",
        "Cedar intake",
        context,
        "must not skip the stamp",
    )
    assert result.rejection is None
    assert result.hypothesis == "Cedar intake must not skip the stamp"
    assert result.relation_kind == "obligation"


@pytest.mark.parametrize("auxiliary", ["Can", "Does", "Should"])
def test_negative_obligation_does_not_become_capability_occurrence_or_advice(auxiliary):
    result = claim(
        f"{auxiliary} Cedar intake skip the stamp?",
        "Cedar intake",
        "Cedar intake must not skip the stamp.",
        "must not skip the stamp",
    )
    assert result.hypothesis is None and result.rejection


@pytest.mark.parametrize(
    ("topic", "context"),
    [
        (
            "Alder symbolic puzzle",
            "Alder is a symbolic puzzle only; "
            "it does not describe a biological sample.",
        ),
        ("Cedar", "Cedar does not describe a biological sample."),
        (
            "Alder symbolic puzzle",
            "Alder is a symbolic puzzle only: its transform of ABC is BCA, "
            "and it does not describe a biological sample.",
        ),
    ],
)
def test_exact_whole_object_can_expand_to_the_complete_verified_negative_predicate(
    topic, context
):
    value = "a biological sample"
    start = context.index(value)
    result = negative_boolean_claim(
        request(f"Does {topic} describe a biological sample?", topic),
        context,
        start,
        start + len(value),
    )
    assert result.rejection is None
    assert result.hypothesis == f"{topic} does not describe a biological sample"
    assert context[result.start : result.end] == "does not describe a biological sample"
    assert (result.raw_start, result.raw_end) == (start, start + len(value))
    assert result.support_start <= result.start < result.end <= result.support_end


@pytest.mark.parametrize(
    ("question", "topic", "context", "value"),
    [
        (
            "Does Alder symbolic puzzle describe a biological sample?",
            "Alder symbolic puzzle",
            "Alder is a symbolic puzzle only; "
            "it does not describe a biological sample.",
            "biological sample",
        ),
        (
            "Does Alder symbolic puzzle describe a biological sample?",
            "Alder symbolic puzzle",
            "Alder is a symbolic puzzle only; "
            "it does not describe a biological sample.",
            "a biological",
        ),
        (
            "Does Alder symbolic puzzle describe a biological sample?",
            "Alder symbolic puzzle",
            "Alder is a symbolic puzzle only; "
            "it does not describe a biological sample archive.",
            "a biological sample",
        ),
        (
            "Does Alder symbolic puzzle describe a biological sample?",
            "Alder symbolic puzzle",
            "Birch is a symbolic puzzle only; "
            "it does not describe a biological sample.",
            "a biological sample",
        ),
        (
            "Does Alder symbolic puzzle describe a biological sample?",
            "Alder symbolic puzzle",
            "Alder is a production puzzle only; "
            "it does not describe a biological sample.",
            "a biological sample",
        ),
        (
            "Does Alder symbolic puzzle describe a biological sample?",
            "Alder symbolic puzzle",
            "Alder is not a symbolic puzzle; it does not describe a biological sample.",
            "a biological sample",
        ),
        (
            "Does Alder symbolic puzzle describe a biological sample?",
            "Alder symbolic puzzle",
            "Alder is a symbolic puzzle only; it describes a biological sample.",
            "a biological sample",
        ),
        (
            "Can Alder symbolic puzzle describe a biological sample?",
            "Alder symbolic puzzle",
            "Alder is a symbolic puzzle only; "
            "it does not describe a biological sample.",
            "a biological sample",
        ),
        (
            "Does Alder symbolic puzzle describe a biological sample?",
            "Alder symbolic puzzle",
            "Alder is a symbolic puzzle only; "
            "it does not describe a biological sample. More text.",
            "a biological sample. More text.",
        ),
    ],
)
def test_object_expansion_refuses_partial_nouns_wrong_actor_class_and_modality(
    question, topic, context, value
):
    result = claim(question, topic, context, value)
    assert result.hypothesis is None and result.rejection


@pytest.mark.parametrize(
    ("question", "topic", "context", "value", "expected", "proof"),
    [
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "Quartz is a symbolic encoder. It does not write an empty record.",
            "does not write an empty record",
            "Quartz does not write an empty record",
            "Quartz is a symbolic encoder. It does not write an empty record.",
        ),
        (
            "Does Cedar describe a sample?",
            "Cedar",
            "Cedar is a puzzle. It does not describe a sample.",
            "does not describe a sample",
            "Cedar does not describe a sample",
            "Cedar is a puzzle. It does not describe a sample.",
        ),
        (
            "Does Quartz symbolic encoder write an empty record?",
            "Quartz symbolic encoder",
            "Quartz is a symbolic encoder. It does not write an empty record.",
            "an empty record",
            "Quartz symbolic encoder does not write an empty record",
            "Quartz is a symbolic encoder. It does not write an empty record.",
        ),
        (
            "Do Quartz devices write an empty record?",
            "Quartz devices",
            "Quartz devices are the symbolic encoders. "
            "They do not write an empty record.",
            "do not write an empty record",
            "Quartz devices do not write an empty record",
            "Quartz devices are the symbolic encoders. "
            "They do not write an empty record.",
        ),
        (
            "For the current batch, does Quartz write an empty record?",
            "Quartz",
            "For the current batch, Quartz is a symbolic "
            "encoder. It does not write an empty record.",
            "does not write an empty record",
            "For the current batch, Quartz does not write an empty record",
            "For the current batch, Quartz is a symbolic "
            "encoder. It does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "For the current batch, Quartz is a symbolic "
            "encoder. It does not write an empty record.",
            "does not write an empty record",
            "For the current batch, Quartz does not write an empty record",
            "For the current batch, Quartz is a symbolic "
            "encoder. It does not write an empty record.",
        ),
        (
            "Does Élan write an empty record?",
            "Élan",
            "💠 Notice. Élan is a symbolic encoder.\n"
            "It does not write an empty record.",
            "does not write an empty record",
            "Élan does not write an empty record",
            "Élan is a symbolic encoder.\nIt does not write an empty record.",
        ),
    ],
)
def test_one_immediately_previous_sentence_can_supply_the_exact_grammatical_actor(
    question, topic, context, value, expected, proof
):
    result = claim(question, topic, context, value)
    assert result.rejection is None and result.hypothesis == expected
    assert context[result.support_start : result.support_end] == proof
    assert context[result.start : result.end].endswith(value)
    assert (result.raw_start, result.raw_end) == (
        context.index(value),
        context.index(value) + len(value),
    )


@pytest.mark.parametrize(
    ("question", "topic", "context"),
    [
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "Willow is a partner of Quartz. It does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "Willow records Quartz. It does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "Willow is a Quartz encoder. It does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "Quartz's partner is a symbolic encoder. "
            "It does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "Quartz is a symbolic encoder. Willow is "
            "ready. It does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "Quartz is a symbolic encoder; Willow is a "
            "reviewer. It does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "Quartz is a symbolic encoder and Willow is "
            "a reviewer. It does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "Quartz is a symbolic encoder. Willow records "
            "a value; it does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "Quartz is a symbolic encoder? It does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "Quartz is a symbolic encoder.\n\nIt does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "Quartz\u200b is a symbolic encoder. It does not write an empty record.",
        ),
        (
            "For the current batch, does Quartz write an empty record?",
            "Quartz",
            "For the old batch, Quartz is a symbolic "
            "encoder. It does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "For the old batch, Quartz is a symbolic encoder. For "
            "the current batch, it does not write an empty record.",
        ),
        (
            "Can Quartz write an empty record?",
            "Quartz",
            "Quartz is a symbolic encoder. It does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "It does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "Quartz is a symbolic encoder: its label is "
            "amber. It does not write an empty record.",
        ),
        (
            "Does Quartz write an empty record?",
            "Quartz",
            "Quartz records an input under old "
            "conditions. It does not write an empty record.",
        ),
    ],
)
def test_previous_sentence_actor_cannot_be_borrowed_from_mentions_or_unrelated_scopes(
    question, topic, context
):
    result = claim(question, topic, context, "does not write an empty record")
    assert result.hypothesis is None and result.rejection


@pytest.mark.parametrize(
    ("topic", "context"),
    [
        (
            "Quartz devices",
            "Quartz devices are the symbolic encoders. It may not use an empty record.",
        ),
        ("Quartz", "Quartz is a symbolic encoder. They may not use an empty record."),
    ],
)
def test_previous_classifier_pronoun_cannot_change_subject_number(topic, context):
    result = claim(
        f"May {topic} use an empty record?",
        topic,
        context,
        "may not use an empty record",
    )
    assert result.hypothesis is None and result.rejection
