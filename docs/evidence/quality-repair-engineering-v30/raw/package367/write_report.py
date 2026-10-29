"""Aggregate this gate's existing observations without changing upstream state."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
Q = ROOT.parent
W = Q.parent / "delivery-worktree"
D = W / ".venv/Scripts/python.exe"
records = []
for invocation in sorted(ROOT.glob("*-invocation.json")):
    phase = invocation.name.removesuffix("-invocation.json")
    result = ROOT / (phase + "-result.json")
    if result.is_file():
        records.append({"phase": phase, **json.loads(invocation.read_text()), **json.loads(result.read_text())})
records.extend([
    {"phase": "stage", "command": [str(D), "-B", str(ROOT / "package_gate.py"), "stage"], "exit": 0},
    {"phase": "extra-assets-before", "command": [str(D), "-B", str(ROOT / "package_gate.py"), "extra-before"], "exit": 0},
    {"phase": "archives-first", "command": [str(D), "-B", str(ROOT / "package_gate.py"), "archives"], "exit": 1, "observation": "Sandbox ACL prevented opening new archive; retained archive-first-failed.json"},
    {"phase": "archives-permission-retry", "command": [str(D), "-B", str(ROOT / "package_gate.py"), "archives"], "exit": 0, "result": "archive-check.json"},
    {"phase": "canonical-closure", "command": [str(D), "-B", str(ROOT / "check_native_closure.py")], "exit": 0, "result": "canonical-closure-result.json"},
    {"phase": "base-installed-inspection", "command": [str(ROOT / "base-env/Scripts/python.exe"), "-I", str(ROOT / "inspect_installed.py"), "base"], "exit": 0, "result": "base-installed-runtime.json"},
    {"phase": "attempt2-preparation", "command": [str(D), "-B", str(ROOT / "make_attempt2.py")], "exit": 0},
    {"phase": "final-upstream-hashes", "command": [str(D), "-B", str(ROOT / "package_gate.py"), "finalize"], "exit": 0, "result": "upstream-stability.json"},
    {"phase": "uv-version", "command": [str(Q / "integration/tooling/bin/uv.exe"), "--version"], "exit": 0, "log": "uv-version.log"},
])
(ROOT / "commands-and-results.json").write_text(json.dumps({"date": "2026-10-26", "scope": "Independent local package engineering; not quality acceptance", "commands": records}, indent=2) + "\n", encoding="utf-8")
files = list(ROOT.glob("*.py")) + list(ROOT.glob("*.json")) + list(ROOT.glob("*.log")) + list(ROOT.glob("*.txt")) + list(ROOT.glob("*.md"))
files += list((ROOT / "dist").glob("*"))
for directory in ("optional-workflow", "optional-workflow-2"):
    files += [path for path in (ROOT / directory).glob("*") if path.is_file() and path.suffix in {".json", ".sqlite"}]
manifest = {str(path.relative_to(ROOT)): {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(set(files)) if path.name != "artifact-manifest.json"}
(ROOT / "artifact-manifest.json").write_text(json.dumps({"scope": "Explicit artifacts only; caches/envs/staging are not a public bundle", "files": manifest}, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"command_records": len(records), "artifact_records": len(manifest)}))
