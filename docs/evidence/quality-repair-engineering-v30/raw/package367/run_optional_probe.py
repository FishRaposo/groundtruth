"""Launch exactly one installed-wheel cache-only CPU workflow after pip check."""
import json

import package_gate as gate

assert json.loads((gate.OUT / "optional-install-2-result.json").read_text())["exit"] == 0
python = str(gate.OUT / "optional-env/Scripts/python.exe")
inspection = gate.command("optional-installed-inspection", [python, "-I", str(gate.OUT / "inspect_installed.py"), "optional"])
if inspection:
    raise SystemExit(inspection)
raise SystemExit(gate.command("optional-workflow", [python, "-I", str(gate.OUT / "probe_optional.py")]))
