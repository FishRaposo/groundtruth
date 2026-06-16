"""Shared fixtures for integration tests using SQLite."""

import os
import sys

# Force SQLite for integration tests before any app imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["OPENAI_API_KEY"] = ""
os.environ["APP_ENV"] = "test"

# Clear cached modules to force reimport with new env
for mod in list(sys.modules):
    if mod.startswith("app."):
        del sys.modules[mod]

import pytest  # noqa: E402  # env-setup
from app.config import get_settings  # noqa: E402  # env-setup

# Clear settings cache to pick up new env
get_settings.cache_clear()

from app.db.session import Base, async_engine  # noqa: E402  # env-setup


@pytest.fixture(autouse=True)
async def reset_db() -> None:
    """Drop and recreate tables before every integration test."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
