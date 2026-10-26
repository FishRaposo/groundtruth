"""SQL authorization predicates shared by retrieval and all document readers.

Workspace membership is supplied by API-key metadata, never a client header.
The predicates narrow candidates before ranking/limiting, including on SQLite.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.models.collection import Collection, CollectionShare, collection_documents
from app.models.document import Document
from app.utils.time import utc_now
from fastapi import HTTPException
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

Principal = dict[str, Any]


def document_scope(principal: Principal, *, write: bool = False):
    workspace = principal.get("workspace_id", "default")
    if principal.get("is_admin"):
        return Document.workspace_id == workspace
    user = str(principal["id"])
    allowed_permissions = ["write", "admin"] if write else ["read", "write", "admin"]
    share = exists(
        select(CollectionShare.id).where(
            CollectionShare.collection_id == Collection.id,
            CollectionShare.permission.in_(allowed_permissions),
            or_(
                CollectionShare.expires_at.is_(None),
                CollectionShare.expires_at > utc_now(),
            ),
            or_(
                CollectionShare.user_id == user,
                CollectionShare.group_id.in_(
                    ["everyone", *principal.get("group_ids", [])]
                ),
            ),
        )
    )
    collection_rules = [Collection.owner_id == user, share]
    if not write:
        collection_rules.append(Collection.is_public == "public")
        if principal.get("organization_id"):
            collection_rules.append(
                and_(
                    Collection.is_public == "organization",
                    Collection.organization_id == principal["organization_id"],
                )
            )
    in_collection = exists(
        select(collection_documents.c.document_id)
        .join(Collection, Collection.id == collection_documents.c.collection_id)
        .where(
            collection_documents.c.document_id == Document.id,
            or_(*collection_rules),
        )
    )
    return and_(
        Document.workspace_id == workspace,
        or_(Document.owner_id == user, in_collection),
    )


def owned_scope(model: Any, principal: Principal):
    workspace = principal.get("workspace_id", "default")
    if principal.get("is_admin"):
        # Null historical workspace belongs only to the default workspace admin.
        return or_(
            model.workspace_id == workspace,
            and_(model.workspace_id.is_(None), workspace == "default"),
        )
    return and_(model.workspace_id == workspace, model.owner_id == str(principal["id"]))


async def require_document(
    db: AsyncSession,
    identifier: uuid.UUID | str,
    principal: Principal,
    *,
    write: bool = False,
) -> Document:
    try:
        identifier = uuid.UUID(str(identifier))
    except ValueError as exc:
        raise HTTPException(404, "Document not found") from exc
    row = await db.scalar(
        select(Document).where(
            Document.id == identifier, document_scope(principal, write=write)
        )
    )
    if row is None:
        raise HTTPException(404, "Document not found")
    return row
