# AGENTS.md — groundtruth

## What This Is

GroundTruth is a production-minded, full-stack **RAG platform**: hybrid (vector + keyword)
retrieval, grounded answers with citations, and graceful refusal when evidence is
insufficient. FastAPI backend + Next.js frontend, PostgreSQL/pgvector, Celery/Redis.
Migrated out of `General Projects/` onto the `shared_core` standard.

## Layout (full-stack)

```
groundtruth/
├── apps/
│   ├── api/                     # FastAPI backend (was backend/)
│   │   ├── app/
│   │   │   ├── main.py          # app wiring (shared_core middleware + error handler)
│   │   │   ├── config.py        # Settings(BaseAppConfig)
│   │   │   ├── core/{logging,celery,metrics}.py
│   │   │   ├── db/session.py    # AsyncDatabaseManager engine + local DeclarativeBase
│   │   │   ├── api/             # routers (documents, queries, keys, health, metrics, v1)
│   │   │   ├── parsers/         # PDF/DOCX/HTML/Markdown
│   │   │   ├── services/        # retrieval, refusal, citation, generation, embeddings,
│   │   │   │                    #   chunking, reranking, query, evaluation, document/*
│   │   │   ├── middleware/  models/  tasks/  schemas/  utils/
│   │   ├── alembic/  tests/  Dockerfile  pyproject.toml  requirements.txt
│   └── web/                     # Next.js frontend (was frontend/) — KEPT as-is
├── examples/run_demo.py         # offline grounded-RAG + refusal demo
├── scripts/  infra/  data/  docs/
├── docker-compose.yml           # groundtruth_postgres + groundtruth_redis + api + web
├── Makefile  ruff.toml  pyrightconfig.json  .env.example
└── .github/workflows/ci.yml
```

**Layout note:** the backend package stays `app/` under `apps/api/` (not `apps/api/src/`).
Tests run from `apps/api/` so `app` resolves. Ruff is configured at the repo root
(`groundtruth/ruff.toml`); the API `pyproject.toml` keeps the pytest config only.

## shared-core adoption (the deep refactor)

| Bespoke (before) | Now |
|---|---|
| `Settings(BaseSettings)` | `Settings(BaseAppConfig)` (keeps domain knobs; `OPENAI_API_KEY` overridden back to plain `str`) |
| `core/logging.py` (structlog config) | `shared_core.logging.setup_logging` (loguru); domain `structlog.get_logger()` calls still work |
| bespoke `RequestLoggingMiddleware` | `shared_core.logging.RequestLoggingMiddleware` |
| ad-hoc `HTTPException` only | + `shared_core.errors.application_error_handler` registered on the app |
| `db/session.py` engine | `shared_core.database.AsyncDatabaseManager` (groundtruth keeps its own `DeclarativeBase` for models + Alembic) |
| `core/celery.py` `Celery(...)` | `shared_core.tasks.create_celery_app` + re-applied routes/beat schedule |

**Preserved domain value:** hybrid retrieval (RRF), refusal engine, citation assembly,
grounded generation + SSE, multi-provider embeddings + LRU cache + offline hash fallback,
chunking strategies, reranking, query understanding, RAGAS eval, document workflows,
and the **`groundtruth_*` Prometheus metrics** (intentionally NOT renamed; Grafana
dashboards depend on them — `core/metrics.py` is kept as the domain registry).

## Commands

```bash
make install      # pip install -e ../shared-core; pip install -r apps/api/requirements.txt; + test tools
make test         # apps/api unit tests (no live infra)  -> 85 passing
make test-all     # + integration tests (needs Postgres + Redis)
make lint         # ruff check apps/api/app apps/api/tests
make format       # ruff format ...
make typecheck    # pyright app
make docker-up    # pgvector + redis + api + web
make demo         # offline grounded-RAG + refusal demo
make worker       # celery -A app.core.celery.celery_app worker
make migrate      # alembic upgrade head
```

Local verification uses `.venv` at the repo root (shared-core editable + `apps/api`
requirements). `sentence-transformers`/torch are optional — the embedding service falls
back to a deterministic offline path, so the unit suite runs without them.

## Current State

**Functional, migrated, green.** `shared_core` provides config/logging/errors/DB/Celery;
domain RAG capability preserved. **85 unit tests pass** (`make test`); `ruff check`/`format
--check` clean; `make demo` runs offline. Integration tests (`tests/integration/`) need a
live Postgres+Redis and run in CI / `make test-all`. The Next.js `apps/web` is unchanged.

## Follow-ups (not done now)

- Converge `parsers/` + `services/chunking` onto `shared_core.docparse`, and the
  embeddings provider/cache onto `shared_core.embeddings` (golden-output tests first).
- Route OpenAI generation through `shared_core.llm.LLMClientFactory` where it doesn't
  disturb the SSE-streaming / offline-simulation paths.
- Docker image installs shared-core via its public git URL (workspace-wide packaging gap).

## When to Update This AGENTS.md

- Backend layout or the shared-core adoption surface changes
- Makefile targets, docker-compose services, or CI steps change
- New services/routers added under `apps/api/app/`
