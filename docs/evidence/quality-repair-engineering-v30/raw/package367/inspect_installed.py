"""Read installed source closure and distribution metadata, never checkout app."""
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

import app

root = Path(__file__).resolve().parent
which = sys.argv[1]
assert which in {"base", "optional"}
assert (root / (which + "-env")).resolve() in Path(sys.executable).resolve().parents
app_root = Path(app.__file__).resolve().parent
assert (root / (which + "-env")).resolve() in app_root.parents
closure = json.loads((root / "stage-closure.json").read_text())["files"]
for name, expected in closure.items():
    actual = app_root.parent / name
    assert hashlib.sha256(actual.read_bytes()).hexdigest() == expected, name
distributions = {}
for distribution in importlib.metadata.distributions():
    record = distribution.read_text("RECORD") or ""
    distributions[distribution.metadata["Name"]] = {"version": distribution.version, "record_sha256": hashlib.sha256(record.encode()).hexdigest()}
target = root / (which + "-installed-runtime.json")
assert not target.exists()
target.write_text(json.dumps({"python": sys.version, "executable": sys.executable, "app_file": app.__file__, "matched_app_files": len(closure), "packages": distributions,
    "scope": "Actual installed app bytes match archive/source closure; distribution RECORD metadata, not installed-binary hashing"}, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"environment": which, "matched_app_files": len(closure), "distributions": len(distributions)}))
