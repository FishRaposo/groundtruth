import math
import uuid

from sqlalchemy import select, update

from app.db.session import AsyncSessionLocal
from app.models.chunk import Chunk


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class VectorStore:
    """Operations for managing embeddings in the database.

    Works with any SQLAlchemy backend (PostgreSQL, SQLite, etc.)
    since embeddings are stored as JSON arrays.
    """

    async def add_vectors(
        self,
        chunk_ids: list[uuid.UUID],
        embeddings: list[list[float]],
    ) -> None:
        """Insert embedding vectors for the given chunk IDs."""
        async with AsyncSessionLocal() as session:
            for chunk_id, embedding in zip(chunk_ids, embeddings):
                await session.execute(
                    update(Chunk)
                    .where(Chunk.id == chunk_id)
                    .values(embedding=embedding)
                )
            await session.commit()

    async def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int,
        threshold: float,
    ) -> list[tuple[uuid.UUID, float]]:
        """Find chunks most similar to the query embedding using cosine similarity."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Chunk.id, Chunk.embedding).where(Chunk.embedding.isnot(None))
            )
            rows = result.all()

        scored: list[tuple[uuid.UUID, float]] = []
        for row in rows:
            chunk_embedding = row.embedding
            if chunk_embedding is None:
                continue
            similarity = _cosine_similarity(query_embedding, chunk_embedding)
            if similarity >= threshold:
                scored.append((row.id, similarity))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def delete_vectors(self, chunk_ids: list[uuid.UUID]) -> None:
        """Remove embedding vectors for the given chunk IDs by setting to NULL."""
        async with AsyncSessionLocal() as session:
            for chunk_id in chunk_ids:
                await session.execute(
                    update(Chunk)
                    .where(Chunk.id == chunk_id)
                    .values(embedding=None)
                )
            await session.commit()


vector_store = VectorStore()
