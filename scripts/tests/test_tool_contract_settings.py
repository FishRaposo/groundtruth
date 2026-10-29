"""Explicit development settings and supported evidence contract authority."""

import copy
import importlib.util
from argparse import Namespace
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "tool_settings_evaluator",
    Path(__file__).parents[1] / "evaluate_portfolio_retrieval.py",
)
EVALUATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATOR)


def metadata_fixture(**extra):
    args = Namespace(
        split="development",
        selection=None,
        execution_arm="candidate",
        require_answer_spans=True,
        expected_refusal_threshold=0.35,
        expected_reader_null_threshold=4,
        expected_reader_model_revision="reader-pin",
        **extra,
    )
    corpus = {
        "manifest": {
            "schema_version": 2,
            "manifest_sha256": "a" * 64,
            "expected_counts": {"development": {"answerable": 0}},
        },
        "profile": {
            "schema_version": 2,
            "corpus_role": "development",
            "revision": "invented-metadata-only",
            "note": "No execution knobs",
        },
    }
    return args, corpus, {"corpus_manifest_sha256": "a" * 64}


def test_metadata_only_development_uses_explicit_top_k_without_mutation():
    args, corpus, seed = metadata_fixture(expected_top_k=5)
    original = copy.deepcopy(corpus)
    coverage, selection, settings = EVALUATOR.evaluation_settings(args, corpus, seed)
    assert coverage is True and selection is None
    assert settings["top_k"] == 5 and settings["refusal_threshold"] == 0.35
    assert corpus == original


def test_metadata_only_development_requires_explicit_top_k():
    args, corpus, seed = metadata_fixture()
    with pytest.raises(ValueError, match="top_k"):
        EVALUATOR.evaluation_settings(args, corpus, seed)


@pytest.mark.parametrize("value", [4, 6, True, 5.0, "5"])
def test_invalid_direct_top_k_override_is_rejected(value):
    args, corpus, seed = metadata_fixture(expected_top_k=value)
    with pytest.raises(ValueError, match="top_k"):
        EVALUATOR.evaluation_settings(args, corpus, seed)


def test_top_k_override_does_not_replace_contradictory_frozen_profile():
    args, corpus, seed = metadata_fixture(expected_top_k=5)
    corpus["profile"]["top_k"] = 3
    with pytest.raises(ValueError, match="top_k"):
        EVALUATOR.evaluation_settings(args, corpus, seed)


def test_top_k_override_is_development_only():
    args, _, _ = metadata_fixture(expected_top_k=5)
    args.split = "held_out"
    with pytest.raises(ValueError, match="development"):
        EVALUATOR.apply_setting_overrides(args, {"top_k": 5}, True)


@pytest.mark.parametrize("value", ["4", "6", "5.0"])
def test_cli_rejects_invalid_top_k_before_reading_inputs(monkeypatch, value):
    import sys

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate",
            "--seed-manifest",
            "unused",
            "--output",
            "unused",
            "--expected-top-k",
            value,
        ],
    )
    with pytest.raises(SystemExit) as error:
        EVALUATOR.main()
    assert error.value.code == 2


def test_cli_accepts_explicit_top_k_and_reaches_input_boundary(monkeypatch):
    import sys

    calls = []

    def unavailable(path):
        calls.append(path)
        raise ValueError("Invented input boundary unavailable")

    monkeypatch.setattr(EVALUATOR, "load_corpus", unavailable)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate",
            "--seed-manifest",
            "unused",
            "--output",
            "unused",
            "--expected-top-k",
            "5",
        ],
    )
    assert EVALUATOR.main() == 2
    assert calls == [None]


@pytest.mark.parametrize(
    "contract", ["requirement-evidence-v1", "requirement-evidence-v2"]
)
def test_known_historical_contract_settings_remain_readable(contract):
    from app.portfolio.comparison import validate_runtime_settings

    assert validate_runtime_settings({"selection_contract": contract}) == {
        "selection_contract": contract
    }


def test_unknown_contract_settings_reject_before_source_rescoring():
    from app.portfolio.comparison import validate_runtime_settings

    with pytest.raises(ValueError, match="contract"):
        validate_runtime_settings({"selection_contract": "unsupported-evidence-v999"})


def test_unknown_development_contract_override_rejects_before_questions():
    args, corpus, seed = metadata_fixture(
        expected_top_k=5, expected_selection_contract="unsupported-evidence-v999"
    )
    # Supply fixed top_k so this assertion isolates the contract, not P158's CLI flag.
    corpus["profile"]["top_k"] = 5
    with pytest.raises(ValueError, match="contract"):
        EVALUATOR.evaluation_settings(args, corpus, seed)
