"""Root-owned disposable typed acceptance process actions, never owner review data."""
import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

q = Path(__file__).resolve().parent.parent
w = q.parent / "delivery-worktree"
parser = argparse.ArgumentParser()
parser.add_argument("action", choices=("migrate", "serve", "seed"))
parser.add_argument("--margin", type=int, choices=range(5), required=True)
args = parser.parse_args()
out = q / "typed-connected-live-v378"
assert out.is_dir() and (out / "private").is_dir()
previous = json.loads((q / "development-v22-composite-activity-margin0-reranked/execution-settings.json").read_text())
spec = importlib.util.spec_from_file_location("typed_controller_environment", q / "development-controller-v346/controller.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
config = SimpleNamespace(source=w, output=out, embedding=Path(previous["embedding"]), reader=Path(previous["reader"]), support=Path(previous["support"]), margin=args.margin, proposal_profile="qa_plus_source_patterns_v1", role_scope_policy="ordinary_session_activity_v1", procedure_profile="source_declared_procedure_copy_v1", source_context_policy="scoped_note_context_v2")
env = module.environment(config)
python = q / "context-package-v329/optional-env/Scripts/python.exe"
if args.action == "migrate":
    assert not (out / "data/groundtruth.sqlite").exists(), "Never migrate another acceptance database"
    command = [str(python), "-B", "-m", "app.db.migrate"]
elif args.action == "seed":
    command = [str(python), "-B", str(q / "typed-connected-recipe-v368/seed_typed_acceptance.py"), "--worktree", str(w), "--inputs", str(q / "typed-connected-inputs-v360/manifest.json"), "--api-url", "http://127.0.0.1:8401", "--private-manifest", str(out / "private/seed.json"), "--expected-database-path", str(out / "data/groundtruth.sqlite"), "--embedding-mode", "local", "--support-margin", str(args.margin), "--execute-disposable-bootstrap"]
else:
    command = [str(python), "-B", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8401", "--no-access-log"]
record = out / (args.action + "-combined-v456-command.json")
with record.open("x", encoding="utf-8") as stream:
    json.dump({"command": command, "margin": args.margin, "environment_authority": "development-controller-v346/controller.py:environment", "port": 8401, "scope": "Fresh disposable engineering acceptance, no owner database or quality scoring"}, stream, indent=2)
child = subprocess.Popen(command, cwd=w, env=env, stdout=sys.stdout, stderr=sys.stderr, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
if args.action == "serve":
    (out / "api-combined-v456-process.json").write_text(json.dumps({"owned_pid": child.pid, "command": command, "port": 8401}) + "\n")
raise SystemExit(child.wait())
