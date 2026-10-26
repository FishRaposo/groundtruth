"""A scheduled start clock uses the same literal relation as its weekday."""

import pytest
from app.services.answer_requirements import plan_requirements
from app.services.requirement_binding import support_claim


@pytest.mark.parametrize("prefix", ["is scheduled for", "starts at"])
def test_scheduled_clock_is_bound_to_the_requested_operation(prefix):
    context = f"The standard Meridian review {prefix} 15:40 on Tuesdays."
    req = plan_requirements("What time does standard Meridian review start?")[0]
    start = context.index("15:40")
    claim = support_claim(req, context, start, start + 5)
    assert claim.rejection is None
    assert claim.value == "15:40"
    assert "standard Meridian review" in claim.hypothesis
    assert "15:40" in claim.hypothesis
    assert claim.premise in context


@pytest.mark.parametrize(
    "context",
    [
        "The standard Meridian review closes at 15:40 on Tuesdays.",
        "The standard Meridian review lasts 15:40 minutes.",
        "The standard Meridian review follows a different meeting scheduled for 15:40.",
        "The standard Meridian review is not scheduled for 15:40 on Tuesdays.",
    ],
)
def test_different_or_negated_clock_relation_is_not_a_start(context):
    req = plan_requirements("What time does standard Meridian review start?")[0]
    start = context.index("15:40")
    assert support_claim(req, context, start, start + 5).rejection is not None
