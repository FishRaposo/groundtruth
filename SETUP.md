# GroundTruth Setup

Start with the [portable connected workflow](docs/portfolio-connected.md) for the
current application: loopback8400/3505, SQLite, inline ingestion, API keys, pinned
CPU semantic embeddings and source-extractive answers. It includes real seeding,
private manifest handling and production frontend startup. WSL/Docker are deferred
on the current host. See [verification](docs/portfolio-verification.md) for checks
actually observed; infrastructure recipes are not passing service tests.

The reader continuation has a separate [verification](docs/answer-coverage-verification.md):
its quality gate and original connected rollback journey remain FAILED. A healthy
cached reader is not a quality pass. Preserve the existing8400/3505 review app;
the isolated follow-up is on8402/3506 pending integration with concurrent work.

## Prerequisites

- Python 3.11+
- Node.js 20.19+ (required by the pinned Vite 8 test toolchain)
- Docker with Compose only for the full infrastructure path

## Offline development setup

From the repository root:

```bash
python -m venv .venv
# PowerShell: .\.venv\Scripts\Activate.ps1
# POSIX: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e "apps/api[dev]"

cd apps/web
npm ci
cd ../..
```

For an explicit deterministic portable API, migrate and run in separate terminals:

```bash
python scripts/portfolio_local.py migrate --embedding deterministic
python scripts/portfolio_local.py serve --embedding deterministic
# Another terminal:
python scripts/portfolio_local.py seed --embedding deterministic
```

- API: http://127.0.0.1:8400
- OpenAPI: http://127.0.0.1:8400/docs
- Follow the connected workflow for the production web server on3505.

Deterministic hashing is explicitly labeled and has no semantic-quality claim.
For semantic retrieval install the CPU/model extra, explicitly download the
pinned model and omit `--embedding deterministic`. Missing local assets fail
readiness; no fallback substitutes a successful result. Library legacy defaults
remain for original offline golden evidence. Authenticated HTTP rejects unscoped
legacy execution until connected modes are configured.

## Optional capabilities

The [continued reader development record](docs/answer-coverage-development-v3.md)
documents the approved, explicitly selected RoBERTa comparison alongside MiniLM,
including exact revision, attribution and setup command. Keep each model cache
separate and set its path and revision together. This comparison has not passed
the answer-coverage acceptance gate; it does not change the review instance or
legacy defaults. Model requests never download missing files.

The [current engineering record](docs/evidence/answer-coverage-v7/README.md)
includes fresh outside-checkout base and optional-reader installations. Both
cached CPU readers were exercised through upload, query, history and source
inspection; those functional smoke probes use threshold0. The separately frozen
quality configuration retains RoBERTa threshold4. Do not substitute smoke-probe
success for the fresh200-case acceptance gate.

```bash
python -m pip install -e "apps/api[dev,parsers,office,ocr,embeddings]"
python -m pip install -e "apps/api[dev,postgres,redis]"
```

Office, OCR, model, PostgreSQL, and Redis paths are opt-in. The `ocr` extra installs
the Python adapters (`pytesseract`, `pdf2image`, and Pillow); OCR execution also
requires the native Tesseract executable, and PDF-to-image conversion requires
Poppler on the host. PostgreSQL and Redis extras still require their corresponding
services when those integration paths are selected.

## Full stack with Docker

Not observed in this continuation. Do not run this while deferring WSL/Docker.
For isolated future infrastructure, prefer `infra/portfolio.compose.yml` on
5545/6385; the historical stack below retains its own existing volumes/ports.

```bash
cp .env.example .env
docker compose up --build
```

The configured stack describes PostgreSQL/pgvector, Redis, API and web. A queued
profile additionally needs the canonical Celery worker and shared storage. Real
queue/index acceptance, indexed benchmarks and hosted execution remain pending.
`docker-compose.prod.yml` is a single-server example, not a verified hosted platform.

## Verify

```bash
make check
```

Before the browser gate, install Chromium once with
`cd apps/web && npx playwright install chromium`. Use `make test-all` only when the
optional PostgreSQL and Redis test services are available.

## Latest isolated reader verification

The [post-seal record](docs/evidence/answer-coverage-v9/README.md) binds the current
`reader-parts-v14` wheel to source and verifies a fresh base installation plus
both cached-reader probes in the separately installed optional environment.
No model downloads occur during requests. The five focused real-API checks use
RoBERTa threshold4; installed smoke probes use0 and make no quality claim. The
new fresh200 trial FAILED69/120+62/80; keep8400/3505 and its database unchanged.
Archived runners use disposable8402/8410 APIs and3506 frontend; adapt paths and
regenerate private seed manifests locally instead of publishing keys.
