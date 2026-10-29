"""Shared fixtures for integration tests using SQLite."""

import os
import sys  # noqa: F401  # module list intentionally unused: no purge below

# Force SQLite for integration tests before any app imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["OPENAI_API_KEY"] = ""
os.environ["APP_ENV"] = "test"

# app.* modules must NOT be purged here: tests/conftest.py already binds the
# same :memory: environment before importing the app, and deleting modules
# would create a second generation of class objects for the rest of the suite.

# get_settings.cache_clear() must NOT run here: app modules bind the cached
# settings object at import, and a second settings generation would diverge
# module-level references from the object tests monkeypatch.

import pytest  # noqa: E402  # env-setup
from app.db.session import Base, async_engine  # noqa: E402  # env-setup


@pytest.fixture(autouse=True)
async def reset_db() -> None:
    """Drop and recreate tables before every integration test."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
