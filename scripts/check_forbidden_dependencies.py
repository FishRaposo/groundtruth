"""Fail when a runtime artifact revives the retired shared-core dependency."""

from __future__ import annotations

import re
import sys
from os import walk
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    ROOT / "apps",
    ROOT / "examples",
    ROOT / "Makefile",
    ROOT / ".github",
    ROOT / "docker-compose.yml",
    ROOT / "docker-compose.prod.yml",
)
PATTERNS = (
    re.compile(r"\.\.[\\/]+(?:operator-)?shared-core", re.IGNORECASE),
    re.compile(
        r"git\+(?:https|ssh)://[^\s\"']+(?:operator-)?shared-core",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:operator-)?shared-core\s*(?:==|!=|<=|>=|~=|===|@)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:\bfile:/{0,3}|(?:^|\s)-e\s+|path\s*=\s*)[^\r\n]*"
        r"(?:operator-)?shared-core",
        re.IGNORECASE,
    ),
    re.compile(r"\bfrom\s+shared_core\b"),
    re.compile(r"\bimport\s+shared_core\b"),
)
SKIP_DIRECTORIES = {
    ".git",
    ".next",
    ".pytest-temp",
    ".venv",
    "__pycache__",
    "artifacts",
    "build",
    "dist",
    "node_modules",
    "playwright-report",
    "test-results",
}


def _files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    files: list[Path] = []
    for root, directories, filenames in walk(target):
        directories[:] = sorted(
            directory for directory in directories if directory not in SKIP_DIRECTORIES
        )
        files.extend(Path(root) / filename for filename in sorted(filenames))
    return files


def main() -> int:
    """Return nonzero with precise locations for actionable retired dependencies."""
    matches: list[str] = []
    for target in TARGETS:
        if not target.exists():
            continue
        for path in _files(target):
            if path.suffix in {".png", ".jpg", ".jpeg", ".gif", ".woff", ".woff2"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if any(pattern.search(line) for pattern in PATTERNS):
                    matches.append(f"{path.relative_to(ROOT)}:{line_number}: {line}")

    if matches:
        print("Retired external shared-core dependencies found:", file=sys.stderr)
        print("\n".join(matches), file=sys.stderr)
        return 1

    print("No actionable external shared-core dependencies found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
