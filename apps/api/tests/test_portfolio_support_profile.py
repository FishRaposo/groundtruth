"""Explicit compatibility profiles retain bounded local configuration."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def launcher(monkeypatch, tmp_path):
    specification = importlib.util.spec_from_file_location(
        "portfolio_support_profile_under_test", ROOT / "scripts/portfolio_local.py"
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    observed = {}

    def dispatch(command, **kwargs):
        # Never retain unrelated host environment values in pytest failure reprs.
        observed["command"] = command
        observed["env"] = {
            key: value
            for key, value in kwargs["env"].items()
            if key.startswith(("ANSWER_", "SUPPORT_", "READER_"))
            or key in {"HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"}
        }
        return SimpleNamespace(returncode=0)

    def invoke(*extra):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "portfolio_local.py",
                "serve",
                "--data-dir",
                str(tmp_path / "data"),
                *extra,
            ],
        )
        return module.main()

    monkeypatch.setattr(module.subprocess, "run", dispatch)
    return invoke, observed


def test_explicit_legacy_profile_clears_inherited_support_without_changing_reader(
    launcher, monkeypatch
):
    invoke, observed = launcher
    monkeypatch.setenv("ANSWER_SUPPORT_MODE", "local_nli")
    monkeypatch.setenv("SUPPORT_MODEL_PATH", "stale-inherited-model")
    monkeypatch.setenv("SUPPORT_MODEL_REVISION", "main")
    monkeypatch.setenv("SUPPORT_MIN_MARGIN", "nan")
    assert invoke("--answer-support", "disabled") == 0
    env = observed["env"]
    assert env["ANSWER_SUPPORT_MODE"] == "disabled"
    assert env["SUPPORT_MODEL_PATH"] == ""
    assert env["SUPPORT_MODEL_REVISION"] == "70de96bd327ef95839a8bd9f6299875cae396433"
    assert float(env["SUPPORT_MIN_MARGIN"]) == 4
    assert env["ANSWER_SELECTION_MODE"] == "reader"
    assert float(env["READER_NULL_THRESHOLD"]) == 4


def test_explicit_local_support_options_preserve_explicit_reader_overrides(
    launcher, tmp_path
):
    invoke, observed = launcher
    model = tmp_path / "support"
    model.mkdir()
    assert (
        invoke(
            "--answer-support",
            "local_nli",
            "--support-dir",
            str(model),
            "--support-margin",
            "0",
            "--reader-model",
            "minilm",
            "--reader-threshold",
            "0",
            "--embedding",
            "deterministic",
            "--answer-selection",
            "lexical",
        )
        == 0
    )
    env = observed["env"]
    assert env["ANSWER_SUPPORT_MODE"] == "local_nli"
    assert Path(env["SUPPORT_MODEL_PATH"]) == model.resolve()
    assert float(env["SUPPORT_MIN_MARGIN"]) == 0
    assert env["SUPPORT_MODEL_REVISION"] == "70de96bd327ef95839a8bd9f6299875cae396433"
    assert env["READER_MODEL_REVISION"] == "934656cdda79824eabf503ed56e15c01ddbdbe3f"
    assert float(env["READER_NULL_THRESHOLD"]) == 0
    assert env["ANSWER_SELECTION_MODE"] == "lexical"
    assert env["HF_HUB_OFFLINE"] == "1"
    assert env["TRANSFORMERS_OFFLINE"] == "1"


def test_directory_option_does_not_change_explicit_lexical_mode(launcher, tmp_path):
    invoke, observed = launcher
    assert invoke("--answer-selection", "lexical", "--support-dir", str(tmp_path)) == 0
    assert observed["env"]["ANSWER_SUPPORT_MODE"] == "disabled"
    assert observed["env"]["SUPPORT_MODEL_PATH"] == ""


@pytest.mark.parametrize("path_kind", ["omitted", "absent", "file"])
def test_local_support_requires_explicit_existing_directory(
    launcher, tmp_path, capsys, path_kind
):
    invoke, observed = launcher
    args = ["--answer-support", "local_nli"]
    if path_kind != "omitted":
        path = tmp_path / "support"
        if path_kind == "file":
            path.write_text("not a directory")
        args.extend(["--support-dir", str(path)])
    with pytest.raises(SystemExit) as error:
        invoke(*args)
    assert error.value.code == 2
    assert "support-dir" in capsys.readouterr().err
    assert observed == {}
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("margin", ["-1", "5", "nan", "inf", "-inf"])
def test_support_margin_rejects_nonfinite_or_outside_grid_before_dispatch(
    launcher, capsys, margin
):
    invoke, observed = launcher
    with pytest.raises(SystemExit) as error:
        invoke(f"--support-margin={margin}")
    assert error.value.code == 2
    assert "support-margin" in capsys.readouterr().err
    assert observed == {}
