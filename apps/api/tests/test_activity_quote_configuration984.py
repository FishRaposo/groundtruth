"""Explicit owner-selected scope mode must survive configuration and comparison."""

import pytest
from app.config import Settings
from app.evidence_policy import recorded_evidence_policy, resolve_evidence_policy
from app.portfolio.comparison import evidence_profile_matches, validate_runtime_settings

from tests.test_captured_policy928 import configured


def test_activity_quote_is_explicit_and_recorded_not_a_library_default():
    config = configured(
        SOURCE_GOVERNANCE_PROFILE="requirement_bound_v1",
        PROCEDURE_SCOPE_PROFILE="activity_quote_v1",
    )
    assert getattr(config, "PROCEDURE_SCOPE_PROFILE", None) == "activity_quote_v1"
    policy = resolve_evidence_policy(config)
    assert policy.record()["procedure_scope_profile"] == "activity_quote_v1"
    assert recorded_evidence_policy(policy.record()) == policy
    default = Settings(_env_file=None)
    assert default.PROCEDURE_SCOPE_PROFILE == "requested_scope_v1"
    assert "procedure_scope_profile" not in resolve_evidence_policy(default).record()


@pytest.mark.parametrize("value", [None, True, "activity_quote_v2"])
def test_unknown_scope_mode_is_not_ignored(value):
    with pytest.raises(ValueError):
        configured(PROCEDURE_SCOPE_PROFILE=value)


@pytest.mark.parametrize(
    "change",
    [
        {"ANSWER_SUPPORT_MODE": "disabled"},
        {"GENERATION_MODE": "provider"},
        {"ANSWER_SELECTION_MODE": "lexical"},
        {"SOURCE_GOVERNANCE_PROFILE": "all_sources_v1"},
    ],
)
def test_quote_profile_keeps_required_engines(change):
    values = {
        "SOURCE_GOVERNANCE_PROFILE": "requirement_bound_v1",
        "PROCEDURE_SCOPE_PROFILE": "activity_quote_v1",
    }
    values.update(change)
    with pytest.raises(ValueError):
        configured(**values)


def test_runtime_validator_rejects_unknown_quote_mode():
    with pytest.raises(ValueError):
        validate_runtime_settings({"procedure_scope_profile": "invented"})


def test_comparison_requires_recorded_scope_and_matches_the_explicit_mode():
    settings = {"procedure_scope_profile": "activity_quote_v1"}
    assert not evidence_profile_matches({}, settings)
    policy = resolve_evidence_policy(
        configured(
            SOURCE_GOVERNANCE_PROFILE="requirement_bound_v1",
            PROCEDURE_SCOPE_PROFILE="activity_quote_v1",
        )
    )
    selection = {
        "contract": policy.record()["requirement_contract"],
        "evidence_profile": policy.record(),
    }
    settings.update(
        procedure_verification_profile="source_declared_procedure_copy_v1",
        source_context_policy="scoped_note_context_v2",
    )
    assert evidence_profile_matches(selection, settings)
    assert not evidence_profile_matches(
        selection, {**settings, "procedure_scope_profile": "requested_scope_v1"}
    )
