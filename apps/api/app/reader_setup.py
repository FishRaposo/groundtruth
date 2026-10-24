"""Explicit setup for the pinned CPU extractive reader; runtime never downloads."""

import argparse
import hashlib
import json
from pathlib import Path

MODEL = "deepset/minilm-uncased-squad2"
REVISION = "934656cdda79824eabf503ed56e15c01ddbdbe3f"
FILES = [
    "config.json",
    "model.safetensors",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "vocab.txt",
]


def download(directory: Path) -> None:
    try:
        from huggingface_hub import hf_hub_download  # pyright: ignore[reportMissingImports]
    except ImportError as exc:
        raise SystemExit("Install groundtruth[reader] first.") from exc
    manifest = {
        "model": MODEL,
        "revision": REVISION,
        "license": "CC-BY-4.0",
        "files": {},
    }
    for filename in FILES:
        path = Path(
            hf_hub_download(
                MODEL, filename=filename, revision=REVISION, local_dir=directory
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
    args = parser.parse_args()
    download(args.directory)


if __name__ == "__main__":
    main()
