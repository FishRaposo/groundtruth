"""Collecting literal-pattern tests must not replace the application package."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "filename",
    [
        "test_source_pattern_grammar.py",
        "test_contextual_mixed_output.py",
        "test_contextual_source_proof.py",
        "test_linguistic_source_scope.py",
    ],
)
def test_literal_pattern_module_preserves_normal_package_initialization(filename):
    test_module = Path(__file__).with_name(filename)
    api = Path(__file__).parents[1]
    script = """
import importlib.util, pathlib, sys, app
spec = importlib.util.spec_from_file_location('collection_only_pattern', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert getattr(app, 'services', None) is sys.modules['app.services']
assert pathlib.Path(app.services.__file__).name == '__init__.py'
print('canonical package retained')
"""
    env = {
        **os.environ,
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "PYTHONPATH": str(api),
    }
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(test_module)],
        env=env,
        cwd=api,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "canonical package retained"
