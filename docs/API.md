# API Documentation

Base URL: `http://localhost:8000`

## Health Check

### `GET /api/health`

Returns service health status.

**Response:**

```json
{
  "status": "healthy",
  "database": "connected",
  "document_count": 42,
  "version": "0.1.0"
}
```

**Example:**

```bash
curl http://localhost:8000/api/health
```

---

## Documents

### `POST /api/documents/upload`

Upload one or more documents for processing.

**Request:** `multipart/form-data`

| Field | Type | Required | Description |
|---|---|---|---|
| `files` | `file[]` | Yes | Document files (PDF, MD, HTML, DOCX) |
| `metadata` | `string` (JSON) | No | Additional metadata to attach |

**Response:** `202 Accepted`

```json
{
  "documents": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "company_handbook.pdf",
      "source_type": "pdf",
      "status": "pending",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/api/documents/upload \
  -F "files=@company_handbook.pdf" \
  -F "files=@product_docs.md"
```

---

### `GET /api/documents`

List all documents.

**Query Parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `status` | `string` | — | Filter by status (pending, processing, ready, error) |
| `limit` | `int` | 50 | Results per page |
| `offset` | `int` | 0 | Pagination offset |

**Response:** `200 OK`

```json
{
  "documents": [
    {
      "id": "...",
      "title": "company_handbook.pdf",
      "source_type": "pdf",
      "status": "ready",
      "chunk_count": 87,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:05Z"
    }
  ],
  "total": 42,
  "limit": 50,
  "offset": 0
}
```

**Example:**

```bash
curl http://localhost:8000/api/documents?status=ready&limit=10
```

---

### `GET /api/documents/{document_id}`

Get details for a specific document.

**Response:** `200 OK`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "company_handbook.pdf",
  "source_type": "pdf",
  "source_url": null,
  "status": "ready",
  "metadata": {
    "page_count": 42,
    "chunk_count": 87,
    "file_size_bytes": 1048576
  },
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T10:30:05Z"
}
```

**Example:**

```bash
curl http://localhost:8000/api/documents/550e8400-e29b-41d4-a716-446655440000
```

---

### `DELETE /api/documents/{document_id}`

Delete a document and all its chunks/embeddings.

**Response:** `204 No Content`

**Example:**

```bash
curl -X DELETE http://localhost:8000/api/documents/550e8400-e29b-41d4-a716-446655440000
```

---

### `POST /api/documents/{document_id}/reindex`

Re-process and re-embed a document.

**Response:** `202 Accepted`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "Re-indexing started"
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/api/documents/550e8400-e29b-41d4-a716-446655440000/reindex
```

---

## Queries

### `POST /api/queries`

Ask a question and receive a grounded answer with citations.

**Request Body:**

```json
{
  "question": "What is the company's remote work policy?",
  "top_k": 5
}
```

**Response:** `200 OK`

```json
{
  "id": "660e8400-e29b-41d4-a716-446655440001",
  "question": "What is the company's remote work policy?",
  "answer": "According to the Company Handbook, employees may work remotely up to 3 days per week with manager approval [1]. Remote work arrangements must be documented in the HR system [2].",
  "sources": [
    {
      "chunk_id": "...",
      "document_id": "...",
      "document_title": "Company Handbook",
      "content_preview": "Employees may work remotely up to 3 days per week...",
      "relevance_score": 0.94,
      "citation_index": 1
    }
  ],
  "retrieval_trace": {
    "vector_results": 8,
    "keyword_results": 5,
    "reranked_results": 5,
    "confidence": 0.87,
    "latency_ms": 340
  },
  "refused": false,
  "confidence": 0.87,
  "token_usage": {
    "prompt_tokens": 1200,
    "completion_tokens": 150,
    "total_tokens": 1350
  },
  "created_at": "2024-01-15T10:35:00Z"
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/api/queries \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the remote work policy?"}'
```

---

### `GET /api/queries`

List query history.

**Query Parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `limit` | `int` | 20 | Results per page |
| `offset` | `int` | 0 | Pagination offset |

**Response:** `200 OK`

```json
{
  "queries": [
    {
      "id": "...",
      "question": "What is the remote work policy?",
      "refused": false,
      "confidence": 0.87,
      "created_at": "2024-01-15T10:35:00Z"
    }
  ],
  "total": 15
}
```

---

### `GET /api/queries/{query_id}`

Get full query details including retrieval trace.

**Response:** `200 OK` — Returns full `QueryResponse` with all sources and trace.

**Example:**

```bash
curl http://localhost:8000/api/queries/660e8400-e29b-41d4-a716-446655440001
```
