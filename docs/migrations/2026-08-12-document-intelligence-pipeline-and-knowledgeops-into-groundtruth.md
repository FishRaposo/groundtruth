# Document intelligence and KnowledgeOps consolidation into GroundTruth

Date: 2026-08-12
Target: GroundTruth (`portfolio/consolidation/groundtruth`)

## Source provenance and license status

| Source | Reviewed revision | License | Use in GroundTruth |
|---|---|---|---|
| [`FishRaposo/document-intelligence-pipeline`](https://github.com/FishRaposo/document-intelligence-pipeline) | `6c85a76be3f564983b50248b5f99f1658875931f` | MIT, copyright 2026 Operator Systems | Selected ingestion algorithms were adapted into GroundTruth-native modules. |
| [`FishRaposo/knowledgeops`](https://github.com/FishRaposo/knowledgeops) | `60cb3848373304f99f5b5c11bd2676ecbb62521d` | MIT, copyright 2025 KnowledgeOps | Architecture and deployment material was reviewed as documentation only; no service or source-code copy was made. |

Both reviewed sources carry permissive MIT licenses. This record preserves the
source names, exact revisions, and copyright holders for adapted material.

## Selected path mapping

| Source path or concept | GroundTruth destination | Decision |
|---|---|---|
| `src/doc_pipeline/parsers.py` plain-text support | `apps/api/app/parsers/text.py`, parser registry, upload type map | Added `.txt` beside GroundTruth's existing PDF, Markdown, HTML, and DOCX parsers. Existing parsers remain authoritative. |
| `src/doc_pipeline/cleaners.py` and `dedup.py` | `apps/api/app/services/document_intelligence.py`; `IngestionService` | Adapted normalized SHA-256 document hashes and stable first-seen chunk deduplication. |
| `src/doc_pipeline/chunkers.py` semantic default | Existing `apps/api/app/services/chunking.py`; `IngestionService` | Reused GroundTruth's tested semantic chunker and deduplicated its output before embedding. No second chunking service was added. |
| `src/doc_pipeline/entities.py` | `apps/api/app/services/document_intelligence.py`; document metadata | Adapted dependency-free email, URL, phone, and capitalised-name extraction. |
| `src/doc_pipeline/pipeline.py` quarantine flow | Existing document `error` lifecycle and `IngestionService.reindex_document` | Failed documents remain the durable quarantine record: metadata records reason, failing stage, retained source path, and reprocessing operation. No parallel persistence service was added. |
| KnowledgeOps hybrid retrieval topology | This document and existing GroundTruth architecture docs | Documented as confirmation of GroundTruth's existing vector + keyword fusion, reranking, confidence/refusal, citation, and trace boundaries. |
| KnowledgeOps deployment topology | This document and existing GroundTruth deployment docs | Retained only the useful operational lesson: independently scale stateless API/web processes and ingestion workers while sharing PostgreSQL/pgvector and Redis. |

## Resulting ingestion boundary

```text
upload -> parse -> normalize/hash -> document dedup -> entity extraction
       -> semantic chunk -> chunk dedup -> embed -> store -> ready
                                      failure -> error/quarantine -> reindex
```

An identical normalized document is recorded as ready with `duplicate_of`
metadata and zero new chunks; it is not embedded again. Failed files remain at
their UUID-derived upload path, and the existing reindex operation is the only
reprocessing entry point.

## KnowledgeOps topology retained as guidance

KnowledgeOps separates gateway, auth, ingestion, retrieval, LLM, evaluation,
tracing, and web concerns across services. GroundTruth already implements the
useful hybrid retrieval sequence inside its established application boundary:
query embedding, pgvector search, keyword search, rank fusion, reranking,
confidence/refusal, citation assembly, grounded generation, and retrieval
tracing. Its deployment can scale API/web processes and ingestion workers
independently against PostgreSQL/pgvector and Redis without copying the eight
KnowledgeOps application services.

## Explicitly excluded material

- KnowledgeOps service directories, API gateway, auth service, LLM gateway,
  eval service, trace service, web app, shared DTO package, Nginx configuration,
  Terraform, Kubernetes, and Docker Compose topology.
- Document Intelligence's FastAPI app, frontend, worker, storage abstraction,
  vector store, embedding generator, exporters, metadata model, SQLAlchemy
  models/migration, and standalone quarantine table/API.
- Any rewrite of GroundTruth retrieval, refusal thresholds, citation assembly,
  answer generation, frontend/UI, public API schemas, or deployment services.
- Any new runtime dependency or external entity-recognition model.

These exclusions prevent duplicate services and preserve GroundTruth's tested
answer-safety and presentation boundaries.

## Archive gate

The source repositories are **not authorized for archive by this migration
alone**. The gate opens only after the portfolio consolidation owner records:

1. This target commit is merged and final GroundTruth verification passes in a
   dependency-complete environment.
2. Repository inventory and cross-project links point to GroundTruth and this
   provenance record.
3. Each source's exact revision, license, and any dirty working-tree state are
   backed up and independently recoverable.
4. A final exclusion review confirms no required unique behavior remains only
   in a source repository.
5. Archive is performed as a separate, explicit remote action.

Until every condition is met, the archive gate is closed.
