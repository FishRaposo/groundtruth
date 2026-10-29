"""Actual retained questions and explicit UNITONLY grammar boundary controls."""

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError

import pytest
from app.services.linguistic_requirements import validate_request_plan
from app.services.staged_request import compile_request, validate_partial_request

from tests.partial_request_fixture_v748 import (
    ACTUAL,
    DEPENDENT,
    EXTERNAL,
    EXTRA_ACTION,
    INCUMBENTS,
    LABELS,
    UNITONLY_734,
    UNITONLY_744,
    actual,
    unitonly,
)


def planned(cap):
    return compile_request(cap["annotation"]["raw_text"], cap)


@pytest.mark.parametrize("row", ACTUAL, ids=lambda r: r["id"])
def test_actual_capture_is_retained_exactly_with_every_token_and_unknown(row):
    cap = actual(row["id"])
    q = cap["annotation"]["raw_text"]
    p = planned(cap)
    record = p.record()
    assert json.loads(p.raw_capture_json) == cap
    assert "".join(t.token.text + t.whitespace for t in p.tokens) == q
    assert all(q[t.token.start : t.token.end] == t.token.text for t in p.tokens)
    assert validate_partial_request(record, question=q, capture=cap)
    assert not validate_request_plan(record, question=q, capture=cap)
    assert (
        not {
            "resolved_request",
            "complete",
            "answerable",
            "supported",
            "reading_profile",
        }
        & record.keys()
    )
    assert json.loads(p.features_json)["raw_token_indices"] == list(
        range(len(cap["annotation"]["tokens"]))
    )
    assert json.loads(p.frame_proposals_json)
    if row["id"].startswith("679-condition-"):
        assert any("reference" in u.reason for u in p.unknowns)


def test_actual_roles_and_negative_premise_are_separate_untrusted_obligations():
    p = planned(actual("d526-03-combined"))
    assert any(n.kind == "role_catalogue" for n in p.nodes)
    assert any(n.kind == "procedure" for n in p.nodes)
    assert any(
        n.kind == "request_constraint" and n.operation == "verify_constraint"
        for n in p.nodes
    )
    assert {"role_catalogue", "verify_request_constraint"} <= {
        s.kind for s in p.deferred
    }
    constraint = next(n for n in p.nodes if n.kind == "request_constraint")
    assert (
        "no session override was issued"
        in " ".join(s.text for s in constraint.evidence).lower()
    )
    assert json.loads(constraint.feature_json)["negation"]


def test_actual_temporal_ambiguity_defers_type_without_losing_scalar_siblings():
    p = planned(actual("d526-12-facts"))
    assert {"quantity", "location", "temporal_attribute"} <= {n.kind for n in p.nodes}
    node = next(n for n in p.nodes if n.kind == "temporal_attribute")
    assert any("inspection time" in s.text for s in node.evidence)
    assert any(
        s.kind == "temporal_attribute" and s.node_id == node.id for s in p.deferred
    )
    assert node.operation == "request_field_value"


def test_actual_passive_method_and_independent_governance_facet_are_retained():
    p = planned(actual("d526-02-procedure"))
    methods = [n for n in p.nodes if n.grammar == "passive_method_request"]
    facets = [n for n in p.nodes if n.kind == "procedure_facet"]
    assert len(methods) == len(facets) == 1
    assert any("incomplete sibling set" in s.text for s in facets[0].evidence)
    assert not any(e.kind == "procedure_facet" for e in p.edges)
    slot = next(s for s in p.deferred if s.kind == "procedure_facet_reference")
    assert json.loads(slot.parameters_json)["candidate_method_ids"] == [methods[0].id]
    assert (
        json.loads(slot.parameters_json)["request_ownership"]
        == "deferred_subject_relation"
    )

    assert any(s.kind == "procedure_facet_reference" for s in p.deferred)


@pytest.mark.parametrize(
    "cap,operation",
    [(LABELS, "labels_only"), (INCUMBENTS, "incumbents")],
    ids=["UNITONLY-labels", "UNITONLY-incumbents"],
)
def test_UNITONLY_catalogue_operation_does_not_assume_actor_values_or_role_count(
    cap, operation
):
    p = planned(cap)
    nodes = [n for n in p.nodes if n.kind == "role_catalogue"]
    assert len(nodes) == 1 and nodes[0].operation == operation
    slots = [s for s in p.deferred if s.kind == "role_catalogue"]
    assert len(slots) == 1
    assert json.loads(slots[0].parameters_json)["operation"] == operation
    assert not any(n.kind in {"owner", "deputy", "role_assignment"} for n in p.nodes)
    assert any(s.kind == "literal_subject_boundary" for s in p.deferred)
    assert not any(
        u.reason in {"unknown_requested_head", "unrecognized_request_predicate"}
        for u in p.unknowns
    )


def test_UNITONLY_symbolic_set_edge_is_not_a_value_substitution():
    p = planned(DEPENDENT)
    group = next(n for n in p.nodes if n.kind == "role_catalogue")
    availability = next(n for n in p.nodes if n.kind == "availability")
    assert any(
        e.kind == "catalogue_member_value"
        and e.source_id == group.id
        and e.target_id == availability.id
        for e in p.edges
    )
    assert "their" in " ".join(s.text for e in p.edges for s in e.evidence)
    assert "source_value" not in p.record()
    assert not any(
        u.reason
        in {"unresolved_reference_or_dependent_attribute", "missing_explicit_scope"}
        and availability.head_indices == u.head_indices
        for u in p.unknowns
    )


def test_UNITONLY_independent_unknown_action_cannot_be_absorbed_by_catalogue():
    p = planned(EXTRA_ACTION)
    assert any(n.kind == "role_catalogue" for n in p.nodes)
    assert p.unknowns
    assert any("destroy" in " ".join(s.text for s in u.evidence) for u in p.unknowns)


def test_UNITONLY_external_instruction_target_remains_hard_even_as_a_named_candidate():
    p = planned(EXTERNAL)
    assert any(u.reason == "external_required_target_not_supported" for u in p.unknowns)
    assert not any(s.kind == "external_target_resolution" for s in p.deferred)


def test_partial_is_deeply_immutable_and_replay_rejects_qualifier_or_type_changes():
    cap = actual("679-condition-modal")
    q = cap["annotation"]["raw_text"]
    p = planned(cap)
    with pytest.raises(FrozenInstanceError):
        p.question = "changed"
    detached = p.record()
    detached["tokens"][0]["token"]["start"] = False
    assert not validate_partial_request(detached, question=q, capture=cap)
    detached = p.record()
    detached["raw_capture_json"] = "{}"
    assert not validate_partial_request(detached, question=q, capture=cap)
    changed = deepcopy(cap)
    changed["annotation"]["tokens"][0]["text"] = "Changed"
    assert not validate_partial_request(p.record(), question=q, capture=changed)
    assert "may" in [s["text"] for s in json.loads(p.features_json)["modality"]]
    assert "not" in [s["text"] for s in json.loads(p.features_json)["modality"]]


def test_actual_request_order_edges_are_not_dropped():
    ordered = planned(actual("d526-15-combined"))
    assert any(
        e.kind == "request_order" and any("then" in s.text for s in e.evidence)
        for e in ordered.edges
    )


def test_actual_prior_value_edges_are_not_dropped():
    dependent = planned(actual("e628-explicit-data-reference"))
    assert any(e.kind == "value_dependency" and e.evidence for e in dependent.edges)


def test_actual_governor_and_attribute_fields_remain_explicit():
    p = planned(actual("671-plain-compatible"))
    procedure = next(n for n in p.nodes if n.kind == "procedure")
    features = json.loads(procedure.feature_json)
    assert "all exception handling" in " ".join(
        s["text"] for s in features["governors"]
    )
    assert "complete process" in features["attribute"]
    assert features["extent"] == "whole_requested"
    assert any(
        s.kind == "procedure_facet_reference" and s.node_id == procedure.id
        for s in p.deferred
    )


@pytest.mark.parametrize(
    "identifier", ["662-e662-why", "662-e662-action", "662-e662-extra-action"]
)
def test_actual_unknown_relation_stays_hard(identifier):
    p = planned(actual(identifier))
    assert p.unknowns
    assert not any(
        s.kind in {"unknown_relation", "external_target_resolution"} for s in p.deferred
    )


def test_UNITONLY_catalogue_without_a_literal_subject_retains_scope_unknown():
    rows = [
        (t["text"], t["lemma"], t["pos"], t["tag"], t["dep"], t["head"])
        for t in LABELS["annotation"]["tokens"][:5]
    ]
    rows.append((".", ".", "PUNCT", ".", "punct", 0))
    p = planned(unitonly(rows))
    assert any(n.kind == "role_catalogue" for n in p.nodes)
    assert any(u.reason == "missing_explicit_scope" for u in p.unknowns)


def test_UNITONLY_labels_do_not_supply_actor_antecedents():
    rows = [
        (t["text"], t["lemma"], t["pos"], t["tag"], t["dep"], t["head"])
        for t in LABELS["annotation"]["tokens"][:-1]
    ]
    rows += [
        ("and", "and", "CCONJ", "CC", "cc", 0),
        ("give", "give", "VERB", "VB", "conj", 0),
        ("their", "their", "PRON", "PRP$", "poss", 11),
        ("availability", "availability", "NOUN", "NN", "dobj", 9),
        (".", ".", "PUNCT", ".", "punct", 0),
    ]
    p = planned(unitonly(rows))
    assert any(n.operation == "labels_only" for n in p.nodes)
    assert not any(e.kind == "catalogue_member_value" for e in p.edges)
    assert any("reference" in u.reason for u in p.unknowns)


def test_UNITONLY_unicode_ranges_do_not_use_casefolded_or_byte_offsets():
    rows = [
        (t["text"], t["lemma"], t["pos"], t["tag"], t["dep"], t["head"])
        for t in LABELS["annotation"]["tokens"]
    ]
    rows[6] = ("Straße🧭", "Straße🧭", *rows[6][2:])
    cap = unitonly(rows)
    p = planned(cap)
    assert "".join(t.token.text + t.whitespace for t in p.tokens) == p.question
    assert any("Straße🧭" in s.text for n in p.nodes for s in n.scopes)
    assert all(
        p.question[t.token.start : t.token.end] == t.token.text for t in p.tokens
    )
    assert validate_partial_request(p.record(), question=p.question, capture=cap)


def test_UNITONLY_each_coordinated_role_field_keeps_its_own_explicit_subject():
    cap = unitonly(
        [
            ("List", "list", "VERB", "VB", "ROOT", 0),
            ("role", "role", "NOUN", "NN", "compound", 2),
            ("labels", "label", "NOUN", "NNS", "dobj", 0),
            ("for", "for", "ADP", "IN", "prep", 2),
            ("Cedar", "Cedar", "PROPN", "NNP", "compound", 5),
            ("review", "review", "NOUN", "NN", "pobj", 3),
            ("and", "and", "CCONJ", "CC", "cc", 2),
            ("role", "role", "NOUN", "NN", "compound", 8),
            ("labels", "label", "NOUN", "NNS", "conj", 2),
            ("for", "for", "ADP", "IN", "prep", 8),
            ("Maple", "Maple", "PROPN", "NNP", "compound", 11),
            ("inspection", "inspection", "NOUN", "NN", "pobj", 9),
            (".", ".", "PUNCT", ".", "punct", 0),
        ]
    )
    groups = [n for n in planned(cap).nodes if n.kind == "role_catalogue"]
    assert len(groups) == 2
    assert [s.text for s in groups[0].scopes] == ["Cedar review"]
    assert [s.text for s in groups[1].scopes] == ["Maple inspection"]


@pytest.mark.parametrize(
    "field",
    [
        "nodes",
        "deferred",
        "unknowns",
        "edges",
        "tokens",
        "features_json",
        "frame_proposals_json",
        "question_sha256",
        "capture_sha256",
    ],
)
def test_replay_refuses_deleted_obligations_or_changed_bindings(field):
    cap = actual("d526-15-combined" if field == "edges" else "d526-03-combined")
    p = planned(cap)
    record = p.record()
    assert record[field]
    record[field] = [] if isinstance(record[field], list) else "{}"
    assert not validate_partial_request(record, question=p.question, capture=cap)


def test_replay_never_mutates_input_and_rejects_extra_schema_success_flags():
    cap = actual("d526-12-facts")
    before = deepcopy(cap)
    p = planned(cap)
    assert cap == before
    record = p.record()
    record["resolved_request"] = True
    assert not validate_partial_request(record, question=p.question, capture=cap)
    assert cap == before


def test_UNITONLY_catalogue_keeps_its_operator_modality_explicit():
    rows = []
    for t in INCUMBENTS["annotation"]["tokens"]:
        i = t["i"]
        if i == 1:
            rows.append(("must", "must", "AUX", "MD", "aux", 2))
        head = t["head"] + (t["head"] >= 1)
        rows.append(
            (
                "fill" if i == 1 else t["text"],
                t["lemma"],
                t["pos"],
                "VB" if i == 1 else t["tag"],
                t["dep"],
                head,
            )
        )
    p = planned(unitonly(rows))
    group = next(n for n in p.nodes if n.kind == "role_catalogue")
    assert [s["text"] for s in json.loads(group.feature_json)["modality"]] == ["must"]


def test_actual_recognized_literal_subjects_remain_typed_source_obligations():
    p = planned(actual("engineering-coordination"))
    for n in p.nodes:
        if n.scopes and n.kind != "generic":
            assert any(
                s.node_id == n.id and s.kind == "literal_subject_boundary"
                for s in p.deferred
            )


# Explicitly UNITONLY ownership and argument controls.
PREFIX = [
    ("How", "how", "SCONJ", "WRB", "advmod", 6),
    ("is", "be", "AUX", "VBZ", "auxpass", 6),
    ("the", "the", "DET", "DT", "det", 5),
    ("full", "full", "ADJ", "JJ", "amod", 5),
    ("Cedar", "Cedar", "PROPN", "NNP", "compound", 5),
    ("review", "review", "NOUN", "NN", "nsubjpass", 6),
    ("performed", "perform", "VERB", "VBN", "ROOT", 6),
]


def question(target, *, second=False, other_argument=False):
    rows = list(PREFIX)
    if second:
        rows += [
            ("and", "and", "CCONJ", "CC", "cc", 6),
            ("how", "how", "SCONJ", "WRB", "advmod", 14),
            ("is", "be", "AUX", "VBZ", "auxpass", 14),
            ("the", "the", "DET", "DT", "det", 13),
            ("full", "full", "ADJ", "JJ", "amod", 13),
            ("Maple", "Maple", "PROPN", "NNP", "compound", 13),
            ("inspection", "inspection", "NOUN", "NN", "nsubjpass", 14),
            ("performed", "perform", "VERB", "VBN", "conj", 6),
        ]
    if other_argument:
        rows += [
            ("with", "with", "ADP", "IN", "prep", 6),
            ("Delta", "Delta", "PROPN", "NNP", "compound", 9),
            ("shutdown", "shutdown", "NOUN", "NN", "pobj", 7),
        ]
    at = len(rows)
    rows += [
        ("and", "and", "CCONJ", "CC", "cc", 14 if second else 6),
        ("what", "what", "PRON", "WP", "nsubj", at + 2),
        ("governs", "govern", "VERB", "VBZ", "conj", 14 if second else 6),
    ]
    # Target head numbers are relative to the target start, -1 means governs.
    start = len(rows)
    rows += [
        (w, lemma, p, t, d, at + 2 if h == -1 else start + h)
        for w, lemma, p, t, d, h in target
    ]
    rows.append(("?", "?", "PUNCT", ".", "punct", 6))
    return unitonly(rows)


IT = [("it", "it", "PRON", "PRP", "dobj", -1)]
ITS_CONDITION = [
    ("its", "its", "PRON", "PRP$", "poss", 2),
    ("entry", "entry", "NOUN", "NN", "compound", 2),
    ("condition", "condition", "NOUN", "NN", "dobj", -1),
]
CEDAR = [
    ("Cedar", "Cedar", "PROPN", "NNP", "compound", 1),
    ("review", "review", "NOUN", "NN", "dobj", -1),
]
DELTA = [
    ("Delta", "Delta", "PROPN", "NNP", "compound", 1),
    ("shutdown", "shutdown", "NOUN", "NN", "dobj", -1),
]
GENERIC = [
    ("an", "an", "DET", "DT", "det", 2),
    ("incomplete", "incomplete", "ADJ", "JJ", "amod", 2),
    ("batch", "batch", "NOUN", "NN", "dobj", -1),
]
QUALIFIED_DELTA = GENERIC + [
    ("for", "for", "ADP", "IN", "prep", 2),
    ("Delta", "Delta", "PROPN", "NNP", "compound", 5),
    ("shutdown", "shutdown", "NOUN", "NN", "pobj", 3),
]
QUALIFIED_CEDAR = GENERIC + [
    ("for", "for", "ADP", "IN", "prep", 2),
    ("Cedar", "Cedar", "PROPN", "NNP", "compound", 5),
    ("review", "review", "NOUN", "NN", "pobj", 3),
]


def plan(cap):
    p = compile_request(cap["annotation"]["raw_text"], cap)
    assert validate_partial_request(p.record(), question=p.question, capture=cap)
    return p


def facet(p):
    return next(n for n in p.nodes if n.kind == "procedure_facet")


def parameters(p, n):
    return json.loads(
        next(
            s.parameters_json
            for s in p.deferred
            if s.node_id == n.id and s.kind == "procedure_facet_reference"
        )
    )


@pytest.mark.parametrize(
    "target",
    [IT, ITS_CONDITION, CEDAR, QUALIFIED_CEDAR],
    ids=["it", "its-condition", "same-subject", "qualified-local"],
)
def test_UNITONLY_local_ownership_requires_actual_unique_reference_or_subject(target):
    p = plan(question(target))
    n = facet(p)
    methods = [m for m in p.nodes if m.grammar == "passive_method_request"]
    assert len(methods) == 1
    assert any(
        e.kind == "procedure_facet"
        and e.source_id == methods[0].id
        and e.target_id == n.id
        for e in p.edges
    )
    assert json.loads(n.feature_json)["facet_target"]
    assert parameters(p, n)["candidate_method_ids"] == [methods[0].id]


@pytest.mark.parametrize(
    "target",
    [DELTA, QUALIFIED_DELTA],
    ids=["foreign-subject", "foreign-qualified-facet"],
)
def test_UNITONLY_foreign_subject_and_full_qualified_target_are_not_overwritten(target):
    cap = question(target)
    p = plan(cap)
    n = facet(p)
    assert any("Delta shutdown" in s.text for s in n.scopes)
    assert not any("Cedar" in s.text for s in n.scopes)
    assert not any(e.kind == "procedure_facet" and e.target_id == n.id for e in p.edges)
    assert parameters(p, n)["candidate_method_ids"] == []
    assert "Delta shutdown" in " ".join(
        s["text"] for s in json.loads(n.feature_json)["facet_target"]
    )
    assert cap == json.loads(p.raw_capture_json)


def test_UNITONLY_generic_facet_is_deferred_with_candidate_not_accepted_lineage():
    p = plan(question(GENERIC))
    n = facet(p)
    method = next(m for m in p.nodes if m.grammar == "passive_method_request")
    assert not any(e.kind == "procedure_facet" for e in p.edges)
    assert parameters(p, n)["candidate_method_ids"] == [method.id]
    assert [s.text for s in n.scopes] == ["an incomplete batch"]
    assert not any("ownership" in u.reason for u in p.unknowns)


def test_UNITONLY_two_methods_leave_pronoun_ownership_deferred_and_distinct():
    p = plan(question(IT, second=True))
    n = facet(p)
    methods = [m for m in p.nodes if m.grammar == "passive_method_request"]
    assert len(methods) == 2
    assert not any(e.kind == "procedure_facet" for e in p.edges)
    assert set(parameters(p, n)["candidate_method_ids"]) == {m.id for m in methods}
    assert any("reference" in u.reason for u in p.unknowns)


def test_UNITONLY_explicit_repeated_subject_selects_only_its_matching_method():
    p = plan(question(CEDAR, second=True))
    n = facet(p)
    local = next(
        m
        for m in p.nodes
        if m.grammar == "passive_method_request"
        and any("Cedar" in s.text for s in m.scopes)
    )
    assert [
        (e.source_id, e.target_id) for e in p.edges if e.kind == "procedure_facet"
    ] == [(local.id, n.id)]
    assert parameters(p, n)["candidate_method_ids"] == [local.id]


def test_retained_unbound_facet_preserves_request_and_needs_source_binding():
    cap = actual("d526-02-procedure")
    p = plan(cap)
    n = facet(p)
    assert "incomplete sibling set" in " ".join(
        s["text"] for s in json.loads(n.feature_json)["facet_target"]
    )
    assert not any(e.kind == "procedure_facet" for e in p.edges)
    assert parameters(p, n)["candidate_method_ids"]
    assert not any("ownership" in u.reason for u in p.unknowns)
    assert cap == json.loads(p.raw_capture_json)


@pytest.mark.parametrize(
    "mutation", ["drop-candidates", "foreign-target", "fabricated-edge"]
)
def test_facet_replay_refuses_changed_deferred_target_candidates_or_lineage(mutation):
    cap = question(GENERIC)
    p = plan(cap)
    n = facet(p)
    record = deepcopy(p.record())
    if mutation == "drop-candidates":
        slot = next(
            s
            for s in record["deferred"]
            if s["node_id"] == n.id and s["kind"] == "procedure_facet_reference"
        )
        values = json.loads(slot["parameters_json"])
        assert values["candidate_method_ids"]
        values["candidate_method_ids"] = []
        slot["parameters_json"] = json.dumps(values)
    elif mutation == "foreign-target":
        record["nodes"][-1]["scopes"] = [{"start": 0, "end": 3, "text": "How"}]
    else:
        record["edges"].append(
            {
                "kind": "procedure_facet",
                "source_id": record["nodes"][0]["id"],
                "target_id": n.id,
                "evidence": [],
            }
        )
    assert not validate_partial_request(record, question=p.question, capture=cap)


@pytest.mark.parametrize("target", [IT, ITS_CONDITION], ids=["it", "its-condition"])
def test_UNITONLY_another_actual_nominal_argument_prevents_unique_pronoun_lineage(
    target,
):
    p = plan(question(target, other_argument=True))
    n = facet(p)
    assert not any(e.kind == "procedure_facet" and e.target_id == n.id for e in p.edges)
    assert parameters(p, n)["candidate_method_ids"]
    assert parameters(p, n)["request_ownership"] == "deferred_subject_relation"


ROWS = UNITONLY_734
OLD = UNITONLY_734


@pytest.mark.parametrize(
    "flag",
    [
        "resolved_request",
        "complete",
        "supported",
        "authorized",
        "publication_allowed",
        "answerable",
    ],
)
def test_no_authority_flag_can_be_added(flag):
    cap = deepcopy(LABELS)
    p = plan(cap)
    record = p.record()
    record[flag] = True
    assert not validate_partial_request(record, question=p.question, capture=cap)
    assert flag not in p.record()


@pytest.mark.parametrize(
    "cap,operation",
    [(LABELS, "labels_only"), (INCUMBENTS, "incumbents")],
    ids=["labels", "incumbents"],
)
def test_catalogue_has_no_fixed_role_count_or_actor_values(cap, operation):
    p = plan(cap)
    catalogues = [n for n in p.nodes if n.kind == "role_catalogue"]
    assert len(catalogues) == 1 and catalogues[0].operation == operation
    assert not any(n.kind in {"owner", "deputy", "role_assignment"} for n in p.nodes)
    assert {s.kind for s in p.deferred} == {
        "literal_subject_boundary",
        "role_catalogue",
    }


@pytest.mark.parametrize(
    "cap", [EXTRA_ACTION, EXTERNAL], ids=["unknown-action", "external-target"]
)
def test_unknown_relations_remain_hard_not_generic_deferred(cap):
    p = plan(cap)
    assert p.unknowns
    assert not any(
        s.kind in {"unknown_relation", "external_target_resolution"} for s in p.deferred
    )


def test_actual_capture_and_detached_record_are_immutable():
    cap = actual("679-condition-modal")
    before = deepcopy(cap)
    p = plan(cap)
    record = p.record()
    record["nodes"].clear()
    record["tokens"][0]["token"]["text"] = "changed"
    assert cap == before and json.loads(p.raw_capture_json) == cap
    with pytest.raises(FrozenInstanceError):
        p.question = "changed"
    assert not validate_partial_request(record, question=p.question, capture=cap)
    assert p.record()["nodes"] and p.record()["tokens"][0]["token"]["text"] != "changed"
    assert {"may", "not"} <= {
        s["text"] for s in json.loads(p.features_json)["modality"]
    }


@pytest.mark.parametrize(
    "field",
    [
        "deferred",
        "edges",
        "tokens",
        "raw_capture_json",
        "capture_sha256",
        "frame_proposals_json",
    ],
)
def test_exact_recompilation_rejects_deleted_obligations(field):
    cap = deepcopy(DEPENDENT)
    p = plan(cap)
    record = p.record()
    assert record[field]
    record[field] = [] if isinstance(record[field], list) else "changed"
    assert not validate_partial_request(record, question=p.question, capture=cap)


def test_scalar_value_dependency_stays_separate_from_catalogue_members():
    p = plan(actual("e628-explicit-data-reference"))
    assert any(e.kind == "value_dependency" for e in p.edges)
    group = plan(DEPENDENT)
    assert any(e.kind == "catalogue_member_value" for e in group.edges)
    labels = plan(LABELS)
    assert not any(e.kind == "catalogue_member_value" for e in labels.edges)


def test_foreign_governance_subject_is_not_retargeted_to_single_method():
    cap = unitonly(
        [
            ("How", "how", "SCONJ", "WRB", "advmod", 6),
            ("is", "be", "AUX", "VBZ", "auxpass", 6),
            ("the", "the", "DET", "DT", "det", 5),
            ("full", "full", "ADJ", "JJ", "amod", 5),
            ("Cedar", "Cedar", "PROPN", "NNP", "compound", 5),
            ("review", "review", "NOUN", "NN", "nsubjpass", 6),
            ("performed", "perform", "VERB", "VBN", "ROOT", 6),
            ("and", "and", "CCONJ", "CC", "cc", 6),
            ("what", "what", "PRON", "WP", "nsubj", 9),
            ("governs", "govern", "VERB", "VBZ", "conj", 6),
            ("Delta", "Delta", "PROPN", "NNP", "compound", 11),
            ("shutdown", "shutdown", "NOUN", "NN", "dobj", 9),
            ("?", "?", "PUNCT", ".", "punct", 6),
        ]
    )
    p = plan(cap)
    assert p.unknowns or not any(e.kind == "procedure_facet" for e in p.edges), (
        "Foreign explicit Delta shutdown must not become a Cedar procedure facet"
    )


@pytest.mark.parametrize("row", ROWS, ids=lambda row: row["summary"]["name"])
def test_ownership_requires_whole_argument_closure(row):
    p = plan(row["capture"])
    n = facet(p)
    assert not any(
        e.kind == "procedure_facet" and e.target_id == n.id for e in p.edges
    ), (
        "An unclosed/foreign qualifier or coordinated independent target "
        "cannot certify local method ownership"
    )


@pytest.mark.parametrize(
    "target", [IT, CEDAR], ids=["unique-pronoun", "literal-subject"]
)
def test_closed_unique_reference_or_exact_literal_still_proposes_edge(target):
    p = plan(question(target))
    n = facet(p)
    assert any(e.kind == "procedure_facet" and e.target_id == n.id for e in p.edges)
    assert parameters(p, n)["candidate_method_ids"]


@pytest.mark.parametrize(
    "mutation",
    [
        "node-candidate",
        "slot-candidate",
        "node-target",
        "slot-target",
        "ownership",
        "fabricated-authority",
    ],
)
def test_recompilation_rejects_ownership_and_target_mutations(mutation):
    cap = question(GENERIC)
    p = plan(cap)
    n = facet(p)
    record = deepcopy(p.record())
    node = next(item for item in record["nodes"] if item["id"] == n.id)
    slot = next(
        item
        for item in record["deferred"]
        if item["node_id"] == n.id and item["kind"] == "procedure_facet_reference"
    )
    if mutation == "fabricated-authority":
        record["publication_allowed"] = True
    else:
        holder = (
            node if mutation.startswith("node") or mutation == "ownership" else slot
        )
        key = "feature_json" if holder is node else "parameters_json"
        values = json.loads(holder[key])
        if mutation.endswith("candidate"):
            values["candidate_method_ids"] = ["nonexistent-method"]
        elif mutation.endswith("target"):
            values["facet_target"] = [{"start": 0, "end": 3, "text": "How"}]
        else:
            values["request_ownership"] = "explicit_same_subject"
        holder[key] = json.dumps(values)
    assert not validate_partial_request(record, question=p.question, capture=cap)


def test_unbound_generic_is_typed_with_candidates_without_accepted_edge():
    p = plan(question(GENERIC))
    n = facet(p)
    data = parameters(p, n)
    assert (
        data["request_ownership"] == "deferred_subject_relation"
        and data["candidate_method_ids"]
    )
    assert not any(e.kind == "procedure_facet" for e in p.edges)
    assert [scope.text for scope in n.scopes] == ["an incomplete batch"]


def test_two_surviving_methods_do_not_resolve_ambiguous_pronoun():
    p = plan(question(IT, second=True))
    n = facet(p)
    assert len(parameters(p, n)["candidate_method_ids"]) == 2
    assert not any(e.kind == "procedure_facet" for e in p.edges)
    assert any("reference" in unknown.reason for unknown in p.unknowns)


def method_qualified(
    preposition="for", *, both=False, operative=False, condition=False
):
    rows = [
        ("How", "how", "SCONJ", "WRB", "advmod", 9),
        ("is", "be", "AUX", "VBZ", "auxpass", 9),
        ("the", "the", "DET", "DT", "det", 5),
        ("full", "full", "ADJ", "JJ", "amod", 5),
        ("Cedar", "Cedar", "PROPN", "NNP", "compound", 5),
        ("review", "review", "NOUN", "NN", "nsubjpass", 9),
        (preposition, preposition, "ADP", "IN", "prep", 5),
        ("Delta", "Delta", "PROPN", "NNP", "compound", 8),
        ("shutdown", "shutdown", "NOUN", "NN", "pobj", 6),
        ("performed", "perform", "VERB", "VBN", "ROOT", 9),
        ("and", "and", "CCONJ", "CC", "cc", 9),
        ("what", "what", "PRON", "WP", "nsubj", 12),
        ("governs", "govern", "VERB", "VBZ", "conj", 9),
        ("Cedar", "Cedar", "PROPN", "NNP", "compound", 14),
        ("review", "review", "NOUN", "NN", "dobj", 12),
    ]
    if both:
        rows += [
            (preposition, preposition, "ADP", "IN", "prep", 14),
            ("Delta", "Delta", "PROPN", "NNP", "compound", 17),
            ("shutdown", "shutdown", "NOUN", "NN", "pobj", 15),
        ]
    if operative:
        # Additional attached relative clause, not a literal activity-name proposal.
        start = len(rows)
        rows += [
            ("that", "that", "PRON", "WDT", "nsubj", start + 1),
            ("omits", "omit", "VERB", "VBZ", "relcl", 5),
            ("records", "record", "NOUN", "NNS", "dobj", start + 1),
        ]
    if condition:
        start = len(rows)
        rows += [
            ("if", "if", "SCONJ", "IN", "mark", start + 4),
            ("the", "the", "DET", "DT", "det", start + 2),
            ("supervisor", "supervisor", "NOUN", "NN", "nsubj", start + 4),
            ("must", "must", "AUX", "MD", "aux", start + 4),
            ("sign", "sign", "VERB", "VB", "advcl", 5),
        ]
    rows.append(("?", "?", "PUNCT", ".", "punct", 9))
    return unitonly(rows)


@pytest.mark.parametrize("prep", ["for", "near", "behind", "alongside"])
def test_full_qualified_method_cannot_equal_unqualified_facet(prep):
    p = plan(method_qualified(prep))
    m = next(n for n in p.nodes if n.grammar == "passive_method_request")
    n = facet(p)
    assert any(prep + " Delta shutdown" in s.text for s in m.scopes)
    assert not any(e.kind == "procedure_facet" and e.target_id == n.id for e in p.edges)
    closure = json.loads(m.feature_json)["argument_closure"]
    assert any(
        c["kind"] == "prepositional_qualifier" and c["preposition"]["text"] == prep
        for c in closure["components"]
    )


@pytest.mark.parametrize("prep", ["for", "near", "behind", "alongside"])
def test_identical_fully_closed_qualified_arguments_can_match(prep):
    p = plan(method_qualified(prep, both=True))
    n = facet(p)
    assert any(e.kind == "procedure_facet" and e.target_id == n.id for e in p.edges)
    assert any(prep + " Delta shutdown" in s.text for s in n.scopes)
    assert not json.loads(n.feature_json)["argument_closure"]["unclassified"]


@pytest.mark.parametrize("row", OLD, ids=lambda r: r["summary"]["name"])
def test_original734_full_argument_inventory_is_independent_of_raw_capture(row):
    p = plan(row["capture"])
    n = facet(p)
    fields = json.loads(n.feature_json)
    closure = fields["argument_closure"]
    assert closure["token_indices"]
    assert (
        sorted({i for c in closure["components"] for i in c["token_indices"]})
        == closure["token_indices"]
    )
    assert not any(e.kind == "procedure_facet" and e.target_id == n.id for e in p.edges)
    if row["summary"]["name"] == "nested_foreign_qualifier":
        assert any("near Delta shutdown" in s.text for s in n.scopes)
    if row["summary"]["name"] == "coordinated_foreign_object":
        assert any(c["kind"] == "nominal_conjunction" for c in closure["components"])


def test_operative_relative_clause_is_not_swallowed_as_a_literal_name():
    p = plan(method_qualified(operative=True))
    m = next(n for n in p.nodes if n.grammar == "passive_method_request")
    closure = json.loads(m.feature_json)["argument_closure"]
    assert closure["unclassified"]
    assert any("incomplete_argument" in u.reason for u in p.unknowns)
    assert not any(
        s.node_id == m.id and s.kind == "literal_subject_boundary" for s in p.deferred
    )
    assert not any(e.kind == "procedure_facet" for e in p.edges)
    assert any("omits" in x["text"] for x in closure["evidence"])


def test_known_condition_and_modality_remain_typed_separate_from_literal_name():
    p = plan(method_qualified(condition=True))
    m = next(n for n in p.nodes if n.grammar == "passive_method_request")
    closure = json.loads(m.feature_json)["argument_closure"]
    conditions = [c for c in closure["components"] if c["kind"] == "condition_clause"]
    assert conditions
    assert "must" in json.dumps(conditions)
    assert not any(
        s.node_id == m.id and s.kind == "literal_subject_boundary" for s in p.deferred
    )
    assert not any(e.kind == "procedure_facet" for e in p.edges)


@pytest.mark.parametrize(
    "mutation",
    ["method-scope", "component", "unclassified", "facet-key", "candidate-closure"],
)
def test_full_argument_closure_is_independently_reconstructed(mutation):
    cap = method_qualified(both=True)
    p = plan(cap)
    r = deepcopy(p.record())
    m = r["nodes"][0]
    n = next(x for x in r["nodes"] if x["kind"] == "procedure_facet")
    if mutation == "method-scope":
        m["scopes"] = []
    else:
        obj = m if mutation in {"component", "unclassified"} else n
        f = json.loads(obj["feature_json"])
        if mutation == "component":
            f["argument_closure"]["components"] = []
        elif mutation == "unclassified":
            f["argument_closure"]["unclassified"] = ["forged"]
        elif mutation == "facet-key":
            f["argument_closure"]["comparison_key"] = []
        else:
            f["candidate_argument_closures"] = []
        obj["feature_json"] = json.dumps(f)
    assert not validate_partial_request(r, question=p.question, capture=cap)


def inserted(cap, index, new_rows):
    old = cap["annotation"]["tokens"]
    shift = len(new_rows)
    rows = []
    for t in old:
        if t["i"] == index:
            rows.extend(new_rows)
        rows.append(
            (
                t["text"],
                t["lemma"],
                t["pos"],
                t["tag"],
                t["dep"],
                t["head"] + shift if t["head"] >= index else t["head"],
            )
        )
    return unitonly(rows)


def test_operative_method_complement_is_an_explicit_incomplete_obligation():
    cap = method_qualified(both=True)
    rows = [
        (t["text"], t["lemma"], t["pos"], t["tag"], t["dep"], t["head"])
        for t in cap["annotation"]["tokens"][:-1]
    ]
    at = len(rows)
    rows += [
        ("omit", "omit", "VERB", "VB", "ccomp", 9),
        ("records", "record", "NOUN", "NNS", "dobj", at),
        ("?", "?", "PUNCT", ".", "punct", 9),
    ]
    p = plan(unitonly(rows))
    m = next(n for n in p.nodes if n.grammar == "passive_method_request")
    assert any("incomplete_argument" in u.reason for u in p.unknowns)
    assert not any(e.kind == "procedure_facet" for e in p.edges)
    assert not any(
        s.kind == "literal_subject_boundary" and s.node_id == m.id for s in p.deferred
    )


def test_qualified_extent_is_not_misread_as_plain_start_to_finish():
    cap = inserted(
        question(CEDAR),
        7,
        [
            ("from", "from", "ADP", "IN", "prep", 6),
            ("start", "start", "NOUN", "NN", "pobj", 7),
            ("near", "near", "ADP", "IN", "prep", 8),
            ("Delta", "Delta", "PROPN", "NNP", "compound", 11),
            ("shutdown", "shutdown", "NOUN", "NN", "pobj", 9),
            ("to", "to", "ADP", "IN", "prep", 6),
            ("finish", "finish", "NOUN", "NN", "pobj", 12),
        ],
    )
    p = plan(cap)
    m = next(n for n in p.nodes if n.grammar == "passive_method_request")
    fields = json.loads(m.feature_json)
    assert not any(e.kind == "procedure_facet" for e in p.edges)
    assert fields["ownership_context_pending"]
    assert any(c.get("argument_closures") for c in fields["method_qualifiers"])
    assert any(
        "near Delta shutdown" in json.dumps(c) for c in fields["method_qualifiers"]
    )


def test_method_modality_is_typed_and_pending_instead_of_skipped_as_auxiliary():
    cap = question(CEDAR)
    rows = [
        (t["text"], t["lemma"], t["pos"], t["tag"], t["dep"], t["head"])
        for t in cap["annotation"]["tokens"]
    ]
    rows[1] = ("must", "must", "AUX", "MD", "aux", 6)
    cap = inserted(unitonly(rows), 6, [("be", "be", "AUX", "VB", "auxpass", 7)])
    p = plan(cap)
    m = next(n for n in p.nodes if n.grammar == "passive_method_request")
    fields = json.loads(m.feature_json)
    assert [x["text"] for x in fields["modality"]] == ["must"]
    assert any(c["kind"] == "method_modality" for c in fields["method_qualifiers"])
    assert fields["ownership_context_pending"]
    assert not any(e.kind == "procedure_facet" for e in p.edges)


@pytest.mark.parametrize("prep", ["without", "before"])
def test_conditional_pp_is_a_typed_constraint_never_a_literal_name_slot(prep):
    p = plan(method_qualified(prep, both=True))
    m = next(n for n in p.nodes if n.grammar == "passive_method_request")
    fields = json.loads(m.feature_json)
    assert any(c.get("conditional") for c in fields["argument_closure"]["components"])
    assert not any(
        s.node_id == m.id and s.kind == "literal_subject_boundary" for s in p.deferred
    )
    assert any(
        s.node_id == m.id and s.kind == "verify_request_constraint" for s in p.deferred
    )


@pytest.mark.parametrize("prep", ["without", "before"])
def test_condition_obligation_keeps_the_entire_qualified_argument(prep):
    p = plan(method_qualified(prep, both=True))
    m = next(n for n in p.nodes if n.grammar == "passive_method_request")
    slots = [
        s
        for s in p.deferred
        if s.node_id == m.id and s.kind == "verify_request_constraint"
    ]
    assert any(
        prep + " Delta shutdown" in span.text for s in slots for span in s.evidence
    )


# Explicit UNITONLY retained744 contrasts; not parser observations.
CASES = UNITONLY_744


@pytest.mark.parametrize("row", CASES, ids=lambda row: row["summary"]["name"])
def test_nested_scope_quantifier_is_not_whole_request_extent(row):
    p = plan(row["capture"])
    n = facet(p)
    assert not any(
        e.kind == "procedure_facet" and e.target_id == n.id for e in p.edges
    ), (
        "Nested quantified scope differs from the unquantified facet scope; "
        "root extent normalization cannot erase it"
    )


@pytest.mark.parametrize("row", CASES, ids=lambda row: row["summary"]["name"])
def test_nested_qualifier_bytes_and_typed_components_remain_retained(row):
    p = plan(row["capture"])
    m = next(n for n in p.nodes if n.grammar == "passive_method_request")
    closure = json.loads(m.feature_json)["argument_closure"]
    assert row["summary"]["name"].split("-")[1] in " ".join(s.text for s in m.scopes)
    assert (
        sorted(
            {
                i
                for component in closure["components"]
                for i in component["token_indices"]
            }
        )
        == closure["token_indices"]
    )
    assert json.loads(p.raw_capture_json) == row["capture"]


def test_root_whole_extent_and_identical_qualified_arguments_are_distinct_controls():
    p = plan(method_qualified("for", both=True))
    n = facet(p)
    assert any(e.kind == "procedure_facet" and e.target_id == n.id for e in p.edges)


def test_nested_numeric_qualifier_does_not_match_shortened_argument():
    cap = inserted(
        method_qualified("for", both=True),
        7,
        [("three", "three", "NUM", "CD", "nummod", 9)],
    )
    p = plan(cap)
    assert not any(e.kind == "procedure_facet" for e in p.edges)


def test_attached_operative_predicate_remains_hard():
    p = plan(method_qualified("for", operative=True))
    assert any("incomplete_argument" in unknown.reason for unknown in p.unknowns)
    assert not any(e.kind == "procedure_facet" for e in p.edges)


@pytest.mark.parametrize(
    "field", ["comparison_key", "components", "token_indices", "argument_indices"]
)
def test_exact_recompilation_rejects_edited_closure(field):
    cap = method_qualified("for", both=True)
    p = plan(cap)
    record = deepcopy(p.record())
    node = next(n for n in record["nodes"] if n["kind"] == "procedure")
    data = json.loads(node["feature_json"])
    data["argument_closure"][field] = []
    node["feature_json"] = json.dumps(data)
    assert not validate_partial_request(record, question=p.question, capture=cap)


def test_inert_contract_rejects_authority_and_extra_source_facts():
    cap = method_qualified("for", both=True)
    p = plan(cap)
    for key, value in [
        ("publication_allowed", True),
        ("supported", True),
        ("source_facts", {"membership": True}),
    ]:
        record = p.record()
        record[key] = value
        assert not validate_partial_request(record, question=p.question, capture=cap)


@pytest.mark.parametrize(
    "word", ["full", "whole", "complete", "entire", "ordered", "all", "every"]
)
def test_owning_top_level_request_extent_normalization_is_preserved(word):
    cap = method_qualified("for", both=True)
    tokens = cap["annotation"]["tokens"]
    remove = 2 if word in {"all", "every"} else None
    rows = []

    def index(i):
        return i - (remove is not None and i > remove)

    for token in tokens:
        if token["i"] == remove:
            continue
        text, lemma, pos, tag, dep, head = (
            token[k] for k in ("text", "lemma", "pos", "tag", "dep", "head")
        )
        if token["i"] == 3:
            text = lemma = word
            if word in {"all", "every"}:
                pos, tag, dep = "DET", "DT", "det"
        rows.append((text, lemma, pos, tag, dep, index(head)))
    p = plan(unitonly(rows))
    n = facet(p)
    assert any(e.kind == "procedure_facet" and e.target_id == n.id for e in p.edges)
    method = next(node for node in p.nodes if node.grammar == "passive_method_request")
    assert word in " ".join(scope.text for scope in method.scopes)


@pytest.mark.parametrize("word", ["all", "every", "complete"])
def test_identical_nested_qualifiers_remain_literal_and_can_match(word):
    cap = method_qualified("for", both=True)
    # Two independent inserts: nested facet first, then method, preserving heads.
    cap = inserted(
        cap,
        16,
        [
            (
                word,
                word,
                "DET" if word != "complete" else "ADJ",
                "DT" if word != "complete" else "JJ",
                "det" if word != "complete" else "amod",
                18,
            )
        ],
    )
    cap = inserted(
        cap,
        7,
        [
            (
                word,
                word,
                "DET" if word != "complete" else "ADJ",
                "DT" if word != "complete" else "JJ",
                "det" if word != "complete" else "amod",
                9,
            )
        ],
    )
    p = plan(cap)
    n = facet(p)
    assert any(e.kind == "procedure_facet" and e.target_id == n.id for e in p.edges)
    for node in (
        next(node for node in p.nodes if node.grammar == "passive_method_request"),
        n,
    ):
        key = json.loads(node.feature_json)["argument_closure"]["comparison_key"]
        assert any(part[0] == word for part in key)


def test_different_nested_quantifiers_do_not_alias():
    cap = method_qualified("for", both=True)
    cap = inserted(cap, 16, [("all", "all", "DET", "DT", "det", 18)])
    cap = inserted(cap, 7, [("every", "every", "DET", "DT", "det", 9)])
    p = plan(cap)
    assert not any(e.kind == "procedure_facet" for e in p.edges)
