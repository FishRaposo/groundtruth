# Vendored from FishRaposo/operator-shared-core v1.3.0.
# Source commit: dbf276a7708da65b55e1f10b35af634b300d1f07.
"""Consolidated LLM token-pricing registry.

Single source of truth for per-model token costs across the workspace. Reconciles
the previously divergent tables (agenttrace per-1K, knowledgeops per-token, and the
legacy per-1M tables) into one registry, and supports an external JSON/YAML
override file so deployments can adjust prices without code changes. The legacy
cost-estimation facade delegates here.
"""

import json
import os
from typing import Optional, Union

from loguru import logger
from pydantic import BaseModel


class PriceEntry(BaseModel):
    """Cost per 1,000,000 tokens, in USD."""

    input_per_1m: float
    output_per_1m: float


# Default per-1M-token pricing (USD). Values for gpt-4o, gpt-4o-mini,
# claude-3-5-sonnet and claude-3-haiku preserve the legacy price table so
# existing cost-estimation callers are unaffected.
MODEL_PRICING: dict[str, PriceEntry] = {
    "gpt-4o": PriceEntry(input_per_1m=5.0, output_per_1m=15.0),
    "gpt-4o-mini": PriceEntry(input_per_1m=0.150, output_per_1m=0.600),
    "gpt-4-turbo": PriceEntry(input_per_1m=10.0, output_per_1m=30.0),
    "gpt-4": PriceEntry(input_per_1m=30.0, output_per_1m=60.0),
    "gpt-3.5-turbo": PriceEntry(input_per_1m=0.50, output_per_1m=1.50),
    "o1": PriceEntry(input_per_1m=15.0, output_per_1m=60.0),
    "o1-mini": PriceEntry(input_per_1m=1.10, output_per_1m=4.40),
    "o3-mini": PriceEntry(input_per_1m=1.10, output_per_1m=4.40),
    "claude-3-5-sonnet": PriceEntry(input_per_1m=3.0, output_per_1m=15.0),
    "claude-3-5-haiku": PriceEntry(input_per_1m=0.80, output_per_1m=4.0),
    "claude-3-opus": PriceEntry(input_per_1m=15.0, output_per_1m=75.0),
    "claude-3-haiku": PriceEntry(input_per_1m=0.25, output_per_1m=1.25),
    "text-embedding-3-small": PriceEntry(input_per_1m=0.02, output_per_1m=0.0),
    "text-embedding-3-large": PriceEntry(input_per_1m=0.13, output_per_1m=0.0),
}

# Conservative default for unknown models (matches the legacy (5.0, 15.0) fallback).
_DEFAULT_PRICE = PriceEntry(input_per_1m=5.0, output_per_1m=15.0)

_warned_unknown: set[str] = set()


def _lookup(model: str) -> PriceEntry:
    """Resolve a price entry, tolerating dated/suffixed model ids via prefix match."""
    entry = MODEL_PRICING.get(model)
    if entry is not None:
        return entry
    # Longest-key-first so e.g. "gpt-4o-mini-2024-07-18" matches "gpt-4o-mini"
    # before the shorter "gpt-4o" prefix.
    for known in sorted(MODEL_PRICING, key=len, reverse=True):
        if model.startswith(known):
            return MODEL_PRICING[known]
    if model not in _warned_unknown:
        _warned_unknown.add(model)
        logger.warning(
            f"No pricing for model '{model}'; using conservative default "
            f"{_DEFAULT_PRICE.input_per_1m}/{_DEFAULT_PRICE.output_per_1m} per 1M"
        )
    return _DEFAULT_PRICE


def calculate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    *,
    provider: Optional[str] = None,
) -> float:
    """Return the USD cost of a completion given token counts."""
    price = _lookup(model)
    input_cost = (prompt_tokens / 1_000_000) * price.input_per_1m
    output_cost = (completion_tokens / 1_000_000) * price.output_per_1m
    return input_cost + output_cost


def register_pricing(model: str, input_per_1m: float, output_per_1m: float) -> None:
    """Add or override a single model's pricing at runtime."""
    MODEL_PRICING[model] = PriceEntry(
        input_per_1m=input_per_1m, output_per_1m=output_per_1m
    )
    _warned_unknown.discard(model)


def load_pricing_override(path: Union[str, os.PathLike]) -> None:
    """Merge a JSON or YAML pricing file over the registry.

    The file maps a model name to ``{"input_per_1m": float, "output_per_1m": float}``.
    YAML requires PyYAML; JSON always works.
    """
    file_path = os.fspath(path)
    with open(file_path, encoding="utf-8") as fh:
        raw = fh.read()

    if file_path.endswith((".yaml", ".yml")):
        try:
            import yaml  # type: ignore
        except ImportError:
            raise ImportError(
                "PyYAML is required to load YAML pricing overrides. "
                "Install it via 'pip install pyyaml' or use a JSON file."
            ) from None
        data = yaml.safe_load(raw) or {}
    else:
        data = json.loads(raw)

    for model, entry in data.items():
        register_pricing(
            model,
            float(entry["input_per_1m"]),
            float(entry["output_per_1m"]),
        )
