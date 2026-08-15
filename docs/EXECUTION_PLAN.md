# Expansion execution record

This is a historical record of the 2026-08 comprehensive expansion. It is not the
current test dashboard; rerun [TESTING.md](TESTING.md) gates for current truth.

## Historical baseline

Before the earlier convergence pass, reports recorded 85 API tests and 8 frontend
tests. That pass later recorded 153 API and 36 frontend tests. Those numbers describe
past snapshots and must not be used as current badges or readiness claims.

## Expansion constraints

- Preserve routes, schemas, status codes, SSE vocabulary, retrieval/refusal/citation
  behavior, migrations, and deterministic fallbacks.
- Require no external `shared_core`, credentials, network evaluation, PostgreSQL, or
  Redis for the default install/demo/CI path.
- Keep Office/OCR/model/provider/SMTP/webhook/PostgreSQL/Redis/Docker integrations
  optional.
- Defer SAML/SSO, hosted/team workflows, hosted notifications, mandatory
  infrastructure, cloud storage, and hosted scheduling.

## Delivered workstreams

1. Pinned and internally vendored the v1.3.0 operator-core closure; aligned package,
   wheel, forbidden-dependency, isolated-import, Docker, and attribution contracts.
2. Added typed provider adapters, request/workspace context, redacted audit, cost
   attribution, group visibility, and workspace/API-key rate buckets.
3. Added optional local cross-encoder fallback, bounded conversation memory,
   CSV/TSV/XLSX/PPTX adapters, and dependency-free fixture evaluation.
4. Added version/diff/restore persistence, workspace-scoped workflows and status SSE,
   notification outbox/adapters, backup/restore helpers, and frontend operational
   evidence surfaces.
5. Wired deterministic portfolio evidence, complete CI/release/package/browser gates,
   and reconciled documentation/provenance.

## Final Task 5 evidence snapshot

| Surface | Recorded result |
|---|---|
| API full suite | 289 passed |
| Evidence contract suite | 16 passed |
| Frontend Vitest | 47 passed across 12 files |
| Ruff check and format | passed |
| Repository-wide Pyright | 0 errors, 0 warnings |
| Task 5 frontend clean install | npm audit 0 vulnerabilities; ESLint and Next.js 16 production build passed |
| Task 5 Chromium | 8/8 across desktop Chromium and Pixel 5 |
| Reproducibility hash | `daaa900b228aa7820ead848bdbf51ae3a6b723b514c24588f25f1f554741e334` |

Optional live PostgreSQL/Redis integration and Docker runtime execution remain
environment-specific checks; ordinary CI and the canonical demo stay offline-first.
The manual extras job reruns offline contracts with optional drivers installed and is
not labeled as a live-service test.
