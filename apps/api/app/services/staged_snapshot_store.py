"""Exact immutable v3 planning identities from both presentation channels.

The caller checks current ACLs. These DB loads establish historical bytes only;
selection fields never supply title, body, metadata or chunk contents.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.cancellation import complete_read
from app.evidence_policy import reading_version
from app.models.document import DocumentVersion
from app.services.staged_plan_replay import CONTRACT as LEGACY_INPUT_CONTRACT
from app.services.staged_publication_context import (
    StagedContextError,
    canonical,
    validated_projection,
)

IDENTITY = (
    "document_id",
    "document_version",
    "content_hash",
    "workspace_id",
    "snapshot_id",
)


def has_known_input_contract(record):
    """Recognize identity transports only; no semantic acceptance is granted."""
    return type(record) is dict and record.get("contract") in {
        LEGACY_INPUT_CONTRACT,
        reading_version("contextual_source_v4").request_inputs,
    }


def _identity(row):
    if type(row) is not dict or any(key not in row for key in IDENTITY):
        raise StagedContextError("staged_snapshot_identity_missing")
    result = {key: row[key] for key in IDENTITY}
    for key in ("document_id", "snapshot_id"):
        if type(result[key]) is not str or str(uuid.UUID(result[key])) != result[key]:
            raise StagedContextError("staged_snapshot_identity_invalid")
    if (
        type(result["document_version"]) is not int
        or result["document_version"] < 1
        or type(result["workspace_id"]) is not str
        or not result["workspace_id"]
        or type(result["content_hash"]) is not str
        or len(result["content_hash"]) != 64
        or any(c not in "0123456789abcdef" for c in result["content_hash"])
    ):
        raise StagedContextError("staged_snapshot_identity_invalid")
    return result


def _identities(selection):
    inputs = selection.get("staged_request_inputs")
    if not has_known_input_contract(inputs):
        raise StagedContextError("staged_snapshot_inputs_missing")
    manifest = inputs.get("manifest")
    snapshots = inputs.get("snapshots")
    if (
        type(manifest) is not dict
        or type(manifest.get("publications")) is not list
        or type(snapshots) is not list
    ):
        raise StagedContextError("staged_snapshot_inputs_invalid")
    groups = (
        manifest["publications"],
        [row.get("identity") if type(row) is dict else None for row in snapshots],
    )
    result = []
    for group in groups:
        if len(group) > 128:
            raise StagedContextError("staged_snapshot_document_budget")
        seen = set()
        for row in group:
            identity = _identity(row)
            if identity["document_id"] in seen:
                raise StagedContextError("staged_snapshot_duplicate_identity")
            seen.add(identity["document_id"])
            result.append(identity)
    return result


async def load_staged_snapshots(db: AsyncSession, selection, *, query_context=None):
    """Return all independently loaded planning members, including noncited ones."""
    from app.services.procedure_output import retained_selection

    if type(selection) is not dict:
        raise StagedContextError("staged_snapshot_selection_invalid")
    channels = [selection]
    retained = retained_selection(query_context) if query_context is not None else None
    if retained is not None:
        channels.append(retained)
    identities = {}
    for channel in channels:
        for identity in _identities(channel):
            key = identity["document_id"]
            if key in identities and canonical(identities[key]) != canonical(identity):
                raise StagedContextError("staged_snapshot_conflicting_identity")
            identities[key] = identity
    if len(identities) > 128:
        raise StagedContextError("staged_snapshot_document_budget")
    result, total = {}, 0
    for key, identity in identities.items():
        with db.no_autoflush:
            snapshot = await complete_read(
                db.scalar(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.id == uuid.UUID(identity["snapshot_id"]),
                        DocumentVersion.document_id == uuid.UUID(key),
                        DocumentVersion.workspace_id == identity["workspace_id"],
                        DocumentVersion.version_number == identity["document_version"],
                        DocumentVersion.content_hash == identity["content_hash"],
                    )
                    .execution_options(populate_existing=True)
                )
            )
        if snapshot is None:
            raise StagedContextError("staged_snapshot_missing")
        projection = validated_projection(snapshot)
        total += len(projection["body"].encode())
        if total > 2 * 1024 * 1024:
            raise StagedContextError("staged_snapshot_total_body_budget")
        result[key] = projection
    return result
