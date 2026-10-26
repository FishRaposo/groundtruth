"""New attempt after correcting one frozen-authority no-inventory expectation."""
import json

import package_gate as gate

assert json.loads((gate.OUT / "optional-install-2-result.json").read_text())["exit"] == 0
assert json.loads((gate.OUT / "optional-workflow-result.json").read_text())["exit"] == 1
raise SystemExit(gate.command("optional-workflow-2", [str(gate.OUT / "optional-env/Scripts/python.exe"), "-I", str(gate.OUT / "probe_optional_attempt2.py")]))
