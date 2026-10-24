"""Approved reader selection must never download or silently change models."""

import hashlib
import json
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from app import reader_setup

ROBERTA_REVISION = "adc3b06f79f797d1c575d5479d6f5efe54a9e3b4"
ROBERTA_FILES = (
    "config.json",
    "model.safetensors",
    "merges.txt",
    "special_tokens_map.json",
    "tokenizer_config.json",
    "vocab.json",
)


def test_catalog_resolves_only_approved_immutable_revisions():
    # A fallback to MiniLM, mutable spec, or branch alias violates model identity.
    resolve = getattr(reader_setup, "get_reader_spec", None)
    assert callable(resolve), "Reader revision catalog is missing"
    spec = resolve(ROBERTA_REVISION)
    assert spec.model == "deepset/roberta-base-squad2"
    assert spec.revision == ROBERTA_REVISION
    assert spec.files == ROBERTA_FILES
    assert spec.license == "CC-BY-4.0"
    with pytest.raises(FrozenInstanceError):
        spec.model = "another/model"
    for revision in ("main", "roberta", "", "0" * 40):
        with pytest.raises(ValueError, match="revision"):
            resolve(revision)
    legacy = resolve(reader_setup.REVISION)
    assert legacy.model == reader_setup.MODEL == "deepset/minilm-uncased-squad2"
    assert legacy.files == tuple(reader_setup.FILES)


@pytest.fixture
def hub_downloads(monkeypatch):
    # Mock only the external network; filesystem writes and manifest are real.
    import huggingface_hub

    calls = []

    def fake_download(repo_id, *, filename, revision, local_dir):
        calls.append((repo_id, filename, revision))
        local_dir.mkdir(parents=True, exist_ok=True)
        result = local_dir / filename
        result.write_bytes(filename.encode())
        return str(result)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake_download)
    return calls


@pytest.mark.parametrize("model", ["minilm", "roberta"])
def test_setup_downloads_only_selected_pinned_files_and_records_digests(
    tmp_path, hub_downloads, model
):
    # The selected weights, revision, and manifest must agree; no pickle weights.
    destination = tmp_path / model
    if model == "minilm":
        reader_setup.download(destination)
        repo, revision, files = (
            reader_setup.MODEL,
            reader_setup.REVISION,
            tuple(reader_setup.FILES),
        )
    else:
        reader_setup.download(destination, model=model)
        repo, revision, files = (
            "deepset/roberta-base-squad2",
            ROBERTA_REVISION,
            ROBERTA_FILES,
        )
    assert hub_downloads == [(repo, filename, revision) for filename in files]
    manifest = json.loads((destination / "groundtruth-reader.json").read_text())
    assert manifest == {
        "model": repo,
        "revision": revision,
        "license": "CC-BY-4.0",
        "files": {
            filename: hashlib.sha256(filename.encode()).hexdigest()
            for filename in files
        },
    }


def test_unknown_setup_model_fails_before_download(tmp_path, hub_downloads):
    with pytest.raises(ValueError, match="model"):
        reader_setup.download(tmp_path / "unknown", model="unknown")
    assert hub_downloads == []
    assert not (tmp_path / "unknown").exists()


@pytest.mark.parametrize("model", [None, "minilm", "roberta"])
def test_cli_supports_explicit_model_and_legacy_default(
    tmp_path, hub_downloads, monkeypatch, model
):
    args = ["reader_setup", "--directory", str(tmp_path)]
    if model:
        args.extend(["--model", model])
    monkeypatch.setattr(sys, "argv", args)
    reader_setup.main()
    manifest = json.loads((tmp_path / "groundtruth-reader.json").read_text())
    assert manifest["model"] == (
        "deepset/roberta-base-squad2"
        if model == "roberta"
        else "deepset/minilm-uncased-squad2"
    )


def test_download_failure_never_writes_success_manifest(tmp_path, monkeypatch):
    import huggingface_hub

    def fail(*args, **kwargs):
        raise OSError("network unavailable")

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fail)
    with pytest.raises(OSError, match="network unavailable"):
        reader_setup.download(Path(tmp_path))
    assert not (tmp_path / "groundtruth-reader.json").exists()
