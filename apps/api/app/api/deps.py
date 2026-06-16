"""FastAPI dependency utilities.

Provides database session and current-user dependencies for API routes.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, Request
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
    return {
        "id": str(api_key.id),
        "name": api_key.name,
        "is_admin": api_key.is_admin,
    }


__all__ = ["get_db", "get_current_user"]
