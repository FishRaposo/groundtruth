"""Explicit setup for the pinned CPU extractive reader; runtime never downloads."""

import argparse
import hashlib
import json
from pathlib import Path

from app.reader_catalog import MINILM, ROBERTA
from app.reader_catalog import get_reader_spec as get_reader_spec

# Preserve the original public MiniLM setup/runtime imports.
MODEL = MINILM.model
REVISION = MINILM.revision
FILES = list(MINILM.files)


def download(directory: Path, *, model: str = "minilm") -> None:
    try:
        spec = {"minilm": MINILM, "roberta": ROBERTA}[model]
    except KeyError as exc:
        raise ValueError(f"Unknown reader model: {model!r}") from exc
    try:
        from huggingface_hub import hf_hub_download  # pyright: ignore[reportMissingImports]
    except ImportError as exc:
        raise SystemExit("Install groundtruth[reader] first.") from exc
    manifest = {
        "model": spec.model,
        "revision": spec.revision,
        "license": spec.license,
        "files": {},
    }
    for filename in spec.files:
        path = Path(
            hf_hub_download(
                spec.model,
                filename=filename,
                revision=spec.revision,
                local_dir=directory,
            )
        )
        manifest["files"][filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    (directory / "groundtruth-reader.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print("Pinned reader assets downloaded. Set READER_MODEL_PATH to this directory.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--model", choices=("minilm", "roberta"), default="minilm")
    args = parser.parse_args()
    download(args.directory, model=args.model)


if __name__ == "__main__":
    main()
