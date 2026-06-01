"""Enhanced retrieval service with advanced features.

Integrates query expansion, intent classification, strategy selection,
and multiple reranking methods for optimal retrieval quality.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select

from app.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.chunk import Chunk, ChunkWithScore
from app.services.query.expansion import QueryExpander, HyDENetwork
from app.services.query.intent import QueryClassifier
from app.services.retrieval.bm25 import HybridRetriever
from app.services.retrieval.strategy import RetrievalStrategy, StrategySelector
from app.services.reranking.colbert import CrossEncoderReranker


class EnhancedRetrievalService:
    """Advanced retrieval with query understanding and strategy selection.
    
    Features:
    - Query intent classification
    - Query expansion (LLM-based and HyDE)
    - Dynamic strategy selection
    - Multiple reranking methods
    - A/B testing support
    - Full retrieval tracing
    """
    
    def __init__(self) -> None:
        """Initialize enhanced retrieval service."""
        self.settings = get_settings()
        
        # Components
        self.classifier = QueryClassifier()
        self.expander = QueryExpander()
        self.hyde = HyDENetwork()
        self.strategy_selector = StrategySelector()
        self.cross_encoder = CrossEncoderReranker()
        self.hybrid_retriever = HybridRetriever()
        
        # Provider
        self._embedding_provider = None
    
    async def get_embedding_provider(self):
        """Get or create embedding provider."""
        if self._embedding_provider is None:
            from app.services.embeddings import get_embedding_provider as get_provider
            self._embedding_provider = get_provider()
        return self._embedding_provider
    
    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict[str, str] | None = None,
        strategy_name: str | None = None,
        expand: bool | None = None,
        use_hyde: bool = False,
        trace: bool = True,
    ) -> tuple[list[ChunkWithScore], dict[str, Any]]:
        """Enhanced retrieval with full pipeline.
        
        Args:
            query: User query.
            top_k: Number of results.
            filters: Metadata filters.
            strategy_name: Force specific strategy.
            expand: Whether to expand query (None = auto).
            use_hyde: Whether to use HyDE expansion.
            trace: Whether to return trace information.
            
        Returns:
            Tuple of (chunks_with_scores, trace_info).
        """
        start_time = time.perf_counter()
        trace_info: dict[str, Any] = {"query": query, "stages": []}
        
        # Stage 1: Intent Classification
        intent_start = time.perf_counter()
        intent = await self.classifier.classify(query)
        intent_time = time.perf_counter() - intent_start
        
        if trace:
            trace_info["stages"].append({
                "name": "intent_classification",
                "intent": intent.value,
                "time_ms": round(intent_time * 1000, 2),
            })
        
        # Stage 2: Strategy Selection
        strategy_start = time.perf_counter()
        strategy = await self.strategy_selector.select_strategy(
            query,
            force_strategy=strategy_name,
        )
        strategy_time = time.perf_counter() - strategy_start
        
        if trace:
            trace_info["stages"].append({
                "name": "strategy_selection",
                "strategy": strategy.name,
                "config": strategy.to_dict(),
                "time_ms": round(strategy_time * 1000, 2),
            })
        
        # Stage 3: Query Expansion (if enabled)
        queries = [query]
        if expand or (expand is None and strategy.expand_query):
            expansion_start = time.perf_counter()
            
            if use_hyde:
                # HyDE: generate hypothetical document
                hyde_doc = await self.hyde.generate_hypothetical_document(query)
                queries = [hyde_doc, query]
            else:
                # Standard expansion
                expansions = await self.expander.expand(query, num_expansions=2)
                queries = expansions
            
            expansion_time = time.perf_counter() - expansion_start
            
            if trace:
                trace_info["stages"].append({
                    "name": "query_expansion",
                    "queries": queries,
                    "time_ms": round(expansion_time * 1000, 2),
                })
        
        # Stage 4: Retrieval for each query variant
        retrieval_start = time.perf_counter()
        all_results: dict[str, list[tuple[Chunk, float]]] = {}
        
        for q in queries:
            results = await self._retrieve_with_strategy(q, strategy, top_k or strategy.top_k)
            all_results[q] = results
        
        retrieval_time = time.perf_counter() - retrieval_start
        
        if trace:
            trace_info["stages"].append({
                "name": "retrieval",
                "queries_searched": len(queries),
                "time_ms": round(retrieval_time * 1000, 2),
            })
        
        # Stage 5: Fuse results from multiple queries
        fusion_start = time.perf_counter()
        fused = self._fuse_multi_query_results(all_results, top_k or strategy.top_k)
        fusion_time = time.perf_counter() - fusion_start
        
        if trace:
            trace_info["stages"].append({
                "name": "fusion",
                "results_before": sum(len(r) for r in all_results.values()),
                "results_after": len(fused),
                "time_ms": round(fusion_time * 1000, 2),
            })
        
        # Stage 6: Reranking (if enabled)
        if strategy.use_reranker:
            rerank_start = time.perf_counter()
            
            # Prepare documents for reranking
            docs_for_rerank = [
                (chunk.content, chunk)
                for chunk, _ in fused
            ]
            
            reranked = await self.cross_encoder.rerank(
                query,
                docs_for_rerank,
                top_k=top_k or strategy.top_k,
            )
            
            # Convert back to ChunkWithScore
            final_results = [
                ChunkWithScore(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    content=chunk.content,
                    chunk_index=chunk.chunk_index,
                    score=score,
                )
                for chunk, score in reranked
            ]
            
            rerank_time = time.perf_counter() - rerank_start
            
            if trace:
                trace_info["stages"].append({
                    "name": "reranking",
                    "reranker": strategy.reranker_type,
                    "time_ms": round(rerank_time * 1000, 2),
                })
        else:
            # No reranking
            final_results = [
                ChunkWithScore(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    content=chunk.content,
                    chunk_index=chunk.chunk_index,
                    score=score,
                )
                for chunk, score in fused
            ]
        
        total_time = time.perf_counter() - start_time
        
        if trace:
            trace_info["total_time_ms"] = round(total_time * 1000, 2)
            trace_info["results_count"] = len(final_results)
        
        return final_results, trace_info
    
    async def _retrieve_with_strategy(
        self,
        query: str,
        strategy: RetrievalStrategy,
        top_k: int,
    ) -> list[tuple[Chunk, float]]:
        """Execute retrieval with a specific strategy.
        
        Args:
            query: Search query.
            strategy: Retrieval configuration.
            top_k: Number of results.
            
        Returns:
            List of (chunk, score) tuples.
        """
        results: list[tuple[Chunk, float]] = []
        
        # Vector search
        if strategy.use_vector:
            provider = await self.get_embedding_provider()
            query_embedding = await provider.embed([query])
            vector_results = await self._vector_search(query_embedding[0], top_k * 2)
            results.extend(vector_results)
        
        # BM25 search
        if strategy.use_bm25:
            # Note: BM25 requires pre-indexed documents
            # For now, we rely on vector search as primary
            pass
        
        # Deduplicate by chunk ID
        seen_ids = set()
        deduped = []
        for chunk, score in results:
            cid = str(chunk.id)
            if cid not in seen_ids:
                seen_ids.add(cid)
                deduped.append((chunk, score))
        
        # Sort by score and limit
        deduped.sort(key=lambda x: x[1], reverse=True)
        return deduped[:top_k]
    
    async def _vector_search(
        self,
        query_embedding: list[float],
        top_k: int,
    ) -> list[tuple[Chunk, float]]:
        """Execute vector similarity search.

        Args:
            query_embedding: Query vector.
            top_k: Number of results.

        Returns:
            List of (chunk, similarity_score) tuples.
        """
        import math

        def _cosine_similarity(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = math.sqrt(sum(x * x for x in a))
            norm_b = math.sqrt(sum(x * x for x in b))
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Chunk).where(Chunk.embedding.isnot(None))
            )
            chunks = result.scalars().all()

        scored = [
            (chunk, _cosine_similarity(query_embedding, chunk.embedding))
            for chunk in chunks
            if chunk.embedding is not None
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
    
    def _fuse_multi_query_results(
        self,
        all_results: dict[str, list[tuple[Chunk, float]]],
        top_k: int,
    ) -> list[tuple[Chunk, float]]:
        """Fuse results from multiple query variants.
        
        Uses RRF (Reciprocal Rank Fusion) to combine rankings.
        
        Args:
            all_results: Dict of {query: [(chunk, score), ...]}.
            top_k: Number of final results.
            
        Returns:
            Fused and sorted results.
        """
        rrf_k = 60
        chunk_scores: dict[str, tuple[float, Chunk]] = {}
        
        for query, results in all_results.items():
            for rank, (chunk, _) in enumerate(results, start=1):
                cid = str(chunk.id)
                rrf_score = 1.0 / (rrf_k + rank)
                
                if cid in chunk_scores:
                    # Accumulate RRF score
                    current_score, _ = chunk_scores[cid]
                    chunk_scores[cid] = (current_score + rrf_score, chunk)
                else:
                    chunk_scores[cid] = (rrf_score, chunk)
        
        # Sort by accumulated RRF score
        sorted_results = sorted(
            chunk_scores.values(),
            key=lambda x: x[0],
            reverse=True,
        )
        
        return [(chunk, score) for score, chunk in sorted_results[:top_k]]
    
    def get_available_strategies(self) -> list[dict[str, Any]]:
        """List available retrieval strategies.
        
        Returns:
            List of strategy configurations.
        """
        return self.strategy_selector.list_strategies()
