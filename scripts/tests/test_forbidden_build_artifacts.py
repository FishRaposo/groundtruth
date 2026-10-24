"""Disposable production builds must not become dependency-scan inputs."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "dependency_scan", ROOT / "scripts/check_forbidden_dependencies.py"
)
assert SPEC and SPEC.loader
SCAN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCAN)


def test_coverage_build_is_excluded_but_application_source_is_scanned(tmp_path):
    app = tmp_path / "apps"
    output = app / "web/.next-coverage/standalone"
    output.mkdir(parents=True)
    (output / "generated.js").write_text("generated", encoding="utf-8")
    source = app / "web/source.ts"
    source.write_text("import shared_core", encoding="utf-8")
    assert SCAN._files(app) == [source]
    assert any(pattern.search(source.read_text()) for pattern in SCAN.PATTERNS)
