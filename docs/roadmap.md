# Roadmap

The product roadmap lives in [../ROADMAP.md](../ROADMAP.md). This file tracks the
engineering follow-ups from the migration onto `shared_core`.

## Now
- ✅ Adopt `shared_core` for config/logging/errors/DB/Celery.
- ✅ Full-stack `apps/api` + `apps/web` layout; standard spine (Makefile, ruff, pyright,
  CI installing shared-core, offline demo); `groundtruth_*` metrics preserved.

## Next — domain-capability convergence
- ✅ **Bytes-based parsing adapter** onto `shared_core.docparse` (`parsers/shared_docparse.py`),
  additive alongside the file-path parsers — see [design-decisions.md](./design-decisions.md).
- ✅ **Lexical reranking pass** onto `shared_core.embeddings` (`services/reranking/lexical.py`),
  an offline reranker added beside the heuristic and cross-encoder rerankers.
- ✅ **Citation grounding evaluation** as a wrapper over `shared_core.evaljudge.CitationJudge`
  (`services/evaluation/citation_scoring.py`).
- ✅ **Per-workspace cost tracking** onto `shared_core.llmmetrics` (`services/cost_tracking.py`),
  exposed at `GET /api/metrics/cost`.
- ⏭️ Swap the ingestion file-path parsers + `services/chunking` *internals* onto
  `shared_core.docparse` (deferred: the bytes API differs and would change golden output).
- ⏭️ Route retrieval's `_cosine_similarity` through `shared_core.embeddings.cosine_similarity`
  (deferred: a ~1-ULP float difference could flip a sort tie — golden-gated, not adopted).
- ⏭️ Route OpenAI generation through `shared_core.llm.LLMClientFactory` (preserving SSE +
  offline simulation).

## Later
- Validate a swap onto `shared_core.database.Base` against the Alembic migrations.
- Solve shared-core Docker packaging (currently installed via git in the image).
- Add a `workspace` field to `QueryRequest` so cost tracking attributes per real tenant
  (currently records under the default workspace).

## Intentionally not building (now)
- Renaming `apps/api/app/` → `apps/api/src/` (a documented layout exception).
- Renaming `groundtruth_*` Prometheus metrics (dashboards depend on them).
