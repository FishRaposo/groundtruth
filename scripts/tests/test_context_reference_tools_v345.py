"""Explicit v2 launcher/evaluator/health contract; no live model acceptance."""

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.config import Settings
from app.evidence_policy import EvidencePolicy
from app.portfolio.comparison import evidence_profile_matches, validate_runtime_settings

ROOT = Path(__file__).resolve().parents[2]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "explicit,expected",
    [(True, "scoped_note_context_v2"), (False, "explicit_target_v1")],
)
def test_launcher_v2_is_explicit_and_default_clears_inherited_v2(
    monkeypatch, tmp_path, explicit, expected
):
    module = script("portfolio_local")
    observed = {}
    monkeypatch.setenv("SOURCE_CONTEXT_POLICY", "scoped_note_context_v2")

    def dispatch(*args, **kwargs):
        observed.update(kwargs["env"])
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", dispatch)
    argv = [
        "portfolio_local.py",
        "serve",
        "--data-dir",
        str(tmp_path),
        "--support-dir",
        str(tmp_path),
        "--procedure-verification-profile",
        "source_declared_procedure_copy_v1",
    ]
    if explicit:
        argv += ["--source-context-policy", "scoped_note_context_v2"]
    monkeypatch.setattr(sys, "argv", argv)
    assert module.main() == 0 and observed["SOURCE_CONTEXT_POLICY"] == expected


def test_evaluator_expected_v2_is_recorded_and_requires_matching_profile():
    module = script("evaluate_portfolio_retrieval")
    args = Namespace(
        split="development",
        expected_refusal_threshold=None,
        expected_reader_null_threshold=None,
        expected_reader_model_revision=None,
        expected_source_context_policy="scoped_note_context_v2",
    )
    settings = {
        "procedure_verification_profile": "source_declared_procedure_copy_v1",
        "answer_selection_mode": "reader",
        "answer_support_mode": "local_nli",
        "generation_mode": "extractive",
    }
    module.apply_setting_overrides(args, settings, True)
    assert settings["source_context_policy"] == "scoped_note_context_v2"
    assert validate_runtime_settings(settings) == settings
    for actual in (
        "explicit_target_v1",
        "scoped_note_context_v1",
        "scoped_note_context_v2",
    ):
        profile = EvidencePolicy(
            "qa_only_v1", "literal_v1", "source_declared_procedure_copy_v1", actual
        ).record()
        assert evidence_profile_matches({"evidence_profile": profile}, settings) is (
            actual == "scoped_note_context_v2"
        )


def test_health_metadata_exposes_distinct_v2_and_keeps_default_strict(monkeypatch):
    from app.api import health

    config = Settings(
        SOURCE_CONTEXT_POLICY="scoped_note_context_v2",
        PROCEDURE_VERIFICATION_PROFILE="source_declared_procedure_copy_v1",
        ANSWER_SELECTION_MODE="reader",
        ANSWER_SUPPORT_MODE="local_nli",
        GENERATION_MODE="extractive",
    )
    monkeypatch.setattr(health, "get_settings", lambda: config)
    profile = health.runtime_metadata()["evidence_profile"]
    assert (
        profile["contract"] == "evidence-profile-v4"
        and profile["source_context_contract"] == "source-note-context-v2"
    )
    assert Settings().SOURCE_CONTEXT_POLICY == "explicit_target_v1"
