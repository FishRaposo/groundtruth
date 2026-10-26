"""Connected launch defaults select the actual strict path, without downloads."""

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def invoke(monkeypatch, tmp_path):
    script = Path(__file__).resolve().parents[3] / "scripts/portfolio_local.py"
    spec = importlib.util.spec_from_file_location("default_evidence_launcher", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    observed = {}

    def dispatch(command, **kwargs):
        observed.update(
            {
                key: value
                for key, value in kwargs["env"].items()
                if key.startswith(("ANSWER_", "SUPPORT_"))
            }
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, "run", dispatch)

    def run(*extra, action="serve"):
        monkeypatch.setattr(sys, "argv", ["portfolio_local.py", action, *extra])
        return module.main(), observed

    return run, tmp_path


def test_default_reader_uses_pinned_cached_support(invoke):
    run, root = invoke
    cached = root / ".tmp/models/support"
    cached.mkdir(parents=True)
    result, observed = run()
    assert result == 0
    assert observed["ANSWER_SELECTION_MODE"] == "reader"
    assert observed["ANSWER_SUPPORT_MODE"] == "local_nli"
    assert Path(observed["SUPPORT_MODEL_PATH"]) == cached
    assert (
        observed["SUPPORT_MODEL_REVISION"] == "70de96bd327ef95839a8bd9f6299875cae396433"
    )


def test_missing_default_support_cache_fails_before_launch(invoke):
    run, root = invoke
    with pytest.raises(SystemExit) as error:
        run()
    assert error.value.code == 2
    assert not (root / ".tmp/portfolio").exists()


@pytest.mark.parametrize("action", ["migrate", "seed"])
def test_non_answering_commands_do_not_require_model_cache(invoke, action):
    run, _ = invoke
    result, observed = run(action=action)
    assert result == 0
    assert observed["ANSWER_SUPPORT_MODE"] == "disabled"


def test_explicit_portable_lexical_mode_needs_no_support_cache(invoke):
    run, _ = invoke
    result, observed = run("--embedding", "deterministic")
    assert result == 0
    assert observed["ANSWER_SELECTION_MODE"] == "lexical"
    assert observed["ANSWER_SUPPORT_MODE"] == "disabled"
