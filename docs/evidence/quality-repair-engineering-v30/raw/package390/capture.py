"""Read-only installed/source/model bindings; all observations go to v390."""
import hashlib
import importlib.metadata
import json
import sys
from pathlib import Path

import app

OUT = Path(__file__).resolve().parent
Q = OUT.parent
PACKAGE = Q / "context-package-v367"
ENV = PACKAGE / "optional-env"
assert ENV.resolve() in Path(sys.executable).resolve().parents
assert ENV.resolve() in Path(app.__file__).resolve().parents
assert sys.dont_write_bytecode, "Require -B to preserve the old environment"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture() -> dict:
    closure = json.loads((PACKAGE / "stage-closure.json").read_text())["files"]
    app_root = Path(app.__file__).resolve().parent.parent
    installed = {}
    for name, expected in closure.items():
        actual = sha(app_root / name)
        assert actual == expected, name
        installed[name] = actual
    assert len(installed) == 191
    packages = {}
    for distribution in importlib.metadata.distributions():
        record = distribution.read_text("RECORD") or ""
        packages[distribution.metadata["Name"]] = {
            "version": distribution.version,
            "record_sha256": hashlib.sha256(record.encode()).hexdigest(),
        }
    baseline = json.loads((PACKAGE / "optional-installed-runtime.json").read_text())
    assert packages == baseline["packages"], "Installed runtime changed from v367"
    records = {}
    previous = json.loads((PACKAGE / "artifact-manifest.json").read_text())["files"]
    for relative, expected in previous.items():
        actual = sha(PACKAGE / relative)
        assert actual == expected["sha256"], relative
        records[str(PACKAGE / relative)] = actual
    for path in (
        PACKAGE / "artifact-manifest.json",
        Q / "typed-margin-independent-v373/REPORT.md",
        Q / "typed-margin-independent-v373/audit-result.json",
        Q / "development-v30-typed-context-v2-locked329-margin2-reranked/execution-settings.json",
        Q / "requirements-source-v30.json",
    ):
        records[str(path)] = sha(path)
    assert records[str(Q / "requirements-source-v30.json")] == "fd0e693629aaae190d1d3759784d857a77bac0e45c4fa5b45a83d3efd1879772"
    selected = json.loads((Q / "development-v30-typed-context-v2-locked329-margin2-reranked/execution-settings.json").read_text())
    assert selected["margin"] == 2 and selected["settings"]["support_min_margin"] == 2
    assert selected["settings"]["reader_null_threshold"] == 4
    for model in selected["model_binding"].values():
        root = Path(model["root"])
        assert sha(root / model["manifest"]) == model["manifest_sha256"]
        records[str(root / model["manifest"])] = model["manifest_sha256"]
        for relative, expected in model["files"].items():
            actual = sha(root / relative)
            assert actual == expected, relative
            records[str(root / relative)] = actual
    return {
        "scope": "Read-only 191 installed app files, installed distribution version/RECORD metadata, retained v367 artifacts and selected exact cached models; not full installed-binary hashing",
        "python": sys.version, "executable": sys.executable, "app_file": app.__file__,
        "installed_app_files": installed, "packages": packages, "upstream_files": records,
    }


phase = sys.argv[1]
assert phase in {"before", "after"}
observed = capture()
with (OUT / ("installed-runtime-" + phase + ".json")).open("x", encoding="utf-8") as target:
    json.dump(observed, target, indent=2)
    target.write("\n")
if phase == "after":
    before = json.loads((OUT / "installed-runtime-before.json").read_text())
    unchanged = before == observed
    with (OUT / "stability.json").open("x", encoding="utf-8") as target:
        json.dump({"unchanged": unchanged, "installed_app_files": len(observed["installed_app_files"]), "distributions": len(observed["packages"]), "upstream_file_records": len(observed["upstream_files"])}, target, indent=2)
        target.write("\n")
    assert unchanged, "Read-only upstream changed"
print(json.dumps({"phase": phase, "installed_app_files": len(observed["installed_app_files"]), "distributions": len(observed["packages"]), "upstream_file_records": len(observed["upstream_files"])}))
