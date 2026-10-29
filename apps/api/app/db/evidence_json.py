"""Lossless large staged query storage; never an evidence or access verdict.

Raw SQL readers must call load_evidence_json on the raw column text with its
column name, before a JSON loader discards duplicate keys. Encoded rows are not
transparent to SQL JSON-path expressions.
Legacy values pass through unchanged; reading never rewrites persisted records.
"""

from __future__ import annotations

import base64
import binascii
import gzip
import hashlib
import json
import math
import re
import zlib
from collections.abc import Callable
from typing import Any

from sqlalchemy import JSON, Text, cast, type_coerce
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import TypeDecorator

from app.evidence_policy import (
    SOURCE_BOUND_PROFILE_CONTRACT,
    reading_version,
    recorded_evidence_policy,
)

MARKER = "__groundtruth_evidence_json__"
MIN_COMPRESS_BYTES = 128 * 1024
MAX_JSON_BYTES = 256 * 1024 * 1024
_COLUMNS = frozenset({"provenance", "retrieval_trace"})
_FIELDS = frozenset({MARKER, "column", "encoding", "raw_bytes", "sha256", "payload"})
_STORAGE_SIGNATURE = _FIELDS - {MARKER}
_MAX_BASE64_BYTES = 4 * ((MAX_JSON_BYTES + 2) // 3)


class EvidenceArchiveError(ValueError):
    """Sanitized storage-integrity failure; callers must withhold content."""


def _invalid() -> EvidenceArchiveError:
    return EvidenceArchiveError("Recorded evidence archive is invalid or unavailable.")


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _archive_shaped(value: Any) -> bool:
    if type(value) is not dict:
        return False
    if MARKER in value or _STORAGE_SIGNATURE.issubset(value):
        return True
    # A partial frame needs a codec-specific compression discriminator. Size/hash
    # metadata alone is ordinary legacy data, even when it names these columns.
    # Removing every discriminator is indistinguishable from such legacy data.
    if len(_STORAGE_SIGNATURE.intersection(value)) < 3:
        return False
    payload = value.get("payload")
    return value.get("encoding") == "gzip+base64" or (
        type(payload) is str and payload.startswith("H4sI")
    )


def _parse_storage_json(raw: str | bytes | bytearray) -> Any:
    duplicate_outer_key = False

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        nonlocal duplicate_outer_key
        # The root object's hook runs last; nested legacy duplicate keys keep
        # ordinary JSON last-value semantics and do not mark the root frame.
        duplicate_outer_key = len(items) != len({key for key, _ in items})
        return dict(items)

    try:
        parsed = json.loads(raw, object_pairs_hook=pairs)
        if _archive_shaped(parsed) and duplicate_outer_key:
            raise _invalid()
        return parsed
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise _invalid() from None


def load_evidence_json(raw: str | bytes | bytearray, *, column: str) -> Any:
    """Read raw SQL JSON text, checking framing before duplicate keys are lost."""
    return decode_evidence_json(_parse_storage_json(raw), column=column)


def _constant(value: str) -> Any:
    raise _invalid()


def _finite_number(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise _invalid()
    return number


def _unique_pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise _invalid()
        result[key] = value
    return result


def _future_staged(value: Any, column: str) -> bool:
    if type(value) is not dict:
        return False
    provenance = value if column == "provenance" else value.get("provenance")
    if type(provenance) is not dict:
        return False
    selection = provenance.get("answer_selection")
    if type(selection) is not dict:
        return False
    profile = selection.get("evidence_profile")
    if type(profile) is not dict:
        return False
    if profile.get("contract") == SOURCE_BOUND_PROFILE_CONTRACT:
        try:
            policy = recorded_evidence_policy(profile)
            return (
                policy.source_governance_profile == "requirement_bound_v1"
                and selection.get("contract") == policy.requirement_contract
            )
        except (ValueError, TypeError, KeyError, RecursionError):
            return False
    return any(
        selection.get("contract") == version.requirement
        and profile.get("contract") == version.evidence_profile
        and profile.get("evidence_reading_profile") == version.profile
        for version in (
            reading_version("contextual_source_v3"),
            reading_version("contextual_source_v4"),
        )
    )


def encode_evidence_json(value: Any, *, column: str) -> Any:
    """Encode eligible future writes without changing legacy JSON binding."""
    if column not in _COLUMNS:
        raise _invalid()
    if _archive_shaped(value):
        raise _invalid()
    if not _future_staged(value, column):
        return value
    try:
        raw = _json_bytes(value)
        if len(raw) < MIN_COMPRESS_BYTES:
            return value
        if len(raw) > MAX_JSON_BYTES:
            raise _invalid()
        compressed = gzip.compress(raw, compresslevel=1, mtime=0)
        envelope = {
            MARKER: 1,
            "column": column,
            "encoding": "gzip+base64",
            "raw_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "payload": base64.b64encode(compressed).decode("ascii"),
        }
        return envelope if len(_json_bytes(envelope)) < len(raw) else value
    except (ValueError, TypeError, UnicodeError, OverflowError):
        raise _invalid() from None


def decode_evidence_json(value: Any, *, column: str) -> Any:
    """Decode JSON-parsed storage or fail closed, before content presentation.

    Storage framing does not replace source authorization or independent output
    reconstruction. Raw SQL callers use load_evidence_json before JSON parsing;
    this parsed-value helper cannot recover already discarded duplicate keys.
    """
    if column not in _COLUMNS:
        raise _invalid()
    if not _archive_shaped(value):
        return value
    try:
        expected = value.get("raw_bytes")
        payload, digest = value.get("payload"), value.get("sha256")
        if (
            set(value) != _FIELDS
            or type(value[MARKER]) is not int
            or value[MARKER] != 1
            or value["column"] != column
            or value["encoding"] != "gzip+base64"
            or type(expected) is not int
            or not 0 < expected <= MAX_JSON_BYTES
            or type(payload) is not str
            or not 0 < len(payload) <= _MAX_BASE64_BYTES
            or type(digest) is not str
            or re.fullmatch(r"[a-f0-9]{64}", digest) is None
        ):
            raise _invalid()
        compressed = base64.b64decode(payload, validate=True)
        if len(compressed) > MAX_JSON_BYTES:
            raise _invalid()
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        raw = decoder.decompress(compressed, expected + 1)
        if (
            len(raw) != expected
            or not decoder.eof
            or decoder.unconsumed_tail
            or decoder.unused_data
            or hashlib.sha256(raw).hexdigest() != digest
        ):
            raise _invalid()
        restored = json.loads(
            raw.decode("utf-8"),
            parse_constant=_constant,
            parse_float=_finite_number,
            object_pairs_hook=_unique_pairs,
        )
        if (
            type(restored) is not dict
            or MARKER in restored
            or not _future_staged(restored, column)
        ):
            raise _invalid()
        return restored
    except (
        ValueError,
        TypeError,
        UnicodeError,
        binascii.Error,
        zlib.error,
        RecursionError,
    ):
        raise _invalid() from None


class EvidenceJSON(TypeDecorator[Any]):
    """Keep SQL JSON and transparently decode each column separately."""

    impl = JSON
    cache_ok = True

    def __init__(self, column: str):
        if column not in _COLUMNS:
            raise ValueError("Unsupported evidence storage column")
        self.column = column
        super().__init__()

    def process_bind_param(self, value: Any, dialect: Any) -> Any:
        return encode_evidence_json(value, column=self.column)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        return decode_evidence_json(value, column=self.column)

    def column_expression(self, colexpr: Any) -> ColumnElement[Any]:
        # asyncpg's JSON codec otherwise performs lossy json.loads before ORM
        # result processors. JSON::text keeps framing available to this type;
        # only SELECT projections change, not storage type or JSON operators.
        return type_coerce(cast(colexpr, Text), self)

    def result_processor(self, dialect: Any, coltype: Any) -> Callable[[Any], Any]:
        # Inspect raw framing before the underlying loader can discard duplicate
        # keys. Casting projections to text also protects the asyncpg boundary.
        loader = self.impl_instance.result_processor(dialect, coltype)

        def process(value: Any) -> Any:
            try:
                if isinstance(value, (str, bytes, bytearray)):
                    parsed = _parse_storage_json(value)
                    if loader is not None and dialect._json_deserializer is not None:
                        parsed = loader(value)
                else:
                    parsed = loader(value) if loader is not None else value
            except (ValueError, TypeError, UnicodeError, RecursionError):
                raise _invalid() from None
            return self.process_result_value(parsed, dialect)

        return process
