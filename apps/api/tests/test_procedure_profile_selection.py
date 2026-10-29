"""A procedure-copy selection cannot disappear or bypass its required engines."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.config import Settings
from app.evidence_policy import resolve_evidence_policy
from pydantic import ValidationError

COPY = "source_declared_procedure_copy_v1"
STRICT = "all_units_nli_v1"


def configured(**changes):
    return Settings(
        **{
            "ANSWER_SELECTION_MODE": "reader",
            "ANSWER_SUPPORT_MODE": "local_nli",
            "GENERATION_MODE": "extractive",
            "PROCEDURE_VERIFICATION_PROFILE": COPY,
            **changes,
        }
    )


def test_existing_profile_serialization_and_library_default_are_preserved():
    config = Settings()
    assert getattr(config, "PROCEDURE_VERIFICATION_PROFILE", None) == STRICT
    assert resolve_evidence_policy(config).record() == {
        "contract": "evidence-profile-v1",
        "proposal_profile": "qa_only_v1",
        "role_scope_policy": "literal_v1",
        "origin_contract": "proposal-origin-v1",
        "role_policy_contract": "ordinary-session-activity-role-v1",
        "pattern_registry_contract": "disabled",
        "pattern_limits": {"per_source_requirement": 3, "per_requirement": 16},
    }


@pytest.mark.parametrize(
    "changes",
    [
        {"ANSWER_SELECTION_MODE": "lexical"},
        {"ANSWER_SUPPORT_MODE": "disabled"},
        {"GENERATION_MODE": "provider"},
        {"GENERATION_MODE": "legacy"},
        {"PROCEDURE_VERIFICATION_PROFILE": "trust_the_copied_answer"},
    ],
)
def test_combined_profile_configuration_rejects_missing_engines(changes):
    with pytest.raises(ValidationError):
        configured(**changes)


def test_selected_policy_is_versioned_and_snapshotted_per_request():
    config = configured()
    snapshot = resolve_evidence_policy(config)
    config.PROCEDURE_VERIFICATION_PROFILE = STRICT
    record = snapshot.record()
    assert record["contract"] == "evidence-profile-v2"
    assert record["procedure_verification_profile"] == COPY
    assert resolve_evidence_policy(config).record()["contract"] == "evidence-profile-v1"


@pytest.mark.parametrize(
    "changes",
    [
        {"ANSWER_SELECTION_MODE": "lexical"},
        {"ANSWER_SUPPORT_MODE": "disabled"},
        {"GENERATION_MODE": "provider"},
    ],
)
def test_mutable_library_settings_are_rechecked_before_request(changes):
    config = configured().model_copy(update=changes)
    with pytest.raises(ValueError):
        resolve_evidence_policy(config)


def test_health_exposes_selected_procedure_profile_without_loading_models(monkeypatch):
    from app.api import health

    monkeypatch.setattr(health, "get_settings", lambda: configured())
    metadata = health.runtime_metadata()
    assert metadata["evidence_profile"]["procedure_verification_profile"] == COPY
    assert metadata["evidence_profile"]["contract"] == "evidence-profile-v2"


def test_operator_option_reaches_process_environment_and_clears_inherited_choice(
    monkeypatch, tmp_path
):
    script = Path(__file__).resolve().parents[3] / "scripts/portfolio_local.py"
    spec = importlib.util.spec_from_file_location("procedure_profile_launcher", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cached = tmp_path / "cached-support"
    cached.mkdir()
    observed = []

    def dispatch(*_args, **kwargs):
        observed.append(kwargs["env"].get("PROCEDURE_VERIFICATION_PROFILE"))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", dispatch)
    monkeypatch.setenv("PROCEDURE_VERIFICATION_PROFILE", COPY)
    base = [
        "portfolio_local.py",
        "serve",
        "--data-dir",
        str(tmp_path / "data"),
        "--support-dir",
        str(cached),
    ]
    monkeypatch.setattr(sys, "argv", [*base, "--procedure-verification-profile", COPY])
    try:
        code = module.main()
    except SystemExit as exc:
        code = exc.code
    assert code == 0
    assert observed == [COPY]
    # Clear inherited copying through an explicit legacy choice, not a bare default.
    monkeypatch.setattr(
        sys, "argv", [*base, "--procedure-verification-profile", STRICT]
    )
    assert module.main() == 0
    assert observed == [COPY, STRICT]
