"""Offline document-enrichment helpers used by GroundTruth ingestion.

The algorithms are adapted from document-intelligence-pipeline at
``6c85a76be3f564983b50248b5f99f1658875931f`` and kept dependency-free so
ingestion remains deterministic when no external AI provider is configured.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from typing import Any

_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
_URL_RE = re.compile(r"https?://[^\s<>\"')]+")
_PHONE_RE = re.compile(
    r"\b(?:\+?\d{1,3}[\s.\-]?)?(?:\(\d{2,4}\)[\s.\-]?)?"
    r"\d{3,4}[\s.\-]\d{3,4}\b"
)
_CAPITALISED_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b")
_URL_TRAILING = ".,;:!?)]}>'\""
_CAPITALISED_STOPWORDS = {
    "A",
    "An",
    "And",
    "At",
    "But",
    "By",
    "For",
    "If",
    "In",
    "It",
    "On",
    "Or",
    "That",
    "The",
    "These",
    "This",
    "Those",
    "When",
    "While",
}


def normalize_content(content: str) -> str:
    """Collapse extraction whitespace into a stable canonical representation."""
    return re.sub(r"\s+", " ", content).strip()


def content_hash(content: str) -> str:
    """Return a SHA-256 digest of normalized document or chunk content."""
    canonical = normalize_content(content)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def deduplicate_chunks(chunks: list[str]) -> list[str]:
    """Drop repeated normalized chunks while preserving first-seen order."""
    unique: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        canonical = normalize_content(chunk)
        if not canonical:
            continue
        digest = content_hash(canonical)
        if digest in seen:
            continue
        seen.add(digest)
        unique.append(canonical)
    return unique


def select_canonical_duplicate(documents: Iterable[Any]) -> Any | None:
    """Choose the earliest prior document, using its UUID as a stable tie-break."""
    return min(
        documents,
        key=lambda document: (document.created_at, str(document.id)),
        default=None,
    )


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def extract_entities(content: str) -> dict[str, list[str]]:
    """Extract common entity shapes without a model, network, or API key."""
    if not content:
        return {"emails": [], "urls": [], "phones": [], "capitalised": []}

    urls = _deduplicate([url.rstrip(_URL_TRAILING) for url in _URL_RE.findall(content)])
    scrubbed = _URL_RE.sub(" ", content)
    emails = _deduplicate(_EMAIL_RE.findall(scrubbed))
    scrubbed = _EMAIL_RE.sub(" ", scrubbed)
    phones = _deduplicate([phone.strip() for phone in _PHONE_RE.findall(scrubbed)])
    capitalised = [
        phrase
        for phrase in _CAPITALISED_RE.findall(scrubbed)
        if phrase not in _CAPITALISED_STOPWORDS
        and phrase.split()[0] not in _CAPITALISED_STOPWORDS
    ]

    return {
        "emails": emails,
        "urls": urls,
        "phones": phones,
        "capitalised": _deduplicate(capitalised),
    }
