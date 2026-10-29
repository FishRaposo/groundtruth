"""Optional local CPU natural-language inference boundary."""

import asyncio
import importlib
import math
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.support_catalog import BATCH_SIZE, MAX_PAIR_TOKENS, NLI, validate_assets


class SupportUnavailableError(RuntimeError):
    """Selected support inference cannot safely execute."""


class SupportInputBudgetExceeded(SupportUnavailableError):
    """Valid runtime, unsupported content budget; never truncate required input."""

    def __init__(self, message: str, lengths: tuple[int, ...] = ()) -> None:
        super().__init__(message)
        self.lengths = lengths


class _CancellationGate:
    """Request-local thread-safe cancellation; never tied to an event loop."""

    def __init__(self) -> None:
        self._cancelled = threading.Event()
        self._publication_lock = threading.Lock()

    def cancel(self) -> None:
        # Publishing contains only small metadata assignments, never CPU work.
        with self._publication_lock:
            self._cancelled.set()

    def check(self) -> None:
        if self._cancelled.is_set():
            raise asyncio.CancelledError

    @contextmanager
    def publication(self) -> Iterator[None]:
        """Prevent cancelled work publishing cache/error/readiness changes."""
        with self._publication_lock:
            self.check()
            yield


@dataclass(frozen=True)
class SupportPair:
    premise: str
    hypothesis: str
    requirement_id: str
    reference_id: str


@dataclass(frozen=True)
class SupportAssessment:
    label: str
    logits: tuple[float, float, float]
    entailment_margin: float
    supported: bool
    pair_tokens: int | None = None


class _CPUBackend:
    """External tokenizer/model boundary; no mutable request state is retained."""

    def __init__(self, tokenizer: Any, model: Any, torch: Any) -> None:
        self.tokenizer, self.model, self.torch = tokenizer, model, torch

    def token_lengths(self, pairs: tuple[SupportPair, ...]) -> list[int]:
        encoded = self.tokenizer(
            [pair.premise for pair in pairs],
            [pair.hypothesis for pair in pairs],
            add_special_tokens=True,
            truncation=False,
            padding=False,
        )
        return [len(row) for row in encoded["input_ids"]]

    def logits(self, pairs: tuple[SupportPair, ...]) -> list[list[float]]:
        encoded = self.tokenizer(
            [pair.premise for pair in pairs],
            [pair.hypothesis for pair in pairs],
            add_special_tokens=True,
            truncation=False,
            padding=True,
            return_tensors="pt",
        )
        with self.torch.inference_mode():
            return self.model(**encoded).logits.detach().cpu().tolist()


def _load_backend(directory: Path) -> _CPUBackend:
    # Optional dependencies are loaded only after all asset checks succeed.
    torch = importlib.import_module("torch")
    transformers = importlib.import_module("transformers")
    tokenizer = transformers.AutoTokenizer.from_pretrained(
        str(directory),
        local_files_only=True,
        trust_remote_code=False,
        token=False,
        use_fast=True,
    )
    if not tokenizer.is_fast:
        raise SupportUnavailableError("Support inference requires a fast tokenizer")
    model = transformers.AutoModelForSequenceClassification.from_pretrained(
        str(directory),
        local_files_only=True,
        trust_remote_code=False,
        token=False,
        use_safetensors=True,
    )
    if model.config.id2label != dict(enumerate(NLI.labels)):
        raise SupportUnavailableError("Support model label mapping is invalid")
    model.to("cpu")
    model.eval()
    return _CPUBackend(tokenizer, model, torch)


def _validate_config(config: Settings) -> None:
    if config.ANSWER_SUPPORT_MODE != "local_nli":
        raise SupportUnavailableError("Select ANSWER_SUPPORT_MODE=local_nli explicitly")
    if config.SUPPORT_MODEL_REVISION != NLI.revision:
        raise SupportUnavailableError("Support model revision is not approved")
    if not config.SUPPORT_MODEL_PATH:
        raise SupportUnavailableError(
            "Set SUPPORT_MODEL_PATH to the pinned local assets"
        )
    if (
        not math.isfinite(config.SUPPORT_MIN_MARGIN)
        or not 0 <= config.SUPPORT_MIN_MARGIN <= 4
    ):
        raise SupportUnavailableError("Support margin must be finite and within 0..4")


def _assessment(row: list[float], minimum_margin: float) -> SupportAssessment:
    if len(row) != 3 or not all(math.isfinite(float(v)) for v in row):
        raise SupportUnavailableError("Support logits must contain three finite values")
    contradiction, entailment, neutral = (float(v) for v in row)
    logits = (contradiction, entailment, neutral)
    margin = entailment - max(contradiction, neutral)
    if not math.isfinite(margin):
        raise SupportUnavailableError("Support logits produce a non-finite margin")
    supported = entailment > max(contradiction, neutral) and margin >= minimum_margin
    label = NLI.labels[max(range(3), key=lambda index: logits[index])]
    return SupportAssessment(label, logits, margin, supported)


class LocalSupportVerifier:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._identity: tuple[str, str] | None = None
        self._error_identity: tuple[str, str] | None = None
        self._backend: Any = None

    def metadata(self, config: Settings | None = None) -> dict[str, Any]:
        config = config or get_settings()
        enabled = config.ANSWER_SUPPORT_MODE == "local_nli"
        identity = (config.SUPPORT_MODEL_PATH, config.SUPPORT_MODEL_REVISION)
        return {
            "mode": config.ANSWER_SUPPORT_MODE,
            "model": NLI.model if enabled else None,
            "revision": config.SUPPORT_MODEL_REVISION if enabled else None,
            "license": NLI.license if enabled else None,
            "minimum_entailment_margin": config.SUPPORT_MIN_MARGIN if enabled else None,
            "max_pair_tokens": MAX_PAIR_TOKENS,
            "batch_size": BATCH_SIZE,
            "device": "cpu" if enabled else None,
            "score_semantics": (
                "raw contradiction/entailment/neutral logits; uncalibrated"
            ),
            "readiness": "disabled"
            if not enabled
            else "error"
            if self._error_identity == identity
            or config.SUPPORT_MODEL_REVISION != NLI.revision
            else "ready"
            if self._identity == identity
            else "not_loaded",
        }

    async def assess(
        self, pairs: list[SupportPair], config: Settings | None = None
    ) -> list[SupportAssessment]:
        snapshot = (config or get_settings()).model_copy(deep=True)
        request = tuple(pairs)
        cancellation = _CancellationGate()
        try:
            return await asyncio.to_thread(
                self._assess, request, snapshot, cancellation
            )
        except asyncio.CancelledError:
            cancellation.cancel()
            raise

    def _assess(
        self,
        pairs: tuple[SupportPair, ...],
        config: Settings,
        cancellation: _CancellationGate,
    ) -> list[SupportAssessment]:
        identity = (config.SUPPORT_MODEL_PATH, config.SUPPORT_MODEL_REVISION)
        cancellation.check()
        while not self._lock.acquire(timeout=0.05):
            cancellation.check()
        try:
            cancellation.check()
            try:
                _validate_config(config)
                cancellation.check()
                directory = validate_assets(Path(config.SUPPORT_MODEL_PATH))
                cancellation.check()
                if self._identity != identity:
                    backend = _load_backend(directory)
                    with cancellation.publication():
                        self._backend, self._identity = backend, identity
                results = self._evaluate(pairs, config.SUPPORT_MIN_MARGIN, cancellation)
                with cancellation.publication():
                    self._error_identity = None
                return results
            except SupportInputBudgetExceeded:
                with cancellation.publication():
                    self._error_identity = None
                raise
            except SupportUnavailableError:
                with cancellation.publication():
                    self._error_identity = identity
                raise
            except Exception as exc:
                with cancellation.publication():
                    self._error_identity = identity
                raise SupportUnavailableError(
                    "Local support model unavailable; install groundtruth[support] "
                    "and run app.support_setup for pinned assets"
                ) from exc
        finally:
            self._lock.release()

    def _evaluate(
        self,
        pairs: tuple[SupportPair, ...],
        minimum_margin: float,
        cancellation: _CancellationGate,
    ) -> list[SupportAssessment]:
        # Check every required pair before inference: never silently truncate.
        batches = [pairs[i : i + BATCH_SIZE] for i in range(0, len(pairs), BATCH_SIZE)]
        batch_lengths = []
        for batch in batches:
            cancellation.check()
            lengths = self._backend.token_lengths(batch)
            cancellation.check()
            if len(lengths) != len(batch) or any(
                type(length) is not int or length <= 0 for length in lengths
            ):
                raise SupportUnavailableError(
                    "Support tokenizer returned invalid lengths"
                )
            if any(length > MAX_PAIR_TOKENS for length in lengths):
                raise SupportInputBudgetExceeded(
                    "Support pair exceeds the fixed 512-token limit; "
                    "split source clauses explicitly",
                    tuple(lengths),
                )
            batch_lengths.append(lengths)
        results: list[SupportAssessment] = []
        for batch, lengths in zip(batches, batch_lengths, strict=True):
            cancellation.check()
            rows = self._backend.logits(batch)
            cancellation.check()
            if len(rows) != len(batch):
                raise SupportUnavailableError(
                    "Support logits batch cardinality is invalid"
                )
            results.extend(
                replace(_assessment(row, minimum_margin), pair_tokens=length)
                for row, length in zip(rows, lengths, strict=True)
            )
        cancellation.check()
        return results


support_service = LocalSupportVerifier()
