# GroundTruth

[![Tests](https://img.shields.io/badge/tests-153%20api%20%2B%2036%20web-brightgreen)]() [![Lint](https://img.shields.io/badge/ruff-clean-brightgreen)]() [![Python](https://img.shields.io/badge/python-3.12-blue)]() [![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi)]() [![Next.js](https://img.shields.io/badge/Next.js-000?logo=next.js)]()

**Production RAG platform with hybrid search, citations, and refusal logic.**

GroundTruth answers questions only from uploaded documents, always cites sources, refuses when evidence is insufficient, and exposes full retrieval traces for debugging.

[Quick Demo](#quick-demo) • [Architecture](#architecture) • [API Docs](docs/API.md)

---

## Quick Demo

```bash
make demo
```

Starts all services, seeds sample data, and opens the UI at http://localhost:3000

---

## 1. What This Is

GroundTruth is an open-source internal assistant template that answers questions **only** from uploaded documents, always **cites sources**, **refuses when evidence is insufficient**, and exposes **retrieval/debug traces**.

It is NOT "chat with your PDFs." It is a production-minded RAG system with evidence discipline — designed for teams that need trustworthy, auditable AI-assisted answers grounded in their own documentation.

---

## 2. What Problem It Solves

Teams deploying internal AI assistants face a common set of failures:

- **Hallucinated answers** that sound confident but are fabricated
- **No source attribution** — users cannot verify where information came from
- **No graceful refusal** — the system tries to answer every question, even when it shouldn't
- **No debuggability** — when answers are wrong, there's no way to trace what was retrieved

GroundTruth addresses all four. Every answer is grounded in retrieved evidence, every claim is cited, and when evidence is insufficient the system says so explicitly. Retrieval traces are exposed so teams can debug and improve their document corpus.

---

## 3. Why Naive AI Systems Fail Here

| Failure Mode | Naive System | GroundTruth |
|---|---|---|
| Hallucination | LLM generates plausible-sounding fiction | LLM is constrained to retrieved context only |
| No Citations | Users must trust answers blindly | Every factual claim links to source chunks |
| No Refusal | System answers everything, even garbage | Confidence thresholds trigger graceful refusal |
| No Debuggability | Black box | Full retrieval trace with scores and ranking |

---

## 4. Architecture

```mermaid
graph TB
    UI[Next.js Frontend :3000]
    API[FastAPI Backend :8000]
    IS[Ingestion Service]
    RS[Retrieval Service]
    GS[Generation Service]
    DB[(PostgreSQL + pgvector)]
    LLM[LLM API]

    UI -->|REST API| API
    API --> IS
    API --> RS
    API --> GS
    IS -->|Parse → Dedup → Enrich → Chunk → Embed| DB
    RS -->|Hybrid Search + Rerank| DB
    GS -->|Prompt with context| LLM
    GS -->|Citations + Trace| API
```

---

## 5. Local Quickstart

```bash
# Clone and enter the project
git clone https://github.com/your-org/groundtruth.git
cd groundtruth

# Copy environment variables
cp .env.example .env

# Start all services
docker compose up --build

# Access the application
# Frontend UI: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs:    http://localhost:8000/docs
```

Upload sample documents from `data/sample/` and start asking questions.

---

## 6. Example Workflow

1. **Upload** — Drag and drop your team's documents (plain text `.txt`, PDF, Markdown, HTML, DOCX) via the UI
2. **Process** — Documents are normalized and content-hashed, duplicate documents/chunks are skipped, entities are extracted offline, and semantic chunks are embedded
3. **Ask** — Type a natural language question in the chat interface
4. **Retrieve** — The system performs hybrid search (vector + keyword), reranks results, and checks confidence
5. **Answer** — The LLM generates a grounded answer using only retrieved context
6. **Cite** — Every factual claim is linked to source chunks with relevance scores
7. **Trace** — Expand the retrieval trace to see exactly which chunks were found, their scores, and how they were ranked

If confidence is low, the system refuses with a clear explanation and suggestion for reformulation.

---

## 7. Key Design Decisions

| Decision | Rationale |
|---|---|
| **Hybrid search** (vector + keyword) | Pure vector search misses exact matches; pure keyword misses semantic similarity |
| **Reranking** | Initial retrieval cast a wide net; reranking narrows to truly relevant results |
| **Refusal logic** | Better to say "I don't know" than to hallucinate; builds user trust |
| **Citation assembly** | Every claim must be traceable to a source chunk; enables verification |
| **pgvector** | Keeps vector storage co-located with relational data; simplifies deployment |
| **Service boundaries** | Each pipeline stage (ingestion, retrieval, generation) is isolated for testability |

---

## 8. Failure Handling

| Scenario | Behavior |
|---|---|
| No documents found | Return refusal: "I don't have any documents matching that topic" |
| Low confidence (< threshold) | Return refusal with confidence score and suggestion |
| LLM API error | Return error response with retry suggestion |
| Document processing failure | Mark document as `error` status, log details |
| Duplicate normalized content | Record `duplicate_of`, create no duplicate chunks, and avoid another embedding call |
| Quarantined document | Retain the UUID-safe source path plus failing stage/reason; retry through the existing reindex operation |
| Empty or malformed query | Return 422 validation error |
| Backend unreachable (frontend) | Chat degrades to a visible **demo mode** with simulated, cited answers |
| Dangling `[n]` citation marker | Rendered muted in the UI; flagged by the citation evaluator |

See [docs/failure-modes.md](docs/failure-modes.md) for the full catalog and the
refusal decision diagram.

The selective ingestion consolidation and KnowledgeOps topology review are
recorded in
[the migration provenance record](docs/migrations/2026-08-12-document-intelligence-pipeline-and-knowledgeops-into-groundtruth.md).

---

## 9. Evaluation & Testing Strategy

GroundTruth is designed for eval-driven iteration:

- **API tests (153)** — every service (chunking, embedding, retrieval, citation,
  refusal, generation, reranking) plus the cost-tracking, lexical-reranking,
  citation-evaluation, and bytes-parser convergence modules; success **and** error paths.
- **Web tests (36)** — component tests for chat, citation highlighting, error boundary,
  loading/refusal states, and the demo-mode library.
- **Playwright smoke** — homepage + chat demo-mode flow (`apps/web/e2e`).
- **Golden-output gating** — numeric outputs (rerank blends, similarity, cost) are pinned
  by tests so convergence refactors can't silently drift. See
  [docs/design-decisions.md](docs/design-decisions.md).
- **Integration tests** for the full pipeline (upload → query → answer) under `make test-all`.
- **Retrieval traces** exposed via API for manual inspection.
- **Citation grounding evaluation** via `shared_core.evaljudge.CitationJudge`.

---

## 10. Deployment Notes

- **Docker Compose** for local development and single-server deployment
- **Environment variables** for all configuration (see `.env.example`)
- **Scaling**: Stateless API servers behind a load balancer; PostgreSQL with read replicas for retrieval
- **Monitoring**: Health check endpoint at `/api/health`; structured logging throughout
- **Security**: API key for LLM access; document-level access control planned

---

## 11. Roadmap

- [x] Streaming responses via Server-Sent Events
- [x] Per-workspace cost & latency tracking (`/api/metrics/cost`, via `shared_core.llmmetrics`)
- [x] Offline lexical reranking pass (via `shared_core.embeddings`)
- [x] Citation grounding evaluation (via `shared_core.evaljudge.CitationJudge`)
- [x] Demo-mode frontend fallback for zero-backend exploration
- [ ] Multi-tenant support with workspace isolation (cost tracker is workspace-ready)
- [ ] Additional parsers (CSV, XLSX, PPTX)
- [ ] Conversation memory with context windowing
- [ ] Admin dashboard for document management
- [ ] Webhook notifications for processing events

See [docs/roadmap.md](docs/roadmap.md) for the engineering convergence backlog.

---

## 12. What This Project Demonstrates

Production-minded RAG design, service boundaries, retrieval observability, source citation, refusal behavior, and eval-driven iteration.
