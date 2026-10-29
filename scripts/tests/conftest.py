"""Script-contract tests share the API test helpers and ``app`` modules.

The API package is installed as a locked (non-editable) project, so the
sibling ``tests`` package is not importable on its own. Put ``apps/api`` on
``sys.path`` so ``tests.*`` helpers resolve the same way they do when the
suite runs from ``apps/api``.
"""

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[2] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))
