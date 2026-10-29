"""Version the opt-in scope correction without changing old/default bytes."""

import hashlib
import json
from dataclasses import replace

import pytest
from app.config import Settings
from app.evidence_policy import (
    EvidencePolicy,
    recorded_evidence_policy,
    resolve_evidence_policy,
)
from app.services.captured_plan_inputs import _profile

from tests.test_captured_policy928 import configured


def test_explicit_requirement_bound_governance_has_a_distinct_canonical_boundary():
    policy = resolve_evidence_policy(
        configured(SOURCE_GOVERNANCE_PROFILE="requirement_bound_v1")
    )
    record = policy.record()
    assert record["contract"] == "evidence-profile-v10"
    assert policy.source_governance_profile == "requirement_bound_v1"
    assert record["source_governance_profile"] == "requirement_bound_v1"
    assert record["source_governance_contract"] == "source-bound-witness-scope-v1"
    assert (
        record["output_contract"]
        == policy.output_contract
        == "procedure-output-cover-v10"
    )
    assert record["request_input_contract"] == "staged-request-inputs-v2"
    assert recorded_evidence_policy(record) == policy
    assert _profile(record) == (record, "contextual_source_v4")


@pytest.mark.parametrize(
    "quantity,expected",
    [
        (
            "legacy_v1",
            "828fdde073578dd74fd30004d44f5736482373afe54844e79cfac0a951688c67",
        ),
        (
            "literal_source_count_v1",
            "e12bb220615462650b4fd07eabacfa0236bf397e5597ab0b0a8818540ffa65db",
        ),
    ],
)
def test_both_original_profile9_serializations_stay_byte_identical(quantity, expected):
    policy = resolve_evidence_policy(configured(QUANTITY_VERIFICATION_PROFILE=quantity))
    record = policy.record()
    assert policy.source_governance_profile == "all_sources_v1"
    assert (
        "source_governance_profile" not in record
        and "source_governance_contract" not in record
    )
    assert (
        record["output_contract"]
        == policy.output_contract
        == "procedure-output-cover-v9"
    )
    raw = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    assert hashlib.sha256(raw.encode()).hexdigest() == expected
    assert recorded_evidence_policy(record).record() == record


def test_library_and_settings_defaults_do_not_promote_source_governance():
    policy = EvidencePolicy("qa_only_v1", "literal_v1")
    assert policy.source_governance_profile == "all_sources_v1"
    assert policy.record()["contract"] == "evidence-profile-v1"
    assert Settings(_env_file=None).SOURCE_GOVERNANCE_PROFILE == "all_sources_v1"


@pytest.mark.parametrize(
    "change",
    [
        {"EVIDENCE_READING_PROFILE": "contextual_source_v3"},
        {"ANSWER_SUPPORT_MODE": "disabled"},
        {"ANSWER_SELECTION_MODE": "lexical"},
        {"GENERATION_MODE": "provider"},
        {"ANSWER_PROPOSAL_PROFILE": "qa_only_v1"},
        {"SOURCE_CONTEXT_POLICY": "explicit_target_v1"},
    ],
)
def test_requirement_bound_mode_cannot_bypass_reading_or_composite_engines(change):
    with pytest.raises(ValueError):
        configured(SOURCE_GOVERNANCE_PROFILE="requirement_bound_v1", **change)


@pytest.mark.parametrize("mode", [None, True, "requirement_bound_v2"])
def test_unknown_governance_mode_is_rejected_by_configuration_and_policy(mode):
    with pytest.raises(ValueError):
        configured(SOURCE_GOVERNANCE_PROFILE=mode)
    old = resolve_evidence_policy(configured())
    with pytest.raises(ValueError):
        replace(old, source_governance_profile=mode)


@pytest.mark.parametrize(
    "field,value",
    [
        ("contract", "evidence-profile-v9"),
        ("output_contract", "procedure-output-cover-v9"),
        ("source_governance_profile", "all_sources_v1"),
        ("source_governance_profile", "requirement_bound_v2"),
        ("source_governance_contract", "unknown"),
        ("extra_success_flag", True),
        ("scope_document_limit", 128.0),
    ],
)
def test_mixed_unknown_downgraded_or_non_native_new_profiles_reject(field, value):
    record = resolve_evidence_policy(
        configured(SOURCE_GOVERNANCE_PROFILE="requirement_bound_v1")
    ).record()
    record[field] = value
    with pytest.raises(ValueError):
        recorded_evidence_policy(record)


@pytest.mark.parametrize(
    "field",
    ["source_governance_profile", "source_governance_contract", "proposal_profile"],
)
def test_partial_new_records_raise_a_controlled_rejection(field):
    record = resolve_evidence_policy(
        configured(SOURCE_GOVERNANCE_PROFILE="requirement_bound_v1")
    ).record()
    del record[field]
    with pytest.raises(ValueError):
        recorded_evidence_policy(record)
