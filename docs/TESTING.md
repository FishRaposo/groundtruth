# Testing and quality gates

## Canonical installs

Run from the repository root:

```bash
python -m pip install -e "apps/api[dev]"
cd apps/web && npm ci && cd ../..
```

The editable API install and the locked npm install are the only default development
and CI dependency paths. No sibling checkout, Git-installed Python package,
credentials, model download, PostgreSQL, or Redis is needed for default gates.

## Complete gate

```bash
make check
```

`make check` wires these executable checks:

1. API pytest excluding `apps/api/tests/integration`.
2. Ruff lint and format checks over API, tests, examples, and scripts.
3. Pyright over `apps/api/app`.
4. External shared-core forbidden-dependency scan.
5. API wheel build, vendored-content check, and isolated-wheel imports.
6. Deterministic offline portfolio evidence/checksum verification.
7. Frontend Vitest, ESLint, production build, and desktop/mobile Chromium Playwright.

Install the Playwright browser once with:

```bash
cd apps/web
npx playwright install chromium
```

## Focused commands

```bash
make test
python -m pytest apps/api/tests/test_ingestion.py -v --basetemp=.pytest-temp-focused
make lint
make format-check
make typecheck
make forbidden
make wheel-import
make evidence

cd apps/web
npm test
npm run lint
npm run build
npm run test:e2e:chromium
```

Use a workspace-local pytest `--basetemp` on Windows because this machine's default
pytest temporary directory may have broken ACLs.

## Evidence snapshot

The final local portfolio pass recorded:

| Surface | Evidence |
|---|---|
| API full suite | 291 passed |
| Evidence contracts | 17 passed, including manifest/tamper/redaction checks |
| Frontend Vitest | 47 passed across 12 files |
| Ruff check | passed |
| Ruff format check | passed |
| Repository-wide Pyright | 0 errors, 0 warnings |
| Frontend clean install | 586 packages from lockfile; npm audit 0 vulnerabilities |
| Frontend quality | 47 tests; ESLint and Next.js 16 production build passed |
| Chromium Playwright | 8/8 across desktop Chromium and Pixel 5 |
| Evidence reproducibility | two byte-identical runs; `daaa900b228aa7820ead848bdbf51ae3a6b723b514c24588f25f1f554741e334` |

Counts are dated evidence, not permanent badges or a substitute for rerunning gates.

## Optional dependency contracts

`make test-all` includes the integration-shaped SQLite/offline contracts. The manual
CI `workflow_dispatch` `integration` input installs the PostgreSQL and Redis extras
before rerunning those contracts, proving dependency compatibility without claiming
live-service behavior. Live PostgreSQL/pgvector and Redis execution remains an
explicit environment check. Docker builds are verified separately and do not prove a
running deployment.

## Determinism

- Offline generation and hash embeddings keep unit behavior credential-free.
- Golden tests pin retrieval/refusal/citation and score-sensitive behavior.
- The local EvalForge-shaped fixture adapter imports no external EvalForge project.
- Portfolio evidence is generated and verified by repository scripts and checksum
  fixtures; CI verifies rather than silently refreshing those artifacts.
