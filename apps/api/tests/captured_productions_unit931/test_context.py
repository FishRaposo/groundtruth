"""Catch changed source offsets, score-based windows and lost governing ledgers."""

from copy import deepcopy

import pytest
from app.services import captured_governing_context as context
from app.services import captured_source_productions as source
from app.services.planning_declarations import RawRange

from .fixtures import arguments, unit_inputs


def selected(inputs):
    ledger = source.reconstruct_source_productions(
        **inputs, reading_profile="contextual_source_v4"
    )
    row = next(
        row
        for item in ledger["sources"]
        for row in item["relation_candidates"]
        if row["original_value_token"]["dep"] == "acomp"
    )
    return ledger, row


def test_actual_explicit_clause_context_preserves_the_full_pending_source_universe():
    inputs = arguments()
    ledger, row = selected(inputs)
    result = context.reconstruct_governing_context(
        **inputs,
        source_identity=row["source"],
        selected_clause=row["raw"],
        reading_profile="contextual_source_v4",
    )
    assert result["context"] == row["raw"], (
        "The explicit captured clause context remains unrepresented"
    )
    assert len(result["full_source_unit_ids"]) == 20
    assert result["read_set"] == ledger["read_set"]
    assert result["sql_read_set_json"] == inputs["sql_read_set_json"]
    assert result["governing_opposition_status"] == "MANDATORY_INDEPENDENT_REPLAY"
    assert result["executions"] == [] and not result["publication_ready"]


def test_legacy_context_stays_whole_body_and_non_native_ranges_fail():
    inputs = arguments()
    _, row = selected(inputs)
    result = context.reconstruct_governing_context(
        **inputs, source_identity=row["source"], selected_clause=row["raw"]
    )
    assert result["context"] == result["historical_whole_body"]
    assert result["status"] == "HISTORICAL_WHOLE_BODY_GATE_UNCHANGED"
    with pytest.raises(ValueError):
        context.reconstruct_governing_context(
            **inputs,
            source_identity=row["source"],
            selected_clause=RawRange(False, row["raw"]["end"], row["raw"]["text"]),
            reading_profile="contextual_source_v4",
        )


def test_context_offsets_identity_and_scores_cannot_forge_replay():
    inputs = arguments()
    _, row = selected(inputs)
    record = context.reconstruct_governing_context(
        **inputs,
        source_identity=row["source"],
        selected_clause=row["raw"],
        reading_profile="contextual_source_v4",
    )
    assert context.validate_governing_context(
        record,
        **inputs,
        source_identity=row["source"],
        selected_clause=row["raw"],
        reading_profile="contextual_source_v4",
    )
    changed = deepcopy(record)
    changed["context"]["end"] -= 1
    changed["producer_score"] = 1e9
    assert not context.validate_governing_context(
        changed,
        **inputs,
        source_identity=row["source"],
        selected_clause=row["raw"],
        reading_profile="contextual_source_v4",
    )
    with pytest.raises(ValueError):
        context.reconstruct_governing_context(
            **inputs,
            source_identity={**row["source"], "snapshot_id": "unrelated"},
            selected_clause=row["raw"],
            reading_profile="contextual_source_v4",
        )


def test_direct_negation_does_not_silently_shorten_a_governing_context():
    from tests.staged_plan_unit837.fixtures_source import ASSIGN, CAT

    rows = [
        (word, pos, lemma, dep, head + (head >= 7))
        for word, pos, lemma, dep, head in ASSIGN
    ]
    rows.insert(7, ("not", "PART", "not", "neg", 6))
    inputs = unit_inputs([CAT, rows])
    ledger = source.reconstruct_source_productions(
        **inputs, reading_profile="contextual_source_v4"
    )
    candidate = ledger["sources"][0]["relation_candidates"][0]
    result = context.reconstruct_governing_context(
        **inputs,
        source_identity=candidate["source"],
        selected_clause=candidate["raw"],
        reading_profile="contextual_source_v4",
    )
    assert result["context"] is None
    assert (
        result["status"] == "UNRESOLVED_CAPTURED_GOVERNORS_REQUIRE_CONTIGUOUS_CLOSURE"
    )
    assert not result["publication_ready"]


def test_external_condition_reference_and_unknown_units_remain_in_full_ledger():
    from tests.staged_plan_unit837.fixtures_source import ASSIGN, CAT, COND, EXTERNAL

    inputs = unit_inputs([CAT, ASSIGN, COND, EXTERNAL])
    ledger = source.reconstruct_source_productions(
        **inputs, reading_profile="contextual_source_v4"
    )
    candidate = ledger["sources"][0]["relation_candidates"][0]
    result = context.reconstruct_governing_context(
        **inputs,
        source_identity=candidate["source"],
        selected_clause=candidate["raw"],
        reading_profile="contextual_source_v4",
    )
    assert len(result["full_source_unit_ids"]) == len(
        ledger["source_inventory"]["units"]
    )
    assert any(row["original_unknowns"] for row in result["governing_inventory"])
    assert all(
        row["status"] == "REQUIRES_OPERATION_BOUND_GOVERNOR_REFERENCE_OPPOSITION_REPLAY"
        for row in result["governing_inventory"]
    )
    assert not result["publication_ready"]
