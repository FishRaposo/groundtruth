# Architecture

## System Overview

GroundTruth is a three-tier system: a Next.js frontend, a FastAPI backend, and a PostgreSQL database with the pgvector extension for vector storage.

```mermaid
graph TB
    subgraph Frontend
        UI[Next.js App :3000]
    end

    subgraph Backend [FastAPI Backend :8000]
        API[API Router]
        IS[Ingestion Service]
        RS[Retrieval Service]
        GS[Generation Service]
        CS[Citation Service]
        RF[Refusal Service]
    end

    subgraph Data [Data Layer]
        DB[(PostgreSQL + pgvector)]
        FS[File Storage]
    end

    subgraph External [External Services]
        LLM[LLM API]
        EM[Embedding API]
    end

    UI -->|REST / JSON| API
    API --> IS
    API --> RS
    API --> GS
    IS -->|Parse → Chunk → Embed| DB
    IS -->|Store files| FS
    IS -->|Generate embeddings| EM
    RS -->|Hybrid Search| DB
    RS -->|Rerank| RS
    GS -->|Generate answer| LLM
    GS -->|Assemble citations| CS
    GS -->|Check refusal| RF
```

## Data Flow

```mermaid
flowchart LR
    Upload[Document Upload] --> Parse[Parsing]
    Parse --> Chunk[Chunking]
    Chunk --> Embed[Embedding]
    Embed --> Store[Vector Store]

    Query[User Question] --> Retrieve[Retrieval]
    Retrieve --> Rerank[Reranking]
    Rerank --> Refuse{Refusal Check}
    Refuse -->|Pass| Generate[Generation]
    Refuse -->|Fail| Refusal[Refusal Response]
    Generate --> Cite[Citation Assembly]
    Cite --> Response[Answer + Citations + Trace]
```

## Service Descriptions

| Service | Responsibility |
|---|---|
| **Ingestion** | Orchestrates document parsing, chunking, and embedding |
| **Parsing** | Extracts structured content from different file formats |
| **Chunking** | Splits documents into retrievable segments |
| **Embedding** | Converts text chunks into vector representations |
| **Retrieval** | Finds relevant chunks via hybrid search |
| **Reranking** | Re-scores retrieved chunks for relevance |
| **Generation** | Produces grounded answers from retrieved context |
| **Citation** | Assembles and validates source citations |
| **Refusal** | Determines whether sufficient evidence exists to answer |

## Technology Choices

| Choice | Technology | Rationale |
|---|---|---|
| Backend | FastAPI | Async support, automatic OpenAPI docs, Pydantic validation |
| Database | PostgreSQL + pgvector | Relational + vector in one system; mature, well-supported |
| Embeddings | OpenAI / sentence-transformers | Flexible: cloud or local; swap via config |
| LLM | OpenAI-compatible API | Broad model support via compatible endpoints |
| Frontend | Next.js + Tailwind | Fast SSR, component model, utility-first CSS |
| Migrations | Alembic | Standard for SQLAlchemy; version-controlled schema changes |
