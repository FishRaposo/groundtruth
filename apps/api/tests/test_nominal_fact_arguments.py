"""Complete declared nominal facts remain eligible for separate NLI checks."""

import pytest
from app.services.answer_requirements import plan_requirements
from app.services.requirement_binding import support_claim

from tests.test_role_scope_classification import classify


@pytest.mark.parametrize(
    "question",
    [
        "For one ordinary Willow token session, give the allocation "
        "in its stated units.",
        "For one ordinary Willow token session, what quantity in the stated units "
        "is allocated to it?",
    ],
)
def test_allocation_reader_question_is_human_and_preserves_relation(question):
    req = plan_requirements(question)[0]
    assert req.kind == "quantity" and req.relation == "allocation"
    assert (
        req.question == f"What is the allocation for {req.topic} in its stated units?"
    )
    assert req.original_text == question


@pytest.mark.parametrize(
    "title",
    [
        "the carton packager",
        "the docket assessor",
        "the circuit evaluator",
        "the chair inventory recorder",
    ],
)
def test_complete_terminal_nominal_compounds_are_role_designators(title):
    # Unknown productive agent nouns and an internal role word are nominal here.
    result = classify(f"For Meridian review sessions, the lead is {title}.")
    assert result["complete"] is True, result


@pytest.mark.parametrize(
    "owner,deputy",
    [
        ("the carton packager", "the docket assessor"),
        ("the records coordinator", "the chair inventory recorder"),
    ],
)
def test_novel_nominal_roles_reach_unique_operation_proof(owner, deputy):
    source = (
        f"The owner of the Willow token ordinary operation is {owner}. "
        f"The deputy for that operation is {deputy}."
    )
    req = plan_requirements(
        "Who is the deputy for the Willow token ordinary operation?"
    )[0]
    start = source.index(deputy)
    claim = support_claim(req, source, start, start + len(deputy))
    assert claim.rejection is None, claim
    assert claim.value == deputy
    assert {c.name for c in claim.checks} == {
        "operation_owner_antecedent",
        "operation_deputy_assignment",
    }
    assert len(claim.proof_edges) == 1
    assert claim.proof_edges[0].name == "operation_antecedent_to_deputy"
    assert claim.proof_edges[0].requirement_id == req.id


@pytest.mark.parametrize("amount", ["29 training folders", "44 empty training cards"])
def test_gerund_before_terminal_unit_head_is_preserved_literally(amount):
    source = f"The allocation for one ordinary Willow token session is {amount}."
    req = plan_requirements(
        "For one ordinary Willow token session, give the allocation "
        "in its stated units."
    )[0]
    start = source.index(amount)
    claim = support_claim(req, source, start, start + len(amount.split()[0]))
    assert claim.rejection is None, claim
    assert claim.value == amount and claim.hypothesis.endswith(amount)


@pytest.mark.parametrize(
    "tail",
    [
        "following a separate appointment",
        "once separately appointed",
        "subject to approval by the shift clerk",
    ],
)
def test_productive_title_does_not_absorb_governing_tail(tail):
    result = classify(
        f"For Meridian review sessions, the lead is the carton packager {tail}."
    )
    assert result["complete"] is False, result


@pytest.mark.parametrize("tail", ["pending approval", "after inspection"])
def test_gerund_unit_modifier_does_not_license_post_head_conditions(tail):
    source = (
        "The allocation for one ordinary Willow token session is "
        f"29 training folders {tail}."
    )
    req = plan_requirements(
        "For one ordinary Willow token session, give the allocation "
        "in its stated units."
    )[0]
    start = source.index("29")
    assert support_claim(req, source, start, start + 2).rejection is not None


@pytest.mark.parametrize(
    "title",
    [
        "the spring gauge evaluator",
        "the string issue assessor",
        "the wing pattern coordinator",
    ],
)
def test_lexical_noun_ending_is_not_a_participial_suffix(title):
    result = classify(f"For Meridian review sessions, the lead is {title}.")
    assert result["complete"] is True, result


@pytest.mark.parametrize(
    "title", ["the training coordinator", "the acting administrator"]
)
def test_nominal_attributive_modifier_precedes_terminal_role_head(title):
    result = classify(f"For Meridian review sessions, the lead is {title}.")
    assert result["complete"] is True, result


@pytest.mark.parametrize(
    "tail", ["assuming replacement coordinator", "acting administrator"]
)
def test_participle_after_existing_role_head_stays_unresolved(tail):
    result = classify(
        f"For Meridian review sessions, the lead is the duty supervisor {tail}."
    )
    assert result["complete"] is False, result
