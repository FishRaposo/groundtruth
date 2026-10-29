"""Source values are UNITONLY; request graph is a retained actual CPU capture."""

from copy import deepcopy

import pytest
from app.services import requirement_answers
from app.services.requirement_binding import support_claim

from tests.test_dependency_frames import planned


def test_dependent_availability_preserves_attribute_and_source_reference():
    plan = planned("e628-explicit-data-reference")
    before = deepcopy(plan.record())
    requirement = plan.requirements[1]
    resolved, binding = requirement_answers.resolve_linguistic_requirement(
        requirement, plan, {"r1": "The records steward"}
    )
    assert resolved.question == "What is The records steward's availability?"
    assert resolved.kind == "availability" and resolved.relation == "availability"
    assert "availability" in resolved.attribute
    assert "present" not in resolved.question
    assert resolved.depends_on == ("r1",)
    assert binding["bindings"][0]["source_requirement_id"] == "r1"
    assert binding["bindings"][0]["source_value"] == "The records steward"
    assert binding["bindings"][0]["reference"]["text"] == "that role's"
    assert plan.record() == before


def test_missing_preceding_evidence_cannot_resolve_a_reference():
    plan = planned("e628-explicit-data-reference")
    with pytest.raises(ValueError, match="missing_dependency"):
        requirement_answers.resolve_linguistic_requirement(
            plan.requirements[1], plan, {}
        )


def test_independent_requirement_keeps_its_exact_prepared_question():
    plan = planned("e628-explicit-data-reference")
    resolved, binding = requirement_answers.resolve_linguistic_requirement(
        plan.requirements[0], plan, {}
    )
    assert resolved is plan.requirements[0] and binding == {}


@pytest.mark.parametrize("actor", ["Zinc review", "The visiting deputy"])
def test_dependent_availability_cannot_bind_a_different_subject(actor):
    plan = planned("e628-explicit-data-reference")
    req, _ = requirement_answers.resolve_linguistic_requirement(
        plan.requirements[1], plan, {"r1": "The records steward"}
    )
    text = f"{actor} is available from 09:00 to 12:00."
    start = text.index("09:00")
    claim = support_claim(
        req, text, start, len(text) - 1, reading_profile="contextual_source_v2"
    )
    assert claim.rejection is not None


def test_availability_is_not_rewritten_as_presence_or_a_partial_window():
    plan = planned("e628-explicit-data-reference")
    req, _ = requirement_answers.resolve_linguistic_requirement(
        plan.requirements[1], plan, {"r1": "The records steward"}
    )
    text = "The records steward is available from 09:00 to 12:00."
    start = text.index("09:00")
    claim = support_claim(
        req, text, start, start + 5, reading_profile="contextual_source_v2"
    )
    assert claim.rejection is None
    assert claim.value == "from 09:00 to 12:00"
    assert "records steward is available" in claim.hypothesis
    assert "present" not in claim.hypothesis


@pytest.mark.parametrize("suffix", ["and from 13:00 to 17:00", "and on Wednesday"])
def test_every_coordinated_availability_window_survives(suffix):
    plan = planned("e628-explicit-data-reference")
    req, _ = requirement_answers.resolve_linguistic_requirement(
        plan.requirements[1], plan, {"r1": "The records steward"}
    )
    text = f"The records steward is available from 09:00 to 12:00 {suffix}."
    start = text.index("09:00")
    claim = support_claim(
        req, text, start, start + 5, reading_profile="contextual_source_v2"
    )
    assert claim.rejection is None and suffix in claim.value


@pytest.mark.parametrize(
    "scope,accepted", [("Zinc review", True), ("Copper review", False)]
)
def test_role_property_retains_its_requested_activity_namespace(scope, accepted):
    plan = planned("e628-explicit-data-reference")
    req, binding = requirement_answers.resolve_linguistic_requirement(
        plan.requirements[1], plan, {"r1": "The records steward"}
    )
    assert req.dependency_scope == binding["original_topic"] == "Zinc review"
    text = f"The records steward is available from 09:00 to 12:00 for {scope}."
    start = text.index("09:00")
    claim = support_claim(
        req, text, start, start + 5, reading_profile="contextual_source_v2"
    )
    assert (claim.rejection is None) is accepted
