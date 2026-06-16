from app.models.chunk import ChunkWithScore


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

        query_terms = set(query.lower().split())

        reranked: list[tuple[float, ChunkWithScore]] = []
        for chunk in chunks:
            rerank_score = self._compute_rerank_score(query_terms, chunk)
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
            query_terms: Set of lowercase terms from the user's query.
            chunk: The chunk to score.

        Returns:
            A float score combining retrieval and overlap signals.
        """
        content_lower = chunk.content.lower()
        overlap_count = sum(1 for term in query_terms if term in content_lower)
        overlap_ratio = overlap_count / max(len(query_terms), 1)

        base_score = chunk.relevance_score
        combined = 0.7 * base_score + 0.3 * overlap_ratio
        return combined


reranking_service = RerankingService()
