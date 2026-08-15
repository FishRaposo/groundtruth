# AGENTS.md — groundtruth

## What This Is

GroundTruth is a production-minded, full-stack **RAG platform**: hybrid (vector + keyword)
retrieval, grounded answers with citations, and graceful refusal when evidence is
insufficient. FastAPI backend + Next.js frontend, PostgreSQL/pgvector, Celery/Redis.
The archived operator-core subset is now vendored under the API package; no
sibling repository or Git-installed shared library is required.

## Layout (full-stack)

```
groundtruth/
├── apps/
│   ├── api/                     # FastAPI backend (was backend/)
│   │   ├── app/
│   │   │   ├── main.py          # app wiring (internal middleware + error handler)
│   │   │   ├── internal/vendor_core/ # pinned archived compatibility subset
│   │   │   ├── config.py        # Settings(BaseAppConfig)
│   │   │   ├── core/{logging,celery,metrics}.py
│   │   │   ├── db/session.py    # AsyncDatabaseManager engine + local DeclarativeBase
│   │   │   ├── api/             # routers (documents, queries, keys, health, metrics, v1)
│   │   │   ├── parsers/         # TXT/PDF/DOCX/HTML/Markdown
│   │   │   ├── services/        # retrieval, refusal, citation, generation, embeddings,
│   │   │   │                    #   chunking, document intelligence, reranking,
│   │   │   │                    #   query, evaluation, document/*
│   │   │   ├── middleware/  models/  tasks/  schemas/  utils/
│   │   ├── alembic/  tests/  Dockerfile  pyproject.toml  requirements.txt
│   └── web/                     # Next.js frontend, unit and Chromium smoke tests
├── examples/run_demo.py         # offline grounded-RAG + refusal demo
├── scripts/  infra/  data/  docs/
├── docker-compose.yml           # groundtruth_postgres + groundtruth_redis + api + web
├── Makefile  ruff.toml  pyrightconfig.json  .env.example
└── .github/workflows/ci.yml
```

**Layout note:** the backend package stays `app/` under `apps/api/` (not `apps/api/src/`).
Tests run from `apps/api/` so `app` resolves. Ruff is configured at the repo root
(`groundtruth/ruff.toml`); the API `pyproject.toml` keeps the pytest config only.

## Internal vendor-core compatibility layer

| Bespoke (before) | Now |
|---|---|
| `Settings(BaseSettings)` | `Settings(BaseAppConfig)` from `app.internal.vendor_core` (keeps domain knobs; `OPENAI_API_KEY` remains a plain `str`) |
| `core/logging.py` (structlog config) | internal vendor logging setup (loguru); domain `structlog.get_logger()` calls still work |
| bespoke `RequestLoggingMiddleware` | internal vendor request logging middleware |
| ad-hoc `HTTPException` only | + internal vendor application error handler registered on the app |
| `db/session.py` engine | internal `AsyncDatabaseManager` (GroundTruth keeps its own `DeclarativeBase` for models + Alembic) |
| `core/celery.py` `Celery(...)` | internal Celery factory + re-applied routes/beat schedule |

**Preserved domain value:** hybrid retrieval (RRF), refusal engine, citation assembly,
grounded generation + SSE, multi-provider embeddings + LRU cache + offline hash fallback,
chunking strategies, reranking, query understanding, RAGAS eval, document workflows,
and the **`groundtruth_*` Prometheus metrics** (intentionally NOT renamed; Grafana
dashboards depend on them — `core/metrics.py` is kept as the domain registry).

**Consolidated ingestion value:** TXT joins the existing parser set; parsed text is
normalized and SHA-256 hashed for document deduplication; GroundTruth's semantic
chunker feeds stable chunk deduplication; dependency-free entities are stored in
document metadata; and failed documents carry quarantine stage/reason/path metadata
for retry through the existing reindex workflow. Do not add a parallel ingestion,
quarantine, retrieval, or KnowledgeOps-style gateway service. Provenance and archive
gates are in `docs/migrations/2026-08-12-document-intelligence-pipeline-and-knowledgeops-into-groundtruth.md`.

## Commands

```bash
make install      # python -m pip install -e "apps/api[dev]"
make test         # apps/api unit tests (no live infra)
make test-all     # all offline tests, including integration-shaped contracts
make lint         # ruff check API/tests/examples/scripts
make format-check # ruff format --check over the same surface
make typecheck    # pyright apps/api/app
make evidence     # deterministic offline evidence generation/checksum verification
make check        # complete API + web gate (Chromium must be installed)
make docker-up    # pgvector + redis + api + web
make demo         # offline grounded-RAG + refusal demo
make worker       # celery -A app.core.celery.celery_app worker
make migrate      # alembic upgrade head
```

The canonical API install is `python -m pip install -e "apps/api[dev]"` from the
repository root. Parser and model extras are optional; the embedding service falls
back to a deterministic offline path, so the unit suite and demo do not require a
provider key or model download.

## Current State

**Self-contained, offline-first.** The internal compatibility layer provides
config/logging/errors/DB/Celery without an external package. Domain RAG capability is
preserved. The offline demo and unit suite use deterministic fallbacks; integration
tests can opt into Postgres and Redis. The web app exposes workflow, version,
citation, trace, and read-only admin evidence surfaces. CI uses the canonical editable
API install and locked `npm ci`; PostgreSQL/Redis integration CI is manual opt-in.

## Delivered and verified boundaries

- Golden fixtures preserve parser, embedding, retrieval, refusal, citation, and
  evaluation behavior before future score-sensitive refactors.
- OpenAI-compatible generation retains SSE streaming while the default demo uses
  deterministic offline simulation.
- Docker and wheel builds install only the repository-local API package and its
  pinned internal compatibility subset.
- Hosted/team tenancy, SAML/SSO, hosted notifications or scheduling, mandatory
  infrastructure, and cloud object storage remain deliberately deferred.

## When to Update This AGENTS.md

- Backend layout or the internal vendor-core compatibility surface changes
- Makefile targets, docker-compose services, or CI steps change
- New services/routers added under `apps/api/app/`
- Ingestion stages, deduplication semantics, entity metadata, or quarantine contract change
