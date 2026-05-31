import hashlib

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.models.api_key import ApiKey

settings = get_settings()


class ApiKeyAuth:
    """FastAPI dependency that validates X-API-Key header against stored hashes.

    In testing mode or when AUTH_ENABLED is false, authentication is bypassed
    and a synthetic admin key is returned.
    """

    async def __call__(
        self,
        request: Request,
        db: AsyncSession = Depends(get_db),
    ) -> ApiKey:
        """Extract and validate the API key from the request header.

        Args:
            request: The incoming HTTP request.
            db: Async database session injected by FastAPI.

        Returns:
            The validated ApiKey ORM object.

        Raises:
            HTTPException: 401 if the key is missing, invalid, or inactive.
        """
        if not settings.AUTH_ENABLED or settings.APP_ENV == "testing":
            return await self._bypass_auth(db)

        raw_key = request.headers.get("X-API-Key")
        if not raw_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-API-Key header",
            )

        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        try:
            result = await db.execute(
                select(ApiKey).where(
                    ApiKey.key_hash == key_hash,
                    ApiKey.is_active == True,
                )
            )
            api_key = result.scalar_one_or_none()
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            )

        if api_key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or inactive API key",
            )

        await db.execute(
            update(ApiKey)
            .where(ApiKey.id == api_key.id)
            .values(last_used_at=__import__("datetime").datetime.utcnow())
        )
        await db.commit()

        request.state.api_key = api_key
        return api_key

    async def _bypass_auth(self, db: AsyncSession) -> ApiKey:
        """Return a synthetic admin key for testing or when auth is disabled.

        Args:
            db: Async database session.

        Returns:
            A synthetic ApiKey with admin privileges.
        """
        from datetime import datetime

        api_key = ApiKey(
            id=__import__("uuid").uuid4(),
            name="admin",
            key_hash="bypass",
            key_prefix="bypass",
            is_active=True,
            is_admin=True,
            rate_limit=9999,
            created_at=datetime.utcnow(),
            last_used_at=None,
        )
        return api_key


api_key_auth = ApiKeyAuth()


async def require_admin(
    api_key: ApiKey = Depends(api_key_auth),
) -> ApiKey:
    """Dependency that requires the authenticated key to have admin privileges.

    Args:
        api_key: The authenticated API key from ApiKeyAuth.

    Returns:
        The admin ApiKey.

    Raises:
        HTTPException: 403 if the key is not an admin key.
    """
    if not api_key.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return api_key
