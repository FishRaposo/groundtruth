"""Wire the opt-in field binder; actual NLI and authority remain required."""

from dataclasses import replace

import pytest
from app.evidence_policy import recorded_evidence_policy
from app.services.linguistic_property_cover import factual_claim
from app.services.requirement_binding import support_claim

from tests.test_ordinary_role_actual975 import actual, positive_source, role


@pytest.mark.parametrize(
    ("kind", "raw"),
    [("owner", "fragment steward"), ("deputy", "buffer clerk")],
)
def test_source_bound_activity_field_is_prepared_without_legacy_scope_loss(kind, raw):
    body = positive_source()["body"]
    requirement = role(kind).prepared("activity")
    policy = recorded_evidence_policy(actual()["evidence_profile"])
    start, end = body.index(raw), body.index(raw) + len(raw)
    claim = factual_claim(requirement, body, start, end, policy=policy)
    assert claim.rejection is None
    assert claim.value == "the " + raw
    assert claim.value == body[claim.start : claim.end]
    assert "ordinary Citrine fragment desk sessions" in claim.hypothesis
    assert claim.proof_edges == ()
    assert factual_claim(
        requirement,
        body,
        start,
        end,
        policy=replace(policy, source_governance_profile="all_sources_v1"),
    ) == support_claim(
        requirement, body, start, end, reading_profile=policy.evidence_reading_profile
    )


def test_rejected_activity_field_does_not_fall_back_to_a_legacy_interpretation():
    body = positive_source()["body"].replace("lead is", "lead may be")
    policy = recorded_evidence_policy(actual()["evidence_profile"])
    start = body.index("fragment steward")
    claim = factual_claim(
        role("owner").prepared("activity"),
        body,
        start,
        start + len("fragment steward"),
        policy=policy,
    )
    assert claim.rejection == "activity_role_field_unbound"
