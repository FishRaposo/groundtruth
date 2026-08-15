# GroundTruth API

GroundTruth is a self-contained, offline-first production RAG API with hybrid
retrieval, citations, and deterministic refusal logic.

From the repository root, install the development environment with:

```bash
python -m pip install -e "apps/api[dev]"
```

The default install uses SQLite, deterministic hash embeddings, and lexical
fallbacks. PostgreSQL, Redis, model-backed embeddings, and extended document
parsers remain optional extras. See the repository-level `README.md` for the full
architecture, demonstration, and verification workflow.
