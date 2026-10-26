"""Summarize existing margin2 observations and hash v390 artifacts only."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
record = json.loads((ROOT / "workflow/result.json").read_text())
stability = json.loads((ROOT / "stability.json").read_text())
assert stability["unchanged"] is True
assert record["selected_margin"] == 2 and record["reader_threshold"] == 4
profile = record["ready"]["runtime"]
assert profile["embedding"] == {
    "mode": "local", "model": "sentence-transformers/all-MiniLM-L6-v2",
    "revision": "1110a243fdf4706b3f48f1d95db1a4f5529b4d41", "dimension": 384,
    "chunking": "minilm-tokenizer-v1",
}
assert profile["evidence_support"]["minimum_entailment_margin"] == 2
summary = {
    "scope": "Candidate-profile installed-wheel engineering, not model quality or authorization/browser/live-server acceptance",
    "selected_margin": 2, "reader_threshold": 4, "outcome": record["response"]["outcome"],
    "output_contract": record["response"]["provenance"]["answer_selection"]["requirements"][0]["procedure_completeness"]["output_certificate"]["contract"],
    "actual_nli_units": record["actual_nli_units"], "profile": profile,
    "stability": stability, "commands": json.loads((ROOT / "results.json").read_text()),
}
with (ROOT / "summary.json").open("x", encoding="utf-8") as target:
    json.dump(summary, target, indent=2)
    target.write("\n")
paths = [path for path in ROOT.rglob("*") if path.is_file() and "uploads" not in path.parts and "temp" not in path.parts and "__pycache__" not in path.parts]
hashes = {path.relative_to(ROOT).as_posix(): {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in sorted(paths) if path.name != "artifact-manifest.json"}
with (ROOT / "artifact-manifest.json").open("x", encoding="utf-8") as target:
    json.dump({"scope": "v390-only explicit artifacts, not old environment or a public bundle", "files": hashes}, target, indent=2)
    target.write("\n")
print(json.dumps({"artifact_records": len(hashes), "selected_margin": 2, "unchanged": stability["unchanged"]}))
