"""Scope-version plumbing only; this does not validate an answer or model."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from app.db.evidence_json import MARKER, decode_evidence_json, encode_evidence_json
from app.evidence_policy import recorded_evidence_policy
from app.portfolio import coverage
from app.portfolio.comparison import evidence_profile_matches
from app.services.requirement_contract import validate_discovery_lineage

from tests.captured_roles_unit943.fixtures import labels_selection


@pytest.fixture(scope="module")
def transports():
    plan, inputs, selected, _ = labels_selection()
    old = inputs["planning_inputs"]["evidence_profile"]
    new = replace(
        recorded_evidence_policy(old), source_governance_profile="requirement_bound_v1"
    ).record()

    def version(value):
        if type(value) is dict:
            if value == old:
                return deepcopy(new)
            return {key: version(child) for key, child in value.items()}
        if type(value) in (tuple, list):
            return [version(child) for child in value]
        if type(value) is str and value == json.dumps(
            old, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ):
            return json.dumps(
                new, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            )
        return value

    selected.update(
        contract="requirement-evidence-v5",
        evidence_profile=old,
        request_plan=plan.record(),
        staged_request_inputs=inputs["planning_inputs"],
        requirements=[],
        inspected_sources=[
            {
                key: proposal[key]
                for key in (
                    "chunk_id",
                    "document_id",
                    "document_version",
                    "content_hash",
                )
            }
            for proposal in selected["proposals"]
        ],
        selected_proposal_ids=[p["proposal_id"] for p in selected["proposals"]],
    )
    return version(selected), new


def test_discovery_validator_preserves_canonical_source_scope_version(transports):
    selection, _ = transports
    assert validate_discovery_lineage(selection) == {
        "status": "recorded",
        "valid": True,
    }


def test_measurement_distinguishes_complete_and_unknown_scope_transport(transports):
    selection, _ = transports
    response = {"provenance": {"answer_selection": selection}}
    sources, complete = coverage._staged_exposure_sources(response)
    assert sources and complete
    damaged = deepcopy(response)
    plan = damaged["provenance"]["answer_selection"]["request_plan"]
    plan["evidence_profile_json"] = '{"contract":"evidence-profile-v10"}'
    assert coverage._staged_exposure_sources(damaged)[1] is False


def test_scope_mode_matches_frozen_expectation(transports):
    selection, _ = transports
    settings = {
        "answer_proposal_profile": "qa_plus_source_patterns_v1",
        "role_scope_policy": "ordinary_session_activity_v1",
        "procedure_verification_profile": "source_declared_procedure_copy_v1",
        "source_context_policy": "scoped_note_context_v2",
        "source_governance_profile": "requirement_bound_v1",
    }
    assert evidence_profile_matches(selection, settings)
    assert not evidence_profile_matches(
        selection, {**settings, "source_governance_profile": "all_sources_v1"}
    )


def test_large_source_scope_storage_remains_lossless(transports):
    selection, _ = transports
    value = {"answer_selection": deepcopy(selection), "UNITONLY": "x" * 150000}
    encoded = encode_evidence_json(value, column="provenance")
    assert encoded.get(MARKER) == 1
    assert decode_evidence_json(encoded, column="provenance") == value
