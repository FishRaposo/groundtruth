"""Run the repository's current canonical archive closure check read-only."""
import importlib.util

import package_gate as gate

spec = importlib.util.spec_from_file_location("canonical_closure_v367", gate.W / "scripts/check_wheel_contents.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.DIST = gate.OUT / "dist"
result = module.main()
gate.write("canonical-closure-result.json", {"exit": result, "source_sha256": gate.sha(gate.W / "scripts/check_wheel_contents.py")})
raise SystemExit(result)
