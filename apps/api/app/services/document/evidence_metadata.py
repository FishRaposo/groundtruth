"""Bounded untrusted source metadata, never identity/access/publication authority."""

from __future__ import annotations

import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

MAX_METADATA_BYTES = 32 * 1024
MAX_METADATA_DEPTH = 4
ShortText = Annotated[str, StringConstraints(strict=True, max_length=256)]
LabelKey = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=128)]
ContentText = Annotated[str, StringConstraints(strict=True, max_length=4096)]

_RESERVED = frozenset(
    {
        "owner",
        "owner_id",
        "workspace",
        "workspace_id",
        "visibility",
        "organization_id",
        "group",
        "groups",
        "group_id",
        "group_ids",
        "role",
        "roles",
        "admin",
        "is_admin",
        "permissions",
        "permission",
        "version",
        "version_number",
        "document_version",
        "content_hash",
        "snapshot_id",
        "status",
        "source_context",
        "source_context_input",
        "source_context_snapshot",
        "staged_publication_context",
        "staged_publication_profile",
        "staged_context_hash",
        "declared_source_scope",
        "source_path",
        "file_path",
        "storage_path",
        "storage_root",
        "api_key",
        "openai_api_key",
        "anthropic_api_key",
        "access_token",
        "refresh_token",
        "authorization",
        "password",
        "password_hash",
        "credentials",
        "secret",
        "secret_key",
        "token",
    }
)

_RESERVED_NORMALIZED = frozenset(
    "".join(char for char in key if char.isalnum()) for key in _RESERVED
)


class EvidenceMetadataError(ValueError):
    """Controlled reason only; never echo credential or source values."""


class EvidenceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    condition: ContentText | None = None
    conflict_group: ContentText | None = None
    description: (
        Annotated[str, StringConstraints(strict=True, max_length=8192)] | None
    ) = None
    tags: list[ShortText] | None = Field(default=None, max_length=64)
    labels: dict[LabelKey, ShortText] | list[ShortText] | None = Field(
        default=None, max_length=64
    )
    fixture_kind: ShortText | None = None
    portfolio_logical_id: ShortText | None = None
    synthetic: bool = False


def _tree(value, depth=0):
    if depth > MAX_METADATA_DEPTH:
        raise EvidenceMetadataError("evidence_metadata_depth_exceeded")
    if type(value) is dict:
        for key, child in value.items():
            if (
                type(key) is not str
                or key.startswith("_")
                or "".join(char for char in key.casefold() if char.isalnum())
                in _RESERVED_NORMALIZED
            ):
                raise EvidenceMetadataError("evidence_metadata_reserved_field")
            _tree(child, depth + 1)
    elif type(value) is list:
        for child in value:
            _tree(child, depth + 1)
    elif type(value) not in {str, bool, int, float, type(None)}:
        raise EvidenceMetadataError("evidence_metadata_invalid_value")


def validate_evidence_metadata(value: object) -> dict[str, object]:
    """Validate and detach public fields; generated/internal fields cannot enter."""
    if type(value) is not dict:
        raise EvidenceMetadataError("evidence_metadata_object_required")
    _tree(value)
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_METADATA_BYTES:
            raise EvidenceMetadataError("evidence_metadata_bytes_exceeded")
        parsed = EvidenceMetadata.model_validate(value)
    except (ValidationError, UnicodeError, TypeError, OverflowError):
        raise EvidenceMetadataError("evidence_metadata_schema_invalid") from None
    except ValueError as exc:
        if isinstance(exc, EvidenceMetadataError):
            raise
        raise EvidenceMetadataError("evidence_metadata_schema_invalid") from None
    return parsed.model_dump(exclude_unset=True)


def _pairs(items):
    value = {}
    for key, item in items:
        if key in value:
            raise EvidenceMetadataError("evidence_metadata_duplicate_field")
        value[key] = item
    return value


def _constant(_value):
    raise EvidenceMetadataError("evidence_metadata_nonfinite_number")


def parse_evidence_metadata(raw: str) -> dict[str, object]:
    """Decode bounded exact JSON, including duplicate-key and depth rejection."""
    try:
        if type(raw) is not str or len(raw.encode("utf-8")) > MAX_METADATA_BYTES:
            raise EvidenceMetadataError("evidence_metadata_bytes_exceeded")
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except EvidenceMetadataError:
        raise
    except (ValueError, UnicodeError, RecursionError, TypeError):
        raise EvidenceMetadataError("evidence_metadata_json_invalid") from None
    return validate_evidence_metadata(value)
