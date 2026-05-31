"""Retrieval strategy selector for dynamic strategy selection.

Routes queries to optimal retrieval strategies based on intent,
query characteristics, and A/B test configuration.
"""

from __future__ import annotations

import random
from typing import Any

from app.services.query.intent import QueryClassifier, QueryIntent


class RetrievalStrategy:
    """Configuration for a retrieval strategy."""
    
    def __init__(
        self,
        name: str,
        use_bm25: bool = True,
        use_vector: bool = True,
        bm25_weight: float = 0.5,
        vector_weight: float = 0.5,
        use_reranker: bool = True,
        reranker_type: str = "cross_encoder",
        expand_query: bool = False,
        top_k: int = 5,
        description: str = "",
    ) -> None:
        """Initialize retrieval strategy.
        
        Args:
            name: Strategy identifier.
            use_bm25: Whether to use BM25 keyword search.
            use_vector: Whether to use vector semantic search.
            bm25_weight: Weight for BM25 scores in hybrid fusion.
            vector_weight: Weight for vector scores in hybrid fusion.
            use_reranker: Whether to apply reranking.
            reranker_type: Type of reranker (cross_encoder, colbert, none).
            expand_query: Whether to expand query for better recall.
            top_k: Number of results to return.
            description: Human-readable description.
        """
        self.name = name
        self.use_bm25 = use_bm25
        self.use_vector = use_vector
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self.use_reranker = use_reranker
        self.reranker_type = reranker_type
        self.expand_query = expand_query
        self.top_k = top_k
        self.description = description
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "use_bm25": self.use_bm25,
            "use_vector": self.use_vector,
            "bm25_weight": self.bm25_weight,
            "vector_weight": self.vector_weight,
            "use_reranker": self.use_reranker,
            "reranker_type": self.reranker_type,
            "expand_query": self.expand_query,
            "top_k": self.top_k,
            "description": self.description,
        }


class StrategySelector:
    """Selects optimal retrieval strategy for each query.
    
    Uses query intent classification and A/B testing to route
    queries to the best retrieval approach.
    """
    
    # Predefined strategies
    STRATEGIES = {
        "hybrid_default": RetrievalStrategy(
            name="hybrid_default",
            use_bm25=True,
            use_vector=True,
            bm25_weight=0.4,
            vector_weight=0.6,
            use_reranker=True,
            reranker_type="cross_encoder",
            expand_query=False,
            top_k=5,
            description="Default hybrid search with reranking",
        ),
        "vector_only": RetrievalStrategy(
            name="vector_only",
            use_bm25=False,
            use_vector=True,
            bm25_weight=0.0,
            vector_weight=1.0,
            use_reranker=True,
            reranker_type="cross_encoder",
            expand_query=False,
            top_k=5,
            description="Pure semantic search",
        ),
        "keyword_heavy": RetrievalStrategy(
            name="keyword_heavy",
            use_bm25=True,
            use_vector=True,
            bm25_weight=0.7,
            vector_weight=0.3,
            use_reranker=True,
            reranker_type="cross_encoder",
            expand_query=True,
            top_k=7,
            description="Keyword-heavy for precise matching",
        ),
        "semantic_heavy": RetrievalStrategy(
            name="semantic_heavy",
            use_bm25=True,
            use_vector=True,
            bm25_weight=0.2,
            vector_weight=0.8,
            use_reranker=True,
            reranker_type="colbert",
            expand_query=True,
            top_k=6,
            description="Semantic-heavy with ColBERT reranking",
        ),
        "fast": RetrievalStrategy(
            name="fast",
            use_bm25=True,
            use_vector=True,
            bm25_weight=0.5,
            vector_weight=0.5,
            use_reranker=False,
            reranker_type="none",
            expand_query=False,
            top_k=5,
            description="Fast search without reranking",
        ),
    }
    
    def __init__(self, ab_test_enabled: bool = False) -> None:
        """Initialize strategy selector.
        
        Args:
            ab_test_enabled: Whether to enable A/B testing.
        """
        self.classifier = QueryClassifier()
        self.ab_test_enabled = ab_test_enabled
        self._ab_test_assignments: dict[str, str] = {}  # query_hash -> strategy
    
    async def select_strategy(
        self,
        query: str,
        user_id: str | None = None,
        force_strategy: str | None = None,
    ) -> RetrievalStrategy:
        """Select best strategy for a query.
        
        Args:
            query: User query.
            user_id: Optional user ID for consistent A/B assignment.
            force_strategy: Force specific strategy (for testing).
            
        Returns:
            Selected retrieval strategy.
        """
        # If forced, use that strategy
        if force_strategy and force_strategy in self.STRATEGIES:
            return self.STRATEGIES[force_strategy]
        
        # Classify query intent
        intent = await self.classifier.classify(query)
        
        # Get intent-based strategy
        strategy_config = self.classifier.get_retrieval_strategy(intent)
        
        # Check A/B test assignment
        if self.ab_test_enabled:
            ab_strategy = self._get_ab_test_strategy(query, user_id)
            if ab_strategy:
                return ab_strategy
        
        # Create strategy from intent config
        return RetrievalStrategy(
            name=f"intent_{intent.value}",
            use_bm25=strategy_config["use_bm25"],
            use_vector=strategy_config["use_vector"],
            bm25_weight=strategy_config["bm25_weight"],
            vector_weight=strategy_config["vector_weight"],
            use_reranker=strategy_config["rerank"],
            reranker_type="cross_encoder" if strategy_config["rerank"] else "none",
            expand_query=strategy_config["expand_query"],
            top_k=strategy_config["top_k"],
            description=f"Auto-selected for {intent.value} intent",
        )
    
    def _get_ab_test_strategy(
        self,
        query: str,
        user_id: str | None = None,
    ) -> RetrievalStrategy | None:
        """Get A/B test strategy assignment.
        
        Args:
            query: User query.
            user_id: Optional user ID.
            
            Returns:
                Assigned strategy or None.
        """
        # Create consistent hash for assignment
        hash_key = f"{user_id or 'anon'}:{query}"
        
        # Check if already assigned
        if hash_key in self._ab_test_assignments:
            strategy_name = self._ab_test_assignments[hash_key]
            return self.STRATEGIES.get(strategy_name)
        
        # Random assignment for A/B test
        # In production, use consistent hashing or user bucketing
        strategy_names = list(self.STRATEGIES.keys())
        assigned = random.choice(strategy_names)
        self._ab_test_assignments[hash_key] = assigned
        
        return self.STRATEGIES.get(assigned)
    
    def list_strategies(self) -> list[dict[str, Any]]:
        """List all available strategies.
        
        Returns:
            List of strategy configurations.
        """
        return [s.to_dict() for s in self.STRATEGIES.values()]


class ABTestFramework:
    """A/B testing framework for retrieval strategies.
    
    Tracks metrics for different strategies and determines winners.
    """
    
    def __init__(self) -> None:
        """Initialize A/B test framework."""
        self._experiments: dict[str, dict[str, Any]] = {}
        self._results: dict[str, list[dict[str, Any]]] = {}
    
    def create_experiment(
        self,
        name: str,
        strategies: list[str],
        metrics: list[str] | None = None,
        duration_days: int = 14,
    ) -> str:
        """Create a new A/B test experiment.
        
        Args:
            name: Experiment name.
            strategies: List of strategy names to test.
            metrics: Metrics to track (precision, recall, latency, etc.).
            duration_days: Experiment duration.
            
        Returns:
            Experiment ID.
        """
        import uuid
        
        exp_id = str(uuid.uuid4())[:8]
        
        self._experiments[exp_id] = {
            "id": exp_id,
            "name": name,
            "strategies": strategies,
            "metrics": metrics or ["precision@5", "recall@10", "latency_ms"],
            "duration_days": duration_days,
            "start_time": None,
            "status": "created",
        }
        
        self._results[exp_id] = []
        
        return exp_id
    
    def start_experiment(self, exp_id: str) -> None:
        """Start an experiment.
        
        Args:
            exp_id: Experiment ID.
        """
        from datetime import datetime
        
        if exp_id in self._experiments:
            self._experiments[exp_id]["start_time"] = datetime.now().isoformat()
            self._experiments[exp_id]["status"] = "running"
    
    def record_result(
        self,
        exp_id: str,
        strategy: str,
        query: str,
        metrics: dict[str, float],
    ) -> None:
        """Record a result for an experiment.
        
        Args:
            exp_id: Experiment ID.
            strategy: Strategy name that served this query.
            query: The query text.
            metrics: Metric values.
        """
        from datetime import datetime
        
        if exp_id not in self._results:
            return
        
        self._results[exp_id].append({
            "timestamp": datetime.now().isoformat(),
            "strategy": strategy,
            "query": query,
            "metrics": metrics,
        })
    
    def get_experiment_results(self, exp_id: str) -> dict[str, Any]:
        """Get aggregated results for an experiment.
        
        Args:
            exp_id: Experiment ID.
            
        Returns:
            Aggregated results by strategy.
        """
        if exp_id not in self._results:
            return {"error": "Experiment not found"}
        
        results = self._results[exp_id]
        
        if not results:
            return {"status": "no_data"}
        
        # Aggregate by strategy
        by_strategy: dict[str, list[dict[str, Any]]] = {}
        for r in results:
            s = r["strategy"]
            if s not in by_strategy:
                by_strategy[s] = []
            by_strategy[s].append(r)
        
        # Compute averages
        aggregated = {}
        for strategy, strategy_results in by_strategy.items():
            metrics_sums: dict[str, float] = {}
            metrics_counts: dict[str, int] = {}
            
            for r in strategy_results:
                for metric, value in r["metrics"].items():
                    metrics_sums[metric] = metrics_sums.get(metric, 0) + value
                    metrics_counts[metric] = metrics_counts.get(metric, 0) + 1
            
            aggregated[strategy] = {
                "query_count": len(strategy_results),
                "metrics": {
                    metric: metrics_sums[metric] / metrics_counts[metric]
                    for metric in metrics_sums
                },
            }
        
        return {
            "experiment_id": exp_id,
            "experiment": self._experiments.get(exp_id, {}),
            "total_queries": len(results),
            "by_strategy": aggregated,
        }
