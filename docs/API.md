# API

Base URL: `http://localhost:8000`. Interactive OpenAPI documentation is available at
`/docs`; it is the field-level authority for request and response schemas.

## Health and metrics

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Basic service health |
| GET | `/api/health/live` | Liveness |
| GET | `/api/health/ready` | Database, pgvector, and embedding readiness |
| GET | `/metrics` | Prometheus exposition |
| GET | `/api/metrics/cost` | Read-only workspace cost/latency summary |

## Documents

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/documents/upload` | Upload one or more supported files |
| GET | `/api/documents` | List documents with status/pagination filters |
| GET | `/api/documents/{document_id}` | Get one document |
| DELETE | `/api/documents/{document_id}` | Delete document and chunks |
| POST | `/api/documents/{document_id}/reindex` | Re-run the canonical ingestion path |
| POST | `/api/v1/documents/{document_id}/ocr` | Optional OCR (`503` when unavailable) |
| POST | `/api/v1/documents/{document_id}/detect-template` | Optional OCR-backed template extraction |
| GET | `/api/v1/documents/templates` | List registered templates |
| GET | `/api/v1/documents/{document_id}/versions` | List immutable snapshots |
| GET | `/api/v1/documents/{document_id}/versions/diff` | Diff two visible versions |
| POST | `/api/v1/documents/{document_id}/versions/{version}/restore` | Restore as a new version |

Accepted upload extensions are TXT, PDF, MD/Markdown, HTML/HTM, DOCX, CSV, TSV,
XLSX, and PPTX. Office and OCR processing require their extras; filenames are not
used as storage paths.

## Queries

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/queries` | Grounded answer/refusal with citations and trace |
| POST | `/api/queries/stream` | Same behavior over the stable SSE vocabulary |
| GET | `/api/queries` | Paginated query history |
| GET | `/api/queries/{query_id}` | Full stored query result |

Minimal request:

```json
{"question": "What is the remote work policy?", "top_k": 5}
```

Conversation memory is additive and disabled by default:

```json
{
  "question": "What changed?",
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "memory_policy": "recent",
  "memory_max_tokens": 1000
}
```

`memory_max_tokens` accepts 1–8000. Omitting `conversation_id`, or leaving
`memory_policy` disabled, preserves the legacy request behavior. Query responses keep
the established answer, `sources`, `retrieval_trace`, `refused`, confidence, usage,
and timestamp fields.

## Workflows and admin

| Method | Path | Purpose |
|---|---|---|
| POST/GET | `/api/v1/workflows/definitions` | Create/list visible definitions |
| POST | `/api/v1/workflows/instances` | Start a workflow |
| GET | `/api/v1/workflows/instances/{id}` | Read a visible instance |
| POST | `/api/v1/workflows/{id}/approve` | Approve or reject the active step |
| POST | `/api/v1/workflows/instances/{id}/cancel` | Cancel a visible instance |
| GET | `/api/v1/workflows/documents/{document_id}/history` | Document workflow history |
| GET | `/api/v1/workflows/instances/{id}/events` | Ordered local SSE status events |
| GET | `/api/v1/admin/usage` | Read-only usage evidence |
| GET | `/api/v1/admin/audit` | Read-only audit evidence |

Workflow access is application-scoped by workspace and owner/organization/system
visibility. These endpoints are not a hosted team or SSO control plane.

## API keys

Administrative endpoints under `/api/keys` create, list, inspect, update, and delete
API keys. Plaintext key material is returned only at creation; rate-limit identity is
derived from a hash rather than logging the secret.
