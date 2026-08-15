# Improvement plan

The previous version of this file was a pre-expansion audit. Its broken-import,
`backend/`/`frontend/` path, zero-test, versioning-stub, group-membership, workflow UI,
notification placeholder, and external shared-core findings have been resolved or
superseded. Git history preserves that audit; repeating it here would misdescribe the
current tree.

## Remaining optional validation

The default local and CI gates are now green: 291 API tests, repository-wide Pyright,
clean frontend install/tests/lint/build, 8 Chromium smoke tests, and two identical
evidence runs. The following checks require services or optional dependencies that
were not available in this local environment:

1. Exercise the manually gated PostgreSQL/pgvector and Redis/Celery integration suite.
2. Build both Docker images and validate Compose health/readiness end to end.
3. Test Office/OCR/cached-cross-encoder, SMTP/webhook, and backup/restore paths in
   dependency-complete environments.

## Deferred product work

The following are deliberate boundaries, not incomplete promises in the current
release:

- SAML/SSO and hosted/team administration.
- Hosted notification services and hosted scheduling.
- Mandatory infrastructure or cloud object storage.
- Database row-level security and a hosted tenancy control plane.

## Change discipline

Preserve public API and SSE contracts, deterministic offline fallbacks, score-sensitive
goldens, migration order, internal-vendor provenance, and optional-integration
boundaries. New capability requires an executable gate and an honest documentation
update in the same change.
