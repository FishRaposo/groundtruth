# Vendored from FishRaposo/operator-shared-core v1.3.0.
# Source commit: dbf276a7708da65b55e1f10b35af634b300d1f07.
import uuid
from datetime import datetime, timezone
from typing import Generator, Generic, List, Optional, Type, TypeVar

from sqlalchemy import Column, DateTime, String, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

Base = declarative_base()

T = TypeVar("T")


def to_async_url(db_url: str) -> str:
    """Rewrite a sync database URL to its async driver equivalent.

    Handles ``postgresql+psycopg://``, plain ``postgresql://``/``postgres://``
    (all -> ``+asyncpg``) and ``sqlite:///`` (-> ``+aiosqlite``). Idempotent for
    URLs already using an async driver.
    """
    async_url = db_url
    if async_url.startswith("postgresql+psycopg://"):
        async_url = async_url.replace(
            "postgresql+psycopg://", "postgresql+asyncpg://", 1
        )
    elif async_url.startswith("postgresql://"):
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif async_url.startswith("postgres://"):
        async_url = async_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif async_url.startswith("sqlite:///"):
        async_url = async_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return async_url


class UUIDMixin:
    """Mixin to use a UUID string as primary key."""

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )


class TimestampMixin:
    """Mixin to add created_at and updated_at timestamps to models."""

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class BaseRepository(Generic[T]):
    """Generic repository pattern implementation for ORM models."""

    def __init__(self, model: Type[T], session: Session):
        self.model = model
        self.session = session

    def get(self, id_val: str) -> Optional[T]:
        """Fetch a single record by its primary key id."""
        return self.session.get(self.model, id_val)

    def list(self) -> List[T]:
        """Fetch all records of this model."""
        return self.session.query(self.model).all()

    def create(self, **kwargs) -> T:
        """Create and persist a new model instance."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        self.session.commit()
        self.session.refresh(instance)
        return instance

    def update(self, id_val: str, **kwargs) -> Optional[T]:
        """Update fields of an existing model instance."""
        instance = self.get(id_val)
        if not instance:
            return None
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        self.session.add(instance)
        self.session.commit()
        self.session.refresh(instance)
        return instance

    def delete(self, id_val: str) -> bool:
        """Delete an instance by its id."""
        instance = self.get(id_val)
        if not instance:
            return False
        self.session.delete(instance)
        self.session.commit()
        return True


class DatabaseManager:
    """Manages SQLAlchemy engine and sessions."""

    def __init__(
        self,
        db_url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
    ):
        engine_kwargs: dict = {"pool_pre_ping": True}
        if "sqlite" not in db_url:
            engine_kwargs.update(
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=pool_timeout,
            )
        self.engine = create_engine(db_url, **engine_kwargs)
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

    def get_session(self) -> Generator[Session, None, None]:
        """Provides a database session generator for FastAPI and generic tasks."""
        session = self.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def create_tables(self) -> None:
        """Create all registered database tables (safe to run repeatedly)."""
        Base.metadata.create_all(bind=self.engine)


class AsyncDatabaseManager:
    """Manages SQLAlchemy async engine and sessions."""

    def __init__(
        self,
        db_url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_timeout: int = 30,
    ):
        from sqlalchemy.ext.asyncio import (  # noqa: I001
            AsyncSession,
            async_sessionmaker,
            create_async_engine,
        )

        async_url = to_async_url(db_url)
        engine_kwargs: dict = {"pool_pre_ping": True}
        if "sqlite" not in db_url:
            engine_kwargs.update(
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=pool_timeout,
            )
        self.engine = create_async_engine(async_url, **engine_kwargs)
        self.AsyncSessionLocal = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def get_session(self):
        """Async session generator for FastAPI Depends()."""
        async with self.AsyncSessionLocal() as session:
            yield session

    async def create_tables(self) -> None:
        """Create all registered tables using async engine."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        """Dispose the engine connection pool."""
        await self.engine.dispose()
