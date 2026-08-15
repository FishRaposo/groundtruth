"""Packaging and self-containment contracts for the GroundTruth API."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import tomllib

API_ROOT = Path(__file__).resolve().parents[1]
ROOT = API_ROOT.parents[1]
VENDOR_ROOT = API_ROOT / "app" / "internal" / "vendor_core"
PINNED_COMMIT = "dbf276a7708da65b55e1f10b35af634b300d1f07"
VENDOR_MODULES = {
    "clients",
    "config",
    "database",
    "docparse",
    "embeddings",
    "errors",
    "evaljudge",
    "llmmetrics",
    "logging",
    "pricing",
    "tasks",
}


def _dependency_name(requirement: str) -> str:
    """Return the normalized project name from a PEP 508 requirement."""
    match = re.match(r"[A-Za-z0-9_.-]+", requirement)
    assert match is not None
    return match.group(0).lower().replace("_", "-")


def test_infrastructure_and_model_dependencies_are_opt_in() -> None:
    """The default wheel stays lightweight and offline-importable."""
    metadata = tomllib.loads((API_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = metadata["project"]
    base = {_dependency_name(item) for item in project["dependencies"]}
    extras = {
        name: {_dependency_name(item) for item in requirements}
        for name, requirements in project["optional-dependencies"].items()
    }

    optional = {
        "asyncpg",
        "pgvector",
        "redis",
        "pdfplumber",
        "python-docx",
        "beautifulsoup4",
        "numpy",
        "sentence-transformers",
    }
    assert base.isdisjoint(optional)
    assert {"asyncpg", "pgvector"} <= extras["postgres"]
    assert {"redis"} <= extras["redis"]
    assert {"pdfplumber", "python-docx", "beautifulsoup4"} <= extras["parsers"]
    assert {"numpy", "sentence-transformers"} <= extras["embeddings"]


def test_app_imports_without_optional_integrations() -> None:
    """Importing the API in SQLite mode must not load optional integrations."""
    code = """
import importlib.abc
import sys

blocked = {
    "asyncpg", "pgvector", "redis", "pdfplumber", "docx", "bs4",
    "numpy", "sentence_transformers",
}

class BlockOptional(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".", 1)[0] in blocked:
            raise ModuleNotFoundError(f"optional dependency loaded: {fullname}")
        return None

sys.meta_path.insert(0, BlockOptional())
import app.main
print("optional-free app import OK")
"""
    env = os.environ.copy()
    env["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().endswith("optional-free app import OK")


def test_vendor_attribution_and_license_are_distributable() -> None:
    """The pinned source and full upstream MIT terms ship beside the code."""
    notice = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
    license_text = (VENDOR_ROOT / "LICENSE").read_text(encoding="utf-8")

    assert PINNED_COMMIT in notice
    assert "FishRaposo/operator-shared-core" in notice
    assert "Copyright (c) 2026 Operator Systems" in license_text
    assert "Permission is hereby granted, free of charge" in license_text
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in license_text


def test_ci_enforces_self_contained_package_contract() -> None:
    """Default CI checks the wheel while infrastructure tests remain opt-in."""
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "python scripts/check_forbidden_dependencies.py" in workflow
    assert "python -m build apps/api" in workflow
    assert "python scripts/check_wheel_contents.py" in workflow
    assert "python scripts/verify_isolated_wheel.py" in workflow
    assert "github.event_name == 'workflow_dispatch'" in workflow


def test_wheel_checks_cover_the_complete_vendor_closure() -> None:
    """Both archive and isolated-import checks cover every vendored module."""
    wheel_check = (ROOT / "scripts" / "check_wheel_contents.py").read_text(
        encoding="utf-8"
    )
    import_check = (ROOT / "scripts" / "verify_isolated_wheel.py").read_text(
        encoding="utf-8"
    )

    for module in VENDOR_MODULES:
        assert f'"{module}.py"' in wheel_check
        assert f"app.internal.vendor_core.{module}" in import_check
    assert '"LICENSE"' in wheel_check
