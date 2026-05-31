# Entry Points

## Frontend
- **Dev server:** `cd frontend && npm run dev` → http://localhost:3000
- **API routes:** `src/app/api/chat/route.ts` — SSE streaming endpoint

## Backend
- **Dev server:** `cd backend && uvicorn main:app --reload --port 8001`
- **API docs:** http://localhost:8001/docs

## Database
- **Connection:** PostgreSQL 15+ with pgvector
- **Key tables:** workspaces, memberships, documents, conversations, messages
