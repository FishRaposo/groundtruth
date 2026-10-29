"""Explicit staged launch selection; no model loading or process launch."""

import argparse
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def launcher():
    script = Path(__file__).resolve().parents[3] / "scripts/portfolio_local.py"
    spec = importlib.util.spec_from_file_location(
        "staged_launch_options_unitonly", script
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def selected():
    return SimpleNamespace(
        answer_proposal_profile="qa_plus_source_patterns_v1",
        role_scope_policy="ordinary_session_activity_v1",
        answer_selection="reader",
        answer_support="local_nli",
        procedure_verification_profile="source_declared_procedure_copy_v1",
        source_context_policy="scoped_note_context_v2",
        evidence_reading_profile="contextual_source_v3",
        quantity_verification_profile="literal_source_count_v1",
        support_margin=2,
        support_dir=Path(__file__).parent,
        request_parser_dir=Path(__file__).parent,
    )


def test_explicit_staged_profile_selects_dependency_validation():
    actual = launcher()
    options = selected()
    actual.validate_support_options(argparse.ArgumentParser(), options)
    actual.validate_parser_options(argparse.ArgumentParser(), options)


def test_explicit_staged_profile_needs_a_cached_parser_directory():
    actual = launcher()
    options = selected()
    options.request_parser_dir = None
    with pytest.raises(SystemExit) as error:
        actual.validate_parser_options(argparse.ArgumentParser(), options)
    assert error.value.code == 2
