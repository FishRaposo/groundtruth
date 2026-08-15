"""Offline lexical reranking pass built on the internal vendor embeddings module.

A dependency-free reranker that re-scores retrieved chunks against the query
using the shared-core text-similarity primitives (TF-IDF cosine and Jaccard).
Unlike :class:`~app.services.reranking.colbert.ColBERTReranker` and
``CrossEncoderReranker`` it needs no model download, so it is the default
reranking pass in offline / demo mode.

The score blends the chunk's existing retrieval score with a lexical relevance
signal, keeping the original score meaningful while sharpening the ordering.
"""

from __future__ import annotations

from app.internal.vendor_core.embeddings import jaccard_similarity, tfidf_cosine
from app.models.chunk import ChunkWithScore


class LexicalReranker:
    """Re-rank chunks by blending retrieval score with shared-core lexical sim.

    Args:
        base_weight: Weight on the chunk's existing ``relevance_score``.
        lexical_weight: Weight on the query/chunk lexical similarity signal.

    The two weights are normalized so they always sum to 1.0, so callers can
    pass any non-negative pair.
    """

    def __init__(self, base_weight: float = 0.6, lexical_weight: float = 0.4) -> None:
        total = base_weight + lexical_weight
        if total <= 0:
            base_weight, lexical_weight, total = 0.6, 0.4, 1.0
        self.base_weight = base_weight / total
        self.lexical_weight = lexical_weight / total

    def lexical_score(self, query: str, content: str) -> float:
        """Return the lexical relevance of ``content`` to ``query`` in [0, 1].

        Uses the max of TF-IDF cosine and Jaccard similarity so that either a
        strong term-frequency match or a strong set-overlap match scores well.
        """
        return max(
            tfidf_cosine(query, content),
            jaccard_similarity(query, content),
        )

    async def rerank(
        self,
        query: str,
        chunks: list[ChunkWithScore],
    ) -> list[ChunkWithScore]:
        """Re-score and re-sort ``chunks`` for ``query``.

        Returns a new list of :class:`ChunkWithScore` with updated
        ``relevance_score`` values, sorted descending. Ties preserve the
        original input order (stable sort), so reranking never reorders
        equally-scored chunks arbitrarily.
        """
        if not chunks:
            return []

        scored: list[tuple[float, ChunkWithScore]] = []
        for chunk in chunks:
            lex = self.lexical_score(query, chunk.content)
            combined = (
                self.base_weight * chunk.relevance_score + self.lexical_weight * lex
            )
            scored.append((combined, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)

        return [
            ChunkWithScore(
                id=chunk.id,
                document_id=chunk.document_id,
                content=chunk.content,
                chunk_index=chunk.chunk_index,
                metadata=chunk.metadata,
                relevance_score=score,
            )
            for score, chunk in scored
        ]


lexical_reranker = LexicalReranker()
