"""Verify copied direct-command observations, without executing their runner."""
import hashlib
import json
from pathlib import Path
root=Path(__file__).resolve().parent
m=json.loads((root/"manifest.json").read_text(encoding="utf-8"))
for name,row in m["files"].items():
    p=(root/name).resolve(strict=True)
    assert p.is_relative_to(root) and p.is_file()
    data=p.read_bytes()
    assert len(data)==row["bytes"] and hashlib.sha256(data).hexdigest()==row["sha256"]
r=json.loads((root/"RESULT.json").read_text(encoding="utf-8"))
assert r["wrapper_exit"]==0 and {c["gate"]:c["exit"] for c in r["commands"]}==m["native_gate_results"]
assert r["source_inventory"]==232 and r["source_before_after_equal"] and r["source_after_equals_frozen232"] and r["bundle818_before_after_equal"]
for stem in ("source","bundle","generated-prerequisites"):
    assert json.loads((root/(stem+"-before.json")).read_text(encoding="utf-8"))==json.loads((root/(stem+"-after.json")).read_text(encoding="utf-8"))
print("Verified direct TypeScript/ESLint observations, zero exits and unchanged source/packet bindings; no native rerun or quality claim.")
