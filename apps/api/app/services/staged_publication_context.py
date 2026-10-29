"""Immutable v3 publication projection inside existing version chunk JSON.

Only publication code creates this context. Loading verifies database bytes;
identity, authorization, current membership and NLI remain separate authorities.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import uuid

from app.models.document import Document, DocumentVersion
from app.services.document.source_context import (
    snapshot_title_input,
    validated_snapshot_context,
)

CONTEXT_KEY = "staged_publication_context"
PROFILE_KEY = "staged_publication_profile"
PROFILE = "contextual_source_v3"
CONTRACT = "staged-publication-context-v1"
REFERENCE = "staged-publication-context-reference-v1"
MAX_CONTEXT_BYTES = 8 * 1024 * 1024
MAX_CHUNKS = 256
_PRIVATE = frozenset(
    {
        "source_path",
        "file_path",
        "storage_path",
        "storage_root",
        "quarantine",
        "error",
        "api_key",
        "access_token",
        "refresh_token",
        "authorization",
        "password",
        "credentials",
        "secret_key",
    }
)


class StagedContextError(ValueError):
    """A controlled reason without source bytes or host paths."""


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _json(value, depth=0):
    if depth > 32:
        raise StagedContextError("staged_context_metadata_depth")
    if value is None or type(value) in {str, int, bool}:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if type(value) is list:
        return [_json(item, depth + 1) for item in value]
    if type(value) is dict and all(type(key) is str for key in value):
        return {
            key: _json(item, depth + 1)
            for key, item in value.items()
            if key.lower() not in _PRIVATE and key != CONTEXT_KEY
        }
    raise StagedContextError("staged_context_metadata_type")


def _base_chunks(snapshot: DocumentVersion):
    chunks = snapshot.chunks
    if type(chunks) is not list or not 1 <= len(chunks) <= MAX_CHUNKS:
        raise StagedContextError("staged_context_chunk_budget")
    result, ids, ordinals = [], set(), set()
    for item in chunks:
        if type(item) is not dict or set(item) != {
            "id",
            "index",
            "content",
            "metadata",
        }:
            raise StagedContextError("staged_context_chunk_schema")
        ident, index, text, metadata = (
            item[key] for key in ("id", "index", "content", "metadata")
        )
        if type(ident) is not str or str(uuid.UUID(ident)) != ident or ident in ids:
            raise StagedContextError("staged_context_chunk_identity")
        if type(index) is not int or index < 0 or index in ordinals:
            raise StagedContextError("staged_context_chunk_ordinal")
        if (
            type(text) is not str
            or not text
            or text not in snapshot.normalized_content
            or type(metadata) is not dict
        ):
            raise StagedContextError("staged_context_chunk_body")
        ids.add(ident)
        ordinals.add(index)
        result.append(
            {"id": ident, "index": index, "content": text, "metadata": _json(metadata)}
        )
    if [row["index"] for row in result] != sorted(ordinals):
        raise StagedContextError("staged_context_chunk_order")
    return result


def _identity(snapshot: DocumentVersion):
    if (
        type(snapshot.version_number) is not int
        or snapshot.version_number < 1
        or not snapshot.workspace_id
    ):
        raise StagedContextError("staged_context_identity")
    body = snapshot.normalized_content
    if type(body) is not str or not body.strip() or len(body.encode()) > 128 * 1024:
        raise StagedContextError("staged_context_body_budget")
    if hashlib.sha256(body.encode()).hexdigest() != snapshot.content_hash:
        raise StagedContextError("staged_context_body_hash")
    return {
        "document_id": str(snapshot.document_id),
        "document_version": snapshot.version_number,
        "content_hash": snapshot.content_hash,
        "workspace_id": snapshot.workspace_id,
        "snapshot_id": str(snapshot.id),
    }


def attach_context(snapshot: DocumentVersion, document: Document) -> None:
    """Freeze final publication data, after metadata/index and actual chunk IDs."""
    if snapshot.id is None:
        raise StagedContextError("staged_context_snapshot_identity_missing")
    identity = _identity(snapshot)
    if (
        str(document.id) != identity["document_id"]
        or document.workspace_id != snapshot.workspace_id
    ):
        raise StagedContextError("staged_context_document_identity")
    title = snapshot_title_input(snapshot)
    if title is None:
        raise StagedContextError("staged_context_title_missing")
    chunks = _base_chunks(snapshot)
    metadata = _json(
        {
            **(document.metadata_ or {}),
            "normalized_content": snapshot.normalized_content,
        }
    )
    payload = {
        "contract": CONTRACT,
        "identity": identity,
        "title_input": title,
        "body_length": len(snapshot.normalized_content),
        "metadata": metadata,
        "owner_id": document.owner_id,
        "status": document.status.value,
        "chunks": chunks,
    }
    if payload["status"] != "ready":
        raise StagedContextError("staged_context_publication_not_ready")
    context = {**payload, "context_hash": digest(payload)}
    if len(canonical(context).encode()) > MAX_CONTEXT_BYTES:
        raise StagedContextError("staged_context_byte_budget")
    snapshot.chunks = [
        {
            **row,
            "metadata": {
                **row["metadata"],
                CONTEXT_KEY: copy.deepcopy(
                    context
                    if index == 0
                    else {
                        "contract": REFERENCE,
                        "context_hash": context["context_hash"],
                    }
                ),
            },
        }
        for index, row in enumerate(chunks)
    ]


def validated_projection(snapshot: DocumentVersion):
    """Rebuild from the immutable DB row; missing legacy context is an error."""
    identity = _identity(snapshot)
    chunks = _base_chunks(snapshot)
    stored = snapshot.chunks
    first = stored[0]["metadata"].get(CONTEXT_KEY)
    if type(first) is not dict or first.get("contract") != CONTRACT:
        raise StagedContextError("staged_publication_context_missing")
    if len(canonical(first).encode()) > MAX_CONTEXT_BYTES:
        raise StagedContextError("staged_context_byte_budget")
    title = snapshot_title_input(snapshot)
    metadata = first.get("metadata")
    if (
        type(metadata) is not dict
        or metadata != _json(metadata)
        or metadata.get("normalized_content") != snapshot.normalized_content
    ):
        raise StagedContextError("staged_context_content_metadata")
    if (
        type(first.get("owner_id")) not in {str, type(None)}
        or first.get("status") != "ready"
    ):
        raise StagedContextError("staged_context_publication_fields")
    payload = {
        "contract": CONTRACT,
        "identity": identity,
        "title_input": title,
        "body_length": len(snapshot.normalized_content),
        "metadata": metadata,
        "owner_id": first["owner_id"],
        "status": "ready",
        "chunks": chunks,
    }
    expected = {**payload, "context_hash": digest(payload)}
    if title is None or canonical(first) != canonical(expected):
        raise StagedContextError("staged_context_binding_mismatch")
    for index, item in enumerate(stored):
        marker = (
            expected
            if index == 0
            else {"contract": REFERENCE, "context_hash": expected["context_hash"]}
        )
        if canonical(item["metadata"].get(CONTEXT_KEY)) != canonical(marker) or _json(
            item["metadata"]
        ) != {
            key: value for key, value in item["metadata"].items() if key != CONTEXT_KEY
        }:
            raise StagedContextError("staged_context_chunk_marker")
    return {
        **identity,
        "body": snapshot.normalized_content,
        "title": title["title"],
        "metadata": copy.deepcopy(metadata),
        "chunks": copy.deepcopy(stored),
        "owner_id": first["owner_id"],
        "status": "ready",
        "role_live_chunks": chunks,
        "captured_scope": validated_snapshot_context(snapshot),
    }
