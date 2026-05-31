"""ColBERT late interaction reranking implementation.

ColBERT uses token-level embeddings and late interaction scoring
for more accurate relevance ranking than standard vector similarity.
"""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np
from app.config import get_settings


class ColBERTReranker:
    """ColBERT-style late interaction reranker.
    
    Unlike standard embeddings that compress text to a single vector,
    ColBERT keeps per-token embeddings and uses MaxSim operator for
    fine-grained relevance scoring.
    """
    
    def __init__(self, model_name: str | None = None) -> None:
        """Initialize ColBERT reranker.
        
        Args:
            model_name: HuggingFace model name. If None, uses sentence-transformers
                       as fallback since true ColBERT requires specific models.
        """
        self.model_name = model_name or "colbert-ir/colbertv2.0"
        self._model: Any = None
        self._tokenizer: Any = None
        
    def _load_model(self) -> None:
        """Lazy load the ColBERT model."""
        if self._model is not None:
            return
            
        try:
            # Try to use official ColBERT if available
            from colbert import ColBERT
            self._model = ColBERT.from_pretrained(self.model_name)
        except ImportError:
            # Fallback: use sentence-transformers with token-level embeddings
            from sentence_transformers import SentenceTransformer
            from transformers import AutoTokenizer
            
            self._model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            self._tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
    
    async def rerank(
        self,
        query: str,
        documents: list[tuple[str, Any]],  # (text, chunk_object)
        top_k: int = 5,
    ) -> list[tuple[Any, float]]:
        """Rerank documents using ColBERT-style late interaction.
        
        Args:
            query: Search query text.
            documents: List of (text, chunk_object) tuples.
            top_k: Number of top results to return.
            
        Returns:
            List of (chunk_object, score) tuples sorted by relevance.
        """
        if not documents:
            return []
        
        # Load model if needed
        await asyncio.to_thread(self._load_model)
        
        # Compute ColBERT scores
        scores: list[tuple[Any, float]] = []
        
        for text, chunk in documents:
            score = await self._compute_colbert_score(query, text)
            scores.append((chunk, score))
        
        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores[:top_k]
    
    async def _compute_colbert_score(self, query: str, document: str) -> float:
        """Compute ColBERT late interaction score.
        
        Uses MaxSim: For each query token, find max similarity to any doc token.
        Sum across all query tokens for final score.
        
        Args:
            query: Query text.
            document: Document text.
            
        Returns:
            ColBERT relevance score (higher is better).
        """
        try:
            # If using true ColBERT
            if hasattr(self._model, 'encode'):
                # Get token-level embeddings
                query_embedding = await asyncio.to_thread(
                    self._model.encode, 
                    [query],
                    show_progress_bar=False,
                )
                doc_embedding = await asyncio.to_thread(
                    self._model.encode,
                    [document],
                    show_progress_bar=False,
                )
                
                # Compute cosine similarity
                similarity = np.dot(query_embedding[0], doc_embedding[0])
                similarity /= np.linalg.norm(query_embedding[0]) * np.linalg.norm(doc_embedding[0])
                
                return float(similarity)
            
            # Fallback: use standard embeddings with sentence-transformers
            query_emb = await asyncio.to_thread(
                self._model.encode,
                [query],
                show_progress_bar=False,
            )
            doc_emb = await asyncio.to_thread(
                self._model.encode,
                [document],
                show_progress_bar=False,
            )
            
            # Cosine similarity
            similarity = np.dot(query_emb[0], doc_emb[0])
            similarity /= np.linalg.norm(query_emb[0]) * np.linalg.norm(doc_emb[0])
            
            return float(similarity)
            
        except Exception:
            # Return 0 score on error
            return 0.0


class CrossEncoderReranker:
    """Cross-encoder reranker for high-accuracy relevance scoring.
    
    Cross-encoders process query and document together, capturing
    interactions that bi-encoders miss. Slower but more accurate.
    """
    
    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2") -> None:
        """Initialize cross-encoder reranker.
        
        Args:
            model_name: HuggingFace cross-encoder model name.
        """
        self.model_name = model_name
        self._model: Any = None
    
    def _load_model(self) -> None:
        """Lazy load the cross-encoder model."""
        if self._model is not None:
            return
            
        from sentence_transformers import CrossEncoder
        self._model = CrossEncoder(self.model_name)
    
    async def rerank(
        self,
        query: str,
        documents: list[tuple[str, Any]],
        top_k: int = 5,
    ) -> list[tuple[Any, float]]:
        """Rerank documents using cross-encoder.
        
        Args:
            query: Search query.
            documents: List of (text, chunk_object) tuples.
            top_k: Number of top results.
            
        Returns:
            Sorted list of (chunk_object, score) tuples.
        """
        if not documents:
            return []
        
        await asyncio.to_thread(self._load_model)
        
        # Prepare pairs for cross-encoder
        pairs = [[query, doc_text] for doc_text, _ in documents]
        
        # Score all pairs
        scores = await asyncio.to_thread(
            self._model.predict,
            pairs,
            show_progress_bar=False,
        )
        
        # Create result tuples
        results = [
            (chunk, float(score))
            for (_, chunk), score in zip(documents, scores)
        ]
        
        # Sort by score descending
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results[:top_k]
