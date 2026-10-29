"""Version boundary for capture-preserving interpretation, never model quality."""

import hashlib
import json

import pytest
from app.config import Settings
from app.evidence_policy import resolve_evidence_policy


def configured(reading="contextual_source_v4", **changes):
    values = {
        "ANSWER_SELECTION_MODE": "reader",
        "ANSWER_SUPPORT_MODE": "local_nli",
        "GENERATION_MODE": "extractive",
        "ANSWER_PROPOSAL_PROFILE": "qa_plus_source_patterns_v1",
        "ROLE_SCOPE_POLICY": "ordinary_session_activity_v1",
        "PROCEDURE_VERIFICATION_PROFILE": "source_declared_procedure_copy_v1",
        "SOURCE_CONTEXT_POLICY": "scoped_note_context_v2",
        "EVIDENCE_READING_PROFILE": reading,
        "REQUEST_PARSER_MODE": "local_dependency",
        "QUANTITY_VERIFICATION_PROFILE": "literal_source_count_v1",
        "READER_MODEL_PATH": "UNITONLY-configuration-does-not-load-assets",
        "SUPPORT_MODEL_PATH": "UNITONLY-configuration-does-not-load-assets",
        "REQUEST_PARSER_MODEL_PATH": "UNITONLY-configuration-does-not-load-assets",
    }
    values.update(changes)
    return Settings(_env_file=None, **values)


def test_new_interpretation_is_explicit_and_carries_its_full_version_boundary():
    # A new policy must not be reported using the old request/output contracts.
    policy, failure = None, None
    try:
        policy = resolve_evidence_policy(configured())
    except ValueError as exc:
        failure = type(exc).__name__
    assert policy is not None, (
        f"Explicit capture-preserving policy unavailable: {failure}"
    )
    record = policy.record()
    assert record["contract"] == "evidence-profile-v9"
    assert record["requirement_contract"] == "requirement-evidence-v5"
    assert record["request_input_contract"] == "staged-request-inputs-v2"
    assert record["request_plan_contract"] == "staged-request-plan-v2"
    assert record["scope_cover_contract"] == "declared-source-scope-cover-v3"
    assert record["role_manifest_contract"] == "declared-context-role-manifest-v4"
    assert record["procedure_contract"] == "complete-immutable-procedure-v7"
    assert record["output_contract"] == "procedure-output-cover-v9"
    assert record["source_production_contract"] == "captured-source-productions-v1"
    assert record["fact_context_contract"] == "captured-governing-context-v1"
    assert policy.staged_request and policy.dependency_reading


def test_recorded_old_profile_does_not_acquire_the_new_interpretation():
    # Hash captured from the actual failed917 API profile, before this change.
    record = resolve_evidence_policy(configured("contextual_source_v3")).record()
    raw = json.dumps(
        record,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode()
    assert hashlib.sha256(raw).hexdigest() == (
        "c3705f87dafa4511117c5adb95fe8f3c19705014ca86f6808603e4c51f997d8a"
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"ANSWER_SUPPORT_MODE": "disabled"},
        {"ANSWER_SELECTION_MODE": "lexical"},
        {"GENERATION_MODE": "provider"},
        {"REQUEST_PARSER_MODE": "bounded"},
    ],
)
def test_new_interpretation_cannot_bypass_required_evidence_engines(changes):
    with pytest.raises(ValueError):
        resolve_evidence_policy(configured(**changes))
