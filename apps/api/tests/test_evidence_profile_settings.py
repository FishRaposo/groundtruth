"""Explicit eligibility profiles cannot silently disable their evidence gates."""

import pytest
from app.config import Settings
from pydantic import ValidationError


@pytest.mark.parametrize(
    "fields",
    [
        {"ANSWER_PROPOSAL_PROFILE": "automatic_fallback"},
        {"ROLE_SCOPE_POLICY": "all_ownership_is_permission"},
        {"ANSWER_PROPOSAL_PROFILE": "qa_plus_source_patterns_v1"},
        {"ROLE_SCOPE_POLICY": "ordinary_session_activity_v1"},
        {
            "ANSWER_PROPOSAL_PROFILE": "qa_plus_source_patterns_v1",
            "ANSWER_SELECTION_MODE": "reader",
            "ANSWER_SUPPORT_MODE": "disabled",
        },
        {
            "ROLE_SCOPE_POLICY": "ordinary_session_activity_v1",
            "ANSWER_SELECTION_MODE": "lexical",
            "ANSWER_SUPPORT_MODE": "local_nli",
        },
    ],
)
def test_invalid_or_unguarded_profile_is_rejected_at_configuration(fields):
    with pytest.raises(ValidationError):
        Settings(**fields)


def test_existing_defaults_are_explicit_qa_only_literal():
    settings = Settings()
    assert getattr(settings, "ANSWER_PROPOSAL_PROFILE", None) == "qa_only_v1"
    assert getattr(settings, "ROLE_SCOPE_POLICY", None) == "literal_v1"


@pytest.mark.parametrize(
    "proposal,role",
    [
        ("qa_only_v1", "literal_v1"),
        ("qa_only_v1", "ordinary_session_activity_v1"),
        ("qa_plus_source_patterns_v1", "literal_v1"),
        ("qa_plus_source_patterns_v1", "ordinary_session_activity_v1"),
    ],
)
def test_explicit_reader_and_nli_permit_each_separate_product_choice(proposal, role):
    settings = Settings(
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        ANSWER_PROPOSAL_PROFILE=proposal,
        ROLE_SCOPE_POLICY=role,
    )
    assert getattr(settings, "ANSWER_PROPOSAL_PROFILE", None) == proposal
    assert getattr(settings, "ROLE_SCOPE_POLICY", None) == role
