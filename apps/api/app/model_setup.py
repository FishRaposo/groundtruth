"Explicit download of the pinned, non-executable local embedding assets."

import argparse
import hashlib
import json
from pathlib import Path

MODEL = "sentence-transformers/all-MiniLM-L6-v2"
REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
FILES = [
    "1_Pooling/config.json",
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
    "model.safetensors",
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise SystemExit("Install groundtruth[embeddings] first.") from exc
    manifest = {
        "model": MODEL,
        "revision": REVISION,
        "license": "Apache-2.0",
        "dimension": 384,
        "max_sequence_tokens": 256,
        "files": {},
    }
    for filename in FILES:
        path = Path(
            hf_hub_download(
                MODEL, filename=filename, revision=REVISION, local_dir=args.directory
            )
        )
        manifest["files"][filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    (args.directory / "groundtruth-model.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        (
            "Pinned local embedding assets downloaded. Configure "
            "LOCAL_MODEL_PATH to this directory."
        )
    )


if __name__ == "__main__":
    main()
