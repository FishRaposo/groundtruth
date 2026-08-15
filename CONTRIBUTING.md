# Contributing

## Setup

From the repository root:

```bash
python -m venv .venv
# Activate the environment for your shell
python -m pip install --upgrade pip
python -m pip install -e "apps/api[dev]"

cd apps/web
npm ci
cd ../..
```

Optional API extras are declared in `apps/api/pyproject.toml`. Do not add a sibling,
Git-installed, or external `shared_core` dependency.

## Before opening a pull request

```bash
make check
git diff --check
```

Install Playwright Chromium once with
`cd apps/web && npx playwright install chromium`. `make check` covers pytest, Ruff
lint/format, Pyright, package and evidence checks, frontend Vitest/lint/build, and
desktop/mobile Chromium smoke tests.

If a change touches PostgreSQL/pgvector or Redis/Celery behavior, also run
`make test-all` with those services available or use the manual CI integration gate.
Do not report optional integrations as verified when they were not run.

## Code locations

- API code: `apps/api/app/`
- API tests: `apps/api/tests/`
- Alembic migrations: `apps/api/alembic/versions/`
- Web pages/components/lib/types: `apps/web/src/`
- Web unit tests: co-located `*.test.ts` / `*.test.tsx`
- Browser tests: `apps/web/e2e/`
- Offline examples and checks: `examples/`, `scripts/`
- Architecture/API/testing/security docs: `docs/`

## Change rules

- Preserve route, response, status-code, SSE, retrieval/refusal/citation, migration,
  and deterministic fallback contracts unless a deliberate breaking change is
  approved and documented.
- Add a regression test before fixing behavior. Configuration-only changes must have
  an executable static/CI contract where practical.
- Keep optional Office/OCR/model/provider/SMTP/webhook/PostgreSQL/Redis/Docker paths
  opt-in.
- Update docs, provenance, package metadata, and generated evidence in the same change
  when their source contract changes.
- Never commit credentials, `.env`, provider responses, or sensitive document data.
- Do not weaken or exclude a failing quality gate merely to make CI green.

## Deferred scope

SAML/SSO, hosted/team workflows, hosted notification services, mandatory
infrastructure, cloud object storage, and hosted scheduling are intentionally outside
the current product boundary.
