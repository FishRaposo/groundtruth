"""Actual frozen CPU question graphs; expected request structure, no answers."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from app.services.linguistic_requirements import plan_request, validate_request_plan
from app.services.request_parser import _cover, _proposals, make_capture


def fixture_rows():
    p = Path(__file__).parent / "fixtures/dependency_graphs_v628.json"
    return json.loads(p.read_text(encoding="utf-8"))["captures"]


def actual(identifier):
    row = next(r for r in fixture_rows() if r["id"] == identifier)
    capture = row.get("capture") or make_capture(row["annotation"])
    question = capture["annotation"]["raw_text"]
    return question, capture


def planned(identifier):
    return plan_request(*actual(identifier))


def kinds(p):
    return [r.kind for r in p.requirements]


def test_actual_coordination_resolves_four_scoped_atomic_requests():
    p = planned("engineering-coordination")
    assert kinds(p) == ["owner", "deputy", "procedure", "location"]
    assert p.resolved_request
    assert [r.topic for r in p.requirements] == ["Zinc review"] * 4
    assert "materials" in p.requirements[3].question
    assert "are" in p.requirements[3].question
    assert "kept" in p.requirements[3].question


def test_actual_fronted_scope_covers_owner_and_full_process_conditions():
    p = planned("engineering-for-scope")
    assert kinds(p) == ["owner", "procedure"] and p.resolved_request
    assert [r.topic for r in p.requirements] == ["Zinc review"] * 2
    assert "conditions" in p.requirements[1].question
    assert "its" in p.requirements[1].question
    assert p.uses[1].governors


def test_actual_nested_lead_attribute_stays_atomic_unknown():
    p = planned("engineering-nested-attribute")
    assert kinds(p) == ["owner", "generic"] and not p.resolved_request
    assert "allocation" in p.requirements[1].question
    assert "lead" in p.requirements[1].question
    assert "participant-hours" in p.requirements[1].question
    assert p.uses[1].references and p.uses[1].units


def test_actual_unknown_why_survives_mistagged_noun_predicate():
    p = planned("engineering-unknown-why")
    assert kinds(p) == ["owner", "generic"] and not p.resolved_request
    assert "why" in p.requirements[1].question
    assert "may" in p.requirements[1].question
    assert "only after approval" in p.requirements[1].question


def test_actual_advcl_root_and_conj_modals_are_three_distinct_requests():
    p = planned("engineering-modal-list")
    assert kinds(p) == ["generic", "generic", "generic"]
    assert not p.resolved_request
    assert [[x.text for x in u.modality] for u in p.uses] == [
        ["must"],
        ["may"],
        ["should"],
    ]


def test_new_actual_engineering_capture_matches_prefrozen_request_structures():
    for row in fixture_rows():
        if row["origin"] != "actual-engineering-v628":
            continue
        p = planned(row["id"])
        if row["id"] == "e628-condition":
            # R634 explicitly distinguishes known request-condition grammar
            # from source truth/applicability. R628 fixture remains immutable.
            assert kinds(p) == ["procedure"] and p.resolved_request
            assert p.uses[0].condition_ast
            assert (
                "unless the supervisor defers the check" in p.requirements[0].question
            )
            assert p.record()["support_or_permissions"] == "NOT_ASSESSED"
            continue
        if "kinds" in row["expected"]:
            assert kinds(p) == row["expected"]["kinds"], row["id"]
        assert p.resolved_request is row["expected"]["resolved"], row["id"]


@pytest.mark.parametrize("identifier", ["e628-duration", "e628-owner"])
def test_actual_canonical_wh_is_not_rejected_by_missing_question_punctuation(
    identifier,
):
    q, capture = actual(identifier)
    p = plan_request(q, capture)
    assert p.resolved_request
    assert p.requirements[0].question == q


def test_actual_qualified_nominal_heads_preserve_all_modifiers():
    p = planned("e628-qualified-fields")
    assert kinds(p) == ["quantity", "duration", "location"] and p.resolved_request
    for r, words in zip(
        p.requirements,
        [("batch", "quantity"), ("observation", "duration"), ("virtual", "location")],
        strict=True,
    ):
        assert all(w in r.question for w in words)
        assert all(w in r.attribute for w in words)


def test_actual_passive_object_list_is_decomposed_without_assuming_pos_truth():
    p = planned("e628-passive-fields")
    assert kinds(p) == ["quantity", "duration", "location"] and p.resolved_request


def test_whole_question_and_graph_replay_reject_unknown_deletion_and_new_capture():
    q, capture = actual("engineering-unknown-why")
    p = plan_request(q, capture)
    record = p.record()
    assert validate_request_plan(record, question=q, capture=capture)
    record["requirements"].pop()
    record["unresolved"] = []
    record["resolved_request"] = True
    assert not validate_request_plan(record, question=q, capture=capture)
    changed = deepcopy(capture)
    changed["annotation"]["tokens"][0]["start"] = False
    assert not validate_request_plan(p.record(), question=q, capture=changed)


def test_actual_contrast_instructions_and_no_argument_never_gain_support():
    for identifier in [
        "engineering-noun-list",
        "engineering-required-reference",
        "e628-no-argument",
    ]:
        p = planned(identifier)
        assert not p.resolved_request and p.unresolved
        assert all(r.kind == "generic" for r in p.requirements)


@pytest.mark.parametrize(
    "identifier",
    [
        "e628-relative-scope",
        "e628-foreign-of",
        "e628-conditional-owner",
        "e628-relative-property",
        "e628-alternative",
        "e628-polite-modal",
        "e628-extra-action",
        "e628-nested-foreign",
        "e628-assignment-qualification",
        "e628-relative-governor",
    ],
)
def test_actual_scope_or_clause_contrast_cannot_hide_in_consumed_span(identifier):
    p = planned(identifier)
    if identifier == "e628-conditional-owner":
        assert p.resolved_request and p.uses[0].condition_ast
        assert "if the deputy is absent" in p.requirements[0].question
        assert p.record()["support_or_permissions"] == "NOT_ASSESSED"
        return
    assert not p.resolved_request and p.unresolved, identifier
    if identifier == "e628-relative-scope":
        assert "visitor owns" in " ".join(r.question for r in p.requirements)
    if identifier == "e628-nested-foreign":
        text = " ".join(r.question for r in p.requirements)
        assert "red widget" in text and "Zinc review" in text


def test_actual_coordinated_entity_and_each_reference_are_not_flattened():
    p = planned("engineering-entity-list")
    assert not p.resolved_request and p.unresolved
    text = " ".join(r.question for r in p.requirements)
    assert "Amber" in text and "Cobalt" in text and "each" in text


def test_actual_of_reference_is_not_an_activity_allocation():
    p = planned("engineering-of-scope")
    assert kinds(p) == ["owner", "generic"] and not p.resolved_request
    assert p.uses[1].references
    assert "that lead" in p.requirements[1].question


def test_actual_decimal_unit_evidence_preserves_precision_and_unit_case():
    p = planned("engineering-decimal-unit")
    assert not p.resolved_request
    units = {x.text for u in p.uses for x in u.units}
    assert {"1.5 MW", "2 participant-hours", "1.50000000000000000001 MW"} <= units


def test_actual_required_reference_evidence_is_retained_without_closure_claim():
    p = planned("e628-required-reference")
    assert not p.resolved_request
    assert any("checklist" in x.text for u in p.uses for x in u.references)


def test_actual_unique_role_reference_and_order_are_distinct_edges():
    p = planned("e628-explicit-data-reference")
    assert kinds(p) == ["owner", "availability"] and p.resolved_request
    assert p.requirements[1].depends_on == ("r1",)
    assert p.uses[1].order_after == ("r1",)
    assert [x.text for x in p.uses[1].order_evidence] == ["then"]
    assert p.uses[1].references


def test_actual_request_order_without_value_dependency_is_preserved():
    p = planned("e628-request-order")
    assert kinds(p) == ["owner", "procedure"] and p.resolved_request
    assert p.requirements[1].depends_on == ()
    assert p.uses[1].order_after == ("r1",)
    assert [x.text for x in p.uses[1].order_evidence] == ["then"]


def test_actual_plural_reference_is_not_singularized_to_one_role():
    p = planned("e628-ambiguous-plural-reference")
    assert kinds(p) == ["owner", "deputy", "generic"] and not p.resolved_request
    assert p.requirements[2].depends_on == ()
    assert p.uses[2].references


def test_wrong_but_well_formed_graph_cannot_hide_raw_foreign_scope_marker():
    # UNITONLY mutation of actual annotations, not another model observation.
    q, original = actual("e628-nested-foreign")
    annotation = deepcopy(original["annotation"])
    tokens = annotation["tokens"]
    widget = next(t["i"] for t in tokens if t["lemma"] == "widget")
    for t in tokens:
        if t["text"].casefold() == "for" or t["lemma"] == "review":
            t.update(dep="compound", head=widget)
    for t in tokens:
        t["children"] = [
            c["i"] for c in tokens if c["head"] == t["i"] and c["i"] != t["i"]
        ]
    annotation["linguistic_proposals"] = _proposals(tokens, annotation["sentences"])
    capture = make_capture(annotation)
    p = plan_request(q, capture)
    assert not p.resolved_request and p.unresolved
    assert "Zinc review" in " ".join(r.question for r in p.requirements)


@pytest.mark.parametrize("identifier", ["e628-wh-hyphen-name", "e628-wh-hyphen-unit"])
def test_actual_canonical_wh_retains_internal_literal_punctuation(identifier):
    q, capture = actual(identifier)
    p = plan_request(q, capture)
    assert p.resolved_request
    assert p.requirements[0].question == q


def test_actual_clausal_or_is_not_reinterpreted_as_all_requests_together():
    p = planned("e628-clausal-alternative")
    assert not p.resolved_request and p.unresolved


@pytest.mark.parametrize("preposition", ["under", "in"])
def test_unclassified_np_pp_is_not_discarded_or_assumed_to_be_a_unit(preposition):
    # UNITONLY coherent graph contrasts, derived from an actual PP topology.
    _, original = actual("e628-foreign-scope")
    annotation = deepcopy(original["annotation"])
    tokens = annotation["tokens"]
    for t in tokens:
        if t["lemma"] == "identify":
            t.update(text="give", lemma="give")
        if t["lemma"] == "lead":
            t.update(text="quantity", lemma="quantity")
    nested = next(t for t in tokens if t["text"].casefold() == "for" and t["i"] > 0)
    nested.update(text=preposition, lemma=preposition)
    if preposition == "under":
        next(t for t in tokens if t["text"] == "Onyx").update(
            text="normal", lemma="normal", pos="ADJ", tag="JJ"
        )
        next(t for t in tokens if t["lemma"] == "inspection").update(
            text="conditions", lemma="condition"
        )
    cursor = 0
    for t in tokens:
        t["start"] = cursor
        t["end"] = cursor + len(t["text"])
        cursor = t["end"] + len(t["whitespace"])
    q = "".join(t["text"] + t["whitespace"] for t in tokens)
    annotation.update(
        raw_text=q, raw_sha256=__import__("hashlib").sha256(q.encode()).hexdigest()
    )
    annotation["sentences"][0].update(start=0, end=len(q), text=q)
    annotation["lossless_input_cover"] = _cover(q, tokens)
    annotation["linguistic_proposals"] = _proposals(tokens, annotation["sentences"])
    p = plan_request(q, make_capture(annotation))
    assert not p.resolved_request and p.unresolved
    assert preposition in " ".join(r.question for r in p.requirements)
