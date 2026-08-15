# Deployment

GroundTruth ships Dockerfiles and Compose examples for local and single-server use.
They are not a managed hosting product or a claim of cloud-production readiness.

## Local full stack

```bash
cp .env.example .env
docker compose up --build
```

This builds from `apps/api` and `apps/web`, then starts PostgreSQL/pgvector, Redis,
API, and web. API health is `/api/health`; OpenAPI is `/docs`.

## Image builds

```bash
docker build -t groundtruth-api ./apps/api
docker build -t groundtruth-web ./apps/web
```

The API image installs only its repository-local package and selected production
extras. The web image uses the committed lockfile with `npm ci`. CI verifies both
builds; a successful build does not prove runtime infrastructure, migrations, or
provider connectivity.

## Single-server Compose example

```bash
docker compose -f docker-compose.prod.yml up -d
```

Set strong database credentials and any intentionally enabled provider settings in
the deployment environment. Terminate TLS at a trusted reverse proxy and restrict
database/API network exposure. Review CORS in `apps/api/app/main.py`.

`docker-compose.prod.yml` is deliberately minimal. Redis/Celery, SMTP/webhook delivery,
cloud storage, hosted scheduling, and externally managed observability are optional
deployment choices—not required product dependencies.

## Release images

Tags matching `v*` trigger `.github/workflows/release.yml`. The release waits for the
canonical reusable CI workflow before publishing API and web images to GHCR. Default
release verification is offline; PostgreSQL/Redis integration remains a separately
reported manual gate.

## Database and recovery

Apply migrations with `make migrate`. Backup and restore helpers live at
`scripts/backup_postgres.py` and `scripts/restore_postgres.py` and are safe dry-run by
default. Follow [BACKUP_RESTORE.md](BACKUP_RESTORE.md) and validate recovery in a
non-production environment before relying on it.

## Production checklist

- Run the final CI commit and record optional integration results separately.
- Configure HTTPS, secrets management, network policy, resource limits, backups, and
  restore drills.
- Validate readiness against the real PostgreSQL/pgvector and provider configuration.
- Decide explicitly whether Redis/Celery and outbound notification adapters are
  enabled.
- Do not claim SAML/SSO, hosted/team administration, hosted notifications, cloud
  object storage, or hosted scheduling; those remain deferred.
