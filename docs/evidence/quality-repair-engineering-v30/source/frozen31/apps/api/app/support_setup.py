"""Explicit anonymous public download of approved local CPU support assets."""

import argparse
import json
from pathlib import Path

from app.support_catalog import MANIFEST, NLI, manifest_metadata, validate_directory


def _prepare_directory(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    root = directory.resolve(strict=True)
    allowed = {name for name, _ in NLI.file_hashes} | {MANIFEST, ".cache"}
    if any(path.name not in allowed for path in root.iterdir()):
        raise ValueError("Use a dedicated directory without unexpected support assets")
    for path in root.iterdir():
        if not path.resolve(strict=True).is_relative_to(root):
            raise ValueError("Support setup path escapes the selected directory")
        if path.name == ".cache" and not path.is_dir():
            raise ValueError("Support setup .cache must be a directory")
        if path.name != ".cache" and not path.is_file():
            raise ValueError("Support setup expects files in a dedicated directory")
    return root


def download(directory: Path) -> None:
    """Fetch only pinned safe assets; runtime never calls this setup command."""
    try:
        from huggingface_hub import hf_hub_download  # pyright: ignore[reportMissingImports]
    except ImportError as exc:
        raise SystemExit("Install groundtruth[support] first.") from exc
    root = _prepare_directory(directory)
    for filename, _ in NLI.file_hashes:
        target = root / filename
        if target.exists() and not target.resolve(strict=True).is_relative_to(root):
            raise ValueError("Support download target escapes the selected directory")
        path = Path(
            hf_hub_download(
                repo_id=NLI.model,
                filename=filename,
                revision=NLI.revision,
                local_dir=str(root),
                token=False,
            )
        )
        if path.resolve(strict=True) != target:
            raise ValueError("Support download returned an unexpected local path")
    validate_directory(root, require_manifest=False)
    manifest_path = root / MANIFEST
    if manifest_path.exists() and not manifest_path.resolve(strict=True).is_relative_to(
        root
    ):
        raise ValueError("Support manifest target escapes the selected directory")
    manifest_path.write_text(
        json.dumps(manifest_metadata(), indent=2) + "\n", encoding="utf-8"
    )
    validate_directory(root)
    print("Pinned support assets verified. Set SUPPORT_MODEL_PATH to this directory.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    download(args.directory)


if __name__ == "__main__":
    main()
