"""Retrieval services for document search.

Provides multiple retrieval strategies including:
- Vector similarity search (semantic)
- BM25 keyword search
- Hybrid fusion (RRF)
- Query expansion
- Intent-based strategy selection
"""

from app.services.retrieval.bm25 import BM25Retriever, HybridRetriever
from app.services.retrieval.strategy import (
    RetrievalStrategy,
    StrategySelector,
    ABTestFramework,
)
from app.services.retrieval.enhanced import EnhancedRetrievalService
from app.services.retrieval.service import RetrievalService, retrieval_service

__all__ = [
    "BM25Retriever",
    "HybridRetriever",
    "RetrievalStrategy",
    "StrategySelector",
    "ABTestFramework",
    "EnhancedRetrievalService",
    "RetrievalService",
    "retrieval_service",
]
