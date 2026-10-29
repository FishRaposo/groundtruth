"""Run bounded read-only reuse of the v367 installed optional environment."""
import json
import os
import subprocess
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
PYTHON = OUT.parent / "context-package-v367/optional-env/Scripts/python.exe"
assert OUT.name == "context-installed-candidate-v390"
env = os.environ.copy()
for key in list(env):
    if key.upper().startswith(("PIP_", "UV_", "OPENAI_", "ANTHROPIC_", "AZURE_OPENAI_", "GOOGLE_API", "GEMINI_")):
        del env[key]
for key in ("PYTHONPATH", "PYTHONHOME"):
    env.pop(key, None)
(OUT / "temp").mkdir(exist_ok=True)
env.update(TEMP=str(OUT / "temp"), TMP=str(OUT / "temp"), HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PYTHONDONTWRITEBYTECODE="1")
commands = [
    ("before", [str(PYTHON), "-I", "-B", str(OUT / "capture.py"), "before"]),
    ("workflow", [str(PYTHON), "-I", "-B", str(OUT / "probe.py")]),
    ("after", [str(PYTHON), "-I", "-B", str(OUT / "capture.py"), "after"]),
]
with (OUT / "invocation.json").open("x", encoding="utf-8") as target:
    json.dump({"commands": [{"phase": name, "command": command} for name, command in commands], "cwd": str(OUT), "scope": "Read-only installed wheel, selected margin2 engineering only"}, target, indent=2)
    target.write("\n")
results = []
for phase, command in commands:
    if phase == "workflow" and results[0]["exit"]:
        continue
    with (OUT / (phase + ".log")).open("x", encoding="utf-8") as log:
        result = subprocess.run(command, cwd=OUT, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    record = {"phase": phase, "command": command, "exit": result.returncode, "log": phase + ".log"}
    results.append(record)
    with (OUT / (phase + "-result.json")).open("x", encoding="utf-8") as target:
        json.dump(record, target, indent=2)
        target.write("\n")
    print(json.dumps(record), flush=True)
with (OUT / "results.json").open("x", encoding="utf-8") as target:
    json.dump(results, target, indent=2)
    target.write("\n")
raise SystemExit(int(any(result["exit"] for result in results)))
