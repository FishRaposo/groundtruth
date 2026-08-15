"""Async SQLAlchemy engine and session management (vendor-core-backed).

The engine and session factory come from
``app.internal.vendor_core.database.AsyncDatabaseManager``;
GroundTruth keeps its own ``DeclarativeBase`` so its models and Alembic migrations
retain their existing metadata/registry.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings
from app.internal.vendor_core.database import AsyncDatabaseManager

settings = get_settings()

_db = AsyncDatabaseManager(settings.DATABASE_URL)
async_engine = _db.engine
AsyncSessionLocal = _db.AsyncSessionLocal


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional database session for FastAPI dependency injection."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create all database tables. Used during application startup."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
