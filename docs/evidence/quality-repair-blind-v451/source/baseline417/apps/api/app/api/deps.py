"""FastAPI dependency utilities.

Provides database session and current-user dependencies for API routes.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import api_key_auth


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Extract and validate the current user from the request.

    Delegates to the shared ApiKeyAuth dependency for validation.

    Args:
        request: The incoming HTTP request.
        db: Async database session.

    Returns:
        A dictionary representing the authenticated user/api-key.
    """
    api_key = await api_key_auth(request, db)
    from app.config import get_settings

    settings = get_settings()
    if settings.AUTH_ENABLED and not settings.connected:
        raise HTTPException(
            503,
            (
                "Authenticated HTTP workflows require explicit connected "
                "embedding and generation modes. Legacy mode remains "
                "available through the library and single-user development "
                "profile."
            ),
        )
    metadata = api_key.metadata_ or {}
    return {
        "id": str(api_key.id),
        "name": api_key.name,
        "is_admin": api_key.is_admin,
        "workspace_id": metadata.get("workspace_id", "default"),
        "organization_id": metadata.get("organization_id"),
        "group_ids": list(metadata.get("group_ids", [])),
    }


__all__ = ["get_db", "get_current_user"]
