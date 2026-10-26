"""The activity interpretation never rewrites the original request or conditions."""

from dataclasses import replace

import pytest
from app.evidence_policy import EvidencePolicy
from app.services.answer_requirements import plan_requirements
from app.services.role_scope_policy import plan_activity_role

POLICY = EvidencePolicy("qa_only_v1", "ordinary_session_activity_v1")


def test_activity_preparation_keeps_original_requirement_and_exact_requested_scopes():
    text = "For an ordinary Meridian review session, identify the lead and the deputy."
    requirements = plan_requirements(text)
    assert len(requirements) == 2
    for requirement, question in zip(
        requirements,
        ["Who leads Meridian review?", "Who is the deputy for Meridian review?"],
        strict=True,
    ):
        interpretation = plan_activity_role(requirement, POLICY)
        assert interpretation is not None
        prepared = interpretation.prepared("activity")
        assert prepared.question == question
        assert prepared.topic == "Meridian review"
        assert prepared.original_text == requirement.original_text
        assert (
            text[prepared.input_start : prepared.input_end] == requirement.original_text
        )
        assert prepared.id == requirement.id
        record = interpretation.record("activity")
        assert record["requested_scope"] == "ordinary Meridian review session"
        assert record["activity_scope"] == "Meridian review"
        assert record["activity_fallback"] is True
        assert "rather than a separate session assignment" in record["disclosure"]
        direct = interpretation.record("session")
        assert direct["activity_fallback"] is False and direct["disclosure"] is None


@pytest.mark.parametrize(
    "topic",
    [
        "emergency Meridian review session",
        "Meridian review session after 18:00",
        "Meridian review session under emergency rules",
        "a particular Meridian review session",
        "Meridian review",
        "Meridian review session without its usual lead",
    ],
)
def test_qualified_request_is_not_silently_reduced_to_ordinary_activity(topic):
    original = plan_requirements("Who leads Meridian review session?")[0]
    requirement = replace(original, topic=topic, original_text=f"Who leads {topic}?")
    assert plan_activity_role(requirement, POLICY) is None


def test_material_condition_outside_topic_and_dependent_person_role_do_not_fall_back():
    requirement = plan_requirements("Who leads Meridian review session?")[0]
    conditional = replace(
        requirement, original_text="After 18:00, who leads Meridian review session?"
    )
    assert plan_activity_role(conditional, POLICY) is None
    assert plan_activity_role(replace(requirement, depends_on=("r0",)), POLICY) is None
    assert (
        plan_activity_role(requirement, EvidencePolicy("qa_only_v1", "literal_v1"))
        is None
    )


@pytest.mark.parametrize(
    "relation", ["owns", "owner", "responsible", "may_lead", "can_lead"]
)
def test_ownership_responsibility_and_permission_do_not_become_activity_leadership(
    relation,
):
    requirement = plan_requirements("Who leads Meridian review session?")[0]
    assert plan_activity_role(replace(requirement, relation=relation), POLICY) is None
