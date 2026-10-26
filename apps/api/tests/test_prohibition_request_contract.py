"""Lossless prohibition facets across inherited atomic request frames."""

from dataclasses import replace

import pytest
from app.services.answer_requirements import plan_requirements
from app.services.requirement_binding import support_claim

from tests.test_binding_additional_scope import METHOD


def prohibition(question):
    requirements = plan_requirements(question)
    assert all(
        question[r.input_start : r.input_end] == r.original_text for r in requirements
    )
    return next(r for r in requirements if r.kind == "prohibition")


def bind(req, source, raw):
    start = source.index(raw)
    return support_claim(req, source, start, start + len(raw))


@pytest.mark.parametrize("namespace", ["Cobalt", "Aster"])
def test_material_nominal_target_survives_preparation_before_generic_allowances(
    namespace,
):
    text = (
        f"State the number of symbolic cards in a standard {namespace} set "
        "and the prohibition on symbol order."
    )
    req = prohibition(text)
    assert "symbol order" in req.original_text
    assert "symbol order" in req.question
    source = (
        f"For a standard {namespace} set, "
        "do not reverse the symbol order while complementing it."
    )
    result = bind(req, source, "reverse the symbol order")
    assert result.rejection is None
    assert "symbol order while complementing it" in result.hypothesis
    wrong = (
        f"For a standard {namespace} set, "
        "do not copy the pass while the symbol order is displayed."
    )
    assert bind(req, wrong, "copy the pass").rejection is not None


@pytest.mark.parametrize(
    "fragment",
    [
        "what action is prohibited in the method",
        "the explicit method prohibition",
        "the method's explicit prohibition",
        "the method's prohibition",
    ],
)
@pytest.mark.parametrize("shape", ["direct", "coordinated", "include"])
def test_complete_method_nominals_have_paired_direct_and_inherited_frames(
    fragment, shape
):
    scope = "ordinary Alder bracket depth"
    if shape == "direct":
        text = (
            f"For {scope}, state {fragment}."
            if fragment.startswith("the")
            else f"For {scope}, {fragment}?"
        )
    elif shape == "coordinated":
        text = f"What is the {scope} session capacity, and {fragment}."
    else:
        text = f"What is the {scope} session capacity? Include {fragment}."
    req = prohibition(text)
    result = bind(req, METHOD, "skip a closing bracket")
    assert result.rejection is None
    assert result.value == "Do not skip a closing bracket"
    assert "must not skip a closing bracket" in result.hypothesis


@pytest.mark.parametrize(
    "fragment,source_action,raw",
    [
        (
            "what substitution must not be made to combining marks",
            "replace combining marks with spacing characters",
            "spacing characters",
        ),
        (
            "the rule against omitting coefficients",
            "omit zero coefficients between nonzero terms",
            "omit zero coefficients",
        ),
        (
            "which edge manipulation is prohibited",
            "reverse an edge to remove a cycle",
            "reverse an edge",
        ),
        (
            "what must not be assigned to a numbered week",
            "assign an intercalary day to a numbered week",
            "an intercalary day",
        ),
        (
            "what must not be inferred from longitude or latitude",
            "infer an altitude from longitude or latitude",
            "an altitude",
        ),
        (
            "what replacement of null values is forbidden",
            "replace null values with empty strings",
            "empty strings",
        ),
        (
            "what must not count as a payload bit",
            "count the row label as a payload bit",
            "the row label",
        ),
    ],
)
@pytest.mark.parametrize("shape", ["direct", "coordinated"])
def test_relation_specific_request_facets_bind_the_complete_governing_action(
    fragment, source_action, raw, shape
):
    scope = "standard Oriole intake"
    text = (
        f"For {scope}, {fragment}?"
        if shape == "direct"
        else f"How many forms go into {scope}, and {fragment}?"
    )
    req = prohibition(text)
    source = f"For {scope}, do not {source_action}."
    result = bind(req, source, raw)
    assert result.rejection is None
    assert source_action in result.value and source_action in result.hypothesis
    wrong = f"For {scope}, do not copy the pass."
    assert bind(req, wrong, "copy the pass").rejection is not None


@pytest.mark.parametrize(
    "suffix",
    [
        "under the blue profile",
        "after 17:00",
        "except during reserve sessions",
        "using 42 reserved cards",
        "without a signed waiver",
    ],
)
def test_unknown_facets_in_material_and_generic_fragments_never_disappear(suffix):
    for fragment in [
        "the prohibition on symbol order",
        "the method's explicit prohibition",
    ]:
        text = (
            f"How many forms go into standard Oriole intake, and {fragment} {suffix}?"
        )
        req = prohibition(text)
        assert suffix in req.original_text and suffix in req.question
        source = "For standard Oriole intake, do not reverse the symbol order."
        assert bind(req, source, "reverse the symbol order").rejection is not None


def test_a_generic_prepared_question_cannot_erase_a_material_original_target():
    req = prohibition(
        "Give the form count for standard Oriole intake "
        "and the prohibition on symbol order."
    )
    req = replace(req, question=f"What is the prohibition for {req.topic}?")
    assert (
        bind(
            req,
            "For standard Oriole intake, do not reverse the symbol order.",
            "reverse the symbol order",
        ).rejection
        is not None
    )


@pytest.mark.parametrize(
    "modal,allowed", [("Do not", True), ("must not", True), ("should not", False)]
)
def test_advisory_modal_is_never_upgraded_to_a_mandatory_prohibition(modal, allowed):
    req = prohibition("What is the prohibition for standard Oriole intake?")
    source = f"For standard Oriole intake, {modal} copy the pass."
    result = bind(req, source, "copy the pass")
    assert (result.rejection is None) == allowed
    if allowed:
        assert result.hypothesis == "standard Oriole intake must not copy the pass"


def test_inherited_nominal_overspan_preserves_complete_verified_raw_context():
    req = prohibition(
        "What is the ordinary Alder bracket depth capacity? "
        "Include the method's explicit prohibition."
    )
    start = METHOD.index("no amber triangle")
    end = METHOD.index("Do not skip a closing bracket") + len(
        "Do not skip a closing bracket"
    )
    claim = support_claim(req, METHOD, start, end)
    assert claim.rejection is None
    assert claim.value == "Do not skip a closing bracket"
    assert claim.premise_start <= start < end <= claim.premise_end
    assert METHOD[claim.premise_start : claim.premise_end] == claim.premise


@pytest.mark.parametrize(
    "fragment,action",
    [
        ("the prohibition on symbol order", "copy the symbol order audit"),
        ("which edge manipulation is prohibited", "copy an edge ledger"),
        (
            "what replacement of null values is forbidden",
            "replace null values records with tags",
        ),
    ],
)
def test_requested_object_is_not_an_incidental_modifier_of_a_different_head(
    fragment, action
):
    req = prohibition(f"For standard Oriole intake, {fragment}?")
    source = f"For standard Oriole intake, do not {action}."
    assert bind(req, source, action).rejection is not None


@pytest.mark.parametrize("prefix", ["under the blue profile", "before noon"])
def test_unknown_prefix_before_an_inherited_method_fragment_is_not_skipped(prefix):
    text = (
        f"For standard Oriole intake, {prefix} "
        "include the method's explicit prohibition."
    )
    req = prohibition(text)
    assert prefix in req.original_text and prefix in req.question
    assert (
        bind(
            req, "For standard Oriole intake, do not copy the pass.", "copy the pass"
        ).rejection
        is not None
    )


def test_inherited_topic_condition_remains_in_every_permitted_prohibition_hypothesis():
    text = (
        "For standard Oriole intake under the blue profile, "
        "give the form count and the method's prohibition."
    )
    req = prohibition(text)
    assert "under the blue profile" in req.topic
    assert "under the blue profile" in req.question
    claim = bind(
        req, "For standard Oriole intake, do not copy the pass.", "copy the pass"
    )
    if claim.rejection is None:
        assert "under the blue profile" in claim.hypothesis


def test_fully_bound_material_target_qualifier_is_copied_instead_of_generalized():
    req = prohibition(
        "For standard Oriole intake, "
        "give the prohibition on symbol order under the blue profile."
    )
    source = (
        "For standard Oriole intake, "
        "do not reverse the symbol order under the blue profile."
    )
    claim = bind(req, source, "reverse the symbol order")
    assert claim.rejection is None
    assert "symbol order under the blue profile" in claim.value
    assert "symbol order under the blue profile" in claim.hypothesis


@pytest.mark.parametrize(
    "fragment,action",
    [
        ("which edge manipulation is prohibited", "copy an edge to vertex mapping"),
        (
            "what replacement of null values is forbidden",
            "replace the null values to tags mapping with an empty map",
        ),
        (
            "the prohibition on symbol order",
            "copy the symbol order to color lookup table",
        ),
        (
            "the rule against reversing an edge",
            "reverse an edge to segment identifier conversion table",
        ),
        (
            "what must not be assigned to a numbered week",
            "assign the task to a numbered week to slot mapping",
        ),
        (
            "what must not be inferred from longitude or latitude",
            "infer the setting from longitude or latitude to zone lookup table",
        ),
        (
            "what must not count as a payload bit",
            "count the row label as a payload bit to flag mapping",
        ),
        (
            "what replacement of null values is forbidden",
            "replace null values while copying the lookup table with empty strings",
        ),
        (
            "which edge manipulation is prohibited",
            "copy an edge between vertex mapping",
        ),
        (
            "the prohibition on symbol order",
            "copy the symbol order while reading table",
        ),
    ],
)
def test_ambiguous_argument_continuation_cannot_hide_a_different_noun_head(
    fragment, action
):
    req = prohibition(f"For standard Kestrel intake, {fragment}?")
    source = f"For standard Kestrel intake, do not {action}."
    assert bind(req, source, action).rejection is not None


@pytest.mark.parametrize(
    "fragment,action",
    [
        (
            "which edge to vertex mapping manipulation is prohibited",
            "copy an edge to vertex mapping",
        ),
        (
            "what replacement of null values to tags mapping is forbidden",
            "replace the null values to tags mapping with an empty map",
        ),
        (
            "the prohibition on symbol order to color lookup table",
            "copy the symbol order to color lookup table",
        ),
        (
            "the rule against reversing an edge to segment identifier conversion table",
            "reverse an edge to segment identifier conversion table",
        ),
    ],
)
def test_complete_requested_compound_argument_remains_bound_as_a_whole(
    fragment, action
):
    req = prohibition(f"For standard Kestrel intake, {fragment}?")
    source = f"For standard Kestrel intake, do not {action}."
    claim = bind(req, source, action)
    assert claim.rejection is None
    assert action in claim.value and action in claim.hypothesis


@pytest.mark.parametrize(
    "fragment,action",
    [
        ("which edge manipulation is prohibited", "reverse an edge to remove a cycle"),
        (
            "which edge manipulation is prohibited",
            "reverse an edge to avoid a crossing",
        ),
        (
            "the prohibition on symbol order",
            "reverse the symbol order while complementing it",
        ),
        (
            "the rule against omitting coefficients",
            "omit zero coefficients between nonzero terms",
        ),
    ],
)
def test_proved_action_adjuncts_keep_the_direct_object_and_all_parameters(
    fragment, action
):
    req = prohibition(f"For standard Kestrel intake, {fragment}?")
    source = f"For standard Kestrel intake, do not {action}."
    claim = bind(req, source, action)
    assert claim.rejection is None
    assert action in claim.hypothesis
    assert claim.premise == source.rstrip(".")
