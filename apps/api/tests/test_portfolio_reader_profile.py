"""The portable launcher's actual default must use the selected reader profile."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]


def run_profile(monkeypatch, tmp_path, extra=()):
    specification = importlib.util.spec_from_file_location(
        "portfolio_reader_profile_under_test", ROOT / "scripts/portfolio_local.py"
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    observed = {}

    def dispatch(command, **kwargs):
        observed.update(command=command, **kwargs)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", dispatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "portfolio_local.py",
            "serve",
            "--data-dir",
            str(tmp_path / "data"),
            "--port",
            "8402",
            *extra,
        ],
    )
    monkeypatch.setenv("OPENAI_API_KEY", "disposable-test-sentinel")
    monkeypatch.setenv("READER_MODEL_REVISION", "stale-inherited-revision")
    assert module.main() == 0
    return observed


def test_default_connected_profile_is_measured_roberta(monkeypatch, tmp_path):
    result = run_profile(monkeypatch, tmp_path)
    env = result["env"]
    assert env["READER_MODEL_REVISION"] == "adc3b06f79f797d1c575d5479d6f5efe54a9e3b4"
    assert (
        Path(env["READER_MODEL_PATH"])
        == (ROOT / ".tmp/models/reader-roberta").resolve()
    )
    assert float(env["READER_NULL_THRESHOLD"]) == 4
    assert env["ANSWER_SELECTION_MODE"] == "reader"
    assert env["OPENAI_API_KEY"] == ""
    assert "127.0.0.1" in result["command"] and "8402" in result["command"]


def test_explicit_minilm_retains_legacy_profile(monkeypatch, tmp_path):
    env = run_profile(monkeypatch, tmp_path, ["--reader-model", "minilm"])["env"]
    assert env["READER_MODEL_REVISION"] == "934656cdda79824eabf503ed56e15c01ddbdbe3f"
    assert Path(env["READER_MODEL_PATH"]) == (ROOT / ".tmp/models/reader").resolve()
    assert float(env["READER_NULL_THRESHOLD"]) == -8


def test_directory_and_zero_threshold_are_explicit_overrides(monkeypatch, tmp_path):
    directory = tmp_path / "configured-reader"
    env = run_profile(
        monkeypatch,
        tmp_path,
        [
            "--reader-dir",
            str(directory),
            "--reader-threshold",
            "0",
            "--embedding",
            "deterministic",
            "--answer-selection",
            "lexical",
        ],
    )["env"]
    assert Path(env["READER_MODEL_PATH"]) == directory.resolve()
    assert float(env["READER_NULL_THRESHOLD"]) == 0
    assert env["ANSWER_SELECTION_MODE"] == "lexical"
