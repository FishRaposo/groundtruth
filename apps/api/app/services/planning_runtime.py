"""Request-local SQL snapshot and dependency-capture planning inspection.

Inspection records observations only. Actual NLI support, request resolution,
opposition and publication checks remain separate, mandatory consumers.
"""

from dataclasses import dataclass

from sqlalchemy import select

from app.db.cancellation import complete_read
from app.evidence_policy import staged_reading_profile
from app.models.document import DocumentVersion
from app.services import planning_declarations as declarations
from app.services import staged_publication_context as staged
from app.services.linguistic_procedure_runtime import _windows
from app.services.request_planning_manifest import (
    check_planning_read_set,
    inspect_planning_manifest,
)


@dataclass(frozen=True)
class PlanningInspection:
    universe: declarations.PlanningUniverse
    snapshots: tuple[declarations.SourceSnapshot, ...]
    captures: tuple[declarations.SourceCaptures, ...]
    inventory: declarations.DeclarationInventory
    sql_read_set_json: str


async def inspect_planning_declarations(db, principal, request, config):
    """Enumerate first, capture immutable bodies, then recheck SQL membership."""
    manifest = await inspect_planning_manifest(db, principal, request)
    if not manifest.complete:
        raise ValueError(f"Planning inspection incomplete: {manifest.reason}")
    snapshots, captures = [], []
    window_cache = {}
    for source in manifest.sources:
        identity = declarations.SourceIdentity(
            **{
                name: source.identity[name]
                for name in declarations.SourceIdentity.__dataclass_fields__
            }
        )
        projection = None
        if staged_reading_profile(config.EVIDENCE_READING_PROFILE):
            import uuid

            snapshot = await complete_read(
                db.scalar(
                    select(DocumentVersion)
                    .where(
                        DocumentVersion.id == uuid.UUID(identity.snapshot_id),
                        DocumentVersion.document_id == uuid.UUID(identity.document_id),
                        DocumentVersion.workspace_id == identity.workspace_id,
                        DocumentVersion.version_number == identity.document_version,
                        DocumentVersion.content_hash == identity.content_hash,
                    )
                    .execution_options(populate_existing=True)
                )
            )
            if snapshot is None:
                raise staged.StagedContextError("staged_planning_snapshot_missing")
            projection = staged.validated_projection(snapshot)
            mapping = [
                {"id": str(row.id), "index": row.chunk_index, "content": row.content}
                for row in source.chunks
            ]
            expected = [
                {key: row[key] for key in ("id", "index", "content")}
                for row in projection["chunks"]
            ]
            if mapping != expected:
                raise staged.StagedContextError("staged_planning_chunk_mapping_changed")
        chunks = []
        for ordinal, member in enumerate(source.chunks):
            start = source.body.find(member.content)
            chunks.append(
                declarations.SourceChunk(
                    str(member.id),
                    member.chunk_index,
                    declarations.RawRange(
                        start, start + len(member.content), member.content
                    ),
                    declarations.canonical(
                        projection["chunks"][ordinal]["metadata"]
                        if projection is not None
                        else (member.metadata or {})
                    ),
                )
            )
        snapshots.append(
            declarations.SourceSnapshot(
                identity,
                projection["title"]
                if projection is not None
                else source.identity["title"],
                source.body,
                declarations.canonical(
                    projection["metadata"]
                    if projection is not None
                    else source.metadata
                ),
                tuple(chunks),
            )
        )
        windows = await _windows(source.body, config, window_cache)
        captures.append(
            declarations.SourceCaptures(
                identity,
                tuple(
                    declarations.CaptureWindow(
                        window["start"],
                        window["end"],
                        declarations.canonical(window["capture"]),
                    )
                    for window in windows
                ),
            )
        )
    universe = declarations.PlanningUniverse(
        declarations.canonical(manifest.record()),
        tuple(source.identity for source in snapshots),
        "bounded_authorized_scan",
    )
    inventory = declarations.declaration_inventory(
        universe, tuple(snapshots), tuple(captures)
    )
    consistent = await check_planning_read_set(
        db, principal, request, manifest.record()
    )
    if not consistent["consistent"]:
        raise ValueError(f"Planning inspection changed: {consistent['reason']}")
    return PlanningInspection(
        universe,
        tuple(snapshots),
        tuple(captures),
        inventory,
        declarations.canonical(manifest.record()),
    )
