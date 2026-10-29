"""Same R622 questions with actual cached CPU graphs; no source/model truth."""

from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest
from app.services.linguistic_requirements import plan_request, validate_request_plan


def actual_capture(raw):
    import json
    from pathlib import Path

    rows = json.loads(
        (Path(__file__).parent / "fixtures/dependency_graphs_v634.json").read_text()
    )["captures"]
    return next(
        r["capture"] for r in rows if r["capture"]["annotation"]["raw_text"] == raw
    )


def planned(q):
    return plan_request(q, actual_capture(q))


def kinds(p):
    return [r.kind for r in p.requirements]


def test_nominal_fields_are_three_consumed_obligations():
    p = planned("For Onyx calibration, give the quantity, duration and location.")
    assert kinds(p) == ["quantity", "duration", "location"]
    assert p.resolved_request
    assert [r.topic for r in p.requirements] == ["Onyx calibration"] * 3
    assert {x.evidence.text for x in p.consumption} >= {
        "quantity",
        "duration",
        "location",
    }


def test_unknown_extra_attribute_blocks_whole_request():
    p = planned("For Onyx calibration, give quantity and rotation angle.")
    assert kinds(p) == ["quantity", "generic"]
    assert not p.resolved_request
    assert "rotation angle" in p.requirements[1].original_text


def test_passive_catalogue_and_routine_remain_separate_and_unknown_catalogue_blocks():
    p = planned("The roles and full routine needed together for Onyx calibration.")
    assert kinds(p) == ["generic", "procedure"]
    assert not p.resolved_request
    assert any(u.reason == "role_catalogue_not_defined" for u in p.unresolved)


def test_passive_field_request_retains_literal_subject():
    p = planned("The quantity, duration and location for Onyx calibration are needed.")
    assert kinds(p) == ["quantity", "duration", "location"]
    assert p.resolved_request


def test_full_procedure_extent_consumes_required_governors():
    p = planned(
        "For Onyx calibration, give the full routine including all conditions "
        "and prohibitions."
    )
    assert kinds(p) == ["procedure"]
    assert p.resolved_request
    assert any("conditions" in x.text for x in p.uses[0].governors)
    assert any("prohibitions" in x.text for x in p.uses[0].governors)
    assert p.uses[0].extent == "whole_requested"
    assert "full routine" in p.requirements[0].attribute


def test_unbounded_routine_is_not_silently_called_complete():
    p = planned("Give the routine for Onyx calibration.")
    assert not p.resolved_request
    assert any(u.reason == "procedure_extent_not_declared" for u in p.unresolved)


def test_session_and_activity_role_targets_are_literal_and_distinct():
    a = planned("Who leads Onyx calibration?")
    b = planned(
        "For the ordinary Onyx calibration session, identify the lead and deputy."
    )
    assert kinds(a) == ["owner"] and kinds(b) == ["owner", "deputy"]
    assert a.resolved_request and b.resolved_request
    assert a.requirements[0].topic == "Onyx calibration"
    assert b.requirements[0].topic == "ordinary Onyx calibration session"
    assert b.uses[0].scopes[0].text == "the ordinary Onyx calibration session"
    assert b.uses[0].scope_kind == "session"


def test_independent_wh_conjuncts_keep_distinct_scopes():
    p = planned(
        "Who leads Onyx calibration and who is the deputy for Quartz inspection?"
    )
    assert kinds(p) == ["owner", "deputy"]
    assert [r.topic for r in p.requirements] == [
        "Onyx calibration",
        "Quartz inspection",
    ]
    assert p.resolved_request


def test_conditional_role_grammar_retains_condition_without_asserting_truth():
    q = "For Onyx calibration, identify the lead unless the deputy is absent."
    p = planned(q)
    assert kinds(p) == ["owner"] and p.resolved_request
    assert [x.text for x in p.uses[0].conditions] == ["unless the deputy is absent"]
    assert p.uses[0].condition_ast
    assert p.record()["support_or_permissions"] == "NOT_ASSESSED"


@pytest.mark.parametrize("modal", ["May", "Must", "Should", "Can"])
def test_modal_action_and_number_unit_remain_unresolved_original_request(modal):
    q = f"{modal} Onyx calibration run for 1.50 mW?"
    p = planned(q)
    assert kinds(p) == ["generic"] and not p.resolved_request
    assert [x.text for x in p.uses[0].modality] == [modal]
    assert [x.text for x in p.uses[0].units] == ["1.50 mW"]
    assert p.requirements[0].question == q.rstrip("?") + "?"


def test_count_unit_is_retained_and_unit_conversion_is_not_guessed():
    p = planned("How many turns for Onyx calibration?")
    assert kinds(p) == ["quantity"] and p.resolved_request
    assert [x.text for x in p.uses[0].units] == ["turns"]
    q = planned("Give duration in seconds for Onyx calibration.")
    assert kinds(q) == ["duration"] and q.resolved_request
    assert [x.text for x in q.uses[0].units] == ["seconds"]
    converted = planned(
        "Convert the duration for Onyx calibration from minutes to seconds."
    )
    assert kinds(converted) == ["generic"] and not converted.resolved_request


def test_explicit_role_data_dependency_and_request_order_are_distinct():
    p = planned(
        "Identify the lead for Onyx calibration, then give that role's availability."
    )
    assert kinds(p) == ["owner", "availability"] and p.resolved_request
    assert p.requirements[1].depends_on == ("r1",)
    assert p.uses[1].order_after == ("r1",)
    assert [x.text for x in p.uses[1].references] == ["that role's"]
    assert [x.text for x in p.uses[1].order_evidence] == ["then"]


@pytest.mark.parametrize("ref", ["its", "their"])
def test_ambiguous_reference_cannot_be_assigned_to_preceding_lead(ref):
    p = planned(f"Who leads Onyx calibration? Give {ref} full routine.")
    assert kinds(p) == ["owner", "generic"] and not p.resolved_request
    assert p.requirements[1].depends_on == ()


def test_named_complete_process_and_scope_conflict_are_not_flattened():
    p = planned("Give the complete Onyx calibration routine.")
    assert kinds(p) == ["procedure"] and p.resolved_request
    assert p.requirements[0].topic == "Onyx calibration"
    bad = planned("For Onyx calibration, identify the lead for Quartz inspection.")
    assert kinds(bad) == ["generic"] and not bad.resolved_request


def test_requested_workspace_is_scope_metadata_not_authority():
    p = planned("Give quantity for Onyx calibration in workspace ops-b.")
    assert kinds(p) == ["quantity"] and p.resolved_request
    assert p.requirements[0].topic == "Onyx calibration"
    assert p.requirements[0].source_workspace == "ops-b"


def test_nested_role_attribute_and_why_cannot_turn_into_easy_role_or_fact():
    for q in [
        "What is the deputy's location for Onyx calibration?",
        "Why is Onyx calibration safe?",
    ]:
        p = planned(q)
        assert kinds(p) == ["generic"] and not p.resolved_request


def test_plan_is_deeply_immutable_and_record_replay_binds_full_capture():
    q = "For Straße İ ﬃ 😀 calibration, give duration and location."
    capture = actual_capture(q)
    p = plan_request(q, capture)
    assert kinds(p) == ["duration", "location"] and p.resolved_request
    assert p.graph_sha256 and p.capture_sha256 and p.model_identity_json
    assert "".join(x.evidence.text for x in p.consumption) == "".join(
        t["text"] for t in capture["annotation"]["tokens"]
    )
    with pytest.raises(FrozenInstanceError):
        p.requirements[0].kind = "generic"
    record = p.record()
    assert validate_request_plan(record, question=q, capture=capture)
    record["requirements"][0]["topic"] = "forged"
    assert not validate_request_plan(record, question=q, capture=capture)
    assert p.requirements[0].topic == "Straße İ ﬃ 😀 calibration"
    assert not validate_request_plan(p.record(), question=q + " why?", capture=capture)
    bad = deepcopy(capture)
    bad["annotation"]["tokens"][0]["start"] = False
    assert not validate_request_plan(p.record(), question=q, capture=bad)


def test_source_and_old_runtime_are_not_part_of_the_public_planner_interface():
    # Pure request grammar cannot accept source bodies, labels or producer flags.
    with pytest.raises(TypeError):
        plan_request(
            "Give duration for Onyx.",
            actual_capture("Give duration for Onyx."),
            source_body="yes",
        )


def test_fronted_conditional_grammar_retains_negation_and_scope_without_truth():
    q = "For an Onyx session with no separate assignment, identify the lead."
    p = planned(q)
    assert kinds(p) == ["owner"] and p.resolved_request
    assert p.uses[0].condition_ast
    assert [x.text for x in p.uses[0].modality] == ["no"]
    q = "For Onyx unless the deputy is absent, identify the lead."
    p = planned(q)
    assert kinds(p) == ["owner"] and p.resolved_request
    assert [x.text for x in p.uses[0].conditions] == ["unless the deputy is absent"]
    assert p.uses[0].condition_ast
    assert p.record()["support_or_permissions"] == "NOT_ASSESSED"


def test_known_process_modifiers_do_not_become_a_new_namespace():
    p = planned("For Onyx calibration, give the complete governed procedure.")
    assert kinds(p) == ["procedure"] and p.resolved_request
    assert p.requirements[0].topic == "Onyx calibration"
    assert "governed" in p.requirements[0].question


@pytest.mark.parametrize("verb", ["leads", "owns", "manages", "runs"])
def test_wh_role_relation_is_not_rewritten_into_another_role(verb):
    q = f"Who {verb} Onyx calibration?"
    p = planned(q)
    assert kinds(p) == ["owner"] and p.resolved_request
    assert p.requirements[0].relation == verb
    assert p.requirements[0].question == q


def test_extra_entity_attribute_and_case_or_workspace_conflicts_block():
    for q in [
        "Give quantity of the red widget for Onyx calibration.",
        "For MW inspection, identify the lead for mW inspection.",
        "For Onyx in workspace ops-a, give quantity for Onyx in workspace ops-b.",
    ]:
        p = planned(q)
        assert kinds(p) == ["generic"] and not p.resolved_request


def test_shared_prefix_applies_to_coordinated_directives_but_not_a_new_sentence():
    p = planned(
        "For Onyx calibration, identify the lead and deputy and provide "
        "the full routine."
    )
    assert kinds(p) == ["owner", "deputy", "procedure"] and p.resolved_request
    assert [r.topic for r in p.requirements] == ["Onyx calibration"] * 3
    separate = planned("Who leads Onyx calibration? Provide the full routine.")
    assert not separate.resolved_request


def test_request_order_between_nominal_fields_is_not_a_data_dependency():
    p = planned("For Onyx calibration, give quantity, then duration and location.")
    assert kinds(p) == ["quantity", "duration", "location"] and p.resolved_request
    assert p.requirements[1].depends_on == ()
    assert p.uses[1].order_after == ("r1",)
    assert [r.text for r in p.uses[1].order_evidence] == ["then"]


def test_all_requirements_are_preserved_when_count_budget_blocks_execution():
    p = planned("For Onyx calibration, give " + ", ".join(["quantity"] * 9) + ".")
    assert len(p.requirements) == 9 and not p.resolved_request
    assert any(u.reason == "requirement_budget_exceeded" for u in p.unresolved)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r["requirements"].pop(),
        lambda r: r["requirements"][0].update(input_start=True),
        lambda r: r["requirements"][0].update(depends_on=["r999"]),
        lambda r: r["uses"][0]["scopes"][0].update(text="a different entity"),
        lambda r: r["uses"][0].update(units=[]),
        lambda r: r["consumption"][0].update(role="unknown producer claim"),
        lambda r: r.update(graph_sha256="0" * 64),
        lambda r: r.update(capture_sha256="0" * 64),
        lambda r: r.update(model_identity_json="{}"),
        lambda r: r.update(question_sha256="0" * 64),
        lambda r: r.update(unrecognized_override=True),
    ],
)
def test_replay_reconstructs_consumption_and_identity_instead_of_flags(mutation):
    q = "How many turns for Onyx calibration?"
    capture = actual_capture(q)
    p = plan_request(q, capture)
    record = p.record()
    mutation(record)
    assert not validate_request_plan(record, question=q, capture=capture)


def test_deleting_unknown_sibling_or_unresolved_records_does_not_certify_request():
    q = "For Onyx calibration, give quantity and rotation angle."
    capture = actual_capture(q)
    p = plan_request(q, capture)
    record = p.record()
    record["requirements"].pop()
    record["uses"].pop()
    record["unresolved"] = []
    record["resolved_request"] = True
    assert not validate_request_plan(record, question=q, capture=capture)
    assert not p.resolved_request


def test_no_argument_surface_still_has_an_explicit_unresolved_request():
    p = planned("??")
    assert kinds(p) == ["generic"] and not p.resolved_request
    assert any(u.reason == "no_request_argument" for u in p.unresolved)
