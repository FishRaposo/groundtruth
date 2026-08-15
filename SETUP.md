# GroundTruth Setup

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

Run the API and web development servers in separate terminals:

```bash
make dev
cd apps/web && npm run dev
```

- Web: http://localhost:3000
- API: http://localhost:8000
- OpenAPI: http://localhost:8000/docs

The API defaults to credential-free local generation/embedding fallbacks. Copy
`.env.example` to `.env` only when you need to override settings.

## Optional capabilities

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

```bash
cp .env.example .env
docker compose up --build
```

This starts PostgreSQL/pgvector, Redis, API, and web. `docker-compose.prod.yml` is a
single-server example, not a hosted platform or mandatory deployment topology.

## Verify

```bash
make check
```

Before the browser gate, install Chromium once with
`cd apps/web && npx playwright install chromium`. Use `make test-all` only when the
optional PostgreSQL and Redis test services are available.
