"""Schedule the independently reviewed controller; preserve every invocation."""
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
version = f"v{args.source_version}"
source_manifest = q / f"requirements-source-{version}.json"
output_name = f"development-{version}-combined-composite-activity-margin{args.margin}-{args.method}"
output = q / output_name
launch_record = q / f"{output_name}.launch.json"
assert source_manifest.is_file() and not output.exists() and not launch_record.exists()
command = [previous["python"], "-B", str(q / "development-controller-v219/controller.py")]
values = {
    "source": str(q / f"requirements-source-{version}"),
    "source-manifest": str(source_manifest),
    "source-manifest-sha256": hashlib.sha256(source_manifest.read_bytes()).hexdigest(),
    "corpus": previous["corpus"],
    "corpus-manifest-sha256": previous["corpus_manifest_sha256"],
    "common-manifest-sha256": previous["common_manifest_sha256"],
    "output": str(output),
    "python": previous["python"],
    "embedding": previous["embedding"],
    "reader": previous["reader"],
    "support": previous["support"],
    "margin": str(args.margin),
    "proposal-profile": "qa_plus_source_patterns_v1",
    "role-scope-policy": "ordinary_session_activity_v1",
    "procedure-profile": "source_declared_procedure_copy_v1",
    "method": args.method,
}
for key, value in values.items():
    command.extend(["--" + key, value])
with launch_record.open("x", encoding="utf-8") as stream:
    json.dump({"command": command, "scope": "Development only; not blind acceptance"}, stream, indent=2)
with (q / f"{output_name}.controller.log").open("x", encoding="utf-8") as log:
    result = subprocess.run(command, cwd=q.parent / "delivery-worktree", stdout=log, stderr=subprocess.STDOUT, check=False)
print(json.dumps({"output": str(output), "controller_exit": result.returncode}))
raise SystemExit(result.returncode)
