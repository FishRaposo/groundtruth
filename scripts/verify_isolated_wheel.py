"""Install the built API wheel in a fresh environment and import its entrypoints."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "apps" / "api" / "dist"
IMPORTS = """\
import app.main
import app.config
import app.db.session
import app.internal.vendor_core.config
import app.internal.vendor_core.database
import app.internal.vendor_core.docparse
import app.internal.vendor_core.embeddings
import app.internal.vendor_core.errors
import app.internal.vendor_core.evaljudge
import app.internal.vendor_core.llmmetrics
import app.internal.vendor_core.logging
import app.internal.vendor_core.pricing
import app.internal.vendor_core.tasks
import app.internal.vendor_core.clients
import importlib.util
assert importlib.util.find_spec("shared_core") is None
"""


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def main() -> int:
    """Install only the wheel and declared dependencies in a fresh virtualenv."""
    wheels = sorted(
        DIST.glob("groundtruth-*.whl"), key=lambda path: path.stat().st_mtime
    )
    if not wheels:
        print(
            f"No GroundTruth wheel found. Run `python -m build apps/api` first: {DIST}"
        )
        return 1

    with tempfile.TemporaryDirectory(prefix="groundtruth-wheel-") as directory:
        environment = Path(directory) / "venv"
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True)
        python = _venv_python(environment)
        subprocess.run(
            [str(python), "-m", "pip", "install", str(wheels[-1])],
            check=True,
        )
        env = os.environ.copy()
        env["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
        subprocess.run([str(python), "-I", "-c", IMPORTS], check=True, env=env)

    print("Isolated wheel imports verified without an external shared_core package.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
