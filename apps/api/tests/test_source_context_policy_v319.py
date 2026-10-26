"""Opt-in contextual reading, full-body closed grammar and immutable replay."""

from copy import deepcopy

import pytest
from app.config import Settings
from app.evidence_policy import EvidencePolicy
from app.services.source_context_scope import parse_context_note


def note(
    scope="Lumen token bench", state="postponed audit", mark="diamond", action="retain"
):
    return (
        f"{scope}: {state} disposition {action}\n\n"
        f"For the {scope} {state} marked with a {mark}, the operator must "
        f"{action} the marked audit card in the station folder.\n\n"
        f"This is a fictional current instruction for a very narrow audit "
        f"state. A {state} means an audit whose appointment was canceled "
        f"before inspection. The {mark} is a mark on its audit cover "
        f"card, not an ordinary batch identifier. An unflagged ordinary "
        f"run remains governed by the operation note and its complete "
        f"procedure. Nothing in this instruction changes owner "
        f"assignments, consultation windows, session start, session "
        f"duration, or ordinary allocation.\n\n"
        f"The decision here concerns the marked audit card only. It does "
        f"not describe treatment of samples, equipment, session cards, or "
        f"records belonging to a completed ordinary run. Before selecting "
        f"any disposition, the operator identifies the card as a {state} "
        f"and confirms the {mark} on its cover. Cards without that "
        f"combination do not fall within this instruction's condition.\n\n"
        "This document is published as a current authority for its "
        "stated condition. It has no precedence over another current "
        "document in the same curated conflict group. The grouping "
        "deliberately preserves an unresolved policy disagreement about "
        "the disposition. A reader must not invent a recency ranking "
        "from the title or choose one action because it appears "
        "convenient. Resolution requires a later authoritative revision "
        "that is not present in this corpus."
    )


def test_new_context_policy_is_opt_in_and_separately_versioned():
    strict = EvidencePolicy(
        "qa_only_v1", "literal_v1", "source_declared_procedure_copy_v1"
    ).record()
    assert strict["contract"] == "evidence-profile-v2"
    assert "source_context_policy" not in strict
    assert Settings().SOURCE_CONTEXT_POLICY == "explicit_target_v1"
    contextual = EvidencePolicy(
        "qa_only_v1",
        "literal_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v1",
    ).record()
    assert contextual["contract"] == "evidence-profile-v3"
    assert contextual["source_context_contract"] == "source-note-context-v1"


def test_context_inventory_accounts_for_every_character_and_reference():
    text = note()
    result = parse_context_note(text, "Lumen token bench", "postponed audit")
    assert result is not None
    intervals = sorted(
        [row["source_range"] for row in [*result["clause_inventory"], *result["gaps"]]],
        key=lambda row: row["start"],
    )
    assert intervals[0]["start"] == 0 and intervals[-1]["end"] == len(text)
    assert all(
        a["end"] == b["start"] for a, b in zip(intervals, intervals[1:], strict=False)
    )
    assert result["adopted_context"]["quantifier_domain"] == "any disposition"
    assert (
        result["adopted_context"]["resolved_quantifier_domain"]
        == "disposition of the marked audit card"
    )
    assert all(row["references"] is not None for row in result["clause_inventory"])
    assert result["disclosure"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s + " For ordinary runs, remove every token.",
        lambda s: s.replace("any disposition", "any disposition in every workflow"),
        lambda s: s.replace("the operator identifies", "the supervisor identifies"),
        lambda s: s.replace(
            "the marked audit card only", "the marked audit card and ordinary records"
        ),
        lambda s: s.replace(
            "Cards without that combination", "Cards with that combination"
        ),
        lambda s: s.replace("before inspection", "before inspection unless approved"),
        lambda s: s.replace(
            "This is a fictional",
            "This rule also governs ordinary runs. This is a fictional",
        ),
        lambda s: s.replace(
            "The decision here concerns the marked audit card only. ", ""
        ),
        lambda s: s.replace(
            "the marked audit card in the station folder", "it in the station folder"
        ),
        lambda s: s.replace("The diamond", "The triangle"),
    ],
)
def test_unknown_broadening_competing_scope_and_omissions_block(mutate):
    assert (
        parse_context_note(mutate(note()), "Lumen token bench", "postponed audit")
        is None
    )


@pytest.mark.parametrize(
    "scope,state,mark,action",
    [
        ("Cedar document desk", "delayed inspection", "square", "discard"),
        ("Juniper sample station", "canceled review", "circle", "retain"),
    ],
)
def test_scope_is_literal_and_has_no_case_identity_dependency(
    scope, state, mark, action
):
    assert (
        parse_context_note(note(scope, state, mark, action), scope, state) is not None
    )


def test_no_body_or_context_aliased_mutable_inventory():
    first = parse_context_note(note(), "Lumen token bench", "postponed audit")
    changed = deepcopy(first)
    changed["clause_inventory"].pop()
    assert changed != parse_context_note(note(), "Lumen token bench", "postponed audit")


@pytest.mark.parametrize(
    "destination",
    [
        "ledger where ordinary batches end",
        "shelf whose ordinary timer doubles",
        "basket with ordinary runs forbidden",
        "folder unless permits arrive",
    ],
)
def test_destination_is_positive_closed_grammar(destination):
    text = note().replace("station folder", destination)
    assert parse_context_note(text, "Lumen token bench", "postponed audit") is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("retain", "retain and discard"),
        ("postponed audit", "postponed audit or ordinary run"),
        ("diamond", "diamond unless approved"),
        ("owner assignments", "owner assignments and ordinary operators must wait"),
        ("samples", "samples which operators discard"),
    ],
)
def test_argument_slot_cannot_swallow_scope_or_clause(field, value):
    assert (
        parse_context_note(
            note().replace(field, value), "Lumen token bench", "postponed audit"
        )
        is None
    )


def test_unicode_codepoint_ranges_are_literal_and_not_utf16():
    text = note(scope="Lúmen 𝒜 desk")
    parsed = parse_context_note(text, "Lúmen 𝒜 desk", "postponed audit")
    assert parsed is not None
    for edge in parsed["reference_edges"]:
        span = edge["source_range"]
        assert text[span["start"] : span["end"]] == edge["source_literal"]
    assert (
        parsed["clause_inventory"][1]["source_range"]["start"]
        < len(
            text[: parsed["clause_inventory"][1]["source_range"]["start"]].encode(
                "utf-16-le"
            )
        )
        // 2
    )


def test_context_policy_cannot_bypass_copy_reader_support_engines():
    with pytest.raises(ValueError):
        Settings(SOURCE_CONTEXT_POLICY="scoped_note_context_v1")
    with pytest.raises(ValueError):
        Settings(
            SOURCE_CONTEXT_POLICY="scoped_note_context_v1",
            PROCEDURE_VERIFICATION_PROFILE="source_declared_procedure_copy_v1",
            GENERATION_MODE="extractive",
            ANSWER_SELECTION_MODE="reader",
        )


def test_descriptor_semantic_templates_are_the_canonical_runtime_projection():
    from app.services.source_context_scope import grammar_descriptor, semantic_checks

    reading = parse_context_note(note(), "Lumen token bench", "postponed audit")
    descriptor = grammar_descriptor()
    assert descriptor["context_constants"].items() <= reading["adopted_context"].items()
    assert (
        descriptor["disclosure_template"].format(**reading["adopted_context"])
        == reading["disclosure"]
    )
    checks = semantic_checks(reading)
    assert len(checks) == 23
    assert [check["name"] for check in checks[-8:]] == [
        row[0] for row in descriptor["semantic_templates"]
    ]
    for check in checks:
        if check["name"] in {"classification_identity", "classification_mark"}:
            assert "any disposition" in check["hypothesis"]
            assert "of the marked" not in check["hypothesis"]
