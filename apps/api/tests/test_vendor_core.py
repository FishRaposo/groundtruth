"""Regression coverage for the repository-local compatibility subset."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

VENDOR_ROOT = Path(__file__).resolve().parents[1] / "app" / "internal" / "vendor_core"


@pytest.mark.parametrize(
    "module_name",
    [
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
        "clients",
    ],
)
def test_vendor_core_modules_import_without_external_package(module_name: str) -> None:
    """The API's compatibility implementation is fully namespaced locally."""
    module = importlib.import_module(f"app.internal.vendor_core.{module_name}")

    assert module.__name__ == f"app.internal.vendor_core.{module_name}"
    assert Path(module.__file__).resolve().is_relative_to(VENDOR_ROOT)


def test_vendor_source_has_no_external_shared_core_imports() -> None:
    """Vendored modules must not revive the retired external namespace."""
    external_import = re.compile(r"\b(?:from|import)\s+shared_core\b")

    matches = [
        path
        for path in VENDOR_ROOT.glob("*.py")
        if external_import.search(path.read_text(encoding="utf-8"))
    ]

    assert matches == []
