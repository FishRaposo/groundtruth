# Entry Points

## API

- Development server: `make dev` or
  `cd apps/api && uvicorn app.main:app --reload --port 8000`
- Application: `apps/api/app/main.py` (`app.main:app`)
- OpenAPI: http://localhost:8000/docs
- Worker: `make worker` (`app.core.celery.celery_app`)
- Migrations: `make migrate`

## Web

- Locked install: `cd apps/web && npm ci`
- Development server: `cd apps/web && npm run dev`
- Production build: `cd apps/web && npm run build`
- App Router pages: `apps/web/src/app/`
- API client and SSE handling: `apps/web/src/lib/api.ts`

## Offline proof and verification

- Grounded answer/refusal demo: `make demo`
- Local evaluation fixture: `python scripts/evaluate_groundtruth_fixture.py apps/api/tests/fixtures/evaluation/offline-suite.json`
- Portfolio evidence verification: `make evidence`
- Complete quality gate: `make check`

## Optional infrastructure

- Full local stack: `docker compose up --build`
- PostgreSQL backup/restore: `scripts/backup_postgres.py` and
  `scripts/restore_postgres.py` (safe dry-run by default)
