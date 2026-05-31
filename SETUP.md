# GroundTruth Setup Guide

## Prerequisites

- Node.js 18+
- Python 3.11+
- PostgreSQL 15+ with pgvector extension
- Redis 7+

## Database Setup

```bash
# Start PostgreSQL with pgvector
docker run -d \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# Verify extension
psql -U postgres -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

## Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

## Environment

Copy `.env.example` to `.env` and fill in your values.

## Verify

- Frontend: http://localhost:3000
- Backend API: http://localhost:8001/docs
- Chat SSE: http://localhost:3000/api/chat
