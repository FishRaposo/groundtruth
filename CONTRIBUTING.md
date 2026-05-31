# Contributing to GroundTruth

Thank you for your interest in contributing to GroundTruth. This guide covers everything you need to get started.

## Development Setup

### Prerequisites

- **Docker** and **Docker Compose** (v2+)
- **Python** 3.11+
- **Node.js** 18+ and **npm** 9+
- **Make** (optional, but recommended)
- **Git**
- An **OpenAI API key** (or compatible endpoint)

### Quick Start

```bash
git clone <repo-url> && cd groundtruth
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
make setup
make dev
```

The application will be available at:

- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Without Make

```bash
cp .env.example .env
cd backend && pip install -e ".[dev]"
cd ../frontend && npm install
docker compose up -d
cd ../backend && alembic upgrade head
cd .. && python scripts/seed.py
```

## Architecture Overview

GroundTruth is a three-tier system: Next.js frontend, FastAPI backend, and PostgreSQL with pgvector.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full architecture document with diagrams and service descriptions.

## Development Workflow

### Branch Naming

Use descriptive branch names with a type prefix:

- `feat/add-export-endpoint`
- `fix/chunking-edge-case`
- `docs/api-reference`
- `refactor/retrieval-pipeline`

### Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add document export endpoint
fix: handle empty chunk in markdown parser
docs: update API reference for queries
refactor: extract embedding logic into service
test: add integration tests for ingestion
```

### Pull Request Process

1. Create a feature branch from `master`
2. Make your changes with tests
3. Ensure all linting and tests pass (`make lint && make test-all`)
4. Open a PR with a clear description
5. Address review feedback
6. Squash merge on approval

## Code Style

### Python (Backend)

- **Linter**: ruff (replaces flake8, isort, and pyupgrade)
- **Formatter**: ruff format (Black-compatible)
- **Type checking**: mypy with strict mode
- **Imports**: absolute imports from `app.*`
- **Line length**: 120 characters
- **Docstrings**: Google style for all public functions and classes

### TypeScript (Frontend)

- **Linter**: ESLint (via `next lint`)
- **Strict mode**: enabled in `tsconfig.json`
- **Imports**: use absolute paths via `@/` alias
- **Components**: functional components with hooks
- **Styling**: Tailwind CSS utility classes

## Testing

### Running Tests

```bash
make test            # Backend tests with coverage
make test-frontend   # Frontend tests
make test-all        # Everything
```

### Running Individual Tests

```bash
cd backend && python -m pytest tests/test_ingestion.py -v
cd backend && python -m pytest tests/test_ingestion.py::test_upload_pdf -v
```

### Test Naming Convention

- Files: `test_<module>.py`
- Functions: `test_<behavior>_<condition>`
- Example: `test_upload_returns_400_for_unsupported_type`

### Coverage

Target: **80%+** coverage on the backend.

```bash
cd backend && python -m pytest --cov=app --cov-report=html
open htmlcov/index.html
```

See [docs/TESTING.md](docs/TESTING.md) for the full testing guide.

## Making Changes

### Backend Changes

1. Modify files under `backend/app/`
2. If changing models, create a migration: `make migrate-create msg="add_foo_column"`
3. Apply migrations: `make migrate`
4. Add tests under `backend/tests/`
5. Run `make lint && make test`

### Frontend Changes

1. Modify files under `frontend/src/`
2. Components go in `frontend/src/components/`
3. Pages go in `frontend/src/app/`
4. API calls go in `frontend/src/lib/api.ts`
5. Types go in `frontend/src/types/`
6. Run `cd frontend && npm run lint`

### Database Changes

1. Modify the SQLAlchemy model in `backend/app/models/`
2. Generate a migration: `make migrate-create msg="description_of_change"`
3. Review the generated migration in `backend/alembic/versions/`
4. Apply: `make migrate`
5. Test the migration up and down

## Submitting Changes

### PR Template

```markdown
## Summary
<!-- 1-3 sentences describing the change -->

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## How Has This Been Tested?
<!-- Describe tests added or manual testing performed -->

## Checklist
- [ ] My code follows the project's style guidelines
- [ ] I have performed a self-review
- [ ] I have added tests for my changes
- [ ] All new and existing tests pass
- [ ] I have updated documentation where applicable
```

### CI Requirements

All PRs must pass:

- `ruff check` with no errors
- `mypy` type checking
- Backend test suite
- Frontend lint

## Project Structure

```
groundtruth/
├── backend/
│   ├── alembic/              # Database migrations
│   ├── alembic.ini
│   ├── app/
│   │   ├── api/              # FastAPI route handlers
│   │   ├── db/               # Database session and vector store
│   │   ├── models/           # SQLAlchemy + Pydantic models
│   │   ├── parsers/          # File format parsers
│   │   ├── services/         # Business logic layer
│   │   ├── config.py         # Settings via pydantic-settings
│   │   └── main.py           # FastAPI application entry
│   ├── tests/                # pytest test suite
│   ├── requirements.txt
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/              # Next.js app router pages
│   │   ├── components/       # React components
│   │   ├── lib/              # API client and utilities
│   │   └── types/            # TypeScript type definitions
│   ├── package.json
│   └── tsconfig.json
├── data/
│   └── sample/               # Sample documents for seeding
├── docs/                     # Project documentation
├── scripts/                  # Dev scripts (seed, reset)
├── docker-compose.yml
├── Makefile
└── .env.example
```
