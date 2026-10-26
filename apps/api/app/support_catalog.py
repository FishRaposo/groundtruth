"""Approved immutable NLI identity and asset pins; imports never download."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SupportSpec:
    model: str
    revision: str
    license: str
    task: str
    labels: tuple[str, str, str]
    file_hashes: tuple[tuple[str, str], ...]


NLI = SupportSpec(
    model="cross-encoder/nli-deberta-v3-small",
    revision="70de96bd327ef95839a8bd9f6299875cae396433",
    license="Apache-2.0",
    task="natural-language-inference",
    labels=("contradiction", "entailment", "neutral"),
    file_hashes=(
        (
            "config.json",
            "885d0dceae8fa5c136da9209121ec9eb11160488e840de3bc1f29353674e5712",
        ),
        (
            "model.safetensors",
            "ebc79588dd73ccfb6a3f6078519cfbf512c5305384c5ea1845bc71cd32216e86",
        ),
        (
            "special_tokens_map.json",
            "ed7c099c988dbb414b18a6980d20cb57b91b7cd119f6f6941eb364b0e892e712",
        ),
        (
            "tokenizer.json",
            "5124ef2ead1a10a717703bc436de7f353da76d6340e4587719b42b1693707964",
        ),
        (
            "tokenizer_config.json",
            "f3eecd07c370ef0bf7dd3780d3cd68cf9c8b00c267e21a208ddcd8f82bfec1a6",
        ),
        (
            "added_tokens.json",
            "a4b6bfe668f2b3cf6f0cd535e98a0663d2d0d4a4a15f13075ad3597d33985a23",
        ),
        (
            "spm.model",
            "c679fbf93643d19aab7ee10c0b99e460bdbc02fedf34b92b05af343b4af586fd",
        ),
        (
            "README.md",
            "a9aa108025ad1984374c5e80365406bafe331aea5abc30239e1796ec0a7c267d",
        ),
    ),
)
MANIFEST = "groundtruth-support.json"
MAX_PAIR_TOKENS = 512
BATCH_SIZE = 8
WEIGHTS_SIZE = 567605820


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_metadata() -> dict:
    return {
        "model": NLI.model,
        "revision": NLI.revision,
        "license": NLI.license,
        "task": NLI.task,
        "label_mapping": {str(i): label for i, label in enumerate(NLI.labels)},
        "files": dict(NLI.file_hashes),
    }


def _validate_files(root: Path) -> None:
    expected = dict(NLI.file_hashes)
    allowed = set(expected) | {MANIFEST}
    for child in root.iterdir():
        if not child.resolve(strict=True).is_relative_to(root):
            raise ValueError("Support asset escapes the configured directory")
        if child.name == ".cache" and child.is_dir():
            continue  # HF download metadata is never an inference source.
        if child.name not in allowed or not child.is_file():
            raise ValueError(
                "Unexpected support asset; use a dedicated pinned directory"
            )
    for name, digest in expected.items():
        path = root / name
        if not path.resolve(strict=True).is_relative_to(root):
            raise ValueError("Support asset escapes the configured directory")
        if name == "model.safetensors" and path.stat().st_size != WEIGHTS_SIZE:
            raise ValueError("Support weights size does not match the approved pin")
        if sha256_file(path) != digest:
            raise ValueError("Support asset hash does not match the approved pin")


def validate_directory(directory: Path, *, require_manifest: bool = True) -> Path:
    """Reject alternate weights, path escapes, hashes and label substitutions."""
    root = directory.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Support assets must be a local directory")
    _validate_files(root)
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    if config.get("id2label") != manifest_metadata()["label_mapping"]:
        raise ValueError("Support config label mapping is invalid")
    if require_manifest:
        manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
        for key, value in manifest_metadata().items():
            if manifest.get(key) != value:
                raise ValueError("Support manifest does not match the approved pin")
    return root


def validate_assets(directory: Path) -> Path:
    """Validate approved local files before any optional model import."""
    return validate_directory(directory)
