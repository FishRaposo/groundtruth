"""Deterministic captured context records; semantic support remains external."""

import json
from dataclasses import asdict

from app.services import planning_declarations as source
from app.services.captured_production_policy import CONTEXT_CONTRACT, selected_version
from app.services.captured_source_productions import reconstruct_source_productions

_GOVERNING = (
    "conditions",
    "modality",
    "negation",
    "references",
    "governors",
    "unbound_condition_markers",
)


def _identity(value):
    if type(value) is source.SourceIdentity:
        return asdict(value)
    source._native(value)
    if type(value) is not dict:
        raise ValueError("An exact immutable source identity is required")
    return value


def _clause(value):
    if type(value) is source.RawRange:
        value = asdict(value)
    source._native(value)
    if type(value) is not dict or set(value) != {"start", "end", "text"}:
        raise ValueError("One exact original clause range is required")
    if (
        type(value["start"]) is not int
        or type(value["end"]) is not int
        or type(value["text"]) is not str
    ):
        raise ValueError("Original clause coordinates must retain their types")
    return value


def _known_production(ledger, identity, clause):
    row = next(item for item in ledger["sources"] if item["identity"] == identity)
    return any(
        candidate["raw"] == clause for candidate in row["relation_candidates"]
    ) or any(
        declaration["source"] == identity
        and declaration["raw"] == clause
        and declaration["kind"]
        in {"role_catalogue", "role_assignment", "literal_field"}
        for declaration in ledger["source_inventory"]["declarations"]
    )


def reconstruct_governing_context(
    question,
    capture,
    manifest,
    snapshots,
    source_captures,
    *,
    sql_read_set_json,
    source_identity,
    selected_clause,
    reading_profile=None,
):
    version = selected_version(reading_profile)
    ledger = reconstruct_source_productions(
        question,
        capture,
        manifest,
        snapshots,
        source_captures,
        sql_read_set_json=sql_read_set_json,
        reading_profile=reading_profile,
    )
    identity, clause = _identity(source_identity), _clause(selected_clause)
    matches = [
        row
        for row in snapshots
        if source.canonical(identity) == source.canonical(asdict(row.identity))
    ]
    if len(matches) != 1:
        raise ValueError("One immutable source identity required")
    snapshot = matches[0]
    units = [
        row
        for row in ledger["source_inventory"]["units"]
        if row["source"] == identity and row["raw"] == clause
    ]
    if (
        len(units) != 1
        or snapshot.body[clause["start"] : clause["end"]] != clause["text"]
    ):
        raise ValueError("Selected clause does not reproduce one original source unit")
    whole = {"start": 0, "end": len(snapshot.body), "text": snapshot.body}
    record = {
        "contract": CONTEXT_CONTRACT,
        "reading_profile": reading_profile,
        "policy_enabled": version is not None,
        "source_identity": identity,
        "selected_clause": clause,
        "historical_whole_body": whole,
        "context": whole,
        "status": "HISTORICAL_WHOLE_BODY_GATE_UNCHANGED",
        "source_production_sha256": source.digest(ledger),
        "read_set": ledger["read_set"],
        "sql_read_set_json": sql_read_set_json,
        "full_source_unit_ids": [
            row["id"] for row in ledger["source_inventory"]["units"]
        ],
        "governing_inventory": [
            {
                "source": row["source"],
                "unit_id": row["id"],
                "raw": row["raw"],
                "original_features_json": row["features_json"],
                "original_unknowns": row["unknowns"],
                "status": (
                    "REQUIRES_OPERATION_BOUND_GOVERNOR_REFERENCE_OPPOSITION_REPLAY"
                ),
            }
            for row in ledger["source_inventory"]["units"]
        ],
        "governing_opposition_status": "MANDATORY_INDEPENDENT_REPLAY",
        "remaining_gates": [
            "actual_captured_request_and_fact_binding",
            "requested_subject_attribute_scope_units_negation_conditions_NI",
            "complete_governing_reference_curated_opposition_replay",
            "source_authority_and_currentness",
        ],
        "executions": [],
        "publication_ready": False,
    }
    if version is not None:
        if not _known_production(ledger, identity, clause):
            raise ValueError(
                "An actual captured factual or relation production is required"
            )
        features = json.loads(units[0]["features_json"])
        if any(features.get(key) for key in _GOVERNING):
            record.update(
                context=None,
                status="UNRESOLVED_CAPTURED_GOVERNORS_REQUIRE_CONTIGUOUS_CLOSURE",
            )
        else:
            record.update(
                context=clause,
                status="SELF_CONTAINED_SELECTED_CLAUSE_CONTEXT_PRODUCTION",
            )
    return json.loads(source.canonical(record))


def validate_governing_context(record, *args, **kwargs):
    try:
        source._native(record)
        return source.canonical(record) == source.canonical(
            reconstruct_governing_context(*args, **kwargs)
        )
    except (ValueError, TypeError, KeyError, IndexError, RecursionError):
        return False
