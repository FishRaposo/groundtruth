"""Pure source-coordinate tests; a built proposition still needs entailment."""

from dataclasses import dataclass, replace

import pytest
from app.services.answer_requirements import Requirement, plan_requirements
from app.services.requirement_relations import (
    question_topic,
    relation_answer_range,
    relation_hypothesis,
    relation_source_range,
)


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


def bound(question, context, value, *, occurrence=0, clause_start=0):
    start = context.index(value, occurrence)
    req = Requirement("r1", question, 0, len(question), question, "generic", "", ())
    return Binding(
        req,
        context,
        value,
        context[clause_start:],
        "",
        start,
        start + len(value),
        clause_start,
    )


@pytest.mark.parametrize(
    ("question", "context", "value", "expected"),
    [
        (
            "Which years have an extra day?",
            "Leap years have an extra day.",
            "Leap years",
            "Leap years have an extra day",
        ),
        (
            "Which year has an extra day?",
            "The leap year has an extra day.",
            "leap year",
            "leap year has an extra day",
        ),
        (
            "Which devices have two ports?",
            "Approved devices have two ports.",
            "Approved devices",
            "Approved devices have two ports",
        ),
        (
            "Which years do not have an extra day?",
            "Common years do not have an extra day.",
            "Common years",
            "Common years do not have an extra day",
        ),
        (
            "Which years have an extra day under the current rule?",
            "Leap years have an extra day under the current rule.",
            "Leap years",
            "Leap years have an extra day under the current rule",
        ),
        (
            "Which years have an extra day and use the blue calendar?",
            "Leap years have an extra day and use the blue calendar.",
            "Leap years",
            "Leap years have an extra day and use the blue calendar",
        ),
        (
            "What is Orchid's label for bundle AX?",
            "Orchid's label for bundle AX is violet.",
            "violet",
            "Orchid's label for bundle AX is violet",
        ),
        (
            "What is the label of Orchid for bundle AX?",
            "Orchid's label for bundle AX is violet.",
            "violet",
            "the label of Orchid for bundle AX is violet",
        ),
        (
            "What is Orchid's current access mode for bundle AX?",
            "The current access mode of Orchid for bundle AX is read-only.",
            "read-only",
            "Orchid's current access mode for bundle AX is read-only",
        ),
        (
            "What is Orchid’s label for bundle AX?",
            "Orchid’s label for bundle AX is ‘violet’.",
            "violet",
            "Orchid’s label for bundle AX is violet",
        ),
        (
            "What is Élan's façade-key for bundle Ω?",
            "💠 Note. Élan's façade-key for bundle Ω is κ-7.",
            "κ-7",
            "Élan's façade-key for bundle Ω is κ-7",
        ),
        (
            "What code corresponds to payload 1010?",
            "Code Z7 corresponds to payload 1010.",
            "Z7",
            "Code Z7 corresponds to payload 1010",
        ),
        (
            "Which token corresponds to input Ω?",
            "The token κ-7 corresponds to input Ω.",
            "κ-7",
            "The token κ-7 corresponds to input Ω",
        ),
        (
            "What current code corresponds to payload 1010?",
            "The current code Z7 corresponds to payload 1010.",
            "Z7",
            "The current code Z7 corresponds to payload 1010",
        ),
    ],
)
def test_relation_keeps_the_full_requested_fact(question, context, value, expected):
    binding = bound(question, context, value)
    before = replace(binding)
    assert relation_hypothesis(binding) == (expected, None)
    assert binding == before and binding.context[binding.start : binding.end] == value


@pytest.mark.parametrize(
    ("question", "context", "value"),
    [
        (
            "Which years have an extra day?",
            "The archive of leap years has an extra day.",
            "leap years",
        ),
        (
            "Which years have an extra day?",
            "Leap years archive has an extra day.",
            "Leap years",
        ),
        ("Which years have an extra day?", "Leap years have an extra day.", "Leap"),
        (
            "Which years have an extra day?",
            "Leap years never have an extra day.",
            "Leap years",
        ),
        (
            "Which years do not have an extra day?",
            "Common years have an extra day.",
            "Common years",
        ),
        (
            "Which years have an extra day under the current rule?",
            "Leap years have an extra day.",
            "Leap years",
        ),
        (
            "Which years have an extra day and use the blue calendar?",
            "Leap years have an extra day.",
            "Leap years",
        ),
        ("Which years have two days?", "Leap years have two hours.", "Leap years"),
        ("Which years have an extra day?", "Leap days have an extra day.", "Leap days"),
        (
            "What is Orchid's label for bundle AX?",
            "Willow's label for bundle AX is violet.",
            "violet",
        ),
        (
            "What is Orchid's label for bundle AX?",
            "Orchid's label for bundle BX is violet.",
            "violet",
        ),
        (
            "What is Orchid's label for bundle AX?",
            "Orchid's label archive for bundle AX is violet.",
            "violet",
        ),
        (
            "What is Orchid's label for bundle AX?",
            "The archive of Orchid's label for bundle AX is violet.",
            "violet",
        ),
        (
            "What is Orchid's label for bundle AX?",
            "Orchid's label for bundle AX is violet archive.",
            "violet",
        ),
        (
            "What is Orchid's label for bundle AX?",
            "Orchid's label for bundle AX is the supervisor of violet.",
            "violet",
        ),
        (
            "What is Orchid's label for bundle AX?",
            "Orchid's label for bundle AX is not violet.",
            "violet",
        ),
        (
            "What is Orchid's current label for bundle AX?",
            "Orchid's old label for bundle AX is violet.",
            "violet",
        ),
        (
            "What is Orchid's label for bundle AX and package BY?",
            "Orchid's label for bundle AX is violet.",
            "violet",
        ),
        (
            "What is Orchid's label for bundle AX?",
            "Orchid's label for bundle AX is green. Willow's label is violet.",
            "violet",
        ),
        (
            "What code corresponds to payload 1010?",
            "Payload 1010 corresponds to code Z7.",
            "Z7",
        ),
        (
            "What code corresponds to payload 1010?",
            "Code Z7 corresponds to payload 1001.",
            "Z7",
        ),
        (
            "What code corresponds to payload 1010?",
            "Code Z7 archive corresponds to payload 1010.",
            "Z7",
        ),
        (
            "What code corresponds to payload 1010?",
            "The label of code Z7 corresponds to payload 1010.",
            "Z7",
        ),
        (
            "What code corresponds to payload 1010?",
            "Code Z7 does not correspond to payload 1010.",
            "Z7",
        ),
        (
            "What current code corresponds to payload 1010?",
            "The former code Z7 corresponds to payload 1010.",
            "Z7",
        ),
        (
            "What code corresponds to payload 1010 and payload 1111?",
            "Code Z7 corresponds to payload 1010.",
            "Z7",
        ),
        ("What is Élan's label?", "Élan\u202e's label is violet.", "violet"),
        ("What is Élan\u200b's label?", "Élan's label is violet.", "violet"),
        ("Why does Orchid use violet?", "Orchid uses violet.", "violet"),
        ("Who approves bundle AX?", "Mira approves bundle AX.", "Mira"),
        ("What is the name of Orchid?", "Orchid is named violet.", "violet"),
    ],
)
def test_wrong_or_incomplete_local_argument_has_no_proposition(
    question, context, value
):
    hypothesis, reason = relation_hypothesis(bound(question, context, value))
    assert hypothesis is None and reason


def test_repeated_literal_requires_the_selected_occurrence_to_bind():
    text = "Orchid's label is violet. Willow's label is violet."
    binding = bound(
        "What is Orchid's label?", text, "violet", occurrence=text.index("Willow")
    )
    assert relation_hypothesis(binding)[0] is None


@pytest.mark.parametrize(
    "changes",
    [
        {"start": -1},
        {"end": 999},
        {"value": "other"},
        {"clause_start": 999},
        {"start": True},
    ],
)
def test_invalid_source_coordinates_never_form_a_proposition(changes):
    binding = bound("What is Orchid's label?", "Orchid's label is violet.", "violet")
    assert relation_hypothesis(replace(binding, **changes))[0] is None


@pytest.mark.parametrize(
    ("question", "context", "value"),
    [
        (
            "What is Orchid's label?",
            "Orchid's label is violet. Willow is green.",
            "violet. Willow is green",
        ),
        (
            "Which years have an extra day?",
            "Leap years. Other years have an extra day.",
            "Leap years. Other years",
        ),
    ],
)
def test_candidate_cannot_cross_a_local_clause_boundary(question, context, value):
    assert relation_hypothesis(bound(question, context, value))[0] is None


def test_unicode_coordinates_are_from_context_even_with_a_reconstructed_premise():
    context = "💠 Note. Élan's label for bundle Ω is κ-7. More text."
    binding = bound("What is Élan's label for bundle Ω?", context, "κ-7")
    binding = replace(binding, premise="Reconstructed header: " + context)
    assert relation_hypothesis(binding) == ("Élan's label for bundle Ω is κ-7", None)
    assert (binding.start, binding.end) == (37, 40)
    assert context[binding.start : binding.end] == "κ-7"


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Which years have an extra day?", "years"),
        ("What is Orchid's label for bundle AX?", "Orchid's label for bundle AX"),
        (
            "What is the label of Orchid for bundle AX?",
            "the label of Orchid for bundle AX",
        ),
        ("What code corresponds to payload 1010?", "payload 1010"),
        ("Who owns Orchid?", None),
    ],
)
def test_topic_helper_preserves_literal_request_scope(question, expected):
    assert question_topic(question) == expected


@pytest.mark.parametrize(
    ("question", "context", "value", "expected", "window"),
    [
        (
            "What must be paused before restoring the staging snapshot?",
            "Browser acceptance rollback runbook version1. Pause the deployment queue. "
            "Restore the staging snapshot and verify all health checks. "
            "This controlledfixture isownedbythelocalbrowsertest. "
            "Recordtherollbackintheincidentlog.",
            "deployment queue",
            "the deployment queue must be paused before restoring the staging snapshot",
            "Pause the deployment queue. Restore the staging snapshot "
            "and verify all health checks.",
        ),
        (
            "What must be paused after restoring the staging snapshot?",
            "Restore the staging snapshot and verify all health checks. "
            "Pause the deployment queue.",
            "deployment queue",
            "the deployment queue must be paused after restoring the staging snapshot",
            "Restore the staging snapshot and verify all health checks. "
            "Pause the deployment queue.",
        ),
        (
            "What should be copied before verifying the release?",
            "Copy the audit file. Verify the release.",
            "audit file",
            "the audit file should be copied before verifying the release",
            "Copy the audit file. Verify the release.",
        ),
        (
            "What must be stopped before copying the report?",
            "Stop the worker. Copy the report.",
            "the worker",
            "the worker must be stopped before copying the report",
            "Stop the worker. Copy the report.",
        ),
        (
            "What must be paused before restoring the Ω snapshot?",
            "💠 Notice. Pause Élan's queue. Restore the Ω snapshot. More text.",
            "Élan's queue",
            "Élan's queue must be paused before restoring the Ω snapshot",
            "Pause Élan's queue. Restore the Ω snapshot.",
        ),
    ],
)
def test_ordered_imperatives_bind_exact_action_object_and_adjacent_condition(
    question, context, value, expected, window
):
    binding = bound(question, context, value)
    before = replace(binding)
    source_range = relation_source_range(
        binding.req, context, binding.start, binding.end
    )
    assert source_range is not None
    assert context[slice(*source_range)] == window
    assert relation_hypothesis(binding) == (expected, None)
    assert binding == before and context[binding.start : binding.end] == value
    assert question_topic(question) in {
        "the staging snapshot",
        "the release",
        "the report",
        "the Ω snapshot",
    }


@pytest.mark.parametrize(
    ("question", "context", "value"),
    [
        (
            "What must be paused before restoring the staging snapshot?",
            "Restore the staging snapshot. Pause the deployment queue.",
            "deployment queue",
        ),
        (
            "What must be paused after restoring the staging snapshot?",
            "Pause the deployment queue. Restore the staging snapshot.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot?",
            "Delete the deployment queue. Restore the staging snapshot.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot?",
            "Pause the deployment queue archive. Restore the staging snapshot.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot?",
            "Pause the deployment queue. Restore the production snapshot.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot?",
            "Pause the deployment queue. Restore the staging snapshot archive.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot?",
            "Do not pause the deployment queue. Restore the staging snapshot.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot?",
            "Pause the deployment queue. Do not restore the staging snapshot.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot?",
            "Pause the deployment queue? Restore the staging snapshot.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot?",
            "Pause the deployment queue. The snapshot belongs to staging. "
            "Restore the staging snapshot.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot?",
            "The operator paused the deployment queue. Restore the staging snapshot.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot?",
            "Pause the deployment queue. The operator restores the staging snapshot.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot?",
            "Pause the deployment queue.\n\nRestore the staging snapshot.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot?",
            "Pause the deployment queue if approved. Restore the staging snapshot.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot?",
            "Pause the deployment queue. Restore the staging snapshot after approval.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot "
            "and approving the release?",
            "Pause the deployment queue. Restore the staging snapshot.",
            "deployment queue",
        ),
        (
            "What must be paused unless restoring the staging snapshot?",
            "Pause the deployment queue. Restore the staging snapshot.",
            "deployment queue",
        ),
        (
            "What must not be paused before restoring the staging snapshot?",
            "Pause the deployment queue. Restore the staging snapshot.",
            "deployment queue",
        ),
        (
            "What must be paused before restoring the staging snapshot?",
            "Pause the deployment queue. Restore the staging snapshot.",
            "staging snapshot",
        ),
    ],
)
def test_ordered_imperatives_never_borrow_wrong_or_unresolved_conditions(
    question, context, value
):
    binding = bound(question, context, value)
    assert (
        relation_source_range(binding.req, context, binding.start, binding.end) is None
    )
    hypothesis, reason = relation_hypothesis(binding)
    assert hypothesis is None and reason


def test_ordered_hypothesis_requires_the_entailment_premise_to_include_the_condition():
    context = "Pause the deployment queue. Restore the staging snapshot."
    binding = bound(
        "What must be paused before restoring the staging snapshot?",
        context,
        "deployment queue",
    )
    binding = replace(binding, premise="Pause the deployment queue.")
    assert relation_hypothesis(binding)[0] is None


def test_source_range_does_not_expand_other_relation_forms():
    binding = bound(
        "What is Orchid's label?",
        "Orchid's label is violet. Pause the queue.",
        "violet",
    )
    assert (
        relation_source_range(binding.req, binding.context, binding.start, binding.end)
        is None
    )


@pytest.mark.parametrize("clause_start", [-1, True, 999])
def test_ordered_hypothesis_rejects_invalid_clause_coordinates(clause_start):
    context = "Pause the deployment queue. Restore the staging snapshot."
    binding = bound(
        "What must be paused before restoring the staging snapshot?",
        context,
        "deployment queue",
    )
    assert relation_hypothesis(replace(binding, clause_start=clause_start))[0] is None


@pytest.mark.parametrize(
    ("question", "context", "value", "expected"),
    [
        (
            "How does Hollow represent the zero polynomial?",
            "Hollow writes the zero polynomial as a single 0 followed by a period.",
            "as a single 0 followed by a period",
            "Hollow represents the zero polynomial as a single 0 followed by a period",
        ),
        (
            "How does Cedar represent the empty vector?",
            "Cedar encodes the empty vector as two brackets.",
            "two brackets",
            "Cedar represents the empty vector as two brackets",
        ),
        (
            "What code identifies Hollow's expansion packet?",
            "The owner-only Hollow expansion packet has the code Silver Den.",
            "Silver Den",
            "Silver Den is the code that identifies Hollow's expansion packet",
        ),
        (
            "What token identifies Élan's current expansion case?",
            "The reserved Élan current expansion case has the token κ-7.",
            "token κ-7",
            "κ-7 is the token that identifies Élan's current expansion case",
        ),
        (
            "What is Cobalt's complement of ACG?",
            "Cobalt is a symbolic puzzle only: its complement of ACG is TGC, "
            "and it does not describe a biological sample.",
            "TGC",
            "Cobalt's complement of ACG is TGC",
        ),
        (
            "What is Élan's rotation of ABC?",
            "Élan's rotation of ABC is BCA.",
            "BCA",
            "Élan's rotation of ABC is BCA",
        ),
        (
            "In Cedar, which years have an extra day?",
            "For Cedar, leap years have an extra day.",
            "leap years",
            "For Cedar, leap years have an extra day",
        ),
    ],
)
def test_generic_relations_keep_named_subject_field_input_and_source_argument(
    question, context, value, expected
):
    binding = bound(question, context, value)
    before = replace(binding)
    assert relation_hypothesis(binding) == (expected, None)
    assert binding == before


@pytest.mark.parametrize(
    ("question", "context", "value"),
    [
        (
            "How does Cedar represent the zero polynomial?",
            "Birch writes the zero polynomial as one zero.",
            "one zero",
        ),
        (
            "How does Cedar represent the zero polynomial?",
            "Cedar writes the unit polynomial as one zero.",
            "one zero",
        ),
        (
            "How does Cedar represent the zero polynomial?",
            "Cedar rejects the zero polynomial as one zero.",
            "one zero",
        ),
        (
            "How does Cedar represent the zero polynomial?",
            "Cedar never writes the zero polynomial as one zero.",
            "one zero",
        ),
        (
            "How does Cedar represent the zero polynomial?",
            "Cedar writes the zero polynomial as one zero archive.",
            "one zero",
        ),
        (
            "How does Cedar represent the current zero polynomial?",
            "Cedar writes the old zero polynomial as one zero.",
            "one zero",
        ),
        (
            "What code identifies Cedar's expansion packet?",
            "The label of Cedar expansion packet has the code κ-7.",
            "κ-7",
        ),
        (
            "What code identifies Cedar's expansion packet?",
            "Cedar expansion packet archive has the code κ-7.",
            "κ-7",
        ),
        (
            "What code identifies Cedar's expansion packet?",
            "Birch expansion packet has the code κ-7.",
            "κ-7",
        ),
        (
            "What code identifies Cedar's expansion packet?",
            "Cedar expansion packet has the label κ-7.",
            "κ-7",
        ),
        (
            "What code identifies Cedar's current expansion packet?",
            "Cedar former expansion packet has the code κ-7.",
            "κ-7",
        ),
        (
            "What code identifies Cedar's expansion packet?",
            "Cedar expansion packet does not have the code κ-7.",
            "κ-7",
        ),
        (
            "What is Cedar's transform of ABC?",
            "Birch is a puzzle: its transform of ABC is BCA.",
            "BCA",
        ),
        (
            "What is Cedar's transform of ABC?",
            "Cedar is a puzzle: its transform of ABD is BCA.",
            "BCA",
        ),
        (
            "What is Cedar's transform of ABC?",
            "Cedar is a puzzle. Its transform of ABC is BCA.",
            "BCA",
        ),
        (
            "What is Cedar's transform of ABC?",
            "Cedar is a puzzle: its transform of ABC is not BCA.",
            "BCA",
        ),
        (
            "What is Cedar's transform of ABC?",
            "Cedar is a puzzle: its transform of ABC is BCA archive.",
            "BCA",
        ),
        (
            "In Cedar, which years have an extra day?",
            "For Birch, leap years have an extra day.",
            "leap years",
        ),
        (
            "In Cedar, which years have an extra day?",
            "Leap years have an extra day.",
            "Leap years",
        ),
        (
            "In Cedar, which years have an extra day and how many do those have?",
            "For Cedar, leap years have an extra day.",
            "leap years",
        ),
    ],
)
def test_generic_relations_refuse_wrong_or_incomplete_requested_slots(
    question, context, value
):
    hypothesis, reason = relation_hypothesis(bound(question, context, value))
    assert hypothesis is None and reason


def test_atomic_production_mappings_preserve_each_operand_and_shared_scope():
    question = "What Flint codewords correspond to the two payloads 1010 and 1000?"
    context = (
        "For Flint, payload 1010 produces codeword 10100; "
        "payload 1000 produces codeword 10001."
    )
    first, second = plan_requirements(question)
    for req, value, expected in (
        (first, "10100", "For Flint, codeword 10100 corresponds to payload 1010"),
        (
            second,
            "codeword 10001",
            "For Flint, codeword 10001 corresponds to payload 1000",
        ),
    ):
        binding = replace(bound(question, context, value), req=req, topic=req.topic)
        source_range = relation_source_range(req, context, binding.start, binding.end)
        assert source_range is not None and context[slice(*source_range)] == context
        assert relation_hypothesis(binding) == (expected, None)
    wrong = replace(bound(question, context, "10001"), req=first)
    assert relation_hypothesis(wrong)[0] is None
    forged = replace(
        second, question="What Flint codewords correspond to payload 1111?"
    )
    assert (
        relation_hypothesis(replace(bound(question, context, "10001"), req=forged))[0]
        is None
    )


@pytest.mark.parametrize(
    "context",
    [
        "For Cedar, payload 1010 produces token κ-7; payload 1000 produces token λ-8.",
        "For Birch, payload 1010 produces token κ-7; payload 1000 produces token λ-8.",
        "For Cedar, payload 1010 produces codeword κ-7; "
        "payload 1000 produces token λ-8.",
        "For Cedar, payload 1010 produces token κ-7; "
        "the archive of payload 1000 produces token λ-8.",
        "For Cedar, payload 1010 produces token κ-7; "
        "payload 1000 never produces token λ-8.",
        "For Cedar, payload 1010 produces token κ-7; unrelated text; "
        "payload 1000 produces token λ-8.",
        "For Cedar, payload 1010 produces token κ-7. Payload 1000 produces token λ-8.",
    ],
)
def test_production_mapping_cannot_change_operand_type_direction_or_namespace(context):
    question = "What Cedar tokens correspond to the two payloads 1010 and 1000?"
    req = plan_requirements(question)[0]
    binding = replace(bound(question, context, "λ-8"), req=req)
    assert relation_hypothesis(binding)[0] is None


def test_scalar_answer_normalization_only_trims_after_a_fully_bound_argument():
    question = "What is Cobalt's complement of ACG?"
    context = (
        "Cobalt is a symbolic puzzle only: its complement of ACG is TGC, "
        "and it does not describe a biological sample. More text."
    )
    raw = "TGC, and it does not describe a biological sample. More text."
    binding = bound(question, context, raw)
    answer_range = relation_answer_range(
        binding.req, context, binding.start, binding.end
    )
    assert answer_range is not None and context[slice(*answer_range)] == "TGC"
    start, end = answer_range
    prepared = replace(binding, start=start, end=end, value=context[start:end])
    proof = relation_source_range(prepared.req, context, start, end)
    assert proof is not None
    assert context[slice(*proof)] == context[: context.index(" More text.")]
    assert relation_hypothesis(prepared) == ("Cobalt's complement of ACG is TGC", None)
    assert (binding.start, binding.end, binding.value) == (59, len(context), raw)


@pytest.mark.parametrize(
    "raw",
    [
        "GC, and it does not describe a sample.",
        "TG",
        "is TGC, and it does not describe a sample.",
    ],
)
def test_scalar_normalization_does_not_pick_a_partial_or_offset_argument(raw):
    context = (
        "Cedar is a puzzle: its transform of ABC is TGC, "
        "and it does not describe a sample."
    )
    binding = bound("What is Cedar's transform of ABC?", context, raw)
    assert (
        relation_answer_range(binding.req, context, binding.start, binding.end) is None
    )


@pytest.mark.parametrize(
    ("question", "context", "value"),
    [
        (
            "How does Cedar represent the zero polynomial?",
            "Cedar writes the zero polynomial as one zero?",
            "one zero",
        ),
        (
            "What code identifies Cedar's expansion packet?",
            "Cedar expansion packet has the code κ-7?",
            "κ-7",
        ),
        (
            "What is Cedar's transform of ABC?",
            "Cedar is a puzzle: its transform of ABC is BCA?",
            "BCA",
        ),
        (
            "What code identifies Cedar's expansion packet?",
            "The former Cedar expansion packet has the code κ-7.",
            "κ-7",
        ),
    ],
)
def test_literal_relations_do_not_turn_questions_or_former_subjects_into_current_facts(
    question, context, value
):
    assert relation_hypothesis(bound(question, context, value))[0] is None


def test_identifier_field_names_are_literal_and_can_have_multiple_words():
    binding = bound(
        "What access token identifies Cedar's active case?",
        "Cedar active case has the access token κ-7.",
        "κ-7",
    )
    assert relation_hypothesis(binding) == (
        "κ-7 is the access token that identifies Cedar's active case",
        None,
    )


def test_topic_helper_does_not_accept_invisible_controls_in_new_forms():
    assert question_topic("How does Élan\u200b represent the zero vector?") is None
