"""Explicit locked-runtime typed-context DEV launcher; never reuse output names."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

q = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("--source-version", type=int, required=True)
parser.add_argument("--margin", type=int, choices=range(5), required=True)
parser.add_argument("--method", choices=("keyword", "vector", "hybrid", "reranked", "all"), default="reranked")
args = parser.parse_args()
previous = json.loads((q / "development-v22-composite-activity-margin0-reranked/execution-settings.json").read_text())
python = q / "context-package-v329/optional-env/Scripts/python.exe"
source = q / f"requirements-source-v{args.source_version}"
manifest = q / f"requirements-source-v{args.source_version}.json"
name = f"development-v{args.source_version}-typed-context-v2-locked329-margin{args.margin}-{args.method}"
output, launch = q / name, q / f"{name}.launch.json"
assert manifest.is_file() and not output.exists() and not launch.exists() and python.is_file()
command = [str(python), "-B", str(q / "development-controller-v346/controller.py")]
values = {
    "source": str(source), "source-manifest": str(manifest),
    "source-manifest-sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
    "corpus": previous["corpus"], "corpus-manifest-sha256": previous["corpus_manifest_sha256"],
    "common-manifest-sha256": previous["common_manifest_sha256"], "output": str(output), "python": str(python),
    "embedding": previous["embedding"], "reader": previous["reader"], "support": previous["support"],
    "margin": str(args.margin), "proposal-profile": "qa_plus_source_patterns_v1", "role-scope-policy": "ordinary_session_activity_v1",
    "procedure-profile": "source_declared_procedure_copy_v1", "source-context-policy": "scoped_note_context_v2", "method": args.method,
}
for key, value in values.items():
    command.extend(["--" + key, value])
with launch.open("x", encoding="utf-8") as stream:
    json.dump({"command": command, "purpose": "Frozen typed-reference development only; not blind or final quality acceptance",
               "controller_sha256": hashlib.sha256((q / "development-controller-v346/controller.py").read_bytes()).hexdigest(),
               "launcher_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, stream, indent=2)
with (q / f"{name}.controller.log").open("x", encoding="utf-8") as log:
    result = subprocess.run(command, cwd=q.parent / "delivery-worktree", stdout=log, stderr=subprocess.STDOUT, check=False)
print(json.dumps({"output": str(output), "controller_exit": result.returncode}))
raise SystemExit(result.returncode)
