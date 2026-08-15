# Engineering roadmap

The product-level boundary is in [../ROADMAP.md](../ROADMAP.md). This file records
engineering follow-ups after the self-contained expansion.

## Delivered

- Internally vendored, pinned operator-core compatibility closure; no external
  `shared_core`, Git URL, or sibling checkout.
- Hybrid retrieval, refusal, citations, SSE, deterministic offline provider paths,
  lexical/cross-encoder fallback, bounded conversation memory, and local fixture eval.
- TXT/PDF/Markdown/HTML/DOCX/CSV/TSV ingestion plus optional XLSX/PPTX/OCR.
- Deduplication, entity metadata, quarantine/reindex, document versions/diff/restore.
- Workspace context, group visibility, audit, cost attribution, per-workspace/API-key
  rate buckets, workflow SLA/escalation/approval/events, and notification outbox.
- Workflow, version, citation, trace, and read-only admin frontend surfaces.
- Canonical CI/release gates for package, evidence, Python, frontend, and Chromium.

## Remaining optional validation

- The default local gates are green: 290 API tests, repository-wide Pyright, frontend
  lint/build, and 8 desktop/mobile Chromium tests. Keep those commands in CI and rerun
  them after synchronized changes.
- Exercise opt-in PostgreSQL/pgvector, Redis/Celery, SMTP, webhook, Office, OCR, and
  cached-model paths in dependency-complete environments.
- Validate Docker and Compose health/readiness end to end, including backup/restore,
  before making deployment claims.
- Expand golden fixtures before any score-sensitive retrieval/refusal/citation change.

## Deferred by design

- SAML/SSO and hosted/team administration.
- Hosted notification delivery, mandatory infrastructure, and hosted scheduling.
- Cloud object storage and mandatory cloud services.
- Database row-level security or a hosted tenancy control plane.
- Renaming `apps/api/app` or the established `groundtruth_*` metric names.
