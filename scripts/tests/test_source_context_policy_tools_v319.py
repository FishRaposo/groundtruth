"""Public opt-in tooling policy binding; no server, model or label changes."""

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.evidence_policy import EvidencePolicy
from app.portfolio.comparison import evidence_profile_matches, validate_runtime_settings

ROOT = Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("policy", ["explicit_target_v1", "scoped_note_context_v1"])
def test_launcher_explicit_setting_clears_inherited_policy(
    monkeypatch, tmp_path, policy
):
    module = script("portfolio_local")
    observed = {}
    monkeypatch.setenv("SOURCE_CONTEXT_POLICY", "inherited_unknown")

    def dispatch(*args, **kwargs):
        observed.update(kwargs["env"])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", dispatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "portfolio_local.py",
            "serve",
            "--data-dir",
            str(tmp_path),
            "--support-dir",
            str(tmp_path),
            "--procedure-verification-profile",
            "source_declared_procedure_copy_v1",
            "--source-context-policy",
            policy,
        ],
    )
    assert module.main() == 0
    assert observed["SOURCE_CONTEXT_POLICY"] == policy


def test_evaluator_records_new_setting_only_when_explicit():
    module = script("evaluate_portfolio_retrieval")
    args = Namespace(
        split="development",
        expected_refusal_threshold=None,
        expected_reader_null_threshold=None,
        expected_reader_model_revision=None,
    )
    strict = {}
    module.apply_setting_overrides(args, strict, True)
    assert strict == {}
    args.expected_source_context_policy = "scoped_note_context_v1"
    module.apply_setting_overrides(args, strict, True)
    assert strict == {"source_context_policy": "scoped_note_context_v1"}


@pytest.mark.parametrize(
    "expected,actual,match",
    [
        (None, "explicit_target_v1", True),
        (None, "scoped_note_context_v1", False),
        ("scoped_note_context_v1", "explicit_target_v1", False),
        ("scoped_note_context_v1", "scoped_note_context_v1", True),
    ],
)
def test_runtime_profile_cannot_silently_expand_or_downgrade(expected, actual, match):
    profile = EvidencePolicy(
        "qa_only_v1", "literal_v1", "source_declared_procedure_copy_v1", actual
    ).record()
    settings = {"procedure_verification_profile": "source_declared_procedure_copy_v1"}
    if expected is not None:
        settings["source_context_policy"] = expected
    assert evidence_profile_matches({"evidence_profile": profile}, settings) is match


def test_context_runtime_requires_its_copy_engines():
    with pytest.raises(ValueError):
        validate_runtime_settings({"source_context_policy": "scoped_note_context_v1"})
