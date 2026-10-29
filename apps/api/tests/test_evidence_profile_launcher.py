"""Operator selections are explicit and inherited expansion is cleared."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    script = Path(__file__).resolve().parents[3] / "scripts/portfolio_local.py"
    spec = importlib.util.spec_from_file_location("evidence_profile_launcher", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observed = {}

    def dispatch(*args, **kwargs):
        observed.update(
            {
                key: value
                for key, value in kwargs["env"].items()
                if key in {"ANSWER_PROPOSAL_PROFILE", "ROLE_SCOPE_POLICY"}
            }
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", dispatch)
    model = tmp_path / "support"
    model.mkdir()

    def invoke(*extra):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "portfolio_local.py",
                "serve",
                "--data-dir",
                str(tmp_path / "data"),
                "--support-dir",
                str(model),
                *extra,
            ],
        )
        return module.main(), observed

    return invoke


def test_operator_can_select_composite_and_activity_policy_separately(launcher):
    result, env = launcher(
        "--answer-proposal-profile",
        "qa_plus_source_patterns_v1",
        "--role-scope-policy",
        "ordinary_session_activity_v1",
    )
    assert result == 0
    assert env == {
        "ANSWER_PROPOSAL_PROFILE": "qa_plus_source_patterns_v1",
        "ROLE_SCOPE_POLICY": "ordinary_session_activity_v1",
    }


def test_explicit_legacy_profile_clears_inherited_eligibility_expansion(
    launcher, monkeypatch
):
    monkeypatch.setenv("ANSWER_PROPOSAL_PROFILE", "qa_plus_source_patterns_v1")
    monkeypatch.setenv("ROLE_SCOPE_POLICY", "ordinary_session_activity_v1")
    # Bare reader serving is measured; this explicitly retains the legacy recipe.
    result, env = launcher("--answer-proposal-profile", "qa_only_v1")
    assert result == 0
    assert env == {
        "ANSWER_PROPOSAL_PROFILE": "qa_only_v1",
        "ROLE_SCOPE_POLICY": "literal_v1",
    }


def test_unguarded_expansion_is_rejected_before_dispatch(launcher):
    with pytest.raises(SystemExit) as error:
        launcher(
            "--answer-proposal-profile",
            "qa_plus_source_patterns_v1",
            "--answer-support",
            "disabled",
        )
    assert error.value.code == 2
