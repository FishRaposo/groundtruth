# GroundTruth comprehensive expansion

## Global constraints

- Preserve current API routes, response keys, status codes, retrieval/refusal/citation semantics, migrations, SSE vocabulary, and deterministic offline fallbacks.
- Vendor the exact GroundTruth shared-core closure from v1.3.0 at dbf276a7708da65b55e1f10b35af634b300d1f07 under apps/api/app/internal/vendor_core/.
- Default install/demo/CI require no external shared_core package, credentials, network-backed evaluation, or live PostgreSQL/Redis.
- Optional parser, embedding, cross-encoder, OCR, SMTP, webhook, PostgreSQL, Redis, and Docker integrations remain opt-in.
- Defer SAML/SSO, hosted/team workflows, hosted notification services, mandatory infrastructure, cloud object storage, and hosted scheduling.

## Tasks

### Task 1 — Baseline contracts, vendored core, and package alignment

Capture baseline evidence and golden fixtures. Vendor config/database/docparse/embeddings/errors/evaljudge/llmmetrics/logging/tasks plus proven transitive pricing modules under the internal namespace. Rewrite imports, add attribution/license, align pyproject/requirements/Makefile/CI/release/Docker, split optional extras, verify wheel contents, and add sibling-free import tests.

### Task 2 — Core correctness, provider contracts, workspace context, and audit/rate limits

Repair remaining import/config/timezone/dead-code defects. Add local generation/embedding protocols preserving AsyncOpenAI and offline behavior, request/workspace context, structured audit events, workspace-scoped cost tracking, group membership checks, per-workspace rate limiting, and golden parity tests.

### Task 3 — RAG, ingestion, memory, and evaluation expansion

Deliver optional cross-encoder fallback, conversation memory, CSV/TSV/XLSX/PPTX/OCR adapters, template/form/enhanced-retrieval coverage, deterministic parser/hash behavior, and an EvalForge-compatible local fixture adapter without a cross-repo dependency.

### Task 4 — Persistence, workflows, notifications, backups, and frontend capability

Add version snapshots/diff/restore migrations and routes, workspace filtering, notification outbox with memory/SMTP/webhook adapters, workflow SLA/escalation/approval behavior, local status stream, backup/restore scripts, and frontend workflow/version/admin/audit/trace/citation surfaces with tests.

### Task 5 — Evidence, CI, docs, public surfaces, receipt, and synchronization

Add deterministic offline evidence scripts/golden fixture/checksums, full CI and browser gates, reconcile all docs and historical claims, update site/GitHub metadata, create/check the portfolio receipt, merge/push GroundTruth and site separately, update hub inventory/changelog, and run hub synchronization checks.
