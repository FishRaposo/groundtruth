# GroundTruth — Improvement Plan

> Comprehensive audit of bugs, inconsistencies, missing features, and growth opportunities.
> Priority levels: **P0** (broken/blocking), **P1** (high value), **P2** (polish), **P3** (long-term growth).

---

## 1. P0 — Broken Code & Critical Fixes

### 1.1 Four models import from nonexistent `app.db.base_class`

| File | Broken Import |
|------|---------------|
| `backend/app/models/collection.py` | `from app.db.base_class import Base` |
| `backend/app/models/conversation.py` | `from app.db.base_class import Base` |
| `backend/app/models/webhook.py` | `from app.db.base_class import Base` |
| `backend/app/models/document/workflow.py` | `from app.db.base_class import Base` |

The actual base class is at `app.db.session.Base`. These models fail to import entirely, meaning the features they represent (collections, conversations, webhooks, workflows) are completely broken at startup.

**Action:** Change all four imports to `from app.db.session import Base`.

### 1.2 Missing `app.api.deps` module

`backend/app/api/v1/documents.py` and `backend/app/api/v1/workflows.py` import `from app.api.deps import get_current_user, get_db`. No `deps.py` exists in `app/api/`. This causes import errors at startup for all v1 routes.

**Action:** Create `app/api/deps.py` with:
- `get_db()` — async session dependency (yields `AsyncSession` from `app.db.session`)
- `get_current_user()` — extracts and validates user from JWT/API key in request

### 1.3 Duplicate `/metrics` endpoint

`backend/app/main.py` lines 71-79:
- Line 71: `app.include_router(metrics_router)` registers `/metrics` from `app/api/metrics.py`
- Lines 78-79: A duplicate `@app.get("/metrics")` route exists inline
- Line 79 has a **duplicate return statement** (unreachable code)

**Action:** Remove the inline `/metrics` route (lines 78-79). Keep the router-registered version.

### 1.4 Missing `Integer` import in `collection.py`

`backend/app/models/collection.py` line 49 uses `Column(Integer, ...)` but `Integer` is not imported from `sqlalchemy`.

**Action:** Add `Integer` to the `sqlalchemy` import block.

### 1.5 Celery config references missing settings

`backend/app/core/celery.py` references `settings.CELERY_BROKER_URL` and `settings.CELERY_RESULT_URL` which are not defined in `config.py`. Would raise `AttributeError` at import time if Celery is loaded.

**Action:** Add `celery_broker_url` and `celery_result_url` to `Settings` in `config.py` with sensible defaults (e.g., `redis://localhost:6379/0`).

---

## 2. P1 — High-Value Fixes

### 2.1 Inconsistent ORM styles across models

| Style | Models | Pattern |
|-------|--------|---------|
| **Modern** (SQLAlchemy 2.0) | `document.py`, `chunk.py`, `query.py`, `api_key.py` | `Mapped[]` + `mapped_column()` |
| **Legacy** (1.x style) | `collection.py`, `conversation.py`, `webhook.py`, `workflow.py` | `Column()` + `from sqlalchemy.dialects.postgresql import UUID` |

The legacy-style models also lack proper type annotations and use `Column()` directly on the class body.

**Action:** Migrate all models to the modern `Mapped[]` / `mapped_column()` style. This is a significant refactor but ensures consistency and enables mypy checking of model attributes.

### 2.2 Synchronous OpenAI client in async code

`backend/app/services/generation.py` uses the synchronous `OpenAI()` client inside async methods, wrapped in `asyncio.to_thread()` for streaming. Works but architecturally awkward.

**Action:** Switch to `AsyncOpenAI()` client. Use `async for` for streaming instead of the background-thread-with-queue pattern.

### 2.3 `get_settings()` is not cached

`backend/app/config.py` docstring says "Return a cached Settings instance" but the function creates a new `Settings()` every time. Pydantic-settings doesn't cache by default.

**Action:** Add `@lru_cache()` decorator or use a module-level singleton pattern.

### 2.4 `__import__("datetime")` hack in auth middleware

`backend/app/middleware/auth.py` line 73: `__import__("datetime").datetime.utcnow()` — unusual, hard to read, and uses deprecated `utcnow`.

**Action:** Import `datetime` normally at module top. Use `datetime.now(timezone.utc)`.

### 2.5 `datetime.utcnow()` deprecation across models

Multiple models use `datetime.utcnow` as default values. Deprecated in Python 3.12+.

**Action:** Replace all occurrences with `datetime.now(timezone.utc)`.

### 2.6 Dev dependencies in production `requirements.txt`

`pytest`, `pytest-asyncio`, `pytest-cov`, `respx`, `mypy`, and `ruff` are in the main `requirements.txt`. These would be installed in the production Docker image, increasing image size and attack surface.

**Action:** Move dev dependencies to `[project.optional-dependencies]` in `pyproject.toml`. Update Dockerfile to install without dev extras.

### 2.7 Stale `src/` directory

`src/app/api/chat/route.ts` contains a hardcoded mock that returns fake data. `src/lib/db.ts` does direct pg queries not used by the actual frontend. This directory appears to be dead code from an earlier monolithic architecture.

**Action:** Delete `src/` entirely. All functionality lives in `backend/` and `frontend/`.

### 2.8 `document_filter` null check missing in webhooks

`backend/app/services/webhooks/delivery.py` accesses `sub.document_filter.get("document_ids", [])` without null-checking. `document_filter` is a nullable JSON column.

**Action:** Add `or {}` default: `(sub.document_filter or {}).get("document_ids", [])`.

### 2.9 Streaming trace not saved properly for frontend

In `stream_query`, citations and traces are emitted as SSE events but the `retrievalTrace` field doesn't get stored in a way that the frontend's "Show Retrieval Trace" toggle can access it after streaming completes.

**Action:** Ensure the final SSE event includes the complete `retrieval_trace` object, and update `ChatMessage` interface to persist it.

---

## 3. P2 — Polish & Depth

### 3.1 Frontend has zero tests

`@testing-library/react` and `@testing-library/jest-dom` are installed but no test files exist.

**Action:** Add tests for:
- `ChatInterface.tsx` — SSE streaming, citation display, refusal messages
- `DocumentUploader.tsx` — file validation, upload flow
- `RetrievalTrace.tsx` — expand/collapse, data rendering
- `SourceCitation.tsx` — score badge, content preview

### 3.2 No integration tests for full pipeline

Unit tests mock the database and external APIs. No test exercises the full pipeline with a real pgvector database.

**Action:** Add a test suite that uses the CI PostgreSQL service container to test: upload -> parse -> chunk -> embed -> store -> search -> generate -> citation assembly. One happy path, one refusal path.

### 3.3 Workflow management UI missing

Backend has full workflow API (`/api/v1/workflows`) but the frontend has no workflow management page.

**Action:** Add a `frontend/src/app/workflows/page.tsx` with: workflow list, instance detail, step status, approval actions. This is noted in `STATUS.md` as remaining work.

### 3.4 Structured logging enhancement

`backend/app/core/logging.py` provides basic structlog setup, but individual services don't consistently add context (trace_id, document_id, query_id).

**Action:** Add structlog context variables for request-scoped data. Configure per-service log levels.

### 3.5 Template detection and form extraction not tested

`backend/app/services/document/processing/templates.py` and `forms.py` have no tests.

**Action:** Add `test_templates.py` and `test_forms.py` with sample documents.

### 3.6 Access control permissions incomplete

`backend/app/services/access_control/permissions.py` has a `TODO: check group membership` at line 165.

**Action:** Implement group membership checking. Add tests for all permission scenarios (owner, shared user, group member, non-member).

### 3.7 Document versioning is a stub

`backend/app/services/document/versioning.py` has three TODOs: store version in separate table, query from version table, implement restoration.

**Action:** Create a `document_versions` table via migration. Implement version creation on document update, version listing, and version restoration.

### 3.8 Notification system is placeholder code

Multiple files have `TODO: Implement actual notification sending`:
- `backend/app/tasks/workflows.py:100` — SLA notification
- `backend/app/services/document/processing/approval.py:344` — approval notification
- `backend/app/services/document/processing/approval.py:399` — escalation notification

**Action:** Implement email notifications using a configurable SMTP backend, or integrate with the existing webhook system.

### 3.9 Enhanced retrieval features untested

`services/retrieval/enhanced.py` (intent classification, query expansion, HyDE, strategy selection) and `services/retrieval/strategy.py` (A/B testing framework) have no tests.

**Action:** Add `test_enhanced_retrieval.py` and `test_retrieval_strategy.py`.

---

## 4. P3 — Growth & Long-Term

### 4.1 Phase 2 roadmap items (from ROADMAP.md)

| Item | Description |
|------|-------------|
| Reranking with cross-encoders | `services/reranking/colbert.py` exists as a stub — implement using sentence-transformers cross-encoder |
| Citation highlighting in UI | Highlight cited passages in the source document viewer |
| Conversation memory persistence | Conversations model exists but no long-term memory management |
| Cost tracking per workspace | Track LLM token costs per collection/workspace |

### 4.2 Phase 3 roadmap items

| Item | Description |
|------|-------------|
| SAML/SSO integration | Add SAML/OIDC authentication for enterprise deployments |
| Audit logging | Comprehensive audit trail for all actions (upload, query, delete, config changes) |
| Usage dashboards | Per-tenant usage metrics, rate limit visualization, cost trends |
| API rate limiting per tenant | Extend existing rate limiter to enforce per-tenant quotas |

### 4.3 Additional parsers

Currently: PDF, Markdown, HTML, DOCX.

**Action:** Add parsers for:
- **CSV/TSV** — tabular data parsing with row-based chunking
- **XLSX** — spreadsheet parsing with sheet-aware chunking
- **PPTX** — presentation parsing with slide-based chunking
- **Images** — OCR via Tesseract or cloud OCR (builds on existing OCR service)

### 4.4 EvalForge integration

`README` mentions "EvalForge integration for automated evaluation" but no integration exists.

**Action:** Add an eval endpoint that runs EvalForge YAML suites against GroundTruth queries. Expose eval results in the dashboard.

### 4.5 Multi-tenant workspace isolation

Collections model exists with shares and access control, but no true tenant isolation at the database level.

**Action:** Add `workspace_id` column to all tenant-scoped tables. Implement row-level security policies in PostgreSQL. Add workspace management API.

### 4.6 Real-time collaboration

No support for multiple users viewing/editing the same document or query simultaneously.

**Action:** Add WebSocket-based real-time updates for document processing status and query results.

### 4.7 Admin dashboard

No admin UI for system management (user management, system health, usage stats).

**Action:** Add `frontend/src/app/admin/page.tsx` with user list, system metrics, document management, and configuration editor.

### 4.8 Backup and disaster recovery

No automated backup strategy for documents or database.

**Action:** Add pg_dump-based backup cron job. Document restore procedures. Add S3-compatible storage for document files.

---

## 5. Explicit TODOs in Code

| File | Line | TODO |
|------|------|------|
| `app/api/v1/workflows.py` | 59 | Add filtering by owner/organization |
| `app/tasks/workflows.py` | 100 | Implement actual notification sending |
| `app/services/document/processing/approval.py` | 344 | Implement actual notification |
| `app/services/document/processing/approval.py` | 399 | Send escalation notifications |
| `app/services/document/processing/forms.py` | 172 | Integrate with actual database service |
| `app/services/access_control/permissions.py` | 165 | Check group membership |
| `app/services/document/versioning.py` | 144, 177, 316 | Store/query/restore from version table |

---

## 6. Implementation Priority Order

```
 1. Fix broken imports (app.db.base_class -> app.db.session)       (4 models can't load)
 2. Create app/api/deps.py with get_db and get_current_user        (v1 routes can't load)
 3. Remove duplicate /metrics endpoint                              (runtime error: unreachable code)
 4. Add missing Integer import in collection.py                     (runtime error)
 5. Add Celery settings to config.py                                (import error if celery loads)
 6. Delete stale src/ directory                                     (dead code)
 7. Fix datetime.utcnow() across all models                         (Python 3.12 compat)
 8. Fix __import__ hack in auth middleware                           (code quality)
 9. Migrate legacy ORM models to modern mapped_column style         (consistency)
10. Switch to AsyncOpenAI client                                    (async correctness)
11. Cache get_settings() with @lru_cache                            (performance)
12. Move dev deps from requirements.txt to pyproject.toml           (Docker image size)
13. Add document_filter null check in webhooks                      (runtime error)
14. Fix streaming trace persistence for frontend                    (data completeness)
15. Add frontend tests                                              (0% coverage)
16. Add workflow management UI page                                 (noted in STATUS.md)
17. Add integration tests for full pipeline                         (confidence)
18. Implement document versioning                                   (3 TODOs)
19. Implement notification system                                   (3 TODOs)
20. Implement Phase 2 roadmap items                                 (feature growth)
```
