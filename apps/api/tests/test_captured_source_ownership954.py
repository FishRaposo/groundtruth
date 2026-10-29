"""Exposed DEV source ownership; no model assessment or answer-quality claim."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from app.services import captured_source_productions as production
from app.services import planning_declarations as source
from app.services.staged_plan_replay import _captures, _snapshot

from tests.captured_productions_unit931.fixtures import arguments
from tests.staged_plan_unit837.fixtures_source import universe


def actual_inputs():
    data = json.loads(
        (Path(__file__).parent / "fixtures/captured_source_actual954.json").read_text(
            encoding="utf-8"
        )
    )
    snapshots = tuple(_snapshot(row) for row in data["snapshots"])
    return {
        **arguments(),
        "manifest": universe(snapshots),
        "snapshots": snapshots,
        "source_captures": tuple(_captures(row) for row in data["source_captures"]),
        "sql_read_set_json": source.canonical(
            {"fixture": "UNITONLY954_retained_actual_captures_NO_SQL"}
        ),
    }


@pytest.mark.parametrize(
    "logical_id", ["d526-01-routine", "d526-15-routine", "d526-16-routine"]
)
def test_actual_declared_qualified_source_has_copy_owner_without_fact_acceptance(
    logical_id,
):
    # Break: positive govern+dobj and qualified complete payload are rejected
    # before the existing exact-copy consumer can discharge its own obligations.
    inputs = actual_inputs()
    result = production.reconstruct_source_productions(
        **inputs, reading_profile="contextual_source_v4"
    )
    snapshot = next(
        row
        for row in inputs["snapshots"]
        if json.loads(row.metadata_json)["portfolio_logical_id"] == logical_id
    )
    row = next(
        row
        for row in result["sources"]
        if row["identity"]["document_id"] == snapshot.identity.document_id
    )
    domain = row["instruction_domain"]
    assert domain["status"] == "copy_domain_structurally_owned", domain.get("reason")
    units = [
        u for u in result["source_inventory"]["units"] if u["source"] == row["identity"]
    ]
    assert [u["unit_id"] for u in domain["units"]] == [u["id"] for u in units]
    assert all(
        receipt["raw"] == unit["raw"]
        for receipt, unit in zip(domain["units"], units, strict=True)
    )
    assert domain["factual_authority"] == "NOT_ASSESSED"
    assert domain["requested_complete_copy"] == "NOT_ASSERTED"
    assert domain["remaining_gates"]
    assert not result["full_plan_accepted"] and result["excluded_sources"] == []
    assert source.canonical(result["original_inputs"]["snapshots"]) == source.canonical(
        [source.asdict(s) for s in inputs["snapshots"]]
    )
    for receipt, unit in zip(domain["units"], units, strict=True):
        if receipt["owner"] == "captured_declared_source_payload":
            assert receipt["original_features_json"] == unit["features_json"]
            assert receipt["original_unknowns"] == unit["unknowns"]


@pytest.mark.parametrize(
    "metadata", [{"condition": "unassessed"}, {"conflict_group": "opposition"}]
)
def test_actual_qualified_source_curated_governance_stays_pending(metadata):
    inputs = actual_inputs()
    inputs["snapshots"] = tuple(
        replace(row, metadata_json=source.canonical(metadata))
        for row in inputs["snapshots"]
    )
    result = production.reconstruct_source_productions(
        **inputs, reading_profile="contextual_source_v4"
    )
    assert all(
        row["instruction_domain"]["status"] == "mandatory_unresolved"
        for row in result["sources"]
    )


def test_old_default_does_not_gain_qualified_source_ownership():
    result = production.reconstruct_source_productions(**actual_inputs())
    assert all(
        row["instruction_domain"]["status"] == "legacy_source_inventory_only"
        for row in result["sources"]
    )


def declared_inputs(payload, *additional):
    from tests.captured_productions_unit931.fixtures import unit_inputs

    captured = actual_inputs()
    snapshot = next(s for s in captured["snapshots"] if "Citrine" in s.body)
    capture = next(
        c for c in captured["source_captures"] if c.identity == snapshot.identity
    )
    annotation = json.loads(capture.windows[0].capture_json)["annotation"]
    header = [
        (t["text"], t["pos"], t["lemma"], t["dep"], t["head"])
        for t in annotation["tokens"]
        if t["end"] <= 132
    ]
    return unit_inputs([header, payload, *additional])


@pytest.mark.parametrize("kind", ["external", "global", "unknown_attachment"])
def test_declared_payload_still_blocks_actual_authority_global_and_unknown_edges(kind):
    from tests.captured_productions_unit931.test_source import ACTION, HEADER
    from tests.staged_plan_unit837.fixtures_source import EXTERNAL

    payload = list(EXTERNAL)
    if kind == "global":
        payload = list(HEADER)
        payload[5:7] = [
            ("all", "DET", "all", "det", 6),
            ("activities", "NOUN", "activity", "pobj", 4),
        ]
    elif kind == "unknown_attachment":
        payload = list(ACTION)
        payload[2] = ("token", "NOUN", "token", "dep", 0)
    result = production.reconstruct_source_productions(
        **declared_inputs(payload), reading_profile="contextual_source_v4"
    )
    assert (
        result["sources"][0]["instruction_domain"]["status"] == "mandatory_unresolved"
    )


def test_copied_role_statement_never_becomes_factual_authority():
    from tests.staged_plan_unit837.fixtures_source import ASSIGN

    result = production.reconstruct_source_productions(
        **declared_inputs(ASSIGN), reading_profile="contextual_source_v4"
    )
    domain = result["sources"][0]["instruction_domain"]
    assert domain["status"] == "copy_domain_structurally_owned"
    assert domain["factual_authority"] == "NOT_ASSESSED"
    assert result["sources"][0]["fact_or_actor_values"] == "UNBOUND"
    assert not result["full_plan_accepted"]


def test_reading_attachment_content_is_not_closed_by_a_prior_data_record():
    anchor = [
        ("Record", "VERB", "record", "ROOT", 0),
        ("the", "DET", "the", "det", 3),
        ("comment", "NOUN", "comment", "compound", 3),
        ("attachment", "NOUN", "attachment", "dobj", 0),
        (".", "PUNCT", ".", "punct", 0),
    ]
    read = [
        ("Read", "VERB", "read", "ROOT", 0),
        ("the", "DET", "the", "det", 2),
        ("attachment", "NOUN", "attachment", "dobj", 0),
        (".", "PUNCT", ".", "punct", 0),
    ]
    result = production.reconstruct_source_productions(
        **declared_inputs(anchor, read), reading_profile="contextual_source_v4"
    )
    assert (
        result["sources"][0]["instruction_domain"]["status"] == "mandatory_unresolved"
    )
