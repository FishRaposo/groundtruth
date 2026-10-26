"""Unknown request/source tails cannot be certified by a favorable prefix."""

import pytest
from app.services.answer_requirements import plan_requirements
from app.services.requirement_binding import support_claim


def bind_all(question, source, value):
    start = source.index(value)
    return [
        support_claim(req, source, start, start + len(value))
        for req in plan_requirements(question)
    ]


@pytest.mark.parametrize(
    "question",
    [
        "When does the Willow token session start and its badge color?",
        "What time does the Willow token session start, and its volume?",
        "For the Willow token session, report its start time after inspection.",
        "For the Willow token session, give its duration following review.",
    ],
)
def test_unconsumed_temporal_requests_cannot_use_unconditional_fact(question):
    """A matching clock/duration is insufficient for the complete request."""
    source = "The Willow token session starts at 08:30 and lasts 12 minutes."
    claims = bind_all(question, source, "08:30" if "duration" not in question else "12")
    assert any(claim.rejection is not None for claim in claims)


@pytest.mark.parametrize(
    "tail",
    [
        ", who also owns the Birch token ordinary operation",
        " overseeing the Birch token ordinary operation",
        ", subject to a separate assignment",
    ],
)
def test_operation_antecedent_requires_complete_role_fact(tail):
    """A relative predicate/condition cannot be absorbed into an owner title."""
    source = (
        "The owner of the Willow token ordinary operation is the record steward"
        + tail
        + ". The deputy for that operation is the shift clerk."
    )
    claims = bind_all(
        "Who is the deputy for the Willow token ordinary operation?",
        source,
        "shift clerk",
    )
    assert all(claim.rejection is not None for claim in claims)


@pytest.mark.parametrize(
    "tail", ["pending approval", "awaiting confirmation", "optional extras"]
)
def test_allocation_requires_closed_nominal_unit(tail):
    """Trailing source applicability/prose cannot become answer units."""
    source = (
        "The allocation for one ordinary Willow token session is "
        f"38 archive tabs {tail}."
    )
    claims = bind_all(
        "For one ordinary Willow token session, give the allocation "
        "in its stated units.",
        source,
        "38",
    )
    assert all(claim.rejection is not None for claim in claims)
