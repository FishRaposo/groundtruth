# GroundTruth FAQ

## Q: Why hybrid search instead of pure vector?
**A:** Keyword matching handles exact terminology, acronyms, and rare terms that embeddings can miss. The 70/30 weight balances precision with semantic understanding.

## Q: How do I add a new document source?
**A:** Use the `/api/documents/ingest` endpoint or configure a webhook in DocFlow.

## Q: Can I use a different vector database?
**A:** Yes. The `hybridSearch` function in `src/lib/db.ts` can be adapted for Pinecone, Weaviate, or Qdrant. Keep the PostgreSQL full-text component for the keyword half.
