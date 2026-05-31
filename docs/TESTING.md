# Testing Guide

## Testing Philosophy

GroundTruth follows a testing pyramid approach:

1. **Unit tests** — Fast, isolated tests for individual functions and services. Mocked external dependencies (LLM, database).
2. **Integration tests** — Tests that exercise multiple layers together (API endpoint through database).
3. **End-to-end tests** — Full stack tests running against a live API.

The majority of tests should be unit tests, with integration tests covering critical paths.

## Backend Tests

### Framework

- **pytest** with **pytest-asyncio** for async test support
- **httpx** `AsyncClient` with `ASGITransport` for API testing without a running server
- Tests live in `backend/tests/`

### Fixtures

Core fixtures are defined in `backend/tests/conftest.py`:

| Fixture | Description |
|---|---|
| `client` | Async HTTP client wired to the FastAPI app |
| `db_session` | Test database session |
| `sample_document_id` | Fixed UUID for document tests |
| `sample_query_id` | Fixed UUID for query tests |
| `sample_document_data` | Sample document metadata dict |
| `sample_query_data` | Sample query request dict |

### Mocking OpenAI

External API calls to OpenAI should be mocked in tests. Use `unittest.mock.patch` or `pytest` monkeypatch:

```python
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_generation_uses_llm(client, monkeypatch):
    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock(message=AsyncMock(content="Test answer"))]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
    monkeypatch.setattr("app.services.generation.openai_client", mock_client)

    response = await client.post("/api/queries", json={"question": "test?"})
    assert response.status_code == 200
```

### Test Database

For integration tests that need a real database, use a test database URL:

```python
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

TEST_DATABASE_URL = "postgresql+asyncpg://groundtruth:groundtruth_dev@localhost:5432/groundtruth_test"


@pytest_asyncio.fixture
async def test_db():
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()
```

## Frontend Tests

### Framework

- **Jest** or **Vitest** (depending on configuration)
- **React Testing Library** for component tests
- Tests should co-locate with components or live in `frontend/__tests__/`

### Example Component Test

```tsx
import { render, screen } from "@testing-library/react";
import { ChatInterface } from "@/components/ChatInterface";

test("renders chat input", () => {
  render(<ChatInterface />);
  expect(screen.getByPlaceholderText(/ask a question/i)).toBeInTheDocument();
});
```

## Running Tests

### All Backend Tests

```bash
make test
```

### Specific Test File

```bash
cd backend && python -m pytest tests/test_ingestion.py -v
```

### Specific Test Function

```bash
cd backend && python -m pytest tests/test_ingestion.py::test_upload_pdf -v
```

### Frontend Tests

```bash
make test-frontend
```

### With Coverage Report

```bash
cd backend && python -m pytest --cov=app --cov-report=html
```

Then open `backend/htmlcov/index.html` in a browser.

## Writing New Tests

### Naming Convention

- **File**: `test_<module>.py` — mirrors the source module name
- **Class** (optional): `Test<Feature>` — group related tests
- **Function**: `test_<behavior>_<condition>` — descriptive and readable

Examples:

```python
def test_upload_returns_document_id():
    ...

def test_upload_rejects_unsupported_file_type():
    ...

def test_retrieval_returns_empty_when_no_chunks():
    ...

def test_refusal_triggered_for_low_confidence():
    ...
```

### Test Structure (AAA Pattern)

```python
@pytest.mark.asyncio
async def test_document_upload_stores_metadata(client):
    # Arrange
    file_content = b"# Test Document\nSome content here."
    files = {"files": ("test.md", file_content, "text/markdown")}

    # Act
    response = await client.post("/api/documents/upload", files=files)

    # Assert
    assert response.status_code == 200
    documents = response.json()["documents"]
    assert len(documents) == 1
    assert documents[0]["title"] == "test.md"
```

### Testing Services

For service-layer tests, mock the database and external calls:

```python
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_ingestion_processes_document():
    mock_db = AsyncMock()
    mock_embedding = AsyncMock()
    mock_embedding.embed.return_value = [[0.1] * 1536]

    service = IngestionService(db=mock_db, embedding_service=mock_embedding)
    result = await service.process_document(uuid.uuid4(), content="# Test")

    assert result is not None
```

## Coverage Requirements

| Layer | Target |
|---|---|
| Overall backend | **80%+** |
| API handlers | **90%+** |
| Services | **80%+** |
| Models | **100%** (trivial) |

Run coverage with:

```bash
cd backend && python -m pytest --cov=app --cov-report=term-missing
```

The `--cov-report=term-missing` flag shows which lines are not covered.

## CI Integration

Tests run automatically on every push and pull request via CI. The pipeline:

1. Installs dependencies
2. Runs `ruff check` and `mypy`
3. Runs backend tests with coverage
4. Runs frontend lint and tests
5. Fails if coverage drops below 80%

### Local CI Check

Before pushing, run:

```bash
make lint && make test-all
```
