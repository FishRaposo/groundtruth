import math
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.chunk import Chunk
from app.models.chunk import ChunkWithScore
from app.services.embedding import embedding_service

settings = get_settings()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class RetrievalService:
    """Finds relevant document chunks using hybrid search strategies.

    Combines vector similarity search with keyword search using
    Reciprocal Rank Fusion to merge results from both methods.
    """

    def __init__(self) -> None:
        self._vector_count: int = 0
        self._keyword_count: int = 0

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict[str, str] | None = None,
        db: AsyncSession | None = None,
    ) -> list[ChunkWithScore]:
        """Retrieve relevant chunks for a query using hybrid search.

        Runs both vector similarity and keyword search, fuses the results
        using Reciprocal Rank Fusion, and returns the top-K chunks.

        Args:
            query: The user's question.
            top_k: Number of results to return. Defaults to config value.
            filters: Optional metadata filters to apply.
            db: Optional database session.

        Returns:
            List of chunks with relevance scores, sorted by score descending.
        """
        top_k = top_k or settings.RETRIEVAL_TOP_K
        return await self.hybrid_search(query, top_k)

    async def hybrid_search(
        self,
        query: str,
        top_k: int,
    ) -> list[ChunkWithScore]:
        """Run hybrid search combining vector and keyword results.

        Uses Reciprocal Rank Fusion (RRF) with k=60 to merge
        results from both search methods into a single ranked list.

        Args:
            query: The user's question.
            top_k: Number of results to return.

        Returns:
            Fused and sorted list of chunks with combined scores.
        """
        query_embedding = await embedding_service.embed_query(query)

        vector_results = await self.similarity_search(query_embedding, top_k * 2)
        keyword_results = await self.keyword_search(query, top_k * 2)

        self._vector_count = len(vector_results)
        self._keyword_count = len(keyword_results)

        rrf_k = 60
        score_map: dict[str, float] = {}

        for rank, (chunk_id, _score) in enumerate(vector_results):
            score_map[str(chunk_id)] = score_map.get(str(chunk_id), 0.0) + 1.0 / (rrf_k + rank + 1)

        for rank, (chunk_id, _score) in enumerate(keyword_results):
            score_map[str(chunk_id)] = score_map.get(str(chunk_id), 0.0) + 1.0 / (rrf_k + rank + 1)

        sorted_ids = sorted(score_map.keys(), key=lambda x: score_map[x], reverse=True)[:top_k]

        if not sorted_ids:
            return []

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Chunk).where(Chunk.id.in_([uuid.UUID(cid) for cid in sorted_ids]))
            )
            chunks_by_id = {str(chunk.id): chunk for chunk in result.scalars().all()}

        return [
            ChunkWithScore(
                id=chunks_by_id[cid].id,
                document_id=chunks_by_id[cid].document_id,
                content=chunks_by_id[cid].content,
                chunk_index=chunks_by_id[cid].chunk_index,
                metadata=chunks_by_id[cid].metadata_,
                relevance_score=score_map[cid],
            )
            for cid in sorted_ids
            if cid in chunks_by_id
        ]

    async def similarity_search(
        self,
        embedding: list[float],
        top_k: int,
    ) -> list[tuple[str, float]]:
        """Find chunks by cosine similarity to the query embedding.

        Args:
            embedding: The query embedding vector.
            top_k: Maximum number of results to return.

        Returns:
            List of (chunk_id, similarity_score) tuples sorted by similarity.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Chunk.id, Chunk.embedding).where(Chunk.embedding.isnot(None))
            )
            rows = result.all()

        scored: list[tuple[str, float]] = []
        for row in rows:
            chunk_id = str(row.id)
            chunk_embedding = row.embedding
            if chunk_embedding is None:
                continue
            similarity = _cosine_similarity(embedding, chunk_embedding)
            scored.append((chunk_id, similarity))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    async def keyword_search(
        self,
        query: str,
        top_k: int,
    ) -> list[tuple[str, float]]:
        """Find chunks using keyword search.

        Uses simple term overlap scoring for portability.

        Args:
            query: The search query string.
            top_k: Maximum number of results to return.

        Returns:
            List of (chunk_id, relevance_score) tuples.
        """
        query_terms = set(query.lower().split())
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Chunk.id, Chunk.content))
            rows = result.all()

        scored: list[tuple[str, float]] = []
        for row in rows:
            content_lower = row.content.lower()
            overlap = sum(1 for term in query_terms if term in content_lower)
            if overlap:
                score = overlap / max(len(query_terms), 1)
                scored.append((str(row.id), score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    @property
    def last_vector_count(self) -> int:
        return self._vector_count

    @property
    def last_keyword_count(self) -> int:
        return self._keyword_count


retrieval_service = RetrievalService()
