"""Publication-captured title scope; never factual attribute authority.

Consumers must resolve from the immutable snapshot, not current display fields
or copied live chunk metadata. No timestamps or random row IDs enter hashes.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
import uuid
from typing import Any

CONTEXT_KEY = "source_context"
INPUT_KEY = "source_context_input"
_ORIGINS = frozenset({"declared_title", "upload_basename", "accepted_document_title"})


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_title(title: str) -> str:
    if (
        not isinstance(title, str)
        or not title.strip()
        or len(title) > 512
        or any(unicodedata.category(c).startswith("C") for c in title)
        or re.match(r"^[A-Za-z]:[\\/]|^[/\\]", title)
    ):
        raise ValueError("Title must be 1 to 512 safe text characters")
    return title


def capture_title(
    title: str, *, origin: str = "accepted_document_title"
) -> dict[str, Any]:
    validate_title(title)
    if origin not in _ORIGINS:
        raise ValueError("Unknown accepted title origin")
    return {
        "contract": "source-title-input-v1",
        "title": title,
        "origin": origin,
        "title_hash": _hash(title),
    }


def _capture(value: dict[str, Any]) -> dict[str, Any]:
    title, origin = value.get("title"), value.get("origin")
    if not isinstance(title, str) or not isinstance(origin, str):
        raise ValueError("Invalid captured source title")
    expected = capture_title(title, origin=origin)
    if value != expected:
        raise ValueError("Invalid captured source title")
    return expected


def _manifest(body: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    manifest = []
    for item in chunks:
        index, text = item.get("index"), item.get("content")
        if (
            type(index) is not int
            or index < 0
            or not isinstance(text, str)
            or not text
            or text not in body
        ):
            raise ValueError("Snapshot chunk is not bound to the literal body")
        manifest.append({"index": index, "content_hash": _hash(text)})
    if len({item["index"] for item in manifest}) != len(manifest):
        raise ValueError("Duplicate snapshot chunk index")
    return sorted(manifest, key=lambda item: item["index"])


def build_source_context(
    captured: dict[str, Any] | None,
    *,
    document_id: Any,
    workspace_id: str,
    version_number: int,
    body: str,
    chunks: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if captured is None:
        return None
    captured = _capture(captured)
    if not chunks or type(version_number) is not int or version_number < 1:
        raise ValueError("Title context requires a published chunk snapshot")
    manifest = _manifest(body, chunks)
    manifest_json = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    payload = {
        "contract": "source-context-v1",
        "mode": "versioned_title",
        "usage": "scope_only",
        "document_id": str(uuid.UUID(str(document_id))),
        "workspace_id": workspace_id,
        "version_number": version_number,
        "title": captured["title"],
        "origin": captured["origin"],
        "title_hash": captured["title_hash"],
        "body_hash": _hash(body),
        "chunk_count": len(manifest),
        "chunk_manifest_hash": _hash(manifest_json),
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {**payload, "context_hash": _hash(encoded)}


def _context_copies(chunks: Any) -> list[Any] | None:
    if not isinstance(chunks, list):
        raise ValueError("Invalid immutable source context chunks")
    contexts = []
    present = False
    for item in chunks:
        if not isinstance(item, dict):
            raise ValueError("Invalid immutable source context chunk")
        metadata = item.get("metadata")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise ValueError("Invalid immutable source context metadata")
        if CONTEXT_KEY in metadata:
            present = True
            if not isinstance(metadata[CONTEXT_KEY], dict):
                raise ValueError("Invalid immutable source context")
        contexts.append(metadata.get(CONTEXT_KEY))
    return contexts if present else None


def validated_snapshot_context(snapshot: Any) -> dict[str, Any] | None:
    """Lifecycle check: missing stays unknown; present corruption is an error."""
    chunks = snapshot.chunks or []
    contexts = _context_copies(chunks)
    if contexts is None:
        return None
    first = contexts[0]
    if not isinstance(first, dict) or any(context != first for context in contexts):
        raise ValueError("Inconsistent immutable source context")
    if _hash(snapshot.normalized_content) != snapshot.content_hash:
        raise ValueError("Snapshot body hash mismatch")
    captured = _capture(
        {
            "contract": "source-title-input-v1",
            "title": first.get("title"),
            "origin": first.get("origin"),
            "title_hash": first.get("title_hash"),
        }
    )
    expected = build_source_context(
        captured,
        document_id=snapshot.document_id,
        workspace_id=snapshot.workspace_id,
        version_number=snapshot.version_number,
        body=snapshot.normalized_content,
        chunks=chunks,
    )
    if first != expected:
        raise ValueError("Invalid immutable source context")
    return copy.deepcopy(expected)


def snapshot_title_input(snapshot: Any) -> dict[str, Any] | None:
    context = validated_snapshot_context(snapshot)
    return (
        capture_title(context["title"], origin=context["origin"]) if context else None
    )


def same_title_input(snapshot: Any, captured: dict[str, Any] | None) -> bool:
    return snapshot_title_input(snapshot) == (
        _capture(captured) if captured is not None else None
    )


def apply_source_context(chunks: list[Any], context: dict[str, Any] | None) -> None:
    for chunk in chunks:
        metadata = dict(chunk.metadata_ or {})
        metadata.pop(CONTEXT_KEY, None)
        if context is not None:
            metadata[CONTEXT_KEY] = copy.deepcopy(context)
        chunk.metadata_ = metadata


def resolve_source_context(
    snapshot: Any,
    *,
    document_id: Any,
    workspace_id: str,
    version_number: int,
    body_hash: str,
    chunk_index: int,
    chunk_content: str,
) -> dict[str, Any] | None:
    """Return only immutable, identity-verified title scope, otherwise unknown.

    Authorization belongs to the caller's existing SQL scope. No current title
    or live chunk metadata is accepted here, including during reindexing.
    """
    try:
        if (
            str(snapshot.document_id) != str(uuid.UUID(str(document_id)))
            or snapshot.workspace_id != workspace_id
            or snapshot.version_number != version_number
            or snapshot.content_hash != body_hash
            or type(chunk_index) is not int
            or type(version_number) is not int
        ):
            return None
        context = validated_snapshot_context(snapshot)
        if context is None:
            return None
        item = next(
            (item for item in snapshot.chunks if item["index"] == chunk_index), None
        )
        if item is None or item["content"] != chunk_content:
            return None
        return context
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
