"""Bounded v367 package gate; all mutations remain below this new directory."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent
Q = OUT.parent
W = Q.parent / "delivery-worktree"
SOURCE = Q / "requirements-source-v30"
D = W / ".venv/Scripts/python.exe"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name: str, value: object) -> None:
    target = OUT / name
    with target.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")


def clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key.upper().startswith(("PIP_", "UV_", "OPENAI_", "ANTHROPIC_", "AZURE_OPENAI_", "GOOGLE_API", "GEMINI_")):
            del env[key]
    for key in ("PYTHONPATH", "PYTHONHOME"):
        env.pop(key, None)
    for directory in ("temp", "pip-cache", "uv-cache"):
        (OUT / directory).mkdir(exist_ok=True)
    env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PIP_CONFIG_FILE=os.devnull,
               PIP_CACHE_DIR=str(OUT / "pip-cache"), TEMP=str(OUT / "temp"), TMP=str(OUT / "temp"))
    return env


def command(name: str, args: list[str], *, env: dict[str, str] | None = None, cwd: Path = OUT) -> int:
    write(name + "-invocation.json", {"command": args, "cwd": str(cwd), "qualification": "Package engineering only; not quality acceptance"})
    with (OUT / (name + ".log")).open("x", encoding="utf-8") as log:
        result = subprocess.run(args, cwd=cwd, env=env or clean_env(), stdout=log, stderr=subprocess.STDOUT, check=False)
    write(name + "-result.json", {"exit": result.returncode, "log": name + ".log"})
    print(json.dumps({"phase": name, "exit": result.returncode}), flush=True)
    return result.returncode


def upstream() -> dict:
    frozen = json.loads((Q / "requirements-source-v30.json").read_text())["files"]
    records = {}
    for name, expected in frozen.items():
        actual = sha(SOURCE / name)
        if actual != expected:
            raise ValueError("Frozen source manifest differs: " + name)
        records[str(SOURCE / name)] = actual
        if name.startswith("apps/api/app/"):
            if sha(W / name) != expected:
                raise ValueError("Current app differs from source30: " + name)
            records[str(W / name)] = expected
    for relative in ("apps/api/pyproject.toml", "apps/api/uv.lock", "apps/api/README.md", "apps/api/LICENSE", "apps/api/requirements.txt", "scripts/verify_isolated_wheel.py", "scripts/check_wheel_contents.py"):
        records[str(W / relative)] = sha(W / relative)
    for relative in ("requirements-source-v30.json", "check_context_wheel_v329.py", "install_context_optional_wheel_v329.py", "run_context_base_wheel_v338.py", "probe_context_optional_wheel_v337.py", "context-package-v329/base-runtime-constraints.txt", "context-package-v329/model-runtime-constraints.txt", "development-v30-typed-context-v2-locked329-margin0-reranked/execution-settings.json"):
        records[str(Q / relative)] = sha(Q / relative)
    settings = json.loads((Q / "development-v30-typed-context-v2-locked329-margin0-reranked/execution-settings.json").read_text())
    for model in settings["model_binding"].values():
        root = Path(model["root"])
        records[str(root / model["manifest"])] = sha(root / model["manifest"])
        if records[str(root / model["manifest"])] != model["manifest_sha256"]:
            raise ValueError("Cached model manifest differs")
        for relative, expected in model["files"].items():
            actual = sha(root / relative)
            if actual != expected:
                raise ValueError("Cached model file differs: " + relative)
            records[str(root / relative)] = actual
    runtime = {}
    for alias, site in (("D", W / ".venv/Lib/site-packages"), ("old329", Q / "context-package-v329/optional-env/Lib/site-packages")):
        runtime[alias] = {}
        for distribution in importlib.metadata.distributions(path=[str(site)]):
            name = distribution.metadata["Name"]
            record = distribution.read_text("RECORD") or ""
            runtime[alias][name] = {"version": distribution.version, "record_sha256": hashlib.sha256(record.encode()).hexdigest()}
    return {"files": records, "runtime_distributions": runtime, "scope": "Read-only upstream files, exact cached models and D/old329 distribution RECORD metadata; not installed-binary hashing"}


def stage() -> None:
    write("upstream-before.json", upstream())
    target = OUT / "staged-api"
    target.mkdir()
    frozen = json.loads((Q / "requirements-source-v30.json").read_text())["files"]
    copied = {}
    for name, expected in frozen.items():
        if not name.startswith("apps/api/app/"):
            continue
        relative = name.removeprefix("apps/api/")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / name, destination)
        if sha(destination) != expected:
            raise ValueError("Staged source bytes differ")
        copied[relative] = expected
    # Explicit packaging assets not necessarily present in the source-code freeze.
    for source in (W / "apps/api/app").rglob("*"):
        if not source.is_file() or "__pycache__" in source.parts or source.suffix == ".pyc":
            continue
        relative = source.relative_to(W / "apps/api").as_posix()
        if relative not in copied:
            counterpart = SOURCE / "apps/api" / relative
            if counterpart.is_file() and sha(counterpart) != sha(source):
                raise ValueError("Unlisted source asset differs from frozen snapshot")
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            copied[relative] = sha(source)
    for name in ("pyproject.toml", "uv.lock", "README.md", "LICENSE", "requirements.txt"):
        shutil.copyfile(W / "apps/api" / name, target / name)
    write("stage-closure.json", {"files": copied, "frozen_app_members": sum(name.startswith("apps/api/app/") for name in frozen), "packaging": {name: sha(target / name) for name in ("pyproject.toml", "uv.lock", "README.md", "LICENSE", "requirements.txt")}})
    print(json.dumps({"staged_app_members": len(copied)}))


def archives() -> None:
    wheel, = (OUT / "dist").glob("*.whl")
    sdist, = (OUT / "dist").glob("*.tar.gz")
    closure = json.loads((OUT / "stage-closure.json").read_text())["files"]
    with zipfile.ZipFile(wheel) as archive, tarfile.open(sdist) as source:
        prefix, = {member.name.split("/")[0] for member in source.getmembers()}
        actual = {name for name in archive.namelist() if name.startswith("app/") and not name.endswith("/")}
        if actual != set(closure):
            raise ValueError("Wheel app closure differs: missing=" + str(set(closure) - actual) + "; extra=" + str(actual - set(closure)))
        for name, expected in closure.items():
            body = archive.read(name)
            saved = source.extractfile(prefix + "/" + name)
            if hashlib.sha256(body).hexdigest() != expected or saved is None or saved.read() != body:
                raise ValueError("Archive source binding differs: " + name)
        for required in ("app/services/source_context_scope.py", "app/services/source_context_references.py", "app/evidence_policy.py"):
            if required not in actual:
                raise ValueError("Typed context closure missing")
        if any(name.startswith("shared_core/") or name.endswith((".safetensors", ".pt", ".bin")) for name in archive.namelist()):
            raise ValueError("Forbidden external namespace/model weights packaged")
    write("archive-check.json", {"wheel": wheel.name, "wheel_sha256": sha(wheel), "sdist": sdist.name, "sdist_sha256": sha(sdist), "app_members": len(closure), "exact_source30_plus_explicit_assets": True, "scope": "Archive closure only; not installation/model quality"})
    print(json.dumps({"archive_app_members": len(closure)}))


def extra_inputs() -> dict[str, str]:
    closure = json.loads((OUT / "stage-closure.json").read_text())["files"]
    frozen = json.loads((Q / "requirements-source-v30.json").read_text())["files"]
    records = {}
    for name, expected in closure.items():
        if "apps/api/" + name in frozen:
            continue
        path = W / "apps/api" / name
        if sha(path) != expected:
            raise ValueError("Explicit extra asset differs from staged bytes")
        records[str(path)] = expected
    return records


def install(which: str) -> int:
    target = OUT / (which + "-env")
    if target.exists():
        raise ValueError("Never reuse a previous install attempt")
    wheel, = (OUT / "dist").glob("*.whl")
    constraints = OUT / ("base-runtime-constraints.txt" if which == "base" else "model-runtime-constraints.txt")
    if not constraints.is_file():
        raise ValueError("Current lock constraints missing")
    python = target / "Scripts/python.exe"
    commands = [[str(D), "-B", "-m", "venv", str(target)],
                [str(python), "-B", "-m", "pip", "install", "--disable-pip-version-check", "--no-input", "--index-url", "https://pypi.org/simple", "--constraint", str(constraints), str(wheel) + ("[embeddings,reader,support]" if which == "optional" else "")],
                [str(python), "-B", "-m", "pip", "check"]]
    for index, args in enumerate(commands):
        result = command(which + "-install-" + str(index), args)
        if result:
            return result
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("stage", "build", "build-retry", "extra-before", "export-base", "export-optional", "archives", "install-base", "install-optional", "finalize"))
    phase = parser.parse_args().phase
    if phase == "stage":
        stage()
    elif phase in ("build", "build-retry"):
        raise SystemExit(command(phase, [str(D), "-B", "-m", "build", "--outdir", str(OUT / "dist"), str(OUT / "staged-api")]))
    elif phase == "extra-before":
        write("extra-assets-before.json", extra_inputs())
    elif phase.startswith("export-"):
        optional = phase == "export-optional"
        uv = Q / "integration/tooling/bin/uv.exe"
        args = [str(uv), "export", "--project", str(OUT / "staged-api"), "--python", str(D), "--locked", "--offline", "--no-dev", "--no-emit-project", "--no-hashes", "--format", "requirements-txt", "--output-file", str(OUT / ("model-runtime-constraints.txt" if optional else "base-runtime-constraints.txt")), "--cache-dir", str(OUT / "uv-cache")]
        if optional:
            args.extend(["--extra", "embeddings", "--extra", "reader", "--extra", "support"])
        raise SystemExit(command(phase, args))
    elif phase == "archives":
        archives()
    elif phase.startswith("install-"):
        raise SystemExit(install(phase.removeprefix("install-")))
    else:
        after = upstream()
        write("upstream-after.json", after)
        before = json.loads((OUT / "upstream-before.json").read_text())
        extra_after = extra_inputs()
        write("extra-assets-after.json", extra_after)
        extra_before = json.loads((OUT / "extra-assets-before.json").read_text())
        write("upstream-stability.json", {"unchanged": before == after and extra_before == extra_after, "file_count": len(after["files"]) + len(extra_after), "runtime_environments": list(after["runtime_distributions"])})
        if before != after or extra_before != extra_after:
            raise SystemExit("Read-only upstream changed during package gate")
