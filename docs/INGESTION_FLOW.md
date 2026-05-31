# Ingestion Flow

## Pipeline Overview

Documents move through a well-defined state machine during ingestion.

```mermaid
sequenceDiagram
    participant User
    participant API
    participant Ingestion
    participant Parser
    participant Chunker
    participant Embedder
    participant DB

    User->>API: POST /api/documents/upload
    API->>DB: Create document (status: pending)
    API-->>User: 202 Accepted with document ID
    API->>Ingestion: Process document async

    Ingestion->>DB: Update status → processing
    Ingestion->>Parser: Parse file
    Parser-->>Ingestion: Parsed content + metadata

    Ingestion->>Chunker: Split into chunks
    Chunker-->>Ingestion: List of text chunks

    Ingestion->>Embedder: Generate embeddings
    Embedder-->>Ingestion: List of vectors

    Ingestion->>DB: Store chunks + embeddings
    Ingestion->>DB: Update status → ready

    Note over User,DB: Document is now searchable
```

## Document States

| Status | Description |
|---|---|
| `pending` | Document uploaded, awaiting processing |
| `processing` | Currently being parsed, chunked, and embedded |
| `ready` | Fully processed and available for retrieval |
| `error` | Processing failed; error details in metadata |

## Metadata Schema

Each document stores the following metadata:

```json
{
  "title": "Company Handbook",
  "source_type": "pdf",
  "source_url": null,
  "content_hash": "sha256:abc123...",
  "file_size_bytes": 1048576,
  "page_count": 42,
  "chunk_count": 87,
  "processing_time_ms": 3200,
  "error": null,
  "custom": {}
}
```

## Chunking Configuration

| Parameter | Default | Description |
|---|---|---|
| `CHUNK_SIZE` | 512 | Target tokens per chunk |
| `CHUNK_OVERLAP` | 64 | Overlap tokens between adjacent chunks |
| `chunking_strategy` | `fixed` | Strategy: `fixed`, `semantic`, or `structural` |

## Embedding Configuration

| Parameter | Default | Description |
|---|---|---|
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Model identifier |
| `EMBEDDING_DIMENSIONS` | 1536 | Vector dimensions |
| `batch_size` | 100 | Texts per embedding API call |
