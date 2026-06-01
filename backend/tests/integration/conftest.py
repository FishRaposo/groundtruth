"""Shared fixtures for integration tests using SQLite."""

import os

# Force SQLite for integration tests before any app imports
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["OPENAI_API_KEY"] = ""
os.environ["APP_ENV"] = "test"

import pytest
from app.db.session import Base, async_engine, init_db


@pytest.fixture(autouse=True)
async def reset_db() -> None:
    """Drop and recreate tables before every integration test."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
