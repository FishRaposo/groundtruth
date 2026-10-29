"""Guard tests using approved cached assets and doubles only for CPU inference.

Asset-backed cases skip explicitly where the optional public model is absent.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from app.config import Settings
from app.services import answer_support as support

ASSETS = (
    Path(__file__).resolve().parents[4]
    / "models/nli-deberta-v3-small--70de96bd327ef95839a8bd9f6299875cae396433"
)


async def test_content_budget_records_lengths_without_asset_error_pure(monkeypatch):
    backend = InferenceBoundary(lengths=[513])
    monkeypatch.setattr(support, "validate_assets", lambda directory: directory)
    verifier = wire(monkeypatch, backend)
    selected = config("unused-pure-test-boundary")
    pair = support.SupportPair("exact source", "required action", "r1", "source")
    with pytest.raises(support.SupportInputBudgetExceeded) as caught:
        await verifier.assess([pair], selected)
    assert caught.value.lengths == (513,)
    assert verifier.metadata(selected)["readiness"] == "ready"
    assert backend.calls == []
    backend.lengths = [17]
    result = await verifier.assess([pair], selected)
    assert result[0].supported and result[0].pair_tokens == 17


@pytest.fixture
def assets(tmp_path):
    if not ASSETS.is_dir():
        pytest.skip("Approved optional support assets are not cached in this checkout")
    for source in ASSETS.iterdir():
        if source.is_file():
            if source.name == "model.safetensors":
                os.link(source, tmp_path / source.name)
            else:
                shutil.copyfile(source, tmp_path / source.name)
    return tmp_path


def config(directory, **changes):
    return Settings(
        ANSWER_SUPPORT_MODE="local_nli", SUPPORT_MODEL_PATH=str(directory), **changes
    )


class InferenceBoundary:
    def __init__(self, rows=None, lengths=None):
        self.rows = rows or [[0.0, 5.0, -1.0]]
        self.lengths = lengths
        self.calls = []
        self.offset = 0
        self.loads = 0

    def token_lengths(self, pairs):
        return self.lengths or [12] * len(pairs)

    def logits(self, pairs):
        self.calls.append(tuple(pairs))
        result = [
            self.rows[(self.offset + i) % len(self.rows)] for i in range(len(pairs))
        ]
        self.offset += len(pairs)
        return result


def wire(monkeypatch, backend):
    def load(directory):
        backend.loads += 1
        return backend

    monkeypatch.setattr(support, "_load_backend", load)
    return support.LocalSupportVerifier()


async def test_order_finite_strict_margin_and_immutable_results(assets, monkeypatch):
    backend = InferenceBoundary(
        [[0, 5, -1], [4, 5, -2], [5, 5, -2], [0, 1, 6], [7, 1, 0]]
    )
    verifier = wire(monkeypatch, backend)
    pairs = [
        support.SupportPair("source", f"claim {i}", str(i), "ref") for i in range(5)
    ]
    result = await verifier.assess(pairs, config(assets))
    assert [row.supported for row in result] == [True, False, False, False, False]
    assert [row.entailment_margin for row in result] == [5, 1, 0, -5, -6]
    assert [row.label for row in result] == [
        "entailment",
        "entailment",
        "contradiction",
        "neutral",
        "contradiction",
    ]
    with pytest.raises(FrozenInstanceError):
        result[0].supported = False
    with pytest.raises(FrozenInstanceError):
        pairs[0].premise = "replacement"


async def test_loads_empty_probe_then_batches_eight_without_changing_inputs(
    assets, monkeypatch
):
    backend = InferenceBoundary()
    verifier = wire(monkeypatch, backend)
    assert await verifier.assess([], config(assets)) == []
    assert verifier.metadata(config(assets))["readiness"] == "ready"
    pairs = [
        support.SupportPair("Exact  source", f"claim {i}", str(i), "r")
        for i in range(17)
    ]
    result = await verifier.assess(pairs, config(assets))
    assert len(result) == 17
    assert [len(call) for call in backend.calls] == [8, 8, 1]
    assert [pair for call in backend.calls for pair in call] == pairs


@pytest.mark.parametrize(
    "row", [[0, float("nan"), 1], [float("inf"), 1, 0], [1, 2], [1, 2, 3, 4]]
)
async def test_invalid_logits_fail_without_assessments(assets, monkeypatch, row):
    verifier = wire(monkeypatch, InferenceBoundary([row]))
    with pytest.raises(support.SupportUnavailableError, match="logits"):
        await verifier.assess([support.SupportPair("s", "h", "q", "r")], config(assets))
    assert verifier.metadata(config(assets))["readiness"] == "error"


async def test_overlength_pair_is_rejected_before_any_inference(assets, monkeypatch):
    backend = InferenceBoundary(lengths=[513])
    verifier = wire(monkeypatch, backend)
    with pytest.raises(support.SupportUnavailableError, match="512"):
        await verifier.assess([support.SupportPair("s", "h", "q", "r")], config(assets))
    assert not backend.calls


async def test_zero_margin_does_not_accept_tie(assets, monkeypatch):
    verifier = wire(monkeypatch, InferenceBoundary([[5, 5, 0], [0, 5, 5]]))
    result = await verifier.assess(
        [support.SupportPair("s", "h", "q", "r")] * 2,
        config(assets, SUPPORT_MIN_MARGIN=0),
    )
    assert [row.supported for row in result] == [False, False]


async def test_disabled_and_missing_assets_never_fabricate_empty_success(tmp_path):
    verifier = support.LocalSupportVerifier()
    with pytest.raises(support.SupportUnavailableError):
        await verifier.assess([], Settings())
    with pytest.raises(support.SupportUnavailableError):
        await verifier.assess([], config(tmp_path))
    assert verifier.metadata(Settings())["readiness"] == "disabled"


@pytest.mark.parametrize(
    "mutation", ["hash", "manifest", "labels", "unexpected", "revision", "escape"]
)
async def test_tampered_or_unpinned_assets_fail_before_inference(
    assets, monkeypatch, mutation
):
    backend = InferenceBoundary()
    verifier = wire(monkeypatch, backend)
    settings = config(assets)
    if mutation == "hash":
        (assets / "tokenizer.json").write_text("{}")
    elif mutation == "manifest":
        manifest = json.loads((assets / "groundtruth-support.json").read_text())
        manifest["files"]["config.json"] = "0" * 64
        (assets / "groundtruth-support.json").write_text(json.dumps(manifest))
    elif mutation == "labels":
        data = json.loads((assets / "config.json").read_text())
        data["id2label"]["1"] = "neutral"
        (assets / "config.json").write_text(json.dumps(data))
    elif mutation == "unexpected":
        (assets / "pytorch_model.bin").write_bytes(b"unsafe")
    elif mutation == "revision":
        settings = config(assets, SUPPORT_MODEL_REVISION="main")
    else:
        # Manifest paths are data, never an alternate path to trust.
        manifest = json.loads((assets / "groundtruth-support.json").read_text())
        manifest["files"]["../escape"] = "0" * 64
        (assets / "groundtruth-support.json").write_text(json.dumps(manifest))
    with pytest.raises(support.SupportUnavailableError):
        await verifier.assess([], settings)
    assert not backend.calls
    assert backend.loads == 0


async def test_snapshots_mutable_settings_and_pair_list(assets, monkeypatch):
    backend = InferenceBoundary([[0, 3, -1]])
    verifier = wire(monkeypatch, backend)
    settings = config(assets, SUPPORT_MIN_MARGIN=4)
    pairs = [support.SupportPair("s", "h", "q", "r")]
    task = asyncio.create_task(verifier.assess(pairs, settings))
    await asyncio.sleep(0)
    settings.SUPPORT_MIN_MARGIN = 0
    pairs.clear()
    result = await task
    assert len(result) == 1
    assert result[0].supported is False


async def test_assets_are_revalidated_after_model_is_cached(assets, monkeypatch):
    backend = InferenceBoundary()
    verifier = wire(monkeypatch, backend)
    await verifier.assess([], config(assets))
    (assets / "tokenizer_config.json").write_text("{}")
    with pytest.raises(support.SupportUnavailableError):
        await verifier.assess([], config(assets))
    assert verifier.metadata(config(assets))["readiness"] == "error"


def test_base_imports_do_not_require_model_libraries():
    program = """
import importlib.abc
import sys
class NoOptionalModels(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch', 'transformers', 'huggingface_hub'}:
            raise AssertionError('optional model import during base import')
sys.meta_path.insert(0, NoOptionalModels())
from app.services.answer_support import LocalSupportVerifier
from app import support_catalog, support_setup
assert LocalSupportVerifier().metadata()['mode'] == 'disabled'
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", program], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_setup_uses_only_anonymous_pinned_safe_downloads(assets, tmp_path, monkeypatch):
    import huggingface_hub
    from app import support_setup

    target = tmp_path / "downloaded"
    calls = []

    def download(**kwargs):
        calls.append(kwargs)
        path = Path(kwargs["local_dir"]) / kwargs["filename"]
        os.link(assets / kwargs["filename"], path)
        return str(path)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    support_setup.download(target)
    manifest = json.loads((target / "groundtruth-support.json").read_text())
    assert manifest["label_mapping"] == {
        "0": "contradiction",
        "1": "entailment",
        "2": "neutral",
    }
    assert len(calls) == 8
    assert all(call["token"] is False for call in calls)
    assert all(
        call["revision"] == "70de96bd327ef95839a8bd9f6299875cae396433" for call in calls
    )
    assert all(
        call["repo_id"] == "cross-encoder/nli-deberta-v3-small" for call in calls
    )
    assert {call["filename"] for call in calls} == {
        "config.json",
        "model.safetensors",
        "special_tokens_map.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "added_tokens.json",
        "spm.model",
        "README.md",
    }


def test_backend_selects_fast_local_safetensors_and_cpu(monkeypatch, tmp_path):
    from types import SimpleNamespace

    calls = []

    class Tokenizer:
        @classmethod
        def from_pretrained(cls, directory, **kwargs):
            calls.append(("tokenizer", directory, kwargs))
            return SimpleNamespace(is_fast=True)

    class Model:
        config = SimpleNamespace(
            id2label={0: "contradiction", 1: "entailment", 2: "neutral"}
        )

        @classmethod
        def from_pretrained(cls, directory, **kwargs):
            calls.append(("model", directory, kwargs))
            return cls()

        def to(self, device):
            calls.append(("device", device))

        def eval(self):
            calls.append(("eval",))

    library = SimpleNamespace(
        AutoTokenizer=Tokenizer, AutoModelForSequenceClassification=Model
    )
    monkeypatch.setattr(support.importlib, "import_module", lambda name: library)
    support._load_backend(tmp_path)
    for kind, directory, kwargs in calls[:2]:
        assert directory == str(tmp_path)
        assert kwargs["local_files_only"] is True
        assert kwargs["trust_remote_code"] is False
        assert kwargs["token"] is False
        if kind == "tokenizer":
            assert kwargs["use_fast"] is True
        else:
            assert kwargs["use_safetensors"] is True
    assert calls[2:] == [("device", "cpu"), ("eval",)]


def test_setup_rejects_malformed_cache_before_network(tmp_path, monkeypatch):
    import huggingface_hub
    from app import support_setup

    (tmp_path / ".cache").write_text("unexpected file")

    def forbidden(**kwargs):
        pytest.fail("Malformed local setup directory reached the network")

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", forbidden)
    with pytest.raises(ValueError, match="directory"):
        support_setup.download(tmp_path)
