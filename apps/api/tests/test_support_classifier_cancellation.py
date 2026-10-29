"""Cancellation must abandon queued work and remaining batches, not CPU calls."""

import asyncio
import threading
from pathlib import Path

import pytest
from app.config import Settings
from app.services import answer_support as support

ASSETS = (
    Path(__file__).resolve().parents[4]
    / "models/nli-deberta-v3-small--70de96bd327ef95839a8bd9f6299875cae396433"
)


async def test_cancelled_budget_preflight_cannot_publish_readiness_pure(monkeypatch):
    class BudgetBoundary(BlockingBackend):
        def token_lengths(self, pairs):
            if pairs and pairs[0].hypothesis == "budget":
                self.started.set()
                assert self.release.wait(5)
                return [513]
            return [4] * len(pairs)

    backend = BudgetBoundary()
    monkeypatch.setattr(support, "validate_assets", lambda directory: directory)
    monkeypatch.setattr(support, "_load_backend", lambda directory: backend)
    verifier = support.LocalSupportVerifier()
    selected = Settings(
        ANSWER_SUPPORT_MODE="local_nli", SUPPORT_MODEL_PATH="unused-pure-test-boundary"
    )
    with pytest.raises(support.SupportUnavailableError):
        await verifier.assess([pair("invalid")], selected)
    assert verifier.metadata(selected)["readiness"] == "error"
    _, finished = instrument_worker(monkeypatch, verifier, "budget")
    task = asyncio.create_task(verifier.assess([pair("budget")], selected))
    try:
        assert await asyncio.to_thread(backend.started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        backend.release.set()
        assert await asyncio.to_thread(finished.wait, 2)
    assert verifier.metadata(selected)["readiness"] == "error"
    result = await verifier.assess([pair("recovered")], selected)
    assert result[0].supported and result[0].pair_tokens == 4


@pytest.fixture
def settings():
    if not ASSETS.is_dir():
        pytest.skip("Approved optional support assets are not cached in this checkout")
    return Settings(ANSWER_SUPPORT_MODE="local_nli", SUPPORT_MODEL_PATH=str(ASSETS))


class BlockingBackend:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.calls = []

    def token_lengths(self, pairs):
        return [4] * len(pairs)

    def logits(self, pairs):
        names = [pair.hypothesis for pair in pairs]
        self.calls.append(names)
        if names[0] == "invalid":
            return [[0, float("nan"), -1]]
        if names[0] == "active-0":
            self.started.set()
            assert self.release.wait(5), "Test must release the active CPU call"
        return [[0, 5, -1]] * len(pairs)


def instrument_worker(monkeypatch, verifier, target):
    entered, finished = threading.Event(), threading.Event()
    original = verifier._assess

    def observe(pairs, *args):
        observed = pairs and pairs[0].hypothesis == target
        if observed:
            entered.set()
        try:
            return original(pairs, *args)
        finally:
            if observed:
                finished.set()

    monkeypatch.setattr(verifier, "_assess", observe)
    return entered, finished


def pair(name):
    return support.SupportPair("source", name, "requirement", "reference")


async def test_cancelled_queued_request_exits_before_active_cpu_call_finishes(
    settings, monkeypatch
):
    backend = BlockingBackend()
    monkeypatch.setattr(support, "_load_backend", lambda directory: backend)
    verifier = support.LocalSupportVerifier()
    entered, finished = instrument_worker(monkeypatch, verifier, "queued")
    active = asyncio.create_task(verifier.assess([pair("active-0")], settings))
    queued = None
    try:
        assert await asyncio.to_thread(backend.started.wait, 2)
        queued = asyncio.create_task(verifier.assess([pair("queued")], settings))
        assert await asyncio.to_thread(entered.wait, 2)
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
        assert await asyncio.to_thread(finished.wait, 1), (
            "Cancelled queued worker remained blocked behind the active CPU call"
        )
        assert not backend.release.is_set()
        assert backend.calls == [["active-0"]]
    finally:
        backend.release.set()
        await active
        if queued is not None and not queued.done():
            queued.cancel()
        await asyncio.to_thread(finished.wait, 2)
    assert backend.calls == [["active-0"]]
    assert verifier.metadata(settings)["readiness"] == "ready"
    result = await verifier.assess([pair("subsequent")], settings)
    assert result[0].supported is True
    assert backend.calls == [["active-0"], ["subsequent"]]


async def test_active_cancellation_abandons_result_and_remaining_batches(
    settings, monkeypatch
):
    backend = BlockingBackend()
    monkeypatch.setattr(support, "_load_backend", lambda directory: backend)
    verifier = support.LocalSupportVerifier()
    # Establish an error through the public seam; cancelled work must not clear it.
    with pytest.raises(support.SupportUnavailableError, match="logits"):
        await verifier.assess([pair("invalid")], settings)
    assert verifier.metadata(settings)["readiness"] == "error"
    _, finished = instrument_worker(monkeypatch, verifier, "active-0")
    active = asyncio.create_task(
        verifier.assess([pair(f"active-{index}") for index in range(17)], settings)
    )
    try:
        assert await asyncio.to_thread(backend.started.wait, 2)
        active.cancel()
        with pytest.raises(asyncio.CancelledError):
            await active
    finally:
        backend.release.set()
        assert await asyncio.to_thread(finished.wait, 2)
    assert backend.calls == [
        ["invalid"],
        [f"active-{index}" for index in range(8)],
    ]
    assert verifier.metadata(settings)["readiness"] == "error"
    result = await verifier.assess([pair("subsequent")], settings)
    assert result[0].supported is True
    assert verifier.metadata(settings)["readiness"] == "ready"


def test_one_verifier_remains_usable_from_independent_event_loops(
    settings, monkeypatch
):
    backend = BlockingBackend()
    monkeypatch.setattr(support, "_load_backend", lambda directory: backend)
    verifier = support.LocalSupportVerifier()
    first = asyncio.run(verifier.assess([pair("loop-one")], settings))
    second = asyncio.run(verifier.assess([pair("loop-two")], settings))
    assert first[0].supported and second[0].supported
    assert backend.calls == [["loop-one"], ["loop-two"]]
