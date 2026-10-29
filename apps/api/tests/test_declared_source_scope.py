"""Whole-source scope is a candidate cover, never factual/NLI acceptance."""

import importlib
import importlib.util
import json
from copy import deepcopy
from hashlib import sha256

import pytest


def api():
    # Missing behavior fails in the test body, not during test collection/import.
    name = "app.services.declared_source_scope"
    assert importlib.util.find_spec(name) is not None, (
        "A reconstructable whole-body declared source cover is not implemented"
    )
    return importlib.import_module(name)


def identity(body, **changes):
    return {
        "document_id": "source-example",
        "document_version": 2,
        "workspace_id": "example-workspace",
        "content_hash": sha256(body.encode("utf-8")).hexdigest(),
        **changes,
    }


def cover(body):
    return api().source_cover(body, identity(body))


def status(body, subject="Cobalt ledger", activity=None):
    return api().scope_relevance(cover(body), subject, activity=activity)["status"]


def test_whole_body_cover_retains_every_character_and_raw_identity():
    body = "  Amber review: operation note.\n\nInspect the card; retain it.  \n"
    value = cover(body)
    assert value["contract"] == "declared-source-scope-cover-v1"
    assert value["identity"] == identity(body)
    assert value["body_length"] == len(body)
    assert value["body_sha256"] == sha256(body.encode("utf-8")).hexdigest()
    assert "".join(unit["text"] for unit in value["units"]) == body
    cursor = 0
    for unit in value["units"]:
        assert unit["start"] == cursor
        assert body[unit["start"] : unit["end"]] == unit["text"]
        cursor = unit["end"]
    assert cursor == len(body)


@pytest.mark.parametrize(
    "body",
    [
        "Amber review: operation note.\nInspect the card. Retain the card.",
        "# Amber review\nInspect the card. Retain the card.",
        "This note applies to Amber review. Inspect the card.",
        "The following routine applies to Amber review sessions. Inspect the card.",
    ],
)
def test_declared_local_context_can_exclude_a_distinct_subject(body):
    assert status(body) == "irrelevant"
    found = api().scope_relevance(
        cover(body), "Amber review session", activity="Amber review"
    )
    assert found["status"] == "relevant"
    assert found["evidence"]
    assert all(item["text"] in body for item in found["evidence"])


@pytest.mark.parametrize(
    "body",
    [
        "The record steward leads Amber review.",
        "Amber review is led by the record steward.",
        "The Amber review activity lead is the record steward.",
        "The Amber review deputy is the puzzle host.",
        "For Amber review sessions, the lead is the duty supervisor.",
        "For evening Amber review sessions, the visitor host "
        "replaces the record steward as lead.",
    ],
)
def test_explicit_role_declarations_are_scoped_without_certifying_assignment(body):
    value = cover(body)
    assert status(body) == "irrelevant"
    assert (
        api().scope_relevance(value, "Amber review", activity="Amber review")["status"]
        == "relevant"
    )
    assert any(unit["kind"] == "role" for unit in value["units"])
    assert "nli" not in json.dumps(value).lower()


def test_subject_and_activity_query_union_retains_qualified_session_assignment():
    body = "The evening Amber review session is led by the visitor host."
    result = api().scope_relevance(
        cover(body), "evening Amber review session", activity="Amber review"
    )
    assert result["status"] == "relevant"
    assert any(
        "evening Amber review session" in item["text"] for item in result["evidence"]
    )


def test_role_anaphora_inherits_only_an_unambiguous_same_paragraph_subject():
    body = (
        "The Amber review activity lead is the record steward; "
        "its deputy is the puzzle host."
    )
    value = cover(body)
    deputy = next(unit for unit in value["units"] if "its deputy" in unit["text"])
    assert deputy["disposition"] == "local"
    assert deputy["subjects"] == ["Amber review"]
    assert deputy["scope_evidence"][0]["text"] == "Amber review"
    assert status(body) == "irrelevant"
    assert status("Its deputy is the puzzle host.") == "unknown"
    assert (
        status(
            "The Amber review lead is the steward.\n\nIts deputy is the puzzle host."
        )
        == "unknown"
    )


@pytest.mark.parametrize(
    "body",
    [
        "Each session requires a separate nomination.",
        "Follow the qualification appendix.",
        "Consult the current handbook.",
        "See the attached schedule.",
        "A separate appointment governs every session.",
        "The central steward leads all sessions.",
    ],
)
def test_global_or_unknown_governance_is_always_a_candidate(body):
    assert status(body) in {"relevant", "unknown"}
    assert status("Amber review: operation note.\n" + body) in {"relevant", "unknown"}


def test_unknown_prefix_suffix_and_middle_are_not_dropped_by_local_heading():
    for body in (
        "Obey the unclassified instruction.\n"
        "Amber review: operation note.\nInspect the card.",
        "Amber review: operation note.\nInspect the card. Opaque governing tail.",
        "Amber review: operation note.\nOpaque prose. Inspect the card.",
    ):
        assert status(body) == "unknown"
        assert any(unit["disposition"] == "unknown" for unit in cover(body)["units"])


def test_multiple_scopes_are_retained_and_no_single_document_allowlist_is_used():
    body = "The steward leads Amber review. The puzzle host leads Cobalt ledger."
    assert status(body, "Amber review") == "relevant"
    assert status(body, "Cobalt ledger") == "relevant"
    assert status(body, "Violet inspection") == "irrelevant"


def test_unresolved_reference_is_not_hidden_by_explicit_or_inherited_local_scope():
    body = (
        "Amber review: operation note.\n"
        "For Amber review, follow the qualification appendix."
    )
    assert status(body) == "unknown"


def test_ambiguous_subjects_and_conditional_governance_do_not_become_local_absence():
    assert status("The steward leads Amber review and Cobalt ledger.") == "unknown"
    assert (
        status("For Amber review unless separately appointed, the lead is the steward.")
        == "unknown"
    )


def test_exact_evidence_ranges_retain_unicode_whitespace_and_no_normalized_body():
    body = "# Étude—queue\n\tInspect the café card.\r\nUnclassified Ω."
    value = cover(body)
    assert "".join(u["text"] for u in value["units"]) == body
    assert api().validate_source_cover(value, body, identity(body)) is True
    assert (
        api().validate_source_cover(value, body.replace("\r\n", "\n"), identity(body))
        is False
    )


@pytest.mark.parametrize("version", [True, False, 0, -1, 1.5, "2", [], {}])
def test_identity_versions_reject_bool_float_and_containers(version):
    body = "# Amber review\nInspect the card."
    with pytest.raises(ValueError):
        api().source_cover(body, identity(body, document_version=version))


def test_wrong_body_hash_or_missing_document_identity_is_rejected():
    body = "The steward leads Amber review."
    with pytest.raises(ValueError):
        api().source_cover(body, identity(body, content_hash="0" * 64))
    with pytest.raises(ValueError):
        api().source_cover(body, {"document_version": 2})


@pytest.mark.parametrize(
    "mutation", ["text", "offset", "scope", "pruned", "contract", "identity", "extra"]
)
def test_tampering_cannot_certify_irrelevance(mutation):
    body = "# Amber review\nInspect the card. Consult the current handbook."
    original = cover(body)
    value = deepcopy(original)
    if mutation == "text":
        value["units"][-1]["text"] = "Inspect the card."
    elif mutation == "offset":
        value["units"][0]["start"] = False
    elif mutation == "scope":
        value["units"][-1]["disposition"] = "local"
        value["units"][-1]["subjects"] = ["Amber review"]
    elif mutation == "pruned":
        value["units"].pop()
    elif mutation == "contract":
        value["contract"] = "declared-source-scope-cover-v999"
    elif mutation == "identity":
        value["identity"]["document_version"] = True
    else:
        value["complete"] = True
    assert api().validate_source_cover(value, body, identity(body)) is False
    assert api().scope_relevance(value, "Cobalt ledger")["status"] == "unknown"


def test_self_consistent_replacement_still_needs_authoritative_snapshot_validation():
    body = "Consult the current handbook."
    replacement = "# Amber review\nInspect the card."
    forged = api().source_cover(replacement, identity(replacement))
    assert api().validate_source_cover(forged, body, identity(body)) is False


def test_stable_json_roundtrip_reconstructs_and_binds_document_version():
    body = "# Amber review\nInspect the card."
    value = cover(body)
    encoded = api().serialize_source_cover(value)
    assert encoded == api().serialize_source_cover(json.loads(encoded))
    assert (
        api().validate_source_cover(json.loads(encoded), body, identity(body)) is True
    )
    assert (
        api().validate_source_cover(value, body, identity(body, document_version=3))
        is False
    )
    assert (
        api().validate_source_cover(
            value, body, identity(body, document_id="another-source")
        )
        is False
    )


@pytest.mark.parametrize("body", ["", " ", "\n\r\n\t"])
def test_empty_or_whitespace_publication_cannot_prove_absence(body):
    assert status(body) == "unknown"


def test_unknown_or_malformed_cover_and_query_fail_closed_without_throwing():
    for malformed in (None, [], {}, {"contract": "future"}):
        assert api().scope_relevance(malformed, "Amber review")["status"] == "unknown"
    assert (
        api().scope_relevance(cover("# Amber review\nInspect the card."), "")["status"]
        == "unknown"
    )


@pytest.mark.parametrize("numeric", [False, 0.0])
def test_nested_scope_evidence_numeric_types_are_not_equal_copies(numeric):
    body = "Amber review is led by the steward."
    value = cover(body)
    assert value["units"][0]["scope_evidence"][0]["start"] == 0
    value["units"][0]["scope_evidence"][0]["start"] = numeric
    assert api().validate_source_cover(value, body, identity(body)) is False
    assert api().scope_relevance(value, "Cobalt ledger")["status"] == "unknown"


def test_local_instruction_prefix_cannot_swallow_a_foreign_governing_clause():
    body = (
        "# Amber review\nInspect the card and "
        "the Cobalt ledger deputy is the coordinator."
    )
    assert status(body) == "unknown"


def test_unparsed_role_qualifiers_remain_unknown_even_in_fronted_scope():
    body = "For Amber review, the lead is the steward who must approve appointments."
    # A reference-bearing suffix must not disappear behind the initial role.
    assert status(body) == "unknown"
    body = "For Amber review, the lead is the steward who must approve records."
    assert status(body) == "unknown"


def test_fronted_scope_can_bind_an_explicit_actor_with_an_omitted_leads_object():
    body = "For Copper Meadow short-mat sessions, the straight-line tutor leads."
    assert status(body) == "irrelevant"
    assert status(body, "Copper Meadow short-mat session") == "relevant"


@pytest.mark.parametrize(
    "body",
    [
        "The Violet board draft capacity is 12 counters. "
        "This is a tentative planning item, not a current limit.",
        "This is an invented teaching fixture, not real professional guidance. "
        "The Violet board contains 12 counters.",
        "For a violet discrepancy flag in Violet board, "
        "retain the card in the marked tray and leave the record open.",
        "For a violet discrepancy flag in Violet board, "
        "discard the card immediately and close the record.",
    ],
)
def test_finite_metadata_scalar_declaratives_and_scoped_instruction_lists(body):
    assert status(body, "Cobalt ledger") == "irrelevant"
    assert status(body, "Violet board") == "relevant"


def test_metadata_grammar_does_not_consume_governing_or_unknown_tails():
    body = (
        "This is an invented teaching fixture, not real professional guidance. "
        "Consult the current handbook."
    )
    assert status(body) == "unknown"
    assert (
        status("This is an invented teaching fixture which appoints all deputies.")
        != "irrelevant"
    )
    assert (
        status("The Violet board capacity is 12 counters if separately approved.")
        == "unknown"
    )


def test_instruction_list_only_accepts_complete_physical_clauses():
    assert (
        status("# Violet board\nInspect the card and confer authority on the deputy.")
        == "unknown"
    )
    assert status("# Violet board\nInspect the card confers authority.") == "unknown"
    assert (
        status(
            "# Violet board\nInspect the card and "
            "the Cobalt ledger is led by the coordinator."
        )
        == "unknown"
    )


@pytest.mark.parametrize(
    ("body", "actor", "target", "role"),
    [
        ("The steward leads Amber review.", "The steward", "Amber review", "owner"),
        ("Amber review is led by the steward.", "the steward", "Amber review", "owner"),
        (
            "The Amber review activity lead is the steward.",
            "the steward",
            "Amber review",
            "owner",
        ),
        ("The Amber review deputy is the host.", "the host", "Amber review", "deputy"),
        (
            "For Amber review, the lead is the steward.",
            "the steward",
            "Amber review",
            "owner",
        ),
        (
            "For Amber review, the new host replaces the steward as lead.",
            "the new host",
            "Amber review",
            "owner",
        ),
    ],
)
def test_role_declarations_expose_exact_actor_target_relation_evidence(
    body, actor, target, role
):
    value = cover(body)
    assignment = next(c for u in value["units"] for c in u.get("role_declarations", []))
    assert assignment["kind"] == role
    assert assignment["actor"]["text"] == actor
    assert assignment["target"]["text"] == target
    for key in ("actor", "target", "relation"):
        evidence = assignment[key]
        assert body[evidence["start"] : evidence["end"]] == evidence["text"]
    assert "support" not in assignment


def test_anaphoric_role_target_points_back_to_its_actual_antecedent_range():
    body = "The Amber review lead is the steward; its deputy is the host."
    declaration = cover(body)["units"][-1]["role_declarations"][0]
    assert declaration["kind"] == "deputy"
    assert declaration["target"] == {"start": 4, "end": 16, "text": "Amber review"}
    assert declaration["actor"]["text"] == "the host"


def test_scalar_prefix_cannot_swallow_an_unclassified_governing_tail():
    body = (
        "The Violet board capacity is 12 counters and "
        "the Cobalt ledger authority changes."
    )
    assert status(body) == "unknown"


def test_fronted_context_does_not_erase_a_second_explicit_role_target():
    body = "For Amber review, the host leads Cobalt ledger."
    assert status(body, "Cobalt ledger") == "relevant"
    assert status(body, "Amber review") == "relevant"
    declaration = cover(body)["units"][0]["role_declarations"][0]
    assert declaration["target"]["text"] == "Cobalt ledger"


@pytest.mark.parametrize(
    "body",
    [
        "The systemwide approval threshold is 2 signatures.",
        "# Amber review\nThe global approval requirement is 2 signatures.",
        "The globally binding approval threshold is 2 signatures.",
        "The mandatory acceptance threshold is 3 authorizations.",
        "The minimum approval count is 2 signatures.",
        "# Amber review\nThe applicable permission capacity is 4 approvals.",
        "The organisation-wide capacity is 12 participants.",
        "The company wide Violet board capacity is 12 counters.",
    ],
)
def test_governing_numeric_declaratives_do_not_prove_a_disjoint_activity(body):
    assert status(body) in {"relevant", "unknown"}
    assert api().validate_source_cover(cover(body), body, identity(body)) is True


@pytest.mark.parametrize(
    "command",
    [
        "Read the manual.",
        "Use the policy.",
        "Read the charter.",
        "Read the statute.",
        "Use the regulation.",
        "Read the revised ordinance.",
        "Inspect the binding protocol.",
        "Inspect the binding record.",
        "Open the required card.",
        "Copy the instruction card.",
        "Read the card.",
        "Use it.",
    ],
)
@pytest.mark.parametrize("preface", ["# Amber review\n", "For Amber review, "])
def test_informational_or_unresolved_operands_are_not_local_physical_absence(
    command, preface
):
    assert status(preface + command) in {"relevant", "unknown"}


@pytest.mark.parametrize(
    "body",
    [
        "# Amber review\nMove the card to the marked tray.",
        "# Amber review\nInspect the card and retain the record.",
        "The Amber review tray contains 12 cards.",
        "The Violet board draft capacity is 12 counters.",
    ],
)
def test_positive_physical_objects_and_typed_local_properties_still_narrow(body):
    assert status(body) == "irrelevant"
