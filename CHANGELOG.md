# Changelog

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
