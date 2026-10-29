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
│   │   ├── alembic/  tests/  Dockerfile  pyproject.toml  uv.lock  requirements.txt
│   └── web/                     # Next.js frontend, unit and Chromium smoke tests
├── examples/run_demo.py         # real offline ingestion/retrieval/refusal CLI
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
make install-locked # uv 0.8.17 sync from apps/api/uv.lock (CI dependency graph)
make lock         # regenerate the lock after dependency changes
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

CI installs the API from `apps/api/uv.lock` with uv 0.8.17 and Python 3.11.
Use `make install-locked` for the same dependency graph in `apps/api/.venv`, or
`python -m pip install -e "apps/api[dev]"` for an unlocked editable install.
After dependency changes, run `make lock` and `uv lock --check --project apps/api`.
Parser and model extras are optional. The legacy library profile
preserves its deterministic fallback for old tests/golden evidence; the connected
application chooses local or deterministic operation explicitly and local-model
failure never substitutes another embedding model.

## Original pre-Project05 baseline

**Self-contained, offline-first.** The internal compatibility layer provides
config/logging/errors/DB/Celery without an external package. Domain RAG capability is
preserved. The CLI demo runs real ingestion, retrieval, reranking, refusal, generation
and citation services on disposable SQLite with deterministic hash embeddings and an
offline generator. Its cited-answer/refusal output is a pipeline smoke check,
separate from answer-quality acceptance. The web app exposes workflow, version,
citation, trace, and read-only admin evidence surfaces. CI uses a locked API install
and `npm ci`. Optional dependency contracts remain manual opt-in; the separate
infrastructure and connected-live jobs are retained.

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

## Project05 application profile (2026-10-24)

The owner explicitly continues without WSL. Use the new portable profile in
`docs/portfolio-connected.md`; it selects SQLite/inline ingestion, explicit local
or deterministic embeddings and extractive generation. Do not treat the earlier
legacy-fallback description above as the authenticated HTTP execution contract.
Legacy library calls/golden fixtures remain compatible; connected model errors
remain errors. Never launch WSL/Docker/reboot without renewed task scope.

New boundaries: `app/services/access_control/scope.py` owns SQL authorization;
`connected_query.py` unifies scoped normal/SSE queries; `ingestion_jobs.py` owns
durable attempts/leases/publication; `app/db/migrate.py` performs additive schema
reconciliation with Alembic history. `app/model_setup.py` explicitly downloads
the pinned local assets. `app/portfolio/` is the packaged frozen corpus/loader.
Root `scripts/portfolio_local.py` selects the credential-free portable profile;
`seed_portfolio.py` writes disposable keys only to an ignored private manifest.

`answer_reader.py` owns local CPU extraction and per-request QA evidence.
`reader_attributes.py` provides an optional literal activity/attribute ranking
signal among already accepted witnesses; it never accepts null predictions or
certifies factual support. `reader_witnesses.py` retains accepted-span fallback
when that signal is absent. Inspect the exact selected clause, not another
sentence in the chunk. Curated opposing sources are checked before witness
ranking. Legacy library normalization can collapse original paragraph boundaries;
the formatting prior cannot recover them or prove coreference.

Connected upload/update uses `connected-paragraphs-v1` on parsed text: canonical LF,
only complete
outer blank lines removed, retained indentation/internal spacing preserved, and
every published chunk is a literal body substring. Explicit deterministic chunking
uses `connected-literal-windows-v1`; local tokenizer chunking keeps its existing
encoder identity. Old deterministic indexes need explicit reindexing. Restore and
reindex reembed exact immutable snapshot partitions, preserving historical body,
profile (or unknown), and manifests. Their distinct snapshot chunking provenance
records the actual current encoder and captured source chunking; it does not claim
to recover formatting already lost in historical content. Citation status hashes
the literal stored body and requires exact immutable chunk membership.

The frontend uses `PortfolioProvider` as the shared source/identity/conversation
authority, `ConnectedClient` for header-authenticated JSON/SSE and the existing
route surfaces. Sample data is explicit and never substitutes for connected
errors. Run sample/live production browser suites separately, never during builds.

Ordinary CI now declares PostgreSQL/pgvector/Redis infrastructure contracts;
configuration is not observed hosted execution. Live services/indexed benchmark
remain deferred locally. Preserve original golden fixtures and first held-out
results separately from new/exposed regression observations. The corpus is
synthetic/agent-authored; no human or general model-quality validation is claimed.
