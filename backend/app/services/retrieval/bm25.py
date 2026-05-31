"""BM25 keyword-based retrieval implementation.

BM25 is a probabilistic retrieval framework that ranks documents
based on query term frequency and inverse document frequency.
Combines well with vector search for hybrid retrieval.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any

import numpy as np


class BM25Retriever:
    """BM25 keyword retrieval with efficient indexing.
    
    Uses the classic BM25 formula:
    score(q, d) = sum(IDF(q_i) * (f(q_i, d) * (k1 + 1)) / (f(q_i, d) + k1 * (1 - b + b * |d|/avgdl)))
    
    Where:
    - IDF = inverse document frequency
    - f(q_i, d) = term frequency in document
    - k1, b = hyperparameters
    - |d| = document length
    - avgdl = average document length
    """
    
    def __init__(
        self,
        k1: float = 1.5,  # Term frequency saturation parameter
        b: float = 0.75,  # Length normalization parameter
    ) -> None:
        """Initialize BM25 retriever.
        
        Args:
            k1: Term frequency saturation (higher = more saturation).
            b: Length normalization (0.0 = no norm, 1.0 = full norm).
        """
        self.k1 = k1
        self.b = b
        
        # Index data structures
        self.documents: dict[str, str] = {}  # id -> text
        self.tokenized_docs: dict[str, list[str]] = {}  # id -> tokens
        self.doc_freqs: dict[str, int] = defaultdict(int)  # term -> doc frequency
        self.doc_lengths: dict[str, int] = {}  # id -> length
        self.avgdl: float = 0.0  # average document length
        self.N: int = 0  # total documents
        
    def _tokenize(self, text: str) -> list[str]:
        """Simple tokenization for BM25.
        
        Args:
            text: Input text.
            
        Returns:
            List of lowercase tokens.
        """
        # Lowercase and extract alphanumeric tokens
        text = text.lower()
        tokens = re.findall(r'\b[a-z0-9]+\b', text)
        return tokens
    
    def index_document(self, doc_id: str, text: str) -> None:
        """Add a document to the BM25 index.
        
        Args:
            doc_id: Unique document identifier.
            text: Document text content.
        """
        # Store document
        self.documents[doc_id] = text
        
        # Tokenize
        tokens = self._tokenize(text)
        self.tokenized_docs[doc_id] = tokens
        
        # Update statistics
        self.doc_lengths[doc_id] = len(tokens)
        
        # Update document frequencies
        unique_terms = set(tokens)
        for term in unique_terms:
            self.doc_freqs[term] += 1
        
        # Update global stats
        self.N += 1
        total_length = sum(self.doc_lengths.values())
        self.avgdl = total_length / self.N if self.N > 0 else 0.0
    
    def _compute_idf(self, term: str) -> float:
        """Compute IDF for a term.
        
        Uses Robertson-Sparck Jones IDF:
        IDF(q) = log((N - n(q) + 0.5) / (n(q) + 0.5) + 1)
        
        Args:
            term: Query term.
            
        Returns:
            IDF score.
        """
        n_q = self.doc_freqs.get(term, 0)
        
        if n_q == 0:
            return 0.0
        
        # Robertson-Sparck Jones IDF
        idf = math.log((self.N - n_q + 0.5) / (n_q + 0.5) + 1.0)
        
        return idf
    
    def _compute_bm25_score(self, query_terms: list[str], doc_id: str) -> float:
        """Compute BM25 score for a document.
        
        Args:
            query_terms: Tokenized query terms.
            doc_id: Document ID to score.
            
        Returns:
            BM25 relevance score.
        """
        if doc_id not in self.tokenized_docs:
            return 0.0
        
        doc_tokens = self.tokenized_docs[doc_id]
        doc_length = self.doc_lengths[doc_id]
        
        # Term frequencies in document
        term_freqs = Counter(doc_tokens)
        
        score = 0.0
        
        for term in query_terms:
            if term not in term_freqs:
                continue
            
            # IDF
            idf = self._compute_idf(term)
            
            # Term frequency
            tf = term_freqs[term]
            
            # BM25 term score
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * (doc_length / self.avgdl))
            
            score += idf * (numerator / denominator)
        
        return score
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        doc_filter: set[str] | None = None,
    ) -> list[tuple[str, float]]:
        """Search for documents using BM25.
        
        Args:
            query: Search query text.
            top_k: Number of top results to return.
            doc_filter: Optional set of document IDs to search within.
            
        Returns:
            List of (doc_id, score) tuples sorted by relevance.
        """
        if not self.documents:
            return []
        
        # Tokenize query
        query_terms = self._tokenize(query)
        
        if not query_terms:
            return []
        
        # Determine documents to search
        if doc_filter is not None:
            doc_ids = list(doc_filter)
        else:
            doc_ids = list(self.documents.keys())
        
        # Score all documents
        scores = []
        for doc_id in doc_ids:
            score = self._compute_bm25_score(query_terms, doc_id)
            if score > 0:
                scores.append((doc_id, score))
        
        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        
        return scores[:top_k]
    
    def batch_index(self, documents: dict[str, str]) -> None:
        """Index multiple documents at once.
        
        Args:
            documents: Dict of {doc_id: text} to index.
        """
        for doc_id, text in documents.items():
            self.index_document(doc_id, text)


class HybridRetriever:
    """Hybrid retrieval combining BM25 and vector search.
    
    Uses reciprocal rank fusion (RRF) to combine rankings from
    multiple retrieval methods.
    """
    
    def __init__(
        self,
        bm25_weight: float = 0.3,
        vector_weight: float = 0.7,
        rrf_k: int = 60,  # RRF constant
    ) -> None:
        """Initialize hybrid retriever.
        
        Args:
            bm25_weight: Weight for BM25 scores (0-1).
            vector_weight: Weight for vector scores (0-1).
            rrf_k: Reciprocal rank fusion constant.
        """
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self.rrf_k = rrf_k
        
        self.bm25 = BM25Retriever()
    
    def compute_rrf_scores(
        self,
        rankings: list[list[tuple[str, float]]],
    ) -> dict[str, float]:
        """Compute Reciprocal Rank Fusion scores.
        
        RRF formula: score(d) = sum(1 / (k + rank_d))
        
        Args:
            rankings: List of rankings, each a list of (doc_id, score).
            
        Returns:
            Dict of {doc_id: rrf_score}.
        """
        rrf_scores: dict[str, float] = defaultdict(float)
        
        for ranking in rankings:
            for rank, (doc_id, _) in enumerate(ranking, start=1):
                rrf_scores[doc_id] += 1.0 / (self.rrf_k + rank)
        
        return dict(rrf_scores)
    
    def fuse_scores(
        self,
        bm25_results: list[tuple[str, float]],
        vector_results: list[tuple[str, float]],
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        """Fuse BM25 and vector search results.
        
        Uses weighted combination of normalized scores.
        
        Args:
            bm25_results: BM25 ranking [(doc_id, score), ...].
            vector_results: Vector ranking [(doc_id, score), ...].
            top_k: Number of top results to return.
            
        Returns:
            Fused ranking sorted by combined score.
        """
        # Get all unique documents
        all_docs = set(doc_id for doc_id, _ in bm25_results + vector_results)
        
        # Create score lookup dicts
        bm25_lookup = {doc_id: score for doc_id, score in bm25_results}
        vector_lookup = {doc_id: score for doc_id, score in vector_results}
        
        # Normalize scores to 0-1 range
        def normalize(scores: dict[str, float]) -> dict[str, float]:
            if not scores:
                return {}
            max_score = max(scores.values()) if scores else 1.0
            if max_score == 0:
                return {k: 0.0 for k in scores}
            return {k: v / max_score for k, v in scores.items()}
        
        bm25_norm = normalize(bm25_lookup)
        vector_norm = normalize(vector_lookup)
        
        # Compute fused scores
        fused = []
        for doc_id in all_docs:
            bm25_score = bm25_norm.get(doc_id, 0.0)
            vector_score = vector_norm.get(doc_id, 0.0)
            
            combined = (
                self.bm25_weight * bm25_score +
                self.vector_weight * vector_score
            )
            fused.append((doc_id, combined))
        
        # Sort by combined score
        fused.sort(key=lambda x: x[1], reverse=True)
        
        return fused[:top_k]
