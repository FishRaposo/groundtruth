"""Catch lost source units, invented actors and blanket operation waivers."""

from copy import deepcopy
from dataclasses import replace

import pytest
from app.services import captured_source_productions as production
from app.services import planning_declarations as source

from .fixtures import actual, arguments, unit_inputs


def test_actual_four_source_operation_ledger_accounts_every_unit_and_candidate():
    inputs = arguments()
    result = production.reconstruct_source_productions(
        **inputs, reading_profile="contextual_source_v4"
    )
    rows = result["sources"]
    assert len(rows) == 4
    assert len(result["source_inventory"]["units"]) == 20
    assert (
        sum(
            row["instruction_domain"]["status"] == "copy_domain_structurally_owned"
            for row in rows
        )
        == 2
    ), "Independent instruction blocks have no operation owner"
    relations = [candidate for row in rows for candidate in row["relation_candidates"]]
    assert len(relations) == 3
    assert sum(row["original_value_token"]["dep"] == "acomp" for row in relations) == 1
    assert all(
        row["actor_value"] == "UNBOUND" and not row["accepted"] for row in relations
    )
    fields = [
        candidate for row in rows for candidate in row["dependent_argument_candidates"]
    ]
    assert len(fields) == 3
    assert any(
        argument["unknowns"]
        for row in fields
        for argument in row["original_declaration"]["arguments"]
    )
    assert result["original_inputs"]["snapshots"] == actual()["snapshots"]
    assert result["original_inputs"]["source_captures"] == actual()["source_captures"]
    assert result["sql_read_set_json"] == inputs["sql_read_set_json"]
    assert result["excluded_sources"] == [] and not result["full_plan_accepted"]


def test_historical_actual_source_assignment_gap_remains_visible():
    inputs = arguments()
    inventory = source.declaration_inventory(
        inputs["manifest"], inputs["snapshots"], inputs["source_captures"]
    )
    catalogue = next(
        row for row in inventory.declarations if row.kind == "role_catalogue"
    )
    assignments = [
        row
        for row in inventory.declarations
        if row.kind == "role_assignment" and row.source == catalogue.source
    ]
    assert len(assignments) == 2 and len(catalogue.members) == 3


def test_old_default_is_exact_original_inventory_without_new_source_semantics():
    inputs = arguments()
    result = production.reconstruct_source_productions(**inputs)
    original = source.declaration_inventory(
        inputs["manifest"], inputs["snapshots"], inputs["source_captures"]
    )
    assert result["source_inventory"] == original.record()
    assert all(
        not row["relation_candidates"] and not row["dependent_argument_candidates"]
        for row in result["sources"]
    )
    assert all(
        row["instruction_domain"]["status"] == "legacy_source_inventory_only"
        for row in result["sources"]
    )


@pytest.mark.parametrize("word", ["mandatory", "optional"])
def test_adjectival_role_values_never_automatically_become_actors(word):
    from tests.staged_plan_unit837.fixtures_source import CAT

    assignment = [
        ("The", "DET", "the", "det", 2),
        ("observer", "NOUN", "observer", "compound", 2),
        ("role", "NOUN", "role", "nsubj", 3),
        ("is", "AUX", "be", "ROOT", 3),
        (word, "ADJ", word, "acomp", 3),
        (".", "PUNCT", ".", "punct", 3),
    ]
    inputs = unit_inputs([CAT, assignment])
    result = production.reconstruct_source_productions(
        **inputs, reading_profile="contextual_source_v4"
    )
    row = result["sources"][0]["relation_candidates"][0]
    assert row["literal_value_candidate"]["text"] == word
    assert row["actor_value"] == "UNBOUND" and not row["accepted"]
    assert "actual_role_relation_subject_attribute_NI" in row["remaining_gates"]


HEADER = [
    ("This", "DET", "this", "det", 2),
    ("complete", "ADJ", "complete", "amod", 2),
    ("routine", "NOUN", "routine", "nsubj", 3),
    ("applies", "VERB", "apply", "ROOT", 3),
    ("to", "ADP", "to", "prep", 3),
    ("Helios", "NOUN", "helios", "compound", 6),
    ("check", "NOUN", "check", "pobj", 4),
    (".", "PUNCT", ".", "punct", 3),
]
ACTION = [
    ("Frobnicate", "VERB", "frobnicate", "ROOT", 0),
    ("the", "DET", "the", "det", 2),
    ("token", "PROPN", "token", "dobj", 0),
    (".", "PUNCT", ".", "punct", 0),
]


@pytest.mark.parametrize(
    "kind",
    [
        "reference",
        "condition",
        "unknown_assertion",
        "global",
        "ambiguous",
        "role_assertion",
        "curated",
        "metadata_condition",
    ],
)
def test_unsupported_instruction_material_stays_mandatory(kind):
    from tests.staged_plan_unit837.fixtures_source import (
        ASSIGN,
        COND,
        EXTERNAL,
        UNKNOWN,
    )

    groups = [list(HEADER), list(ACTION)]
    metadata = None
    if kind == "reference":
        groups[1] = EXTERNAL
    elif kind == "condition":
        groups.append(COND)
    elif kind == "unknown_assertion":
        groups.append(UNKNOWN)
    elif kind == "global":
        groups[0][5:7] = [
            ("all", "DET", "all", "det", 6),
            ("activities", "NOUN", "activity", "pobj", 4),
        ]
    elif kind == "ambiguous":
        groups += [HEADER, ACTION]
    elif kind == "role_assertion":
        groups.append(ASSIGN)
    elif kind == "curated":
        metadata = {"conflict_group": "UNITONLY931-opposition"}
    else:
        metadata = {"condition": "UNITONLY931-unassessed"}
    result = production.reconstruct_source_productions(
        **unit_inputs(groups, metadata=metadata), reading_profile="contextual_source_v4"
    )
    domain = result["sources"][0]["instruction_domain"]
    assert domain["status"] == "mandatory_unresolved" and domain["reason"]
    assert domain["curated_opposition_inspection"] == "REQUIRED"


def test_source_candidates_and_producer_flags_cannot_replace_independent_replay():
    inputs = arguments()
    record = production.reconstruct_source_productions(
        **inputs, reading_profile="contextual_source_v4"
    )
    assert production.validate_source_productions(
        record, **inputs, reading_profile="contextual_source_v4"
    )
    changed = deepcopy(record)
    changed["sources"][0]["relation_candidates"][0]["actor_value"] = "forged"
    assert not production.validate_source_productions(
        changed, **inputs, reading_profile="contextual_source_v4"
    )
    changed = deepcopy(record)
    changed["source_inventory"]["units"][0]["unknowns"] = []
    changed["full_plan_accepted"] = True
    assert not production.validate_source_productions(
        changed, **inputs, reading_profile="contextual_source_v4"
    )
    altered = {
        **inputs,
        "snapshots": (
            replace(
                inputs["snapshots"][0], body=inputs["snapshots"][0].body + " unseen"
            ),
            *inputs["snapshots"][1:],
        ),
    }
    with pytest.raises(ValueError):
        production.reconstruct_source_productions(
            **altered, reading_profile="contextual_source_v4"
        )


def test_selected_root_composition_retains_four_sources_without_all_world_claims():
    inputs = arguments()
    ledger = production.reconstruct_source_productions(
        **inputs, reading_profile="contextual_source_v4"
    )
    root = next(
        row
        for row in ledger["sources"]
        if row["instruction_domain"].get("definition_parser")
        == "contextual_procedures.declared_envelope_inventory"
    )
    result = production.reconstruct_root_composition(
        **inputs,
        selected_root_identity=root["identity"],
        reading_profile="contextual_source_v4",
    )
    assert len(result["sources"]) == 4
    assert any(
        row["candidate_operation"]
        == "UNREACHED_DECLARED_BLOCK_CANDIDATE_PENDING_RELATION_REPLAY"
        for row in result["sources"]
    )
    assert result["all_world_procedure_completeness"] == "NOT_ASSERTED"
    assert result["excluded_sources"] == [] and not result["accepted"]
    assert production.validate_root_composition(
        result,
        **inputs,
        selected_root_identity=root["identity"],
        reading_profile="contextual_source_v4",
    )
    with pytest.raises(ValueError):
        production.reconstruct_root_composition(
            **inputs,
            selected_root_identity=ledger["sources"][0]["identity"],
            reading_profile="contextual_source_v4",
        )
