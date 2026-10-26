"""Shared raw uploads cannot be silently replaced by arm-canonical text."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from app.portfolio import load_corpus


def corpus_copy(tmp_path):
    import app.portfolio

    root = tmp_path / "corpus"
    shutil.copytree(Path(app.portfolio.__file__).parent / "assets", root)
    return root


def update_documents(root, mutate):
    path = root / "documents.json"
    docs = json.loads(path.read_bytes())
    mutate(docs[0]["versions"][0])
    path.write_text(json.dumps(docs), encoding="utf-8")
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"]["documents.json"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_loader_rejects_tampered_raw_upload_even_with_valid_canonical_hash(tmp_path):
    # A verified canonical body must not conceal changed shared experimental input.
    root = corpus_copy(tmp_path)
    update_documents(
        root,
        lambda version: version.update(
            input_content="changed raw upload", input_sha256="0" * 64
        ),
    )
    with pytest.raises(ValueError, match="[Ii]nput.*hash"):
        load_corpus(root)


@pytest.mark.parametrize("missing", ["input_content", "input_sha256"])
def test_loader_rejects_incomplete_raw_lineage(tmp_path, missing):
    root = corpus_copy(tmp_path)

    def mutate(version):
        version.update(input_content="shared raw", input_sha256="0" * 64)
        version.pop(missing)

    update_documents(root, mutate)
    with pytest.raises(ValueError, match="[Ii]nput"):
        load_corpus(root)


def test_legacy_and_exact_shared_raw_projections_still_load(tmp_path):
    root = corpus_copy(tmp_path)
    original = load_corpus(root)
    raw = "\nFrozen raw upload with separate canonical representation.\r\n"
    update_documents(
        root,
        lambda version: version.update(
            input_content=raw, input_sha256=hashlib.sha256(raw.encode()).hexdigest()
        ),
    )
    loaded = load_corpus(root)
    assert loaded["documents"][0]["versions"][0]["input_content"] == raw
    assert loaded["cases"] == original["cases"]
