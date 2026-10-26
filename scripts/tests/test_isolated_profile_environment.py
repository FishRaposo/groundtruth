"""Fresh wheel smoke cannot inherit a model-dependent development profile."""

import importlib.util
from pathlib import Path


def test_isolated_wheel_child_uses_explicit_portable_profile(monkeypatch, tmp_path):
    script = Path(__file__).parents[1] / "verify_isolated_wheel.py"
    spec = importlib.util.spec_from_file_location("isolated_profile_smoke", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "groundtruth-0.1.0-py3-none-any.whl").write_bytes(
        b"process-boundary fixture"
    )
    monkeypatch.setattr(module, "DIST", dist)
    for name, value in {
        "ANSWER_PROPOSAL_PROFILE": "qa_plus_source_patterns_v1",
        "ROLE_SCOPE_POLICY": "ordinary_session_activity_v1",
        "PROCEDURE_VERIFICATION_PROFILE": "source_declared_procedure_copy_v1",
        "ANSWER_SUPPORT_MODE": "local_nli",
    }.items():
        monkeypatch.setenv(name, value)
    observed = []

    def child(_argv, **kwargs):
        observed.append(kwargs["env"])

    monkeypatch.setattr(module.subprocess, "run", child)
    assert module.main() == 0
    assert len(observed) == 3
    for env in observed:
        assert env["ANSWER_SELECTION_MODE"] == "lexical"
        assert env.get("ANSWER_PROPOSAL_PROFILE") == "qa_only_v1"
        assert env.get("ROLE_SCOPE_POLICY") == "literal_v1"
        assert env.get("PROCEDURE_VERIFICATION_PROFILE") == "all_units_nli_v1"
        assert env.get("ANSWER_SUPPORT_MODE") == "disabled"
