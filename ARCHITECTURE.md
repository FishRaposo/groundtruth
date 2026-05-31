# GroundTruth Architecture

## Overview

GroundTruth is a RAG-powered internal AI assistant with multi-tenancy, hybrid search, and real-time streaming.

## Components

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Next.js App   │────▶│  FastAPI API │────▶│  PostgreSQL+    │
│   (Frontend)    │     │  (Backend)    │     │  pgvector       │
└─────────────────┘     └──────────────┘     └─────────────────┘
        │                       │
        ▼                       ▼
┌─────────────────┐     ┌──────────────┐
│  SSE Stream     │     │  Document     │
│  /api/chat      │     │  Ingestion    │
└─────────────────┘     └──────────────┘
```

## Data Model

- **Workspace** — Tenant isolation unit
- **Membership** — User roles within a workspace
- **Document** — Indexed content with embedding vector
- **Conversation** — Chat thread
- **Message** — Individual chat message with citations

## Hybrid Search

Combines pgvector cosine similarity (30%) with PostgreSQL full-text search ts_rank (70%).

## Multi-Tenancy

Every query is scoped to `workspace_id`. Users can only access workspaces they are members of.
