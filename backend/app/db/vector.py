import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal


class VectorStore:
    """Operations for managing pgvector embeddings in the database."""

    async def add_vectors(
        self,
        chunk_ids: list[uuid.UUID],
        embeddings: list[list[float]],
    ) -> None:
        """Insert embedding vectors for the given chunk IDs."""
        async with AsyncSessionLocal() as session:
            for chunk_id, embedding in zip(chunk_ids, embeddings):
                embedding_str = "[" + ",".join(str(v) for v in embedding) + "]"
                await session.execute(
                    text(
                        "UPDATE chunks SET embedding = :embedding "
                        "WHERE id = :chunk_id"
                    ),
                    {"embedding": embedding_str, "chunk_id": chunk_id},
                )
            await session.commit()

    async def similarity_search(
        self,
        query_embedding: list[float],
        top_k: int,
        threshold: float,
    ) -> list[tuple[uuid.UUID, float]]:
        """Find chunks most similar to the query embedding using cosine distance."""
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    """
                    SELECT id, 1 - (embedding <=> :query::vector) AS similarity
                    FROM chunks
                    WHERE embedding IS NOT NULL
                      AND 1 - (embedding <=> :query::vector) >= :threshold
                    ORDER BY embedding <=> :query::vector
                    LIMIT :top_k
                    """
                ),
                {
                    "query": embedding_str,
                    "threshold": threshold,
                    "top_k": top_k,
                },
            )
            return [(row.id, row.similarity) for row in result.fetchall()]

    async def delete_vectors(self, chunk_ids: list[uuid.UUID]) -> None:
        """Remove embedding vectors for the given chunk IDs by setting to NULL."""
        async with AsyncSessionLocal() as session:
            for chunk_id in chunk_ids:
                await session.execute(
                    text("UPDATE chunks SET embedding = NULL WHERE id = :chunk_id"),
                    {"chunk_id": chunk_id},
                )
            await session.commit()


vector_store = VectorStore()
