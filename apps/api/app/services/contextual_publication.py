"""Pure replay of factual publication inventory, not an SQL execution attestation.

The coordinator executes the canonical SQL checks. This module binds their
recorded source inventory to independently supplied immutable snapshots. The
successful before-publication annotation is not a new model/source input.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from copy import deepcopy

from app.services.requirement_contract import PROCEDURE_READ_SET_CONTRACT

_SUCCESS = {
    "consistent": True,
    "reason": None,
    "changed_source_ids": [],
    "changed_groups": [],
}


def _same(actual, expected):
    if json.dumps(actual, sort_keys=True, allow_nan=False) != json.dumps(
        expected, sort_keys=True, allow_nan=False
    ):
        raise ValueError("Factual publication inventory/check mismatch")


def stable_capture(selection, presentation_fields):
    capture = deepcopy(
        {k: v for k, v in selection.items() if k not in presentation_fields}
    )
    read_set = capture.get("procedure_read_set")
    if isinstance(read_set, dict) and "before_publication" in read_set:
        _same(read_set.pop("before_publication"), _SUCCESS)
    return capture


def validate_inventory(selection, chunks, snapshots):
    record = selection["procedure_read_set"]
    if type(record) is not dict or set(record) not in (
        {
            "contract",
            "document_ids",
            "collection_ids",
            "sources",
            "groups",
            "after_proofs",
        },
        {
            "contract",
            "document_ids",
            "collection_ids",
            "sources",
            "groups",
            "after_proofs",
            "before_publication",
        },
    ):
        raise ValueError("Factual publication inventory required")
    _same(record["contract"], PROCEDURE_READ_SET_CONTRACT)
    for key in ("document_ids", "collection_ids"):
        values = record[key]
        if values is not None and (
            type(values) is not list
            or any(type(v) is not str or str(uuid.UUID(v)) != v for v in values)
            or values != sorted(set(values))
        ):
            raise ValueError("Factual publication selectors invalid")
    expected = []
    for inspected in sorted(
        selection["inspected_sources"], key=lambda s: s["chunk_id"]
    ):
        entry = chunks[inspected["chunk_id"]]
        metadata = entry["metadata"]
        if metadata.get("conflict_group") is not None:
            raise ValueError(
                "Curated group replay is not supported by factual-only slice"
            )
        expected.append(
            {
                **entry["identity"],
                "workspace_id": snapshots[inspected["document_id"]].get("workspace_id"),
                "condition": metadata.get("condition"),
                "conflict_group": None,
                "chunk_hash": hashlib.sha256(
                    entry["chunk"].content.encode()
                ).hexdigest(),
            }
        )
    _same(record["sources"], expected)
    _same(record["groups"], [])
    _same(record["after_proofs"], _SUCCESS)
    if "before_publication" in record:
        _same(record["before_publication"], _SUCCESS)
    return stable_capture({"procedure_read_set": record}, ())["procedure_read_set"]
