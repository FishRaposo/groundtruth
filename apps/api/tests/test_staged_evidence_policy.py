"""Version registry distinguishes staged request semantics from old evidence."""

import pytest
from app.evidence_policy import (
    EvidencePolicy,
    reading_version,
    recorded_evidence_policy,
    source_copy_version,
    validate_evidence_engines,
)


def controls():
    return {
        "proposal": "qa_plus_source_patterns_v1",
        "role": "ordinary_session_activity_v1",
        "reader": "reader",
        "support": "local_nli",
        "procedure": "source_declared_procedure_copy_v1",
        "generation": "extractive",
        "context": "scoped_note_context_v2",
        "reading": "contextual_source_v3",
        "request_parser": "local_dependency",
        "quantity": "literal_source_count_v1",
    }


def test_staged_profile_has_own_immutable_version_and_count_dispatch():
    validate_evidence_engines(**controls())
    staged = reading_version("contextual_source_v3")
    old = reading_version("contextual_source_v2")
    assert staged.request_plan == "staged-request-plan-v1"
    assert staged.requirement == "requirement-evidence-v5"
    assert staged.procedure == "complete-immutable-procedure-v6"
    assert staged.output == "procedure-output-cover-v8"
    assert staged.evidence_profile == "evidence-profile-v8"
    assert staged != old
    policy = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        "contextual_source_v3",
        "literal_source_count_v1",
    )
    assert policy.staged_request and policy.dependency_reading
    assert policy.output_contract == staged.output
    assert policy.record()["contract"] == staged.evidence_profile
    assert recorded_evidence_policy(policy.record()).record() == policy.record()
    assert source_copy_version(reading_profile=staged.profile).policy == (
        source_copy_version(reading_profile=old.profile).policy
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("request_parser", "bounded"),
        ("reader", "lexical"),
        ("support", "disabled"),
        ("generation", "provider"),
        ("proposal", "qa_only_v1"),
        ("role", "literal_v1"),
        ("procedure", "all_units_nli_v1"),
        ("context", "explicit_target_v1"),
    ],
)
def test_staged_profile_requires_all_evidence_engines(key, value):
    chosen = controls()
    chosen[key] = value
    with pytest.raises(ValueError):
        validate_evidence_engines(**chosen)


def test_old_count_record_and_library_defaults_keep_their_contracts():
    old = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        "contextual_source_v2",
        "literal_source_count_v1",
    )
    assert old.record()["contract"] == "evidence-profile-v7"
    assert old.output_contract == "procedure-output-cover-v7"
    assert old.record()["request_plan_contract"] == "linguistic-request-plan-v1"
    assert not old.staged_request and old.dependency_reading
    default = EvidencePolicy("qa_only_v1", "literal_v1")
    assert not default.staged_request and not default.dependency_reading
    assert default.record()["contract"] == "evidence-profile-v1"
