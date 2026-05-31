import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.db.session import AsyncSessionLocal


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provide an async HTTP client for testing the FastAPI application."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[None, None]:
    """Provide a test database session."""
    yield


@pytest.fixture
def sample_document_id() -> uuid.UUID:
    """Provide a fixed UUID for sample document tests."""
    return uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


@pytest.fixture
def sample_query_id() -> uuid.UUID:
    """Provide a fixed UUID for sample query tests."""
    return uuid.UUID("660e8400-e29b-41d4-a716-446655440001")


@pytest.fixture
def sample_document_data() -> dict[str, str]:
    """Provide sample document metadata for testing."""
    return {
        "title": "Test Document",
        "source_type": "md",
        "source_url": None,
        "metadata": {"test": True},
    }


@pytest.fixture
def sample_query_data() -> dict[str, str]:
    """Provide sample query request data for testing."""
    return {
        "question": "What is the company remote work policy?",
    }
