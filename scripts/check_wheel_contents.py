"""Check that a built GroundTruth wheel carries its local vendor closure."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "apps" / "api" / "dist"
VENDOR_MODULES = (
    "__init__.py",
    "clients.py",
    "config.py",
    "database.py",
    "docparse.py",
    "embeddings.py",
    "errors.py",
    "evaljudge.py",
    "llmmetrics.py",
    "logging.py",
    "pricing.py",
    "tasks.py",
    "LICENSE",
)


def main() -> int:
    """Validate the newest wheel and report any missing vendor files."""
    wheels = sorted(
        DIST.glob("groundtruth-*.whl"), key=lambda path: path.stat().st_mtime
    )
    if not wheels:
        print(
            f"No GroundTruth wheel found. Run `python -m build apps/api` first: {DIST}"
        )
        return 1

    with zipfile.ZipFile(wheels[-1]) as archive:
        names = set(archive.namelist())

    missing = [
        module
        for module in VENDOR_MODULES
        if f"app/internal/vendor_core/{module}" not in names
    ]
    external = sorted(name for name in names if name.startswith("shared_core/"))
    if missing or external:
        if missing:
            print(
                f"Wheel is missing vendor modules: {', '.join(missing)}",
                file=sys.stderr,
            )
        if external:
            print(
                "Wheel unexpectedly packages external namespace: "
                f"{', '.join(external)}",
                file=sys.stderr,
            )
        return 1

    print(f"Wheel vendor closure verified: {wheels[-1].name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
