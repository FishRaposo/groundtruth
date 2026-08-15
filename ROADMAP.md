# GroundTruth roadmap

## Delivered

- Hybrid vector/keyword retrieval, reranking fallbacks, citations, refusal, SSE, and
  bounded conversation memory.
- Deterministic offline generation/embeddings/evaluation plus optional provider/model
  adapters.
- Structured/tabular/Office/OCR ingestion boundaries, deduplication, quarantine, and
  document version history/diff/restore.
- Workspace-aware context, access checks, audit, cost tracking, rate limits, workflows,
  notification outbox, read-only admin evidence, and frontend operational surfaces.
- Self-contained package provenance and full executable CI/release gate wiring.

## Remaining optional validation

- The synchronized local snapshot is green: repository-wide Pyright, frontend
  lint/build, and desktop plus Pixel 5 Chromium Playwright all pass.
- Opt-in integration runs for PostgreSQL/pgvector, Redis/Celery, SMTP/webhooks,
  Office/OCR, cached cross-encoder weights, Docker, and backup/restore.

## Deliberately deferred

- SAML/SSO.
- Hosted/team workflows and hosted notification services.
- Mandatory infrastructure, cloud object storage, and hosted scheduling.
- Database row-level security and a hosted tenant control plane.
