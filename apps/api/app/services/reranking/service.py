from app.models.chunk import ChunkWithScore
from app.utils.text import content_terms, query_terms


class RerankingService:
    """Re-scores retrieved chunks to improve relevance ordering.

    Takes the initial retrieval results and applies a secondary scoring
    pass to produce a more accurate ranking. The current implementation
    uses a simple heuristic; a production system would use a cross-encoder.
    """

    async def rerank(
        self,
        query: str,
        chunks: list[ChunkWithScore],
    ) -> list[ChunkWithScore]:
        """Rerank chunks based on query relevance.

        Re-scores each chunk by combining the original retrieval score
        with a heuristic query-term overlap score.

        Args:
            query: The user's question.
            chunks: Initially retrieved chunks with scores.

        Returns:
            Re-scored and re-sorted list of chunks.
        """
        if not chunks:
            return []

        terms = query_terms(query)

        reranked: list[tuple[float, ChunkWithScore]] = []
        for chunk in chunks:
            rerank_score = self._compute_rerank_score(terms, chunk)
            reranked.append((rerank_score, chunk))

        reranked.sort(key=lambda x: x[0], reverse=True)

        return [
            ChunkWithScore(
                id=chunk.id,
                document_id=chunk.document_id,
                content=chunk.content,
                chunk_index=chunk.chunk_index,
                metadata=chunk.metadata,
                relevance_score=score,
            )
            for score, chunk in reranked
        ]

    def _compute_rerank_score(
        self,
        query_terms: set[str],
        chunk: ChunkWithScore,
    ) -> float:
        """Compute a rerank score combining retrieval score with query overlap.

        Uses a weighted combination of the original retrieval score and
        the fraction of query terms that appear in the chunk content.

        Args:
            query_terms: Content-bearing terms from the user's query
                (see :func:`app.utils.text.query_terms`).
            chunk: The chunk to score.

        Returns:
            A float score combining retrieval and overlap signals.
        """
        overlap_count = len(query_terms & content_terms(chunk.content))
        overlap_ratio = overlap_count / max(len(query_terms), 1)

        base_score = chunk.relevance_score
        combined = 0.7 * base_score + 0.3 * overlap_ratio
        return combined


reranking_service = RerankingService()
