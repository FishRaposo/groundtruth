# Changelog

## 2026-10-24 — 0.2.0

- Delivered the scoped portable application profile: SQLite, inline ingestion,
  pinned local CPU embeddings or explicit deterministic mode, and extractive
  answers with workspace-scoped SQL authorization, durable ingestion jobs and
  immutable document versions. No WSL, Docker or paid providers required.
- Added the coverage-v2 answer-coverage cycle: a pinned local extractive reader
  (`deepset/minilm-uncased-squad2` at a fixed revision with sha256-verified
  assets and no fallback), per-citation exact answer spans, mid-stream scope
  rechecks on SSE, a frozen development evaluation and an immutable candidate
  freeze before blind authoring. The recorded first held-out failure remains
  preserved unchanged; blind validation evidence is recorded separately.
- Audit hardening: bounded `limit`/`offset` on document, key, version-history
  and workflow-definition list endpoints; version string now single-sourced
  from `app.__version__`. Fixed the rate-limit middleware ignoring each key's
  configured `rate_limit` (it read `request.state.api_key`, which only route
  dependencies set) — reproduced as a real 429 during a seeded browser run and
  covered by a configured-limit regression test.
- Frontend stack: React 19 (fixed the removed `JSX.Element` global), Playwright
  1.64 for `ubuntu-latest` runners, `@testing-library` updates and a new axe
  WCAG 2.1 A/AA browser suite, which found and verified a fixed
  `label-content-name-mismatch` defect on the shared header logo link;
  OpenGraph/Twitter metadata added.
- Hosted CI: added script contract tests, recorded connected-evidence integrity
  verification, added the missing production build step to the browser job
  (its Playwright web server requires a standalone build — a guaranteed
  first-push failure), and a connected-live job that runs the real portable
  API in two phases: lexical-mode workflow verification across a restart on
  the default corpus, then a reader-mode coverage-corpus instance with a
  durable reader-error row for the connected and diagnostic browser suites.
  PostgreSQL/pgvector/Redis contract tests run against real service
  containers.

## 2026-08-15

- Made the API package self-contained by vendoring the pinned operator-core v1.3.0
  closure under an internal namespace with MIT provenance and wheel/import gates.
- Added typed generation/embedding providers, workspace context, audit, cost tracking,
  group visibility, and workspace/API-key rate limiting.
- Added bounded conversation memory, structured and optional Office parsers, local
  reranking fallbacks, and dependency-free fixture evaluation.
- Added document versions/diff/restore, workflow status/approval/escalation, local
  notification outbox/adapters, backup/restore helpers, and frontend operational
  evidence surfaces.
- Reconciled canonical editable API and locked npm installs across Makefile, CI,
  release, Docker, pre-commit, package scripts, and docs. Added executable pytest,
  Ruff, Pyright, package, evidence, Vitest, ESLint, build, and Chromium gates while
  keeping PostgreSQL/Redis integration optional.
- Upgraded the frontend gate stack to patched Next.js 16, Vitest 4, Vite 8, and
  ESLint 9 releases; the clean lockfile audit reports zero vulnerabilities.
- Verified the final local suite: 291 API tests, 47 frontend tests, Ruff,
  repository-wide Pyright, production build, 8 Chromium smoke tests, and two
  byte-identical evidence runs with hash
  `daaa900b228aa7820ead848bdbf51ae3a6b723b514c24588f25f1f554741e334`.

Live PostgreSQL/Redis integration and Docker runtime execution were not available in
the local environment and remain separately opt-in rather than implied pass claims.
