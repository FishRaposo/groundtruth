"""Explicit setup of pinned model data only; never installs or executes code.

Run python -m app.request_parser_setup --directory PATH [--wheel LOCAL_WHEEL].
Without --wheel this explicit setup downloads the official model wheel. Install
the separately pinned optional spaCy library in the chosen runtime separately.
"""

import argparse
import hashlib
import io
import json
import urllib.request
import uuid
import zipfile
from pathlib import Path

from app.request_parser_catalog import (
    MODEL_PREFIX,
    MODEL_REVISION,
    MODEL_WHEEL_BYTES,
    MODEL_WHEEL_URL,
    parser_identity,
)


def cache_model(directory, *, wheel=None):
    """Cache only reviewed inert model data/licenses, from exact verified bytes."""
    directory = Path(directory)
    target = directory / MODEL_REVISION
    if target.exists():
        verify_assets(target)
        return target
    if wheel is None:
        with urllib.request.urlopen(MODEL_WHEEL_URL, timeout=60) as response:
            data = response.read(MODEL_WHEEL_BYTES + 1)
    else:
        path = Path(wheel)
        if path.stat().st_size != MODEL_WHEEL_BYTES:
            raise ValueError("Pinned request parser wheel size mismatch")
        data = path.read_bytes()
    identity = parser_identity()
    if (
        len(data) != MODEL_WHEEL_BYTES
        or hashlib.sha256(data).hexdigest() != identity["model_wheel_sha256"]
    ):
        raise ValueError("Pinned request parser wheel hash/size mismatch")
    directory.mkdir(parents=True, exist_ok=True)
    if directory.is_symlink():
        raise ValueError("Model cache cannot be a symlink")
    staging = directory / (".model-" + uuid.uuid4().hex)
    staging.mkdir()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for name, expected in identity["model_file_hashes"].items():
            content = archive.read(MODEL_PREFIX + name)
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError("Pinned model member hash mismatch")
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
    verify_assets(staging)
    staging.rename(target)
    (directory / "request-parser-assets.json").write_text(
        json.dumps({"official_source": MODEL_WHEEL_URL, "parser": identity}, indent=2)
        + "\n",
        encoding="utf-8",
    )
    return target


def verify_assets(directory):
    """Require the complete fixed inventory, before any model/config is loaded."""
    directory = Path(directory)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Pinned local model directory is missing or linked")
    actual = {}
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("Pinned model files cannot be symlinks")
        if path.is_file():
            actual[path.relative_to(directory).as_posix()] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    if actual != parser_identity()["model_file_hashes"]:
        raise ValueError("Pinned model file inventory/hash mismatch")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--wheel", type=Path)
    args = parser.parse_args()
    path = cache_model(args.directory, wheel=args.wheel)
    print(
        f"Pinned model data cached at {path}. Optional spaCy 3.8.18 remains required."
    )


if __name__ == "__main__":
    main()
