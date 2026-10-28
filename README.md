# GroundTruth

[![CI](https://github.com/FishRaposo/groundtruth/actions/workflows/ci.yml/badge.svg)](https://github.com/FishRaposo/groundtruth/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](apps/api/pyproject.toml)

**Ask an operational question. Inspect the evidence before trusting the answer.**

GroundTruth combines scoped retrieval, immutable citations, document versions and
human review in a FastAPI/Next.js application. The portable connected profile uses
real SQLite persistence, pinned local CPU semantic embeddings and clearly labeled
source-extractive answers. A separate visual sample tour runs without a backend.
PostgreSQL/pgvector and Redis/Celery code is included; live infrastructure
verification remains deferred while the owner continues without WSL.

[Visual tour](#portfolio-demo) · [Actual workflow](docs/portfolio-connected.md) · [Original verification](docs/portfolio-verification.md) · [Reader verification](docs/answer-coverage-verification.md) · [Case study](docs/portfolio-case-study.md) · [Setup](SETUP.md) · [Architecture](docs/ARCHITECTURE.md)

## Portfolio demo

Choose **Start guided demo** or explore freely. Persistent **Interactive sample
data** labeling distinguishes the preview from actual execution. One scenario
state drives Chat, Documents, Workflows and Admin, with complete reset.

```bash
cd apps/web
npm ci
npm run demo:ui
```

Open http://localhost:3505.

**Click path:**

1. Ask about staging rollback; open the highlighted current citation.
2. Compare an outdated runbook with the current version.
3. Inspect an unsupported-question refusal and a curated procedural conflict.
4. Follow a quarantined-file recovery, then inspect consistent review/audit views.
5. Open the actual workflow and engineering evidence.

The preview makes no API/provider/font request. Sample file selection does not
transmit file contents. Keyboard-operable source details return focus to the
citation; reduced motion and mobile/tablet layouts are supported. See the
[walkthrough](docs/portfolio-walkthrough.md).

Set `NEXT_PUBLIC_DEMO_MODE=true` in any Next.js build or dev command to enable
forced demo mode without the `demo:ui` script.

## Offline demo

The fastest proof path needs no credentials, database, Redis, model download, or
sibling repository:

```bash
python -m pip install -e "apps/api[dev]"
make demo
```

`make demo` runs the deterministic command-line grounded-answer and refusal demo.
It does not start Docker or open the web interface.

## Actual connected quickstart

```bash
python -m pip install -e "apps/api[dev,embeddings,reader]"
python -m app.model_setup --directory .tmp/models/minilm
python -m app.model_setup --reader --directory .tmp/models/reader
python scripts/portfolio_local.py migrate
python scripts/portfolio_local.py serve
```

- API: http://127.0.0.1:8400
- OpenAPI: http://127.0.0.1:8400/docs
- Production frontend: http://127.0.0.1:3505

Seed in a separate terminal with `python scripts/portfolio_local.py seed`, then
enter the generated disposable API key through **Connection**. The
[complete setup](docs/portfolio-connected.md) includes isolated environments,
CPU-only dependency installation, frontend build/start, private manifest handling
and explicit deterministic mode. Connected failures remain errors; switching to
sample mode is always explicit. Historical library defaults preserve the original
offline golden fixture and are not the authenticated application profile.

The local reader is an optional, separately cached CPU extractive QA model. It
copies source passages and highlights their exact offsets; it does not generate
new factual prose. Missing assets produce an error. Explicit lexical mode remains
available. [Answer-coverage work](docs/answer-coverage-baseline.md) preserves the
first failed evaluation and defines the separate frozen blind acceptance gate;
adding a reader does not by itself demonstrate that this gate passes. The frozen
reader candidate currently fails the original rollback browser journey at its
development-selected threshold -8. The original review instance remains on the
previous version; the separate successful factual-answer diagnostic is scoped
evidence, not a passing complete connected acceptance suite.
The first new 200-case comparison also **failed**: default reader 55/120 correct
answers and 77/80 correct negatives, versus baseline 30/120 and 68/80. The target
is 114/120 and 80/80. Both complete first reports, the concurrent-editor integrity
qualification and a subsequently repaired diagnostic-access defect are recorded
in [reader verification](docs/answer-coverage-verification.md). Multi-document
support remains; no failed evidence was replaced.

## Measured limits

The frozen corpus has 12 synthetic runbooks and 100 agent-authored cases; labels
have no human/model-quality validation. After development-only tuning, the first
held-out measurement passed 37/80 contracts per method: expected sources were
retrieved, but conservative support checks refused42 answerable cases and missed
one refusal. Zero unauthorized-source exposures or execution errors were observed.
The first result is preserved; subsequent repairs are exposed regressions, not
fresh held-out validation. Literal coverage is not entailment. See
[the case study](docs/portfolio-case-study.md) before making quality claims.

Live PostgreSQL/Redis, large indexed performance, hosted CI, provider quality and
hosted multi-user authentication remain unverified. No production-capacity or
universal contradiction-detection claim is made.

## What it does

1. **Ingests** TXT, PDF, Markdown, HTML, DOCX, CSV, and TSV by default. XLSX/PPTX,
   OCR, and model-backed embeddings/reranking are explicit extras.
2. **Normalizes and deduplicates** documents and chunks before embedding, retaining
   failed source files with quarantine metadata for reindexing.
3. **Retrieves** with vector and keyword search, reciprocal-rank fusion, and
   deterministic reranking fallbacks.
4. **Answers or refuses** using confidence and safety gates, with citations and a
   retrieval trace in normal and SSE flows.
5. **Tracks operations** with request/workspace context, structured audit events,
   cost attribution, API-key-aware rate limits, document version history, workflow
   status events, and a notification outbox.
6. **Supports local evaluation** through a dependency-free fixture adapter and a
   deterministic portfolio evidence bundle.

## Architecture

```mermaid
flowchart LR
    WEB[Next.js web] -->|REST and SSE| API[FastAPI API]
    API --> ING[Ingestion]
    API --> RAG[Retrieve, rerank, refuse, generate, cite]
    API --> WF[Versions, workflows, audit, notifications]
    ING --> DB[(PostgreSQL and pgvector)]
    RAG --> DB
    WF --> DB
    WF -. optional .-> REDIS[(Redis and Celery)]
    RAG -. optional .-> PROVIDER[LLM and embedding providers]
```

The API owns a narrow compatibility subset vendored at
`apps/api/app/internal/vendor_core/`. It is pinned to
`FishRaposo/operator-shared-core` v1.3.0 at commit
`dbf276a7708da65b55e1f10b35af634b300d1f07`, internally namespaced, MIT-licensed,
and shipped in the wheel. No external `shared_core` install, Git URL, or sibling
checkout is required. See [migration provenance](docs/migrations/2026-08-15-operator-shared-core-v1.3.0-vendoring.md).

## Verification

```bash
# Canonical installs
python -m pip install -e "apps/api[dev]"
cd apps/web && npm ci && cd ../..

# Complete local gate; Playwright Chromium must already be installed
make check

# Install the browser once when needed
cd apps/web && npx playwright install chromium
```

The gate covers API pytest, Ruff lint and format checks, Pyright, the forbidden
external-dependency scan, wheel build/content/isolated-import verification,
deterministic portfolio evidence, frontend Vitest, ESLint, production build, and
Chromium Playwright smoke tests across three viewports plus axe WCAG scans. The CI
`workflow_dispatch`
`integration` input installs PostgreSQL and Redis extras before rerunning the
SQLite/offline integration-shaped contracts; it does not claim live-service coverage.

The default gate (`make test` / CI) runs the `apps/api/tests` suite —
**396 tests pass with 1 skip** at the 0.2.0 audit — plus **18** repository-level
verifier contracts under `scripts/tests`. The final local pass also recorded
**72 passing frontend Vitest tests across 20 files**, Ruff check/format,
repository-wide Pyright with zero errors, a production Next.js build, and
**21/21** Chromium browser checks (sample journey plus axe WCAG scans across
desktop, mobile, and tablet viewports). The connected live and reader-diagnostic
browser suites run against a real disposable FastAPI + production Next.js stack;
they are exercised in the dedicated `connected-live` CI job rather than the
default browser gate.
The evidence bundle reproduced byte-for-byte twice with hash
`daaa900b228aa7820ead848bdbf51ae3a6b723b514c24588f25f1f554741e334`.
Live PostgreSQL/Redis integration and Docker runtime execution were not available on
this host and are not implied pass claims.

## Security and deployment boundaries

- API authentication and rate limiting are configurable; rate buckets are isolated
  by workspace and hashed API-key identity.
- Uploaded filenames are not trusted for storage paths.
- SMTP, webhooks, OCR, Office parsing, local model inference, PostgreSQL, Redis, and
  Docker are opt-in integrations.
- SAML/SSO, hosted/team workflows, hosted notification services, mandatory
  infrastructure, cloud object storage, and hosted scheduling are deliberately
  deferred. See [Security](docs/SECURITY.md) and [Roadmap](ROADMAP.md).

## Part of the stack

[evalforge](https://github.com/FishRaposo/evalforge) · [llm-gateway](https://github.com/FishRaposo/llm-gateway) · [aria-agent](https://github.com/FishRaposo/aria-agent) · [agenttrace](https://github.com/FishRaposo/agenttrace) · [WCP-Compliance-Agent-V5](https://github.com/FishRaposo/WCP-Compliance-Agent-V5)

## License and provenance

GroundTruth is MIT licensed. Third-party provenance and the vendored upstream license
are recorded in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
