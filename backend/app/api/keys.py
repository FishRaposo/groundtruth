import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.middleware.auth import require_admin
from app.models.api_key import (
    ApiKey,
    ApiKeyCreate,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
    ApiKeyUpdate,
    generate_api_key,
)

router = APIRouter(tags=["keys"])


@router.post("/keys", response_model=ApiKeyCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreate,
    db: AsyncSession = Depends(get_db),
    _admin: ApiKey = Depends(require_admin),
) -> ApiKeyCreateResponse:
    """Create a new API key. The raw key is returned only once.

    Args:
        body: The key creation payload with name, is_admin, and rate_limit.
        db: Async database session.
        _admin: The authenticated admin key (enforced by dependency).

    Returns:
        The created key details including the raw key (shown once).
    """
    raw_key, key_hash, key_prefix = generate_api_key()

    api_key = ApiKey(
        name=body.name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_admin=body.is_admin,
        rate_limit=body.rate_limit,
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)

    return ApiKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key=raw_key,
        is_admin=api_key.is_admin,
        rate_limit=api_key.rate_limit,
        created_at=api_key.created_at,
    )


@router.get("/keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    _admin: ApiKey = Depends(require_admin),
) -> ApiKeyListResponse:
    """List all API keys. Raw keys are never included in the response.

    Args:
        limit: Maximum number of keys to return.
        offset: Pagination offset.
        db: Async database session.
        _admin: The authenticated admin key.

    Returns:
        A paginated list of API key details.
    """
    count_result = await db.execute(select(func.count()).select_from(ApiKey))
    total: int = count_result.scalar() or 0

    result = await db.execute(
        select(ApiKey).order_by(ApiKey.created_at.desc()).offset(offset).limit(limit)
    )
    keys = list(result.scalars().all())

    return ApiKeyListResponse(
        keys=[ApiKeyResponse.model_validate(k) for k in keys],
        total=total,
    )


@router.get("/keys/{key_id}", response_model=ApiKeyResponse)
async def get_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: ApiKey = Depends(require_admin),
) -> ApiKeyResponse:
    """Retrieve details for a single API key by its identifier.

    Args:
        key_id: The unique API key identifier.
        db: Async database session.
        _admin: The authenticated admin key.

    Returns:
        The API key details (never includes raw key).

    Raises:
        HTTPException: 404 if the key is not found.
    """
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    return ApiKeyResponse.model_validate(api_key)


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_api_key(
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: ApiKey = Depends(require_admin),
) -> None:
    """Deactivate an API key (soft delete by setting is_active=False).

    Args:
        key_id: The unique API key identifier.
        db: Async database session.
        _admin: The authenticated admin key.

    Raises:
        HTTPException: 404 if the key is not found.
    """
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    api_key.is_active = False
    await db.commit()


@router.patch("/keys/{key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    key_id: uuid.UUID,
    body: ApiKeyUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: ApiKey = Depends(require_admin),
) -> ApiKeyResponse:
    """Update an API key's name and/or rate limit.

    Args:
        key_id: The unique API key identifier.
        body: The fields to update.
        db: Async database session.
        _admin: The authenticated admin key.

    Returns:
        The updated API key details.

    Raises:
        HTTPException: 404 if the key is not found.
    """
    result = await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    api_key = result.scalar_one_or_none()

    if api_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    if body.name is not None:
        api_key.name = body.name
    if body.rate_limit is not None:
        api_key.rate_limit = body.rate_limit

    await db.commit()
    await db.refresh(api_key)

    return ApiKeyResponse.model_validate(api_key)
