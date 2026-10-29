"""Contextual reading is explicit, versioned and unable to bypass its engines."""

import pytest
from app.config import Settings
from app.evidence_policy import resolve_evidence_policy


def contextual_settings(**changes):
    return Settings(
        **{
            "EVIDENCE_READING_PROFILE": "contextual_source_v1",
            "ANSWER_SELECTION_MODE": "reader",
            "ANSWER_SUPPORT_MODE": "local_nli",
            "GENERATION_MODE": "extractive",
            "ANSWER_PROPOSAL_PROFILE": "qa_plus_source_patterns_v1",
            "ROLE_SCOPE_POLICY": "ordinary_session_activity_v1",
            "PROCEDURE_VERIFICATION_PROFILE": "source_declared_procedure_copy_v1",
            "SOURCE_CONTEXT_POLICY": "scoped_note_context_v2",
            **changes,
        }
    )


def test_contextual_profile_cannot_silently_be_ignored_by_legacy_engines():
    with pytest.raises(ValueError, match="Contextual source reading"):
        contextual_settings(
            ANSWER_SELECTION_MODE="lexical",
            ANSWER_SUPPORT_MODE="disabled",
            GENERATION_MODE="legacy",
            ANSWER_PROPOSAL_PROFILE="qa_only_v1",
            ROLE_SCOPE_POLICY="literal_v1",
            PROCEDURE_VERIFICATION_PROFILE="all_units_nli_v1",
            SOURCE_CONTEXT_POLICY="explicit_target_v1",
        )


@pytest.mark.parametrize(
    "change",
    [
        {"ANSWER_PROPOSAL_PROFILE": "qa_only_v1"},
        {"ROLE_SCOPE_POLICY": "literal_v1"},
        {"SOURCE_CONTEXT_POLICY": "explicit_target_v1"},
    ],
)
def test_contextual_profile_requires_the_declared_compound_contract(change):
    with pytest.raises(ValueError, match="Contextual source reading"):
        contextual_settings(**change)


def test_contextual_profile_records_its_distinct_identity():
    policy = resolve_evidence_policy(contextual_settings())
    record = policy.record()
    assert record["contract"] == "evidence-profile-v5"
    assert record["evidence_reading_profile"] == "contextual_source_v1"
    assert record["requirement_contract"] == "requirement-evidence-v3"
    assert record["request_plan_contract"] == "contextual-request-plan-v1"
    assert record["scope_cover_contract"] == "declared-source-scope-cover-v1"
    assert record["role_manifest_contract"] == "declared-context-role-manifest-v1"
    assert record["procedure_contract"] == "complete-immutable-procedure-v4"
    assert record["output_contract"] == "procedure-output-cover-v5"


def test_unknown_reading_profile_fails_instead_of_using_legacy():
    with pytest.raises(ValueError):
        contextual_settings(EVIDENCE_READING_PROFILE="unrecognized")


def test_library_defaults_and_existing_context_record_remain_legacy():
    default = resolve_evidence_policy(Settings())
    assert "evidence_reading_profile" not in default.record()
    legacy = resolve_evidence_policy(
        contextual_settings(EVIDENCE_READING_PROFILE="clause_bound_v1")
    )
    assert legacy.record() == {
        "contract": "evidence-profile-v4",
        "proposal_profile": "qa_plus_source_patterns_v1",
        "role_scope_policy": "ordinary_session_activity_v1",
        "origin_contract": "proposal-origin-v1",
        "role_policy_contract": "ordinary-session-activity-role-v1",
        "pattern_registry_contract": "typed-source-patterns-v1",
        "pattern_limits": {"per_source_requirement": 3, "per_requirement": 16},
        "procedure_verification_profile": "source_declared_procedure_copy_v1",
        "source_context_policy": "scoped_note_context_v2",
        "source_context_contract": "source-note-context-v2",
    }
