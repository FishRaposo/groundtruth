# Design Decisions

This file records the decisions made when GroundTruth was migrated onto the
`shared_core` standard. Domain/architecture docs: [ARCHITECTURE.md](./ARCHITECTURE.md),
[RETRIEVAL_FLOW.md](./RETRIEVAL_FLOW.md), [INGESTION_FLOW.md](./INGESTION_FLOW.md).

## Decision: adopt `shared_core` for infrastructure

- **Context:** GroundTruth shipped its own `config`, `logging` (structlog), `db/session`,
  Celery, and request-logging middleware — duplicating the workspace's `shared_core`.
- **Choice:** route config/logging/errors/DB/Celery through `shared_core`
  (`BaseAppConfig`, `setup_logging`, `application_error_handler`, `AsyncDatabaseManager`,
  `create_celery_app`). Keep all RAG domain code.
- **Tradeoff:** the app-level logger becomes loguru while domain modules keep their
  `structlog.get_logger()` calls (both emit); one source of truth for infrastructure.

## Decision: keep GroundTruth's `DeclarativeBase`

- The models and Alembic migrations are authored against GroundTruth's own
  `DeclarativeBase`. We adopt `AsyncDatabaseManager` for the **engine/session** but keep
  the local `Base`, avoiding a metadata/registry swap that would risk the migrations.

## Decision: do not rename the `groundtruth_*` metrics

- Prometheus metrics + Grafana dashboards depend on the `groundtruth_*` names.
  `core/metrics.py` stays as the domain metrics registry; `shared_core.metrics` is not
  forced in (it would rename HTTP metrics). 

## Decision: `OPENAI_API_KEY` stays a plain `str`

- `BaseAppConfig` declares it as `Optional[SecretStr]`, but GroundTruth's embedding and
  generation services use it via truthiness checks and `AsyncOpenAI(api_key=...)`. The
  subclass overrides the field back to `str = ""` so those call sites are unchanged.

## Decision: `apps/api/app/` (layout)

- Full-stack layout is `apps/api` + `apps/web` (the PKB precedent). The backend package
  stays `app/` (not `src/`) to avoid a ~100-file import rewrite; documented in AGENTS.md.

## Decision: converge capabilities *additively*, golden-gate numeric output

When adopting `shared_core` domain primitives, the rule was **add capability beside
working internals; never silently change a number**. Each adopted item is golden-pinned
by a test before/while it lands:

- **Cost tracking** (`cost_tracking.py` → `llmmetrics`): new module, new endpoint, no
  existing output touched. Tests pin token/cost aggregation.
- **Lexical reranker** (`reranking/lexical.py` → `embeddings`): a *new* reranker added
  next to the heuristic + cross-encoder ones. The query pipeline still calls the original
  `reranking_service`, so no scores changed. Tests pin the blend formula.
- **Citation evaluation** (`evaluation/citation_scoring.py` → `evaljudge.CitationJudge`):
  a new evaluation surface; the in-pipeline `CitationService.assemble_citations` is
  unchanged. Tests pin pass/fail and dangling-marker detection.
- **Bytes parser adapter** (`shared_docparse.py` → `docparse`): a *complementary* parse
  path for in-memory bytes; the file-path parsers still drive ingestion. Tests pin the
  mapped `ParsedDocument` shape and sections.

## Decision: do NOT swap retrieval's `cosine_similarity` (golden-gated, skipped)

- `shared_core.embeddings.cosine_similarity` (numpy-accelerated) and the in-house
  `_cosine_similarity` in `retrieval/service.py` differ by ~1 ULP (e.g. `0.9333333333333331`
  vs `…332`) due to summation order. That FP noise could, in principle, flip a tie in the
  retrieval sort and change which chunk ranks first.
- Per do-no-harm, the swap was **skipped** and recorded as a follow-up. The shared-core
  cosine is instead used only where there is no pre-existing golden value to preserve.

## Decision: do NOT replace the ingestion file parsers with `docparse`

- `shared_core.docparse` parsers take `bytes` and return a different `ParsedDocument`
  (no `sections`, `text` instead of `content`, different metadata). Swapping them into the
  file-path ingestion flow would change parser output and break the parser/ingestion golden
  tests. Instead a **bytes adapter** was added (`parsers/shared_docparse.py`) that maps
  shared-core output back into GroundTruth's shape, leaving the working parsers intact.
