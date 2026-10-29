"""Generic source11 relation and Step-label regressions; no model assertions."""

from dataclasses import replace

import pytest
from app.services.answer_requirements import Requirement
from app.services.requirement_binding import condition_relation, support_claim


def requirement(kind, topic, *, relation="", attribute="", question=None):
    question = question or f"Give the {kind} for {topic}."
    return Requirement(
        "r1",
        question,
        0,
        len(question),
        question,
        kind,
        topic,
        ("alder",),
        relation=relation,
        attribute=attribute,
    )


def bind(req, source, selected):
    start = source.index(selected)
    return support_claim(req, source, start, start + len(selected))


def test_explicit_lead_field_binds_scoped_role_without_becoming_owner():
    req = requirement(
        "owner", "Alder bracket depth", relation="leads", attribute="lead"
    )
    source = "For Alder bracket depth, the lead is the Tracekeeper."
    result = bind(req, source, "Tracekeeper")
    assert result.rejection is None
    assert result.hypothesis == "The lead for Alder bracket depth is Tracekeeper"
    assert source[result.start : result.end] == result.value


@pytest.mark.parametrize("field", ["owner", "deputy", "attendant"])
def test_explicit_lead_cannot_take_another_role_field(field):
    req = requirement(
        "owner", "Alder bracket depth", relation="leads", attribute="lead"
    )
    result = bind(
        req, f"For Alder bracket depth, the {field} is the Tracekeeper.", "Tracekeeper"
    )
    assert result.rejection is not None


def test_explicit_lead_does_not_take_role_for_another_activity():
    req = requirement(
        "owner", "Alder bracket depth", relation="leads", attribute="lead"
    )
    result = bind(
        req, "For Alder budget review, the lead is the Tracekeeper.", "Tracekeeper"
    )
    assert result.rejection is not None


def test_subject_deputy_keeps_cover_permission_day_and_interval():
    req = requirement(
        "deputy",
        "Alder bracket depth",
        relation="deputy",
        question=(
            "Which deputy can cover Alder bracket depth "
            "under what day-and-time restriction?"
        ),
    )
    source = (
        "The Margin steward is the deputy for Alder bracket depth and may substitute "
        "only on Friday from 13:00 to 14:00."
    )
    result = bind(req, source, "Margin steward")
    assert result.rejection is None
    assert "may substitute" not in result.hypothesis
    assert "Alder bracket depth" in result.hypothesis
    assert result.premise == source.rstrip(".")
    assert source[result.support_start : result.support_end] == source


@pytest.mark.parametrize("permission", ["may not substitute", "must never substitute"])
def test_deputy_cover_does_not_turn_a_denial_into_permission(permission):
    req = requirement(
        "deputy",
        "Alder bracket depth",
        relation="deputy",
        question="Which deputy may cover Alder bracket depth, and when?",
    )
    source = (
        f"The Margin steward is the deputy for Alder bracket depth and {permission} "
        "on Friday from 13:00 to 14:00."
    )
    assert bind(req, source, "Margin steward").rejection is not None


METHOD = (
    "This is an invented Alder bracket depth worksheet convention. "
    "Ordinary worksheets carry no amber triangle. "
    "An ordinary Alder bracket depth session lasts 11 minutes. "
    "Do not skip a closing bracket. "
    "The following complete procedure applies to ordinary worksheets "
    "with no amber triangle. "
    "Step 1. Write depth zero in the left margin. "
    "Step 2. Read each bracket from left to right. "
    "Step 3. Record the resulting depth beneath every bracket, "
    "including the final bracket. "
    "Step 4. Circle any negative depth and stop before reading the next bracket."
)


def procedure_req():
    return requirement(
        "procedure",
        "ordinary Alder bracket depth worksheet with no amber triangle",
        relation="procedure",
        question=(
            "List the complete ordered method for an ordinary Alder bracket depth "
            "worksheet with no amber triangle."
        ),
    )


def test_step_labels_expand_nonnull_step_to_complete_conditioned_method():
    result = bind(procedure_req(), METHOD, "Write depth zero in the left margin")
    assert result.rejection is None
    assert all(f"Step {n}." in result.value for n in range(1, 5))
    assert "Do not skip a closing bracket." in result.value
    assert "applies to ordinary worksheets with no amber triangle" in result.value
    assert METHOD[result.start : result.end] == result.value
    assert any(
        "Alder bracket depth worksheet convention" in check.hypothesis
        for check in result.checks
    )
    assert all(check.premise in METHOD for check in result.checks)


@pytest.mark.parametrize("replacement", ["Step 3.", "Step 1."])
def test_step_labels_do_not_accept_gap_or_restart_as_complete_method(replacement):
    source = METHOD.replace("Step 2.", replacement)
    assert (
        bind(procedure_req(), source, "Write depth zero in the left margin").rejection
        is not None
    )


@pytest.mark.parametrize(
    "replacement", ["with an amber triangle", "with a blue square"]
)
def test_method_requires_original_negative_applicability_condition(replacement):
    source = METHOD.replace("with no amber triangle", replacement)
    assert (
        bind(procedure_req(), source, "Write depth zero in the left margin").rejection
        is not None
    )


def test_step_number_inside_instruction_is_not_a_new_marker():
    source = METHOD.replace(
        "Read each bracket from left to right.",
        "Read the label Step 7 before scanning each bracket.",
    )
    result = bind(procedure_req(), source, "Write depth zero in the left margin")
    assert result.rejection is None
    assert "Read the label Step 7" in result.value and "Step 4." in result.value


def test_step_method_stops_before_competing_activity_heading():
    source = (
        METHOD + " Alder budget audit: Step 1. Open the reserve ledger. "
        "Step 2. Close the ledger."
    )
    result = bind(procedure_req(), source, "Write depth zero in the left margin")
    assert result.rejection is None
    assert "reserve ledger" not in result.value


def test_step_method_cannot_borrow_namespace_from_other_worksheet_convention():
    source = METHOD.replace(
        "Alder bracket depth worksheet convention",
        "Alder budget audit worksheet convention",
    )
    assert (
        bind(procedure_req(), source, "Write depth zero in the left margin").rejection
        is not None
    )


@pytest.mark.parametrize(
    ("kind", "selected"), [("start_time", "09:30"), ("weekday", "Tuesday")]
)
def test_scheduled_session_starts_bind_actual_session_and_exclude_arrival(
    kind, selected
):
    req = requirement(
        kind,
        "ordinary Alder bracket depth session",
        relation="starts",
        attribute=kind,
        question=(
            "What time does ordinary Alder bracket depth session start?"
            if kind == "start_time"
            else None
        ),
    )
    source = (
        "Ordinary Alder bracket depth sessions start on Tuesday at 09:30; "
        "arrival is permitted from 09:20."
    )
    good = bind(req, source, selected)
    assert good.rejection is None
    assert "arrival" not in good.premise
    assert (
        bind(
            replace(req, kind="start_time", attribute="start_time"), source, "09:20"
        ).rejection
        is not None
    )


def test_dependent_cover_window_keeps_exact_deputy_target_only_and_weekday():
    req = replace(
        requirement(
            "availability",
            "the Margin steward",
            relation="cover_window",
            question=(
                "For ordinary Alder bracket depth, "
                "when may the Margin steward cover as deputy?"
            ),
        ),
        id="r2",
        depends_on=("r1",),
    )
    source = (
        "The Margin steward is the deputy for Alder bracket depth and may substitute "
        "only on Friday from 13:00 to 14:00."
    )
    result = bind(req, source, "13:00 to 14:00")
    assert result.rejection is None
    assert result.hypothesis == (
        "the Margin steward may substitute only on Friday from 13:00 to 14:00"
    )
    assert result.premise == source.rstrip(".")
    assert source[result.support_start : result.support_end] == source


@pytest.mark.parametrize("change", ["actor", "target", "polarity", "limit"])
def test_dependent_cover_window_cannot_borrow_actor_scope_permission_or_day(change):
    req = replace(
        requirement(
            "availability",
            "the Margin steward",
            relation="cover_window",
            question=(
                "For ordinary Alder bracket depth, "
                "when may the Margin steward cover as deputy?"
            ),
        ),
        id="r2",
        depends_on=("r1",),
    )
    source = (
        "The Margin steward is the deputy for Alder bracket depth and may substitute "
        "only on Friday from 13:00 to 14:00."
    )
    if change == "actor":
        source = source.replace("Margin steward", "Margin steward's assistant")
    elif change == "target":
        source = source.replace("Alder bracket depth", "Alder budget audit")
    elif change == "polarity":
        source = source.replace("may substitute", "may not substitute")
    else:
        req = replace(req, question=req.question.replace("when", "on Tuesday when"))
    assert bind(req, source, "13:00 to 14:00").rejection is not None


@pytest.mark.parametrize("heading", ["Willow budget audit:", "Alder budget audit:"])
def test_worksheet_ancestor_cannot_cross_an_explicit_competing_activity(heading):
    source = METHOD.replace(
        "The following complete procedure",
        heading + " The following complete procedure",
    )
    assert (
        bind(procedure_req(), source, "Write depth zero in the left margin").rejection
        is not None
    )


def test_worksheet_ancestor_cannot_cross_a_foreign_namespace_sentence():
    source = METHOD.replace(
        "The following complete procedure",
        "Willow budget audit. The following complete procedure",
    )
    assert (
        bind(procedure_req(), source, "Write depth zero in the left margin").rejection
        is not None
    )


def test_explicit_worksheet_convention_does_not_require_synthetic_status_words():
    source = METHOD.replace("This is an invented ", "")
    assert (
        bind(procedure_req(), source, "Write depth zero in the left margin").rejection
        is None
    )


def test_explicit_worksheet_method_governs_its_immediately_preceding_prohibition():
    req = requirement(
        "prohibition",
        "ordinary Alder bracket depth session",
        relation="prohibition",
        question=(
            "For ordinary Alder bracket depth, what action is prohibited in the method?"
        ),
    )
    result = bind(req, METHOD, "skip a closing bracket")
    assert result.rejection is None
    assert (
        result.hypothesis
        == "ordinary Alder bracket depth session must not skip a closing bracket"
    )
    assert "worksheet convention" in result.premise
    assert "Step 1" not in result.value


def test_worksheet_method_prohibition_does_not_borrow_another_namespace():
    req = requirement(
        "prohibition",
        "ordinary Alder bracket depth session",
        relation="prohibition",
        question=(
            "For ordinary Alder bracket depth, what action is prohibited in the method?"
        ),
    )
    source = METHOD.replace("Do not skip", "Willow budget audit. Do not skip")
    assert bind(req, source, "skip a closing bracket").rejection is not None


@pytest.mark.parametrize("raw", ["Friday", "13:00", "Friday from 13:00 to 14:00"])
def test_nonnull_cover_day_or_clock_expands_only_its_complete_bound_window(raw):
    req = replace(
        requirement(
            "availability",
            "the Margin steward",
            relation="cover_window",
            question=(
                "For ordinary Alder bracket depth, "
                "when may the Margin steward cover as deputy?"
            ),
        ),
        id="r2",
        depends_on=("r1",),
    )
    source = (
        "The Margin steward is the deputy for Alder bracket depth and may substitute "
        "only on Friday from 13:00 to 14:00."
    )
    result = bind(req, source, raw)
    assert result.rejection is None
    assert result.value == "Friday from 13:00 to 14:00"
    assert source[result.start : result.end] == result.value
    assert "only on Friday from 13:00 to 14:00" in result.hypothesis


def test_lead_field_cannot_be_a_nested_role_title():
    req = requirement(
        "owner", "Alder bracket depth", relation="leads", attribute="owner"
    )
    source = "The assistant to the lead for Alder bracket depth is the Tracekeeper."
    assert bind(req, source, "Tracekeeper").rejection is not None


def test_cover_activity_may_omit_only_requested_generic_session_head():
    req = replace(
        requirement(
            "availability",
            "the Margin steward",
            relation="cover_window",
            question=(
                "For ordinary Alder bracket depth session, "
                "under what restriction may the Margin steward cover?"
            ),
        ),
        id="r2",
        depends_on=("r1",),
    )
    source = (
        "The Margin steward is the deputy for Alder bracket depth and may substitute "
        "only on Friday from 13:00 to 14:00."
    )
    result = bind(req, source, "Friday")
    assert result.rejection is None
    assert "for ordinary Alder bracket depth session" not in result.hypothesis
    assert result.proof_edges[0].depends_on == ("r1",)


def test_atomic_proof_records_are_additive_and_legacy_constructors_still_work():
    from app.services import requirement_binding as module

    old_check = module.SupportCheck("legacy", "source", "hypothesis")
    assert old_check.start is None and old_check.end is None
    old_claim = module.SupportClaim("h", "p", "v", 0, 1, None)
    assert old_claim.proof_edges == ()
    assert old_claim.premise_start is None and old_claim.premise_end is None
    edge = module.SupportEdge("join", 0, 1, 2, 3, "r1")
    assert edge.depends_on == ()


def test_atomic_worksheet_proof_has_literal_namespace_condition_and_instruction_joins():
    result = bind(procedure_req(), METHOD, "Write depth zero in the left margin")
    assert result.rejection is None
    assert result.premise == result.value
    assert METHOD[result.premise_start : result.premise_end] == result.premise
    assert "requires the following steps in order" in result.hypothesis
    assert all(f"Step {number}." in result.hypothesis for number in range(1, 5))
    checks = {check.name: check for check in result.checks}
    assert {
        "procedure_namespace",
        "procedure_applicability",
        "procedure_prohibition_1",
    } <= checks.keys()
    assert (
        "ordinary worksheets with no amber triangle"
        in checks["procedure_applicability"].hypothesis
    )
    assert (
        "Alder bracket depth worksheet convention"
        in checks["procedure_namespace"].hypothesis
    )
    assert "skipping a closing bracket" in checks["procedure_prohibition_1"].hypothesis
    assert "Do not skip a closing bracket." in result.value
    verified = [(result.premise_start, result.premise_end)]
    for check in result.checks:
        assert type(check.start) is int and type(check.end) is int
        assert METHOD[check.start : check.end] == check.premise
        verified.append((check.start, check.end))
    names = {edge.name for edge in result.proof_edges}
    assert names == {
        "worksheet_namespace_to_applicability",
        "worksheet_applicability_to_instructions",
        "worksheet_namespace_to_prohibition",
    }
    for edge in result.proof_edges:
        assert edge.requirement_id == "r1" and edge.depends_on == ()
        assert (
            0
            <= edge.source_start
            < edge.source_end
            <= edge.target_start
            < edge.target_end
            <= len(METHOD)
        )
        assert any(a <= edge.source_start < edge.source_end <= b for a, b in verified)
        assert any(a <= edge.target_start < edge.target_end <= b for a, b in verified)


def test_atomic_cover_needs_external_dependency_and_monotonic_scoped_join():
    req = replace(
        requirement(
            "availability",
            "the Margin steward",
            relation="cover_window",
            question=(
                "For ordinary Alder bracket depth session, "
                "when may the Margin steward cover?"
            ),
        ),
        id="r2",
        depends_on=("r1",),
    )
    source = (
        "The Margin steward is the deputy for Alder bracket depth "
        "and may substitute only on Friday from 13:00 to 14:00."
    )
    result = bind(req, source, "Friday")
    assert result.rejection is None
    assert (
        result.hypothesis
        == "the Margin steward may substitute only on Friday from 13:00 to 14:00"
    )
    assert len(result.proof_edges) == 1
    edge = result.proof_edges[0]
    assert edge.name == "scoped_deputy_to_permission"
    assert edge.requirement_id == "r2" and edge.depends_on == ("r1",)
    assert edge.source_end <= edge.target_start
    assert (
        "deputy for Alder bracket depth" in source[edge.source_start : edge.source_end]
    )
    assert source[edge.target_start : edge.target_end].startswith("may substitute only")
    assert source[result.premise_start : result.premise_end] == result.premise
    assert bind(replace(req, depends_on=()), source, "Friday").rejection is not None
    assert (
        bind(replace(req, depends_on=("r2",)), source, "Friday").rejection is not None
    )


@pytest.mark.parametrize(
    "intervening",
    [
        "Willow budget audit: ",
        "Alder budget audit: ",
        "When an amber triangle is present, use these instructions. ",
        "Exception: use the ordinary method only after review. ",
    ],
)
def test_atomic_worksheet_join_cannot_cross_a_scope_reset(intervening):
    source = METHOD.replace(
        "The following complete procedure",
        intervening + "The following complete procedure",
    )
    assert (
        bind(procedure_req(), source, "Write depth zero in the left margin").rejection
        is not None
    )


def test_repeated_applicability_text_has_the_actual_selected_namespace_coordinates():
    second = METHOD.replace("Alder bracket depth", "Willow budget audit")
    source = METHOD + "\n" + second
    req = replace(
        procedure_req(),
        topic=procedure_req().topic.replace(
            "Alder bracket depth", "Willow budget audit"
        ),
        original_text=procedure_req().original_text.replace(
            "Alder bracket depth", "Willow budget audit"
        ),
        question=procedure_req().question.replace(
            "Alder bracket depth", "Willow budget audit"
        ),
        anchors=("willow",),
    )
    start = source.rindex("Write depth zero in the left margin")
    result = support_claim(
        req, source, start, start + len("Write depth zero in the left margin")
    )
    assert result.rejection is None
    check = next(c for c in result.checks if c.name == "procedure_applicability")
    assert check.start > len(METHOD)
    assert source[check.start : check.end] == check.premise
    wrong = support_claim(
        procedure_req(),
        source,
        start,
        start + len("Write depth zero in the left margin"),
    )
    assert wrong.rejection is not None


def test_complete_method_does_not_drop_a_governing_prerequisite():
    source = METHOD.replace(
        "Do not skip a closing bracket.",
        "Before starting Alder bracket depth, obtain the review stamp. "
        "Do not skip a closing bracket.",
    )
    result = bind(procedure_req(), source, "Write depth zero in the left margin")
    assert result.rejection is None
    assert "obtain the review stamp" in result.value
    assert "Do not skip a closing bracket" in result.value
    assert "obtain the review stamp" in result.hypothesis or any(
        "obtain the review stamp" in c.hypothesis for c in result.checks
    )


@pytest.mark.parametrize(
    "replacement",
    ["may substitute on", "may substitute for Alder budget audit only on"],
)
def test_atomic_cover_cannot_rebind_permission_or_remove_only(replacement):
    req = replace(
        requirement(
            "availability",
            "the Margin steward",
            relation="cover_window",
            question=(
                "For ordinary Alder bracket depth, when may the Margin steward cover?"
            ),
        ),
        id="r2",
        depends_on=("r1",),
    )
    source = (
        "The Margin steward is the deputy for Alder bracket depth "
        "and may substitute only on Friday from 13:00 to 14:00."
    )
    assert (
        bind(
            req, source.replace("may substitute only on", replacement), "Friday"
        ).rejection
        is not None
    )


def test_unknown_extra_requested_profile_is_never_removed_by_factoring():
    req = procedure_req()
    req = replace(
        req, original_text=req.original_text.rstrip(".") + ", using the blue profile."
    )
    source = METHOD.replace(
        "Write depth zero in the left margin.",
        "Use the red profile. Write depth zero in the left margin.",
    )
    result = bind(req, source, "Write depth zero in the left margin")
    assert result.rejection is not None or (
        "blue profile" in result.hypothesis
        or any("blue profile" in check.hypothesis for check in result.checks)
    )


def test_unbound_extra_qualifier_is_not_dropped_by_atomic_instruction_echo():
    req = replace(
        procedure_req(),
        original_text=(
            "List the complete ordered method with the blue profile for an ordinary "
            "Alder bracket depth worksheet with no amber triangle."
        ),
    )
    result = bind(req, METHOD, "Write depth zero in the left margin")
    assert (
        result.rejection is not None
        or "blue profile" in result.hypothesis
        or any("blue profile" in check.hypothesis for check in result.checks)
    )


def test_atomic_proof_budget_refuses_instead_of_omitting_prohibitions():
    prelude = " ".join(f"Do not discard bracket {n}." for n in range(9))
    source = METHOD.replace("Do not skip a closing bracket.", prelude)
    result = bind(procedure_req(), source, "Write depth zero in the left margin")
    assert result.rejection == "proof_budget_exceeded"


def test_cover_same_actor_under_second_activity_does_not_reuse_first_root():
    req = replace(
        requirement(
            "availability",
            "the Margin steward",
            relation="cover_window",
            question=(
                "For ordinary Alder bracket depth, when may the Margin steward cover?"
            ),
        ),
        id="r2",
        depends_on=("r1",),
    )
    first = (
        "The Margin steward is the deputy for Alder bracket depth "
        "and may substitute only on Friday from 13:00 to 14:00. "
    )
    second = (
        "The Margin steward is the deputy for Alder budget audit "
        "and may substitute only on Tuesday from 15:00 to 16:00."
    )
    source = first + second
    start = source.index("Tuesday")
    assert (
        support_claim(req, source, start, start + len("Tuesday")).rejection is not None
    )


def test_explicit_requested_cover_endpoint_cannot_change_during_factoring():
    req = replace(
        requirement(
            "availability",
            "the Margin steward",
            relation="cover_window",
            question=(
                "For ordinary Alder bracket depth, "
                "may the Margin steward cover from 13:00 to 15:00?"
            ),
        ),
        id="r2",
        depends_on=("r1",),
    )
    source = (
        "The Margin steward is the deputy for Alder bracket depth "
        "and may substitute only on Friday from 13:00 to 14:00."
    )
    assert bind(req, source, "Friday").rejection is not None


def test_atomic_request_range_keeps_its_coordination_comma_without_losing_factoring():
    req = replace(
        procedure_req(), original_text=procedure_req().original_text.rstrip(".") + ","
    )
    result = bind(req, METHOD, "Write depth zero in the left margin")
    assert result.rejection is None
    assert any(c.name == "procedure_namespace" for c in result.checks)
    assert result.proof_edges


def test_identical_namespace_and_applicability_proofs_keep_second_occurrence():
    source = METHOD + "\n" + METHOD
    start = source.rindex("Write depth zero in the left margin")
    result = support_claim(
        procedure_req(),
        source,
        start,
        start + len("Write depth zero in the left margin"),
    )
    assert result.rejection is None
    for check in result.checks:
        assert check.start > len(METHOD)
        assert source[check.start : check.end] == check.premise
    assert result.premise_start > len(METHOD)


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("Quartz review stores the archive. Bob leads Willow review.", "irrelevant"),
        ("Alice leads Quartz review.", "applies"),
        ("Bob leads Willow review.", "irrelevant"),
        ("Bob leads the review.", "unknown"),
        ("Bob leads Quartz budget review.", "irrelevant"),
        ("Bob leads the Quartz review archive.", "irrelevant"),
        ("Bob leads an archive for Quartz review.", "irrelevant"),
        ("Quartz review leads Willow review.", "irrelevant"),
        ("For Quartz review, the lead is not Alice.", "applies"),
        ("Alice does not lead Quartz review.", "applies"),
        ("Quartz review is not led by Bob.", "applies"),
        ("Willow review is led by Bob.", "irrelevant"),
        ("For Quartz review, the lead is Alice.", "applies"),
        ("For Willow review, the lead is Bob.", "irrelevant"),
        ("For the review, the lead is Bob.", "unknown"),
        ("For Quartz review, the owner is Bob.", "irrelevant"),
        ("For Quartz review, the deputy is Bob.", "irrelevant"),
        ("For Quartz review, the attendant is Bob.", "irrelevant"),
        ("Bob owns Quartz review.", "irrelevant"),
        ("Bob leads Willow review. Alice leads Quartz review.", "applies"),
        ("Bob leads Willow review. Carol leads the review.", "unknown"),
        ("Quartz review stores the archive.", "unknown"),
    ],
)
def test_relation_scope_binds_the_requested_role_predicate_target(source, expected):
    from app.services import requirement_binding as module

    req = replace(
        requirement("owner", "Quartz review", relation="leads"), anchors=("quartz",)
    )
    assert module.source_relation_scope(req, source) == expected


@pytest.mark.parametrize(
    ("kind", "relation", "source", "expected"),
    [
        ("deputy", "deputy", "The clerk is the deputy for Quartz review.", "applies"),
        (
            "deputy",
            "deputy",
            "The clerk is the deputy for Willow review.",
            "irrelevant",
        ),
        ("deputy", "deputy", "The clerk is the deputy for the review.", "unknown"),
        ("owner", "owns", "Alice owns Quartz review.", "applies"),
        ("owner", "owns", "For Quartz review, the owner is Alice.", "applies"),
        ("owner", "owns", "Alice leads Quartz review.", "irrelevant"),
        ("quantity", "quantity", "Quartz review contains 8 records.", "unknown"),
    ],
)
def test_relation_scope_other_bounded_roles_reuse_the_same_target_authority(
    kind, relation, source, expected
):
    from app.services import requirement_binding as module

    req = replace(
        requirement(kind, "Quartz review", relation=relation), anchors=("quartz",)
    )
    assert module.source_relation_scope(req, source) == expected


def test_relation_scope_does_not_infer_activity_to_ordinary_session_role():
    from app.services import requirement_binding as module

    req = replace(
        requirement("owner", "ordinary Quartz review session", relation="leads"),
        anchors=("quartz",),
    )
    assert (
        module.source_relation_scope(req, "For Quartz review, the lead is Alice.")
        == "unknown"
    )


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("For Quartz review: 1. Open the pass. 2. Read the pass.", "applies"),
        ("For Willow review: 1. Open the pass. 2. Read the pass.", "irrelevant"),
        (
            "Quartz review stores the archive. For Willow review: "
            "1. Open the pass. 2. Read the pass.",
            "irrelevant",
        ),
        ("Complete procedure: 1. Open the pass. 2. Read the pass.", "unknown"),
    ],
)
def test_relation_scope_bounded_procedure_header_is_not_a_word_anywhere_match(
    source, expected
):
    from app.services import requirement_binding as module

    req = replace(
        requirement("procedure", "Quartz review", relation="procedure"),
        anchors=("quartz",),
    )
    assert module.source_relation_scope(req, source) == expected


@pytest.mark.parametrize(
    "mutation, expected",
    [
        ("same", "applies"),
        ("foreign", "irrelevant"),
        ("opposed_mark", "irrelevant"),
    ],
)
def test_relation_scope_worksheet_body_ancestor_and_condition(mutation, expected):
    from app.services import requirement_binding as module

    source = METHOD
    if mutation == "foreign":
        source = source.replace(
            "Alder bracket depth worksheet convention",
            "Willow budget audit worksheet convention",
        )
    elif mutation == "opposed_mark":
        source = source.replace(
            "applies to ordinary worksheets with no amber triangle",
            "applies to ordinary worksheets with an amber triangle",
        )
    assert module.source_relation_scope(procedure_req(), source) == expected


def test_relation_scope_explicit_foreign_workspace_is_not_inherited():
    from app.services import requirement_binding as module

    req = replace(
        requirement("owner", "Quartz review", relation="leads"),
        anchors=("quartz",),
        source_workspace="alpha",
    )
    assert (
        module.source_relation_scope(
            req, "In workspace beta, Alice leads Quartz review."
        )
        == "irrelevant"
    )
    assert (
        module.source_relation_scope(
            req, "In workspace alpha, Alice leads Quartz review."
        )
        == "applies"
    )


def test_relation_scope_never_invokes_answer_or_model_proposal(monkeypatch):
    from app.services import requirement_binding as module

    def fail(*args, **kwargs):
        raise AssertionError("source scope must remain a pure body relation inspection")

    monkeypatch.setattr(module, "support_claim", fail)
    req = replace(
        requirement("owner", "Quartz review", relation="leads"), anchors=("quartz",)
    )
    assert module.source_relation_scope(req, "Alice leads Quartz review.") == "applies"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("The assistant to the lead for Quartz review is Bob.", "irrelevant"),
        ("For Quartz review, the current lead is Alice.", "applies"),
        ("For Quartz review, the work lead is Alice.", "unknown"),
    ],
)
def test_relation_scope_does_not_confuse_a_modified_or_nested_role_field(
    source, expected
):
    from app.services import requirement_binding as module

    req = replace(
        requirement("owner", "Quartz review", relation="leads"), anchors=("quartz",)
    )
    assert module.source_relation_scope(req, source) == expected


def test_relation_scope_modified_field_keeps_explicit_workspace_condition():
    from app.services import requirement_binding as module

    req = replace(
        requirement("owner", "Quartz review", relation="leads"),
        anchors=("quartz",),
        source_workspace="alpha",
    )
    source = "For Quartz review, the current lead is Bob in workspace beta."
    assert module.source_relation_scope(req, source) == "irrelevant"


@pytest.mark.parametrize(
    "kind,relation,field,expected",
    [
        ("owner", "owns", "current owner", "applies"),
        ("deputy", "deputy", "current deputy", "applies"),
        ("deputy", "deputy", "record deputy", "unknown"),
    ],
)
def test_precise_field_scope_is_not_suppressed_by_a_broad_role_pattern(
    kind, relation, field, expected
):
    from app.services import requirement_binding as module

    req = replace(
        requirement(kind, "Quartz review", relation=relation), anchors=("quartz",)
    )
    assert (
        module.source_relation_scope(req, f"For Quartz review, the {field} is Bob.")
        == expected
    )


def compound_method_fixture():
    source = METHOD.replace("bracket depth", "two-part audit")
    text = (
        "Give all ordered worksheet steps for ordinary Alder two-part audit "
        "with no amber triangle"
    )
    req = requirement(
        "procedure",
        "ordinary Alder two-part audit with no amber triangle",
        relation="procedure",
        question=text,
    )
    return req, source


def test_compound_activity_exact_ancestor_keeps_mandatory_atomic_method_proof():
    req, source = compound_method_fixture()
    result = bind(req, source, "Write depth zero in the left margin")
    assert result.rejection is None
    assert {
        "procedure_namespace",
        "procedure_applicability",
        "procedure_prohibition_1",
    } <= {c.name for c in result.checks}
    assert "two-part audit worksheet convention" in next(
        c.hypothesis for c in result.checks if c.name == "procedure_namespace"
    )
    assert "requires the following steps in order" in result.hypothesis
    assert "Do not skip a closing bracket." in result.value
    assert all(f"Step {n}." in result.value for n in range(1, 5))


def test_compound_comparison_does_not_create_a_new_activity_alias():
    req, source = compound_method_fixture()
    req = replace(
        req,
        topic=req.topic.replace("two-part", "two part"),
        original_text=req.original_text.replace("two-part", "two part"),
    )
    assert (
        bind(req, source, "Write depth zero in the left margin").rejection is not None
    )


def test_compound_method_does_not_drop_unknown_configuration_or_prerequisite():
    req, source = compound_method_fixture()
    req = replace(req, original_text=req.original_text + ", using the blue profile.")
    result = bind(req, source, "Write depth zero in the left margin")
    assert (
        result.rejection is not None
        or "blue profile" in result.hypothesis
        or any("blue profile" in c.hypothesis for c in result.checks)
    )


def test_cover_applicability_uses_retained_activity_scope_not_selected_actor():
    req = replace(
        requirement(
            "availability",
            "the Margin steward",
            relation="cover_window",
            question=(
                "For Alder two-part audit, "
                "under what restriction may the Margin steward cover?"
            ),
        ),
        id="r2",
        depends_on=("r1",),
    )
    source = (
        "For Alder two-part audit, the lead is the review clerk. "
        "The Margin steward is the deputy for Alder two-part audit and may substitute "
        "only on Friday from 13:00 to 14:00."
    )
    result = bind(req, source, "Friday")
    assert result.rejection is None
    assert condition_relation(req, source, {}) == "applies"
    assert "only on Friday from 13:00 to 14:00" in result.hypothesis
    assert result.proof_edges[0].depends_on == ("r1",)
    assert (
        condition_relation(req, source, {"condition": "exception retest"})
        == "irrelevant"
    )
    foreign = source.replace("Alder two-part audit", "Willow budget audit")
    assert condition_relation(req, foreign, {}) != "applies"
    assert bind(req, foreign, "Friday").rejection is not None


def test_prohibition_mark_refuses_but_complete_contained_command_may_refine():
    _, source = compound_method_fixture()
    req = requirement(
        "prohibition",
        "ordinary Alder two-part audit",
        relation="prohibition",
        question="What is the prohibition for ordinary Alder two-part audit?",
    )
    assert bind(req, source, "no amber triangle").rejection is not None
    start = source.index("no amber triangle")
    end = source.index("Do not skip a closing bracket") + len(
        "Do not skip a closing bracket"
    )
    result = support_claim(req, source, start, end)
    assert result.rejection is None
    assert result.value == "Do not skip a closing bracket"
    assert start <= result.start < result.end <= end
    assert bind(req, source, "skip a closing bracket").rejection is None


def prohibition_fixture(source=METHOD):
    req = requirement(
        "prohibition",
        "ordinary Alder bracket depth",
        relation="prohibition",
        question="What action is prohibited in ordinary Alder bracket depth?",
    )
    start = source.index("no amber triangle")
    end = source.index("Do not skip a closing bracket") + len(
        "Do not skip a closing bracket"
    )
    return req, source, start, end


def test_accepted_overspan_refines_one_complete_governing_prohibition_only():
    req, source, start, end = prohibition_fixture()
    result = support_claim(req, source, start, end)
    assert result.rejection is None
    assert result.value == "Do not skip a closing bracket"
    assert start <= result.start < result.end <= end
    assert source[result.start : result.end] == result.value
    assert (
        result.hypothesis
        == "ordinary Alder bracket depth must not skip a closing bracket"
    )
    assert "worksheet convention" in result.premise
    assert "Ordinary worksheets carry no amber triangle" in result.premise
    assert "applies to ordinary worksheets with no amber triangle" in result.premise
    assert source[result.premise_start : result.premise_end] == result.premise


@pytest.mark.parametrize("selection", ["mark", "partial", "nonoverlap"])
def test_prohibition_refinement_cannot_find_or_complete_a_command_outside_raw(
    selection,
):
    req, source, start, end = prohibition_fixture()
    if selection == "mark":
        end = start + len("no amber triangle")
    elif selection == "partial":
        end = source.index("closing bracket")
    else:
        start = source.index("The following complete procedure")
        end = start + len("The following complete procedure")
    assert support_claim(req, source, start, end).rejection is not None


def test_accepted_overspan_does_not_choose_among_multiple_complete_prohibitions():
    req, source, start, _ = prohibition_fixture()
    source = source.replace(
        "Do not skip a closing bracket.",
        "Do not skip a closing bracket. Do not erase a depth.",
    )
    end = source.index("Do not erase a depth") + len("Do not erase a depth")
    assert support_claim(req, source, start, end).rejection is not None


@pytest.mark.parametrize(
    "change",
    [
        "namespace",
        "activity_header",
        "condition_prefix",
        "permission_denial",
        "applicability",
    ],
)
def test_prohibition_refinement_preserves_source_governance_and_polarity(change):
    req, source, start, end = prohibition_fixture()
    if change == "namespace":
        source = source.replace("Alder bracket depth", "Willow budget audit")
    elif change == "activity_header":
        source = source.replace("Do not skip", "Alder budget audit: Do not skip")
    elif change == "condition_prefix":
        source = source.replace("Do not skip", "When the stamp is missing, do not skip")
    elif change == "permission_denial":
        source = source.replace(
            "Do not skip a closing bracket",
            "The instructions do not prohibit skipping a closing bracket",
        )
    else:
        source = source.replace(
            "applies to ordinary worksheets", "applies to exceptional worksheets"
        )
    start = source.index("no amber triangle")
    end = source.index("The following complete procedure")
    assert support_claim(req, source, start, end).rejection is not None


def test_prohibition_refinement_does_not_drop_a_qualifying_suffix_or_parameters():
    req, source, start, _ = prohibition_fixture()
    source = source.replace(
        "Do not skip a closing bracket",
        "Do not round 1.5 credits to 2 credits unless the review is signed",
    )
    end = source.index("The following complete procedure")
    result = support_claim(req, source, start, end)
    assert result.rejection is None
    assert (
        result.value
        == "Do not round 1.5 credits to 2 credits unless the review is signed"
    )
    assert "1.5 credits to 2 credits unless the review is signed" in result.hypothesis
    assert result.end <= end


def test_prohibition_refinement_requires_the_requested_action_and_body_class():
    req, source, start, end = prohibition_fixture()
    wrong = replace(req, original_text="Give the rule against erasing labels.")
    assert support_claim(wrong, source, start, end).rejection is not None
    no_class_fact = source.replace(
        "Ordinary worksheets carry no amber triangle.",
        "Some worksheets carry an amber triangle.",
    )
    no_class_start = no_class_fact.index("amber triangle")
    no_class_end = no_class_fact.index("Do not skip a closing bracket") + len(
        "Do not skip a closing bracket"
    )
    assert (
        support_claim(req, no_class_fact, no_class_start, no_class_end).rejection
        is not None
    )


@pytest.mark.parametrize("where", ["topic", "original"])
def test_prohibition_refinement_cannot_discard_an_extra_requested_condition(where):
    req, source, start, end = prohibition_fixture()
    if where == "topic":
        req = replace(req, topic=req.topic + " with the blue profile")
    else:
        req = replace(
            req, original_text="With the blue profile, what action is prohibited?"
        )
    assert support_claim(req, source, start, end).rejection is not None


def test_prohibition_refinement_does_not_drop_a_prior_conditional_scope_fragment():
    req, source, start, _ = prohibition_fixture()
    source = source.replace("Do not skip", "only after the review. Do not skip")
    end = source.index("The following complete procedure")
    assert support_claim(req, source, start, end).rejection is not None


@pytest.mark.parametrize(
    "condition",
    [
        "under the blue profile",
        "after 17:00",
        "before noon",
        "except during reserve sessions",
        "following certification",
        "subject to review",
        "per the second policy",
    ],
)
@pytest.mark.parametrize("frame", ["scoped_command", "direct_question"])
def test_contained_prohibition_requires_complete_request_frame(condition, frame):
    # A retained unknown condition must not become an unqualified prohibition.
    from app.services.answer_requirements import plan_requirements

    req, source, start, end = prohibition_fixture()
    if frame == "scoped_command":
        text = f"For ordinary Alder bracket depth, state the prohibition {condition}."
        req = plan_requirements(text)[0]
        assert condition in req.original_text
    else:
        req = replace(req, original_text=req.original_text[:-1] + f" {condition}?")
    assert support_claim(req, source, start, end).rejection is not None


@pytest.mark.parametrize(
    "suffix",
    [
        "This prohibition does not apply to ordinary worksheets.",
        "This prohibition applies only during reserve sessions.",
        "This prohibition was withdrawn.",
        "An independent authorization is required.",
    ],
)
@pytest.mark.parametrize("raw_includes_suffix", [True, False])
def test_contained_prohibition_cannot_skip_unknown_governing_clause_after_declaration(
    suffix, raw_includes_suffix
):
    # The declaration cannot skip a following qualification to reach Step 1.
    req, source, start, end = prohibition_fixture()
    source = source.replace("Step 1.", suffix + " Step 1.", 1)
    if raw_includes_suffix:
        end = source.index("Step 1.")
    assert support_claim(req, source, start, end).rejection is not None


def test_contained_prohibition_refuses_raw_continuation_beyond_verified_declaration():
    req, source, start, _ = prohibition_fixture()
    end = source.index("Step 2.")
    assert support_claim(req, source, start, end).rejection is not None


def test_contained_prohibition_cannot_drop_raw_prefix_before_governing_namespace():
    req, source, _, _ = prohibition_fixture()
    source = "Approval pending. " + source
    end = source.index("Do not skip a closing bracket") + len(
        "Do not skip a closing bracket"
    )
    assert support_claim(req, source, 0, end).rejection is not None


@pytest.mark.parametrize(
    "text",
    [
        "For ordinary Alder bracket depth, state the prohibition.",
        "What action is prohibited in ordinary Alder bracket depth?",
        "What is the prohibition for ordinary Alder bracket depth?",
        "the method's prohibition.",
    ],
)
def test_known_complete_prohibition_request_keeps_all_accepted_raw_in_primary(text):
    req, source, start, _ = prohibition_fixture()
    req = replace(req, original_text=text)
    end = source.index("Step 1.") - 1
    result = support_claim(req, source, start, end)
    assert result.rejection is None
    assert result.value == "Do not skip a closing bracket"
    assert result.premise_start <= start < end <= result.premise_end
    assert source[result.premise_start : result.premise_end] == result.premise
    assert "ordinary Alder bracket depth" in result.hypothesis


def test_prepared_prohibition_question_unknown_qualification_is_not_discarded():
    req, source, start, end = prohibition_fixture()
    req = replace(req, question=req.question[:-1] + " under the blue profile?")
    assert support_claim(req, source, start, end).rejection is not None


@pytest.mark.parametrize(
    "condition",
    [
        "under the blue profile",
        "after 17:00",
        "before noon",
        "except during reserve sessions",
        "following certification",
    ],
)
@pytest.mark.parametrize(
    "selected", ["skip a closing bracket", "Do not skip a closing bracket"]
)
def test_clean_prohibition_cannot_drop_a_planned_request_qualifier(condition, selected):
    from app.services.answer_requirements import plan_requirements

    text = f"For ordinary Alder bracket depth, state the prohibition {condition}."
    req = plan_requirements(text)[0]
    assert condition in req.original_text
    assert bind(req, METHOD, selected).rejection is not None


def test_clean_prohibition_does_not_ignore_qualifying_clause_after_applicability():
    req, source, _, _ = prohibition_fixture()
    source = source.replace(
        "Step 1.", "This authorization has been rescinded. Step 1.", 1
    )
    assert bind(req, source, "skip a closing bracket").rejection is not None


@pytest.mark.parametrize(
    "scope",
    [
        "Alder intake under the blue profile",
        "Alder intake after 17:00",
        "Alder intake with the blue profile",
    ],
)
def test_complete_explicit_prohibition_scope_stays_in_hypothesis(scope):
    req = requirement(
        "prohibition",
        scope,
        relation="prohibition",
        question=f"What is the prohibition for {scope}?",
    )
    result = bind(req, f"{scope} prohibits skipping the stamp.", "skipping the stamp")
    assert result.rejection is None
    assert result.hypothesis == f"{scope} prohibits skipping the stamp"


@pytest.mark.parametrize("inline", ["then", "next", "finally"])
@pytest.mark.parametrize(
    "selected", ["Write depth zero in the left margin", "Record the resulting depth"]
)
def test_numbered_steps_keep_inline_discourse_inside_step_body(inline, selected):
    source = METHOD.replace(
        "including the final bracket.",
        f"including the final bracket, {inline} push the result.",
    )
    result = bind(procedure_req(), source, selected)
    assert result.rejection is None
    assert f", {inline} push the result." in result.value
    assert all(f"Step {n}." in result.value for n in range(1, 5))
    assert "procedure_namespace" in {c.name for c in result.checks}


@pytest.mark.parametrize(
    "separate",
    [
        "Then write a second ledger.",
        "First open a separate ledger.",
        "Step 4. Open a separate ledger.",
    ],
)
def test_numbered_steps_do_not_discard_a_separate_or_restarted_outline(separate):
    source = METHOD.replace("Step 3.", separate + " Step 3.")
    result = bind(procedure_req(), source, "Write depth zero in the left margin")
    assert result.rejection is not None


def prefaced_ordered_worksheet_request():
    text = (
        "For Alder bracket depth, take me through every step of the ordinary "
        "no-amber-triangle procedure in order."
    )
    return requirement(
        "procedure",
        "ordinary Alder bracket depth no-amber-triangle procedure",
        relation="procedure",
        question=text,
    )


@pytest.mark.parametrize(
    "selected", ["Write depth zero in the left margin", "Record the resulting depth"]
)
def test_prefaced_ordered_request_factors_exact_condition_before_procedure_noun(
    selected,
):
    result = bind(prefaced_ordered_worksheet_request(), METHOD, selected)
    assert result.rejection is None
    assert {
        "procedure_namespace",
        "procedure_applicability",
        "procedure_prohibition_1",
    } <= {c.name for c in result.checks}
    assert "requires the following steps in order" in result.hypothesis
    assert all(f"Step {n}." in result.value for n in range(1, 5))
    assert "Do not skip a closing bracket." in result.value


@pytest.mark.parametrize(
    "suffix",
    [
        "under the blue profile",
        "after 17:00",
        "except during reserve sessions",
        "with prior authorization",
    ],
)
def test_prefaced_ordered_request_cannot_discard_unknown_extra_qualifiers(suffix):
    req = prefaced_ordered_worksheet_request()
    req = replace(req, original_text=req.original_text[:-1] + " " + suffix + ".")
    result = bind(req, METHOD, "Write depth zero in the left margin")
    assert (
        result.rejection is not None
        or suffix in result.hypothesis
        or any(suffix in c.hypothesis for c in result.checks)
    )


def test_prefaced_ordered_request_keeps_unknown_prerequisite_in_complete_proof():
    source = METHOD.replace(
        "The following complete procedure",
        "Approval is required. The following complete procedure",
    )
    result = bind(
        prefaced_ordered_worksheet_request(),
        source,
        "Write depth zero in the left margin",
    )
    assert result.rejection is not None or "Approval is required." in result.premise


def test_prefaced_ordered_request_does_not_borrow_another_namespace_or_mark():
    req = prefaced_ordered_worksheet_request()
    for source in [
        METHOD.replace("Alder bracket depth", "Willow budget audit"),
        METHOD.replace("amber triangle", "blue square"),
    ]:
        assert (
            bind(req, source, "Write depth zero in the left margin").rejection
            is not None
        )


@pytest.mark.parametrize(
    "qualifier",
    [
        "in the blue profile",
        "under the blue profile",
        "after 17:00",
        "before noon",
        "except during reserve sessions",
        "for the blue profile",
        "in the method under authorization",
    ],
)
def test_targeted_prohibition_cannot_elide_any_requested_argument_qualifier(qualifier):
    from app.services.answer_requirements import plan_requirements

    text = (
        f"Give the rule against skipping a closing bracket {qualifier} "
        "for ordinary Alder bracket depth session."
    )
    req = plan_requirements(text)[0]
    assert qualifier in req.original_text
    assert bind(req, METHOD, "skip a closing bracket").rejection is not None


def test_exact_review_targeted_request_has_no_witness_even_with_entailing_double(
    monkeypatch,
):
    import asyncio

    from app.config import Settings
    from app.models.query import AnswerSpan
    from app.services import requirement_answers as controller
    from app.services.answer_reader import ReaderSelection
    from app.services.answer_requirements import plan_requirements
    from app.services.answer_support import SupportAssessment

    from tests.test_requirement_cover_boundaries import chunk

    text = (
        "Give the rule against skipping a closing bracket in the blue profile "
        "for ordinary Alder bracket depth session."
    )
    req = plan_requirements(text)[0]
    start = METHOD.index("skip a closing bracket")
    assessed = []

    async def predict(question, contexts, config=None):
        return [
            ReaderSelection(
                AnswerSpan(
                    start=start,
                    end=start + len("skip a closing bracket"),
                    text="skip a closing bracket",
                ),
                {
                    "raw_span": {
                        "start": start,
                        "end": start + len("skip a closing bracket"),
                    },
                    "null_margin": -9,
                },
            )
        ]

    async def assess(pairs, config=None):
        assessed.extend(pairs)
        return [SupportAssessment("entailment", (-5, 5, -5), 10, True) for _ in pairs]

    monkeypatch.setattr(controller.reader_service, "select_atomic", predict)
    monkeypatch.setattr(controller.support_service, "assess", assess)
    found = asyncio.run(
        controller._find_witnesses(req, [chunk(METHOD, 1)], Settings(), [])
    )
    assert not found
    assert not assessed


@pytest.mark.parametrize(
    "qualifier",
    ["in the blue profile", "after 17:00", "except during reserve sessions"],
)
def test_targeted_prohibition_keeps_a_fully_bound_source_action_qualifier(qualifier):
    from app.services.answer_requirements import plan_requirements

    req = plan_requirements(
        f"Give the rule against skipping a closing bracket {qualifier} "
        "for ordinary Alder bracket depth session."
    )[0]
    source = METHOD.replace(
        "Do not skip a closing bracket", f"Do not skip a closing bracket {qualifier}"
    )
    result = bind(req, source, "skip a closing bracket")
    assert result.rejection is None
    assert qualifier in result.value and qualifier in result.hypothesis


@pytest.mark.parametrize(
    "requested", ["the closing bracket", "a closing bracket in the method"]
)
def test_targeted_prohibition_object_is_not_a_bag_of_incidental_source_words(requested):
    from app.services.answer_requirements import plan_requirements

    req = plan_requirements(
        f"Give the rule against skipping {requested} "
        "for ordinary Alder bracket depth session."
    )[0]
    source = METHOD.replace(
        "Do not skip a closing bracket",
        "Do not skip the review while a closing bracket is pending",
    )
    assert bind(req, source, "skip the review").rejection is not None


def test_targeted_prohibition_also_checks_a_selected_positive_prohibits_argument():
    from app.services.answer_requirements import plan_requirements

    req = plan_requirements(
        "Give the rule against skipping a closing bracket in the blue profile "
        "for ordinary Alder bracket depth session."
    )[0]
    source = (
        "ordinary Alder bracket depth session prohibits skipping a closing bracket."
    )
    assert bind(req, source, "skipping a closing bracket").rejection is not None
