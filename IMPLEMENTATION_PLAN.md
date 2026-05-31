# Implementation Plan

## Phase 1 — Core Pipeline

- [x] Set up project scaffolding (docker-compose, configs, database)
- [x] Implement document upload endpoint with file storage
- [x] Build parser infrastructure (base class + PDF, Markdown parsers)
- [x] Implement text chunking service with configurable size/overlap
- [x] Set up embedding service with OpenAI provider
- [x] Create pgvector schema and vector storage operations
- [x] Implement basic similarity search retrieval
- [x] Build generation service with constrained prompt template
- [x] Wire query endpoint: retrieve → generate → respond
- [x] Create minimal frontend with chat interface and document upload
- [x] Add health check endpoint with dependency status

## Phase 2 — Intelligence Layer

- [x] Implement keyword search alongside vector search
- [x] Build hybrid search with score fusion (Reciprocal Rank Fusion)
- [x] Implement reranking service with cross-encoder scoring
- [x] Build citation assembly from retrieved chunks
- [x] Implement refusal logic with configurable thresholds
- [x] Add retrieval trace recording and API exposure
- [x] Build HTML and DOCX parsers
- [x] Add semantic chunking strategy (placeholder)
- [x] Implement document re-indexing endpoint
- [x] Add confidence scoring for generated answers

## Phase 3 — Polish & Production Readiness

- [x] Polish UI with responsive layout and loading states
- [x] Implement streaming responses via SSE
- [x] Add query cost tracking (token usage, latency)
- [x] Build admin document management page
- [x] Add integration tests for full pipeline
- [x] Implement EvalForge evaluation hooks
- [x] Add structured logging with request tracing
- [x] Create deployment documentation
- [x] Add database migration strategy with Alembic
- [x] Performance testing and optimization
