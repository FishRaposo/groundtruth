"""Measured reader-serving defaults, explicit legacy recipes, no subprocess launch."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.config import Settings

ROOT = Path(__file__).resolve().parents[2]
PROFILE_KEYS = (
    "ANSWER_PROPOSAL_PROFILE",
    "ROLE_SCOPE_POLICY",
    "PROCEDURE_VERIFICATION_PROFILE",
    "SOURCE_CONTEXT_POLICY",
)
MEASURED = (
    "qa_plus_source_patterns_v1",
    "ordinary_session_activity_v1",
    "source_declared_procedure_copy_v1",
    "scoped_note_context_v2",
)
LEGACY = ("qa_only_v1", "literal_v1", "all_units_nli_v1", "explicit_target_v1")


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location(
        "measured_launcher_v375", ROOT / "scripts/portfolio_local.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    cached = tmp_path / ".tmp/models/support"
    cached.mkdir(parents=True)
    observed = []

    def dispatch(command, **kwargs):
        observed.append(
            {"command": command, "env": kwargs["env"], "cwd": kwargs["cwd"]}
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", dispatch)

    def invoke(*flags, action="serve"):
        monkeypatch.setattr(sys, "argv", ["portfolio_local.py", action, *flags])
        assert module.main() == 0
        return observed[-1]["env"]

    return invoke, observed


def profile(env):
    return tuple(env[key] for key in PROFILE_KEYS)


def test_bare_reader_serve_uses_measured_recipe_and_clears_inherited_expansion(
    launcher, monkeypatch
):
    invoke, _ = launcher
    for key in (*PROFILE_KEYS, "SUPPORT_MIN_MARGIN", "READER_NULL_THRESHOLD"):
        monkeypatch.setenv(key, "inherited_unknown")
    env = invoke()
    assert profile(env) == MEASURED
    assert env["READER_NULL_THRESHOLD"] == "4"
    assert env["SUPPORT_MIN_MARGIN"] == "2.0"
    assert (
        env["ANSWER_SELECTION_MODE"] == "reader"
        and env["ANSWER_SUPPORT_MODE"] == "local_nli"
    )


@pytest.mark.parametrize(
    "flag,value,index",
    [
        ("--answer-proposal-profile", "qa_plus_source_patterns_v1", 0),
        ("--role-scope-policy", "ordinary_session_activity_v1", 1),
        ("--procedure-verification-profile", "source_declared_procedure_copy_v1", 2),
        ("--source-context-policy", "explicit_target_v1", 3),
    ],
)
def test_any_explicit_profile_flag_preserves_legacy_peers_and_margin(
    launcher, flag, value, index
):
    invoke, _ = launcher
    env = invoke(flag, value)
    expected = list(LEGACY)
    expected[index] = value
    assert profile(env) == tuple(expected)
    assert env["SUPPORT_MIN_MARGIN"] == "4.0"


@pytest.mark.parametrize(
    "action,flags",
    [
        ("migrate", ()),
        ("seed", ()),
        ("serve", ("--answer-selection", "lexical")),
        ("serve", ("--embedding", "deterministic")),
        ("serve", ("--answer-support", "disabled")),
    ],
)
def test_nonreader_nonserve_and_explicit_disabled_preserve_legacy_behavior(
    launcher, action, flags
):
    invoke, _ = launcher
    env = invoke(*flags, action=action)
    assert profile(env) == LEGACY
    assert env["SUPPORT_MIN_MARGIN"] == "4.0"
    assert env["ANSWER_SUPPORT_MODE"] == "disabled"


@pytest.mark.parametrize("flags", [(), ("--answer-proposal-profile", "qa_only_v1")])
def test_explicit_support_margin_is_honored_for_both_recipes(launcher, flags):
    invoke, _ = launcher
    assert invoke(*flags, "--support-margin", "1")["SUPPORT_MIN_MARGIN"] == "1.0"


def test_explicit_minilm_and_reader_threshold_overrides_remain_available(launcher):
    invoke, _ = launcher
    assert invoke("--reader-model", "minilm")["READER_NULL_THRESHOLD"] == "-8"
    assert invoke("--reader-threshold", "7")["READER_NULL_THRESHOLD"] == "7.0"


def test_library_defaults_are_unchanged_by_launcher_recipe():
    config = Settings()
    assert (
        config.ANSWER_PROPOSAL_PROFILE,
        config.ROLE_SCOPE_POLICY,
        config.PROCEDURE_VERIFICATION_PROFILE,
        config.SOURCE_CONTEXT_POLICY,
    ) == LEGACY
    assert config.SUPPORT_MIN_MARGIN == 4.0
