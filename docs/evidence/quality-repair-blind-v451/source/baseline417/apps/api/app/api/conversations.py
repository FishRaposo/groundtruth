"""Owned conversation metadata and permission-aware durable history."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.conversation import Conversation
from app.models.query import Query
from app.services.access_control.scope import owned_scope
from app.services.connected_query import present_query

router = APIRouter(tags=["conversations"])


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


@router.get("/identity")
async def identity(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    return {key: user[key] for key in ("id", "name", "is_admin", "workspace_id")}


@router.post("/conversations")
async def create_conversation(
    body: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    row = Conversation(
        title=body.title,
        owner_id=str(user["id"]),
        workspace_id=user.get("workspace_id", "default"),
    )
    db.add(row)
    await db.commit()
    return row.to_dict()


@router.get("/conversations")
async def list_conversations(
    db: AsyncSession = Depends(get_db), user: dict[str, Any] = Depends(get_current_user)
) -> list[dict[str, Any]]:
    rows = (
        await db.scalars(
            select(Conversation)
            .where(owned_scope(Conversation, user))
            .order_by(Conversation.updated_at.desc())
            .limit(100)
        )
    ).all()
    return [row.to_dict() for row in rows]


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    row = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, owned_scope(Conversation, user)
        )
    )
    if row is None:
        raise HTTPException(404, "Conversation not found")
    queries = (
        await db.scalars(
            select(Query)
            .where(Query.conversation_id == row.id, owned_scope(Query, user))
            .order_by(Query.created_at)
            .limit(100)
        )
    ).all()
    return {
        **row.to_dict(),
        "queries": [
            (await present_query(db, query, user)).model_dump(mode="json")
            for query in queries
        ],
    }
