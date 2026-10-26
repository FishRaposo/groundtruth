"""New source-context eligibility must not leak into a base-wheel smoke."""

import contextlib
import importlib.util
from pathlib import Path


def test_isolated_wheel_overrides_inherited_context_policy(monkeypatch, tmp_path):
    path = Path(__file__).parents[1] / "verify_isolated_wheel.py"
    spec = importlib.util.spec_from_file_location("context_wheel_smoke", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "groundtruth-0.2.0-py3-none-any.whl").write_bytes(b"boundary only")
    monkeypatch.setattr(module, "DIST", dist)
    monkeypatch.setenv("SOURCE_CONTEXT_POLICY", "scoped_note_context_v1")

    @contextlib.contextmanager
    def temporary(**_kwargs):
        root = tmp_path / "smoke"
        root.mkdir()
        yield str(root)

    monkeypatch.setattr(module.tempfile, "TemporaryDirectory", temporary)
    captured = []
    monkeypatch.setattr(
        module.subprocess, "run", lambda _argv, **kwargs: captured.append(kwargs["env"])
    )
    assert module.main() == 0
    assert len(captured) == 3
    assert all(env["SOURCE_CONTEXT_POLICY"] == "explicit_target_v1" for env in captured)
