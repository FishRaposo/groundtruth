"""Configured readers must load locally and report their actual identity."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from app.config import Settings
from app.services.answer_reader import LocalReader

ROBERTA_REVISION = "adc3b06f79f797d1c575d5479d6f5efe54a9e3b4"


def test_configured_roberta_never_claims_minilm_identity():
    evidence = LocalReader().metadata(
        Settings(ANSWER_SELECTION_MODE="reader", READER_MODEL_REVISION=ROBERTA_REVISION)
    )
    assert evidence["model"] == "deepset/roberta-base-squad2"
    assert evidence["revision"] == ROBERTA_REVISION


@pytest.mark.parametrize(
    "extra",
    [None, "tokenizer.json", "added_tokens.json", "model.safetensors.index.json"],
)
def test_roberta_loads_only_validated_local_safetensors(tmp_path, monkeypatch, extra):
    files = (
        "config.json",
        "model.safetensors",
        "merges.txt",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "vocab.json",
    )
    manifest = {
        "model": "deepset/roberta-base-squad2",
        "revision": ROBERTA_REVISION,
        "files": {},
    }
    for filename in files:
        (tmp_path / filename).write_bytes(b"fixture")
        manifest["files"][filename] = hashlib.sha256(b"fixture").hexdigest()
    (tmp_path / "groundtruth-reader.json").write_text(json.dumps(manifest))
    if extra:
        (tmp_path / extra).write_bytes(b"unverified override")
    calls = []

    class Tokenizer:
        @classmethod
        def from_pretrained(cls, directory, **options):
            calls.append(("tokenizer", directory, options))
            return SimpleNamespace(is_fast=True)

    class Model:
        @classmethod
        def from_pretrained(cls, directory, **options):
            calls.append(("model", directory, options))
            return cls()

        def to(self, device):
            assert device == "cpu"

        def eval(self):
            pass

    monkeypatch.setattr(
        "app.services.answer_reader.importlib.import_module",
        lambda name: SimpleNamespace(
            AutoTokenizer=Tokenizer, AutoModelForQuestionAnswering=Model
        ),
    )
    config = Settings(
        ANSWER_SELECTION_MODE="reader",
        READER_MODEL_PATH=str(tmp_path),
        READER_MODEL_REVISION=ROBERTA_REVISION,
    )
    reader = LocalReader()
    if extra:
        with pytest.raises(RuntimeError, match="unverified"):
            reader._load(config)
        assert calls == []
        return
    reader._load(config)
    assert [call[0] for call in calls] == ["tokenizer", "model"]
    for _, directory, options in calls:
        assert directory == str(tmp_path.resolve())
        assert options["local_files_only"] is True
        assert options["trust_remote_code"] is False
    assert calls[1][2]["use_safetensors"] is True
    assert reader.metadata(config)["readiness"] == "ready"
