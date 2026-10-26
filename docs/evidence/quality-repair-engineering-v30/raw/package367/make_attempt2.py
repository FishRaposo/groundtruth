"""Keep attempt1 intact; derive one corrected, explicitly scoped scratch probe."""
from pathlib import Path

root = Path(__file__).resolve().parent
old = (root / "probe_optional.py").read_text(encoding="utf-8")
assert old.count('OUT = ROOT / "optional-workflow"') == 1
assert old.count('assert proof["output_certificate"]["contract"] == "procedure-output-cover-v4"') == 1
new = old.replace('OUT = ROOT / "optional-workflow"', 'OUT = ROOT / "optional-workflow-2"').replace(
    'assert proof["output_certificate"]["contract"] == "procedure-output-cover-v4"',
    '# Frozen procedure_output emits v1 for this exact Cedar/no-inventory case.\n'
    '        assert "condition_exclusion_inventory" not in proof\n'
    '        assert proof["output_certificate"]["contract"] == "procedure-output-cover-v1"',
)
with (root / "probe_optional_attempt2.py").open("x", encoding="utf-8") as output:
    output.write(new)
