"""Shared factual productions retain their explicit dependency-reading scope."""

from dataclasses import asdict

from app.evidence_policy import EvidencePolicy
from app.services.answer_requirements import Requirement
from app.services.requirement_binding import support_claim
from app.services.role_scope_policy import plan_activity_role
from app.services.source_pattern_grammar import ENVELOPE_PATTERN, pattern_ids


def policy(name):
    return EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        name,
    )


def test_staged_discovery_retains_existing_dependency_pattern_registry():
    assert ENVELOPE_PATTERN in pattern_ids("contextual_source_v3")
    assert pattern_ids("contextual_source_v3") == pattern_ids("contextual_source_v2")


def test_activity_scope_uses_the_same_documented_role_interpretation():
    question = "Who leads an ordinary Cedar inspection session?"
    requirement = Requirement(
        "r1",
        question,
        0,
        len(question),
        question,
        "owner",
        "ordinary Cedar inspection session",
        ("cedar",),
        relation="lead",
    )
    old = plan_activity_role(requirement, policy("contextual_source_v2"))
    assert old is not None
    actual = plan_activity_role(requirement, policy("contextual_source_v3"))
    assert actual is not None
    assert asdict(actual) == asdict(old)


def test_dependency_factual_binding_does_not_fall_back_to_contextual_v1():
    question = "How many counters are used for Cedar inspection?"
    requirement = Requirement(
        "r1",
        question,
        0,
        len(question),
        question,
        "quantity",
        "Cedar inspection",
        ("cedar",),
        relation="use",
        attribute="counters",
    )
    body = "Cedar inspection uses 12 counters."
    first = body.index("12")
    old = support_claim(
        requirement, body, first, first + 2, reading_profile="contextual_source_v2"
    )
    actual = support_claim(
        requirement, body, first, first + 2, reading_profile="contextual_source_v3"
    )
    assert asdict(actual) == asdict(old)
