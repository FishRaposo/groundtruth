"""Saved actual source syntax; all inference/authorization remains unassessed."""

import hashlib
import json
from dataclasses import replace
from functools import lru_cache
from pathlib import Path

import pytest
from app.evidence_policy import resolve_evidence_policy
from app.services import captured_source_productions as production
from app.services import planning_declarations as source
from app.services.staged_plan_replay import _captures, _snapshot

from tests.staged_plan_unit837.fixtures_source import universe
from tests.test_captured_policy928 import configured
from tests.test_captured_source_ownership954 import declared_inputs


@lru_cache
def actual():
    raw = json.loads(
        (Path(__file__).parent / "fixtures/captured_copy_actual966.json").read_text(
            encoding="utf-8"
        )
    )
    snapshots = tuple(_snapshot(row) for row in raw["snapshots"])
    captures = tuple(_captures(row) for row in raw["source_captures"])
    inventory = source.declaration_inventory(universe(snapshots), snapshots, captures)
    return snapshots, captures, inventory


def selected(logical_id):
    snapshots, captures, inventory = actual()
    snapshot = next(
        row
        for row in snapshots
        if json.loads(row.metadata_json)["portfolio_logical_id"] == logical_id
    )
    capture = next(row for row in captures if row.identity == snapshot.identity)
    units = tuple(row for row in inventory.units if row.source == snapshot.identity)
    return snapshot, capture, units


@pytest.mark.parametrize(
    ("logical_id", "text"),
    [
        ("d526-11-routine", "The separate Azure listening demo"),
        ("d526-05-routine", "If a sample is not a unit quaternion"),
        ("d526-05-routine", "Pearl Spin orientation ribbon is held"),
        ("d526-06-routine", "If a logical counter is absent"),
        ("d526-06-routine", "The separate Wren appointment board"),
        ("d526-08-routine", "The separate Ruby URL lesson"),
        ("d526-03-routine", "Fourth, repeat the midpoint comparison"),
        ("d526-03-routine", "If the list is not ascending"),
        ("d526-14-routine", "If either serial is absent"),
        ("d526-07-routine", "Do not follow symbol-consuming transitions"),
        ("d526-07-routine", "Fourth, repeat until the pending list"),
    ],
)
def test_actual_selected_copy_retains_data_operands_and_negative_declarations(
    logical_id, text
):
    snapshot, capture, units = selected(logical_id)
    unit = next(row for row in units if row.raw.text.startswith(text))
    header, _ = production._instruction_definition(snapshot)
    declaration = production.procedures._envelope_declaration(snapshot.body)
    left, right = production.procedures._envelope_named_subject(declaration["subject"])
    result = production._declared_payload_unit(
        snapshot,
        production._windows(snapshot, capture),
        unit,
        header,
        declaration["subject"][left:right],
        [],
        selected_copy=True,
    )
    assert result["owner"] == "captured_declared_source_payload"
    assert result["raw"] == source.asdict(unit.raw)
    assert result["original_features_json"] == unit.features_json
    assert result["original_unknowns"] == list(unit.unknowns)
    assert result["factual_authority"] == "NOT_ASSESSED"
    tokens = [
        token for clause in result["captured_clauses"] for token in clause["tokens"]
    ]
    assert all(
        snapshot.body[t["source_start"] : t["source_end"]] == t["text"] for t in tokens
    )


def profile():
    return resolve_evidence_policy(
        configured(SOURCE_GOVERNANCE_PROFILE="requirement_bound_v1")
    ).record()


def test_default_all_actual_domains_keep_exact_prechange_bytes():
    snapshots, captures, inventory = actual()
    domains = []
    for snapshot in snapshots:
        capture = next(row for row in captures if row.identity == snapshot.identity)
        units = tuple(row for row in inventory.units if row.source == snapshot.identity)
        domains.append(
            {
                "logical_id": json.loads(snapshot.metadata_json)[
                    "portfolio_logical_id"
                ],
                "domain": production._instruction_domain(snapshot, capture, units),
            }
        )
    assert hashlib.sha256(source.canonical(domains).encode()).hexdigest() == (
        "19359d171335759f1a71aa8dff0364a47a168a370194cbf6b858b3799032d540"
    )


@pytest.mark.parametrize("change", ["old", "unknown", "mixed"])
def test_only_canonical_source_bound_profile_can_select_new_copy(change):
    snapshot, capture, units = selected("d526-01-routine")
    record = profile()
    if change == "old":
        record = resolve_evidence_policy(configured()).record()
    elif change == "unknown":
        record["source_governance_profile"] = "unknown"
    else:
        record["contract"] = "evidence-profile-v9"
    with pytest.raises(ValueError):
        production._instruction_domain(
            snapshot, capture, units, evidence_profile=record
        )


@pytest.mark.parametrize("change", ["drop", "features", "identity"])
def test_selected_units_and_captures_must_match_complete_independent_rebuild(change):
    snapshot, capture, units = selected("d526-01-routine")
    if change == "drop":
        units = units[:-1]
    elif change == "features":
        units = (replace(units[0], features_json="{}"), *units[1:])
    else:
        capture = replace(
            capture, identity=replace(capture.identity, document_id="other")
        )
    with pytest.raises(ValueError):
        production._instruction_domain(
            snapshot, capture, units, evidence_profile=profile()
        )


@pytest.mark.parametrize(
    "kind",
    [
        "external",
        "global",
        "unknown",
        "read_attachment",
        "follow_unknown",
        "apply_appendix",
        "reported_external",
        "then_read_appendix",
        "negative_follow_instruction",
    ],
)
def test_selected_payload_does_not_own_unclosed_authority_edges(kind):
    from tests.captured_productions_unit931.test_source import ACTION, HEADER
    from tests.staged_plan_unit837.fixtures_source import EXTERNAL

    payload = list(EXTERNAL)
    if kind == "global":
        payload = list(HEADER)
        payload[5:7] = [
            ("all", "DET", "all", "det", 6),
            ("activities", "NOUN", "activity", "pobj", 4),
        ]
    elif kind == "unknown":
        payload = list(ACTION)
        payload[2] = ("token", "NOUN", "token", "dep", 0)
    elif kind == "read_attachment":
        payload = [
            ("Read", "VERB", "read", "ROOT", 0),
            ("the", "DET", "the", "det", 2),
            ("attachment", "NOUN", "attachment", "dobj", 0),
            (".", "PUNCT", ".", "punct", 0),
        ]
    elif kind in {"follow_unknown", "apply_appendix"}:
        verb, noun = (
            ("Follow", "quasar") if kind == "follow_unknown" else ("Apply", "appendix")
        )
        payload = [
            (verb, "VERB", verb.casefold(), "ROOT", 0),
            ("the", "DET", "the", "det", 2),
            (noun, "NOUN", noun, "dobj", 0),
            (".", "PUNCT", ".", "punct", 0),
        ]
    elif kind == "reported_external":
        payload = [
            ("Do", "VERB", "do", "ROOT", 0),
            ("as", "ADP", "as", "mark", 2),
            ("described", "VERB", "describe", "advcl", 0),
            ("by", "ADP", "by", "agent", 2),
            ("Foobar", "PROPN", "Foobar", "pobj", 3),
            (".", "PUNCT", ".", "punct", 0),
        ]
    elif kind == "then_read_appendix":
        payload = [
            ("Repeat", "VERB", "repeat", "ROOT", 0),
            (",", "PUNCT", ",", "punct", 0),
            ("then", "ADV", "then", "advmod", 0),
            ("read", "VERB", "read", "dep", 0),
            ("the", "DET", "the", "det", 5),
            ("appendix", "NOUN", "appendix", "dobj", 3),
            (".", "PUNCT", ".", "punct", 0),
        ]
    elif kind == "negative_follow_instruction":
        payload = [
            ("Do", "AUX", "do", "aux", 2),
            ("not", "PART", "not", "neg", 2),
            ("follow", "VERB", "follow", "ROOT", 2),
            ("the", "DET", "the", "det", 5),
            ("unknown", "ADJ", "unknown", "amod", 5),
            ("instructions", "NOUN", "instruction", "dobj", 2),
            (".", "PUNCT", ".", "punct", 2),
        ]
    inputs = declared_inputs(payload)
    snapshot, capture = inputs["snapshots"][0], inputs["source_captures"][0]
    inventory = source.declaration_inventory(
        inputs["manifest"], inputs["snapshots"], inputs["source_captures"]
    )
    unit = next(
        row for row in inventory.units if row.raw.text.startswith(payload[0][0])
    )
    header = source.asdict(inventory.units[0].raw)
    with pytest.raises(ValueError):
        production._declared_payload_unit(
            snapshot,
            production._windows(snapshot, capture),
            unit,
            header,
            "Citrine fragment desk",
            [],
            selected_copy=True,
        )


@pytest.mark.parametrize("field", ["condition", "conflict_group"])
def test_selected_copy_does_not_close_curated_or_conditioned_source(field):
    snapshot, capture, units = selected("d526-01-routine")
    snapshot = replace(snapshot, metadata_json=source.canonical({field: "pending"}))
    result = production._instruction_domain(
        snapshot, capture, units, evidence_profile=profile()
    )
    assert result["status"] == "mandatory_unresolved"
    assert "Curated or conditioned" in result["reason"]


def test_selected_finite_header_keeps_every_original_unit_feature():
    from tests.captured_productions_unit931.fixtures import unit_inputs
    from tests.captured_productions_unit931.test_source import ACTION, HEADER

    inputs = unit_inputs([HEADER, ACTION])
    inventory = source.declaration_inventory(
        inputs["manifest"], inputs["snapshots"], inputs["source_captures"]
    )
    result = production._instruction_domain(
        inputs["snapshots"][0],
        inputs["source_captures"][0],
        inventory.units,
        evidence_profile=profile(),
    )
    assert result["status"] == "copy_domain_structurally_owned", result.get("reason")
    assert all(
        receipt["original_features_json"] == unit.features_json
        and receipt["original_unknowns"] == list(unit.unknowns)
        for receipt, unit in zip(result["units"], inventory.units, strict=True)
    )


def test_all_actual_selected_domains_replay_whole_sources_without_fact_authority():
    snapshots, _, _ = actual()
    for original in snapshots:
        snapshot, capture, units = selected(
            json.loads(original.metadata_json)["portfolio_logical_id"]
        )
        result = production._instruction_domain(
            snapshot, capture, units, evidence_profile=profile()
        )
        assert result["status"] == "copy_domain_structurally_owned", result.get(
            "reason"
        )
        assert result["source_governance_profile"] == "requirement_bound_v1"
        assert result["source_identity"] == source.asdict(snapshot.identity)
        assert result["factual_authority"] == "NOT_ASSESSED"
        assert not result["source_relevance_exclusion"]
        assert result["namespace_disjointness"] == "NOT_ASSERTED"
        assert result["requested_complete_copy"] == "NOT_ASSERTED"
        assert result["remaining_gates"]
        declaration = production.procedures._envelope_declaration(snapshot.body)
        assert (
            result["definition_relation"]["literal_scope"]["text"]
            == declaration["subject"]
        )
        assert [row["raw"] for row in result["units"]] == [
            source.asdict(unit.raw) for unit in units
        ]
        assert all(
            row["original_features_json"] == unit.features_json
            and row["original_unknowns"] == list(unit.unknowns)
            for row, unit in zip(result["units"], units, strict=True)
        )
        assert "".join(row["raw"]["text"] for row in result["units"]) == snapshot.body
