"""Literal connected content profile, separate from legacy library normalization."""

from __future__ import annotations

from typing import Any

PROFILE = "connected-paragraphs-v1"
PROFILE_KEY = "content_profile"
LITERAL_CHUNKING = "connected-literal-windows-v1"
SNAPSHOT_CHUNKING = {
    "restore": "immutable-snapshot-restore-v1",
    "reindex": "immutable-snapshot-reindex-v1",
}
ENCODER_KEYS = ("mode", "model", "revision", "dimension")


def canonical_content(content: str) -> str:
    """Canonical LF; trim complete outer blank lines, never retained indentation."""
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    first, last = 0, len(lines)
    while first < last and not lines[first].strip():
        first += 1
    while first < last and not lines[last - 1].strip():
        last -= 1
    return "\n".join(lines[first:last])


def literal_windows(content: str, size: int, overlap: int) -> list[str]:
    size = max(1, size)
    stride = size - min(max(0, overlap), size - 1)
    result = []
    for first in range(0, len(content), stride):
        result.append(content[first : first + size])
        if first + size >= len(content):
            break
    return result


def exact_chunks(body: str, chunks: list[str]) -> list[str]:
    """Validate literal passages, then deduplicate exact text without rewriting."""
    result, seen = [], set()
    for text in chunks:
        if not isinstance(text, str) or text not in body:
            raise ValueError("Chunk is not a literal body passage")
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def snapshot_profile(snapshot: Any) -> str | None:
    profiles = {
        (item.get("metadata") or {}).get(PROFILE_KEY) for item in snapshot.chunks or []
    }
    if not profiles:
        return None
    if len(profiles) != 1:
        raise ValueError("Inconsistent snapshot content profile")
    profile = profiles.pop()
    if profile is not None and (not isinstance(profile, str) or not profile):
        raise ValueError("Invalid snapshot content profile")
    return profile


def encoder_identity(signature: dict[str, Any]) -> dict[str, Any]:
    return {key: signature.get(key) for key in ENCODER_KEYS}


def known_connected_encoder(signature: dict[str, Any]) -> bool:
    return (
        signature.get("mode") in {"local", "deterministic"}
        and all(
            isinstance(signature.get(key), str) and signature[key]
            for key in ("model", "revision")
        )
        and type(signature.get("dimension")) is int
        and signature["dimension"] > 0
    )


def snapshot_chunk_metadata(
    snapshot: Any, item: dict, signature: dict, kind: str
) -> dict:
    source_signature = (item.get("metadata") or {}).get("embedding_signature") or {}
    source_chunking = source_signature.get("chunking")
    method = SNAPSHOT_CHUNKING[kind]
    return {
        "embedding_signature": {**signature, "chunking": method},
        "chunking_provenance": {
            "method": method,
            "source_version": snapshot.version_number,
            "source_chunk_index": item["index"],
            "source_chunking": source_chunking
            if isinstance(source_chunking, str)
            else None,
            "reembedded_encoder": encoder_identity(signature),
        },
    }
