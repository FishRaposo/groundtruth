"""Version new request semantics without retroactively changing factual v3."""

import pytest
from app.config import Settings
from app.evidence_policy import EvidencePolicy, reading_version, resolve_evidence_policy
from app.services.requirement_contract import validate_discovery_lineage
from pydantic import ValidationError

CONTROLS = {
    "ANSWER_SELECTION_MODE": "reader",
    "ANSWER_SUPPORT_MODE": "local_nli",
    "GENERATION_MODE": "extractive",
    "ANSWER_PROPOSAL_PROFILE": "qa_plus_source_patterns_v1",
    "ROLE_SCOPE_POLICY": "ordinary_session_activity_v1",
    "PROCEDURE_VERIFICATION_PROFILE": "source_declared_procedure_copy_v1",
    "SOURCE_CONTEXT_POLICY": "scoped_note_context_v2",
    "EVIDENCE_READING_PROFILE": "contextual_source_v2",
}


def test_new_linguistic_profile_has_a_distinct_captured_contract():
    config = Settings(**CONTROLS, REQUEST_PARSER_MODE="local_dependency")
    policy = resolve_evidence_policy(config)
    assert policy.contextual_source
    assert policy.requirement_contract == "requirement-evidence-v4"
    record = policy.record()
    assert record["contract"] == "evidence-profile-v6"
    assert record["request_plan_contract"] == "linguistic-request-plan-v1"
    assert record["request_parser_mode"] == "local_dependency"
    assert record["request_parser_contract"] == "dependency-request-capture-v1"
    assert record["scope_document_limit"] == 128
    assert reading_version("contextual_source_v2").output == "procedure-output-cover-v6"


def test_linguistic_profile_requires_its_actual_parser_mode():
    with pytest.raises(ValidationError, match="local_dependency"):
        Settings(**CONTROLS)


def test_dependency_parser_cannot_silently_run_as_the_legacy_reader():
    with pytest.raises(ValidationError, match="contextual_source_v2"):
        Settings(REQUEST_PARSER_MODE="local_dependency")


@pytest.mark.parametrize("change", [None, "contract", "typed_limit", "parser"])
def test_new_discovery_metadata_is_typed_and_contract_bound(change):
    policy = resolve_evidence_policy(
        Settings(**CONTROLS, REQUEST_PARSER_MODE="local_dependency")
    )
    record = {
        "contract": policy.requirement_contract,
        "evidence_profile": policy.record(),
        "requirements": [],
        "inspected_sources": [],
        "proposals": [],
        "qa_observations": [],
        "selected_proposal_ids": [],
    }
    if change == "contract":
        record["contract"] = "requirement-evidence-v999"
    elif change == "typed_limit":
        record["evidence_profile"]["scope_document_limit"] = 128.0
    elif change == "parser":
        record["evidence_profile"]["request_parser_mode"] = []
    assert validate_discovery_lineage(record)["valid"] is (change is None)
    # Metadata discovery validity is not a completed answer/output certificate.


@pytest.mark.parametrize(
    "key,value",
    [
        ("ANSWER_SELECTION_MODE", "lexical"),
        ("ANSWER_SUPPORT_MODE", "disabled"),
        ("GENERATION_MODE", "provider"),
        ("ANSWER_PROPOSAL_PROFILE", "qa_only_v1"),
        ("ROLE_SCOPE_POLICY", "literal_v1"),
        ("PROCEDURE_VERIFICATION_PROFILE", "all_units_nli_v1"),
        ("SOURCE_CONTEXT_POLICY", "explicit_target_v1"),
    ],
)
def test_new_parser_never_bypasses_the_existing_engines(key, value):
    with pytest.raises(ValidationError):
        Settings(**{**CONTROLS, key: value}, REQUEST_PARSER_MODE="local_dependency")


def test_old_factual_profile_and_library_defaults_keep_their_recorded_identity():
    old = EvidencePolicy(
        "qa_plus_source_patterns_v1",
        "ordinary_session_activity_v1",
        "source_declared_procedure_copy_v1",
        "scoped_note_context_v2",
        "contextual_source_v1",
    ).record()
    assert old["contract"] == "evidence-profile-v5"
    assert old["requirement_contract"] == "requirement-evidence-v3"
    assert old["request_plan_contract"] == "contextual-request-plan-v1"
    assert old["output_contract"] == "procedure-output-cover-v5"
    assert "request_parser_mode" not in old and "request_parser_contract" not in old
    config = Settings()
    assert config.EVIDENCE_READING_PROFILE == "clause_bound_v1"
    assert config.REQUEST_PARSER_MODE == "bounded"


@pytest.mark.parametrize("count", [0, 2049, True])
def test_parser_question_limit_cannot_truncate_the_request(count):
    with pytest.raises(ValidationError):
        Settings(REQUEST_PARSER_MAX_CHARS=count)
