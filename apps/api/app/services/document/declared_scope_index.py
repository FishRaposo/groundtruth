"""SQLite candidate scanning over server-derived, immutable source covers.

This is a portable correctness path, not a native indexed-performance claim.
The SQL predicate validates the cover against the actual current snapshot before
the ORM body limit. Missing/forged/unsupported indexes retain a candidate. SQL
authorization remains the caller's authority and precedes the final result limit.
"""

from __future__ import annotations

import hashlib
import json
import uuid

from app.evidence_policy import reading_version, resolve_evidence_policy
from app.models.document import Document, DocumentVersion
from app.services.answer_requirements import plan_requirements
from app.services.declared_source_scope import (
    scope_relevance,
    source_cover,
    validate_source_cover,
)
from sqlalchemy import func, select

INDEX_KEY = "declared_source_scope"
SQL_FUNCTION = "groundtruth_scope_candidate_v1"


def publication_metadata(metadata, body, *, document_id, version, workspace, config):
    """Regenerate only a current derived index; never rewrite content snapshots."""
    result = dict(metadata)
    profile = getattr(config, "EVIDENCE_READING_PROFILE", "clause_bound_v1")
    if profile == "clause_bound_v1":
        return result
    reading_version(profile)
    if not resolve_evidence_policy(config).contextual_source:
        return result
    result.pop(INDEX_KEY, None)
    identity = {
        "document_id": str(document_id),
        "document_version": version,
        "content_hash": hashlib.sha256(body.encode()).hexdigest(),
        **(
            {"workspace_id": workspace}
            if isinstance(workspace, str) and workspace
            else {}
        ),
    }
    if len(body.encode()) > 128 * 1024:
        result[INDEX_KEY] = {
            "contract": reading_version("contextual_source_v1").scope_cover,
            "identity": identity,
            "status": "unavailable",
            "reason": "source_scope_body_budget_exceeded",
        }
    else:
        result[INDEX_KEY] = source_cover(body, identity)
    return result


def _identifier(value):
    return str(uuid.UUID(str(value)))


def _candidate(index, body, document_id, version, digest, workspace, scopes_json):
    """An uncertain index is never authority for excluding a source."""
    try:
        cover, scopes = json.loads(index), json.loads(scopes_json)
        if (
            not isinstance(cover, dict)
            or not isinstance(body, str)
            or len(body.encode("utf-8")) > 128 * 1024
            or not isinstance(scopes, list)
            or not 0 < len(scopes) <= 16
            or any(not isinstance(s, str) or not s.strip() for s in scopes)
        ):
            return 1
        identity = cover["identity"]
        authoritative_identity = {
            "document_id": _identifier(document_id),
            "document_version": version,
            "content_hash": digest,
            "workspace_id": workspace,
        }
        if (
            identity != authoritative_identity
            or type(identity["document_version"]) is not int
            or hashlib.sha256(body.encode()).hexdigest() != digest
            or not validate_source_cover(cover, body, authoritative_identity)
        ):
            return 1
        return int(
            any(
                scope_relevance(cover, subject)["status"] != "irrelevant"
                for subject in scopes
            )
        )
    except (KeyError, TypeError, ValueError, AttributeError, UnicodeError):
        return 1


def _scopes(question):
    try:
        requirements = plan_requirements(
            question, reading_profile="contextual_source_v1"
        )
    except ValueError:
        return []
    values = []
    for req in requirements:
        if req.kind not in {"owner", "deputy"} or not req.topic:
            continue
        values.append(req.topic)
    return list(dict.fromkeys(values))


async def candidate_predicate(db, question):
    """Return a SQL predicate; unsupported dialects retain all authorized rows."""
    scopes = _scopes(question)
    connection = await db.connection()
    if connection.dialect.name != "sqlite":
        return None, {"mode": "unavailable", "subjects": scopes}

    def register(sync_connection):
        sync_connection.connection.dbapi_connection.create_function(
            SQL_FUNCTION, 7, _candidate, deterministic=True
        )

    await connection.run_sync(register)
    body = (
        select(DocumentVersion.normalized_content)
        .where(
            DocumentVersion.document_id == Document.id,
            DocumentVersion.workspace_id == Document.workspace_id,
            DocumentVersion.version_number == Document.version_number,
            DocumentVersion.content_hash == Document.content_hash,
        )
        .correlate(Document)
        .scalar_subquery()
    )
    predicate = (
        getattr(func, SQL_FUNCTION)(
            func.json_extract(Document.metadata_, "$." + INDEX_KEY),
            body,
            Document.id,
            Document.version_number,
            Document.content_hash,
            Document.workspace_id,
            json.dumps(scopes),
        )
        == 1
    )
    return predicate, {
        "mode": "sqlite_verified_source_cover_scan",
        "contract": reading_version("contextual_source_v1").scope_cover,
        "subjects": scopes,
        "performance": "SQL compatibility scan; no indexed-scale claim",
    }


async def capture_index_universe(db, authority):
    """Retain scalar membership/fingerprints, never the private source bodies."""
    rows = (
        await db.execute(
            select(
                Document.id,
                Document.workspace_id,
                Document.owner_id,
                Document.version_number,
                Document.content_hash,
                Document.metadata_[INDEX_KEY],
            )
            .where(authority)
            .order_by(Document.id)
        )
    ).all()
    return [
        {
            "document_id": str(row[0]),
            "workspace_id": row[1],
            "owner_id": row[2],
            "document_version": row[3],
            "content_hash": row[4],
            "index_hash": hashlib.sha256(
                json.dumps(
                    row[5], sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()
            ).hexdigest(),
        }
        for row in rows
    ]
