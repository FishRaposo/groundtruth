import pytest
from app.services.answer_requirements import plan_requirements
from app.services.requirement_answers import witness_value_identity
from app.services.requirement_binding import support_claim


@pytest.mark.parametrize(
    "scope",
    [
        "for Zinc mapping",
        "of Zinc mapping",
        "in Zinc mapping",
        "for the evening session",
        "of the evening session",
        "in the evening session",
        "during the evening session",
    ],
)
def test_fronted_context_cannot_erase_a_second_explicit_role_scope(scope):
    req = plan_requirements(
        f"For Copper engraving, identify the lead {scope}.",
        reading_profile="contextual_source_v1",
    )[0]
    source = "The Copper engraving lead is the map steward."
    start = source.index("map steward")
    claim = support_claim(
        req, source, start, start + 11, reading_profile="contextual_source_v1"
    )
    assert (
        claim.rejection
        or ("Zinc" if "Zinc" in scope else "evening") in claim.hypothesis
    )
    assert scope in req.original_text


@pytest.mark.parametrize(
    "question",
    [
        "Who is the lead of Zinc mapping?",
        "Who is the lead in Zinc mapping?",
        "Who is responsible for Zinc mapping?",
        "Who manages Zinc mapping?",
    ],
)
def test_standalone_role_frames_retain_their_exact_explicit_subject(question):
    req = plan_requirements(question, reading_profile="contextual_source_v1")[0]
    assert "Zinc mapping" in req.topic
    assert "Zinc mapping" in req.question


@pytest.mark.parametrize("unit,other", [("MW", "mW"), ("mL", "ML"), ("N/m", "N m")])
def test_unit_symbols_are_case_and_punctuation_sensitive(unit, other):
    req = plan_requirements(f"How many {unit} are in the Copper pack?")[0]
    assert witness_value_identity(
        req, f"3 {unit}", reading_profile="contextual_source_v1"
    ) != witness_value_identity(
        req, f"3 {other}", reading_profile="contextual_source_v1"
    )


def test_shared_ordinary_session_scope_applies_to_both_bare_roles():
    question = (
        "List the full Copper engraving routine in order and identify the lead "
        "and deputy for an ordinary session."
    )
    roles = plan_requirements(question, reading_profile="contextual_source_v1")[1:]
    assert [r.topic for r in roles] == [
        "ordinary Copper engraving session",
        "ordinary Copper engraving session",
    ]


def test_explicit_activity_role_is_not_reinterpreted_as_a_session_role():
    question = (
        "For Copper engraving, name the activity lead and the deputy "
        "for an ordinary session."
    )
    roles = plan_requirements(question, reading_profile="contextual_source_v1")
    assert roles[0].topic == "Copper engraving"
    assert "activity lead" in roles[0].original_text
