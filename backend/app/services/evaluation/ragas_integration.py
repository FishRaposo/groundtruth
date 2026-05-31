"""RAGAS integration for automated RAG evaluation.

RAGAS (Retrieval-Augmented Generation Assessment)
provides metrics for evaluating RAG systems without
human-annotated ground truth.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.config import get_settings
from app.services.retrieval.enhanced import EnhancedRetrievalService


class RAGASEvaluator:
    """RAGAS metrics evaluator.
    
    Implements RAGAS metrics:
    - Faithfulness: Are claims grounded in context?
    - Answer Relevancy: Is answer relevant to question?
    - Context Precision: Is retrieved context relevant?
    - Context Recall: Is relevant context retrieved?
    """
    
    def __init__(self) -> None:
        """Initialize RAGAS evaluator."""
        self.settings = get_settings()
        self.retrieval = EnhancedRetrievalService()
        
        # Try to import RAGAS
        try:
            from ragas import evaluate
            from ragas.metrics import (
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            )
            self._ragas_available = True
            self._metrics = {
                "faithfulness": faithfulness,
                "answer_relevancy": answer_relevancy,
                "context_precision": context_precision,
                "context_recall": context_recall,
            }
        except ImportError:
            self._ragas_available = False
            self._metrics = {}
    
    async def evaluate_query_response(
        self,
        query: str,
        response: str,
        contexts: list[str] | None = None,
    ) -> dict[str, Any]:
        """Evaluate a single query-response pair.
        
        Args:
            query: User query.
            response: Generated response.
            contexts: Retrieved contexts (if None, will retrieve).
            
        Returns:
            RAGAS metrics.
        """
        if not self._ragas_available:
            # Fallback to custom evaluation
            return await self._custom_evaluate(query, response, contexts)
        
        # Retrieve contexts if not provided
        if contexts is None:
            chunks, _ = await self.retrieval.retrieve(query, top_k=5)
            contexts = [chunk.content for chunk in chunks]
        
        try:
            from datasets import Dataset
            
            # Create dataset
            data = {
                "question": [query],
                "answer": [response],
                "contexts": [contexts],
            }
            dataset = Dataset.from_dict(data)
            
            # Evaluate
            from ragas import evaluate as ragas_evaluate
            result = ragas_evaluate(
                dataset,
                metrics=list(self._metrics.values()),
            )
            
            return {
                "faithfulness": result.get("faithfulness", [0.0])[0],
                "answer_relevancy": result.get("answer_relevancy", [0.0])[0],
                "context_precision": result.get("context_precision", [0.0])[0],
                "context_recall": result.get("context_recall", [0.0])[0],
                "overall_score": self._compute_overall(result),
                "method": "ragas",
            }
            
        except Exception as e:
            return await self._custom_evaluate(query, response, contexts)
    
    async def _custom_evaluate(
        self,
        query: str,
        response: str,
        contexts: list[str] | None = None,
    ) -> dict[str, Any]:
        """Custom evaluation when RAGAS not available.
        
        Args:
            query: User query.
            response: Generated response.
            contexts: Retrieved contexts.
            
        Returns:
            Evaluation metrics.
        """
        if contexts is None:
            chunks, _ = await self.retrieval.retrieve(query, top_k=5)
            contexts = [chunk.content for chunk in chunks]
        
        # Simple heuristics
        # Faithfulness: Check if response terms appear in contexts
        response_words = set(response.lower().split())
        context_text = " ".join(contexts).lower()
        context_words = set(context_text.split())
        
        if response_words:
            faithfulness = len(response_words & context_words) / len(response_words)
        else:
            faithfulness = 0.0
        
        # Answer relevancy: Simple keyword overlap
        query_words = set(query.lower().split())
        if query_words:
            relevancy = len(query_words & response_words) / len(query_words)
        else:
            relevancy = 0.0
        
        # Context recall: Did we retrieve relevant context?
        if query_words:
            recall = len(query_words & context_words) / len(query_words)
        else:
            recall = 0.0
        
        return {
            "faithfulness": round(faithfulness, 2),
            "answer_relevancy": round(relevancy, 2),
            "context_recall": round(recall, 2),
            "context_precision": 0.8,  # Placeholder
            "overall_score": round((faithfulness + relevancy + recall) / 3, 2),
            "method": "custom_heuristic",
        }
    
    def _compute_overall(self, result: dict[str, Any]) -> float:
        """Compute overall score from RAGAS results.
        
        Args:
            result: RAGAS result dict.
            
        Returns:
            Average score.
        """
        scores = []
        for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
            if metric in result:
                val = result[metric]
                if isinstance(val, list):
                    scores.append(val[0] if val else 0.0)
                else:
                    scores.append(val)
        
        return round(sum(scores) / len(scores), 2) if scores else 0.0
    
    async def evaluate_dataset(
        self,
        dataset: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Evaluate a dataset of query-response pairs.
        
        Args:
            dataset: List of {query, response, contexts?} dicts.
            
        Returns:
            Aggregated metrics.
        """
        results = []
        
        for item in dataset:
            result = await self.evaluate_query_response(
                item["query"],
                item["response"],
                item.get("contexts"),
            )
            results.append(result)
        
        # Aggregate
        aggregated = {
            "total_evaluated": len(results),
            "faithfulness_avg": round(sum(r["faithfulness"] for r in results) / len(results), 2),
            "answer_relevancy_avg": round(sum(r["answer_relevancy"] for r in results) / len(results), 2),
            "context_recall_avg": round(sum(r["context_recall"] for r in results) / len(results), 2),
            "overall_score_avg": round(sum(r["overall_score"] for r in results) / len(results), 2),
            "individual_results": results,
        }
        
        return aggregated


class AnswerRelevanceScorer:
    """Scores answer relevance using LLM-as-judge.
    
    Evaluates how well an answer addresses a question
    on multiple dimensions.
    """
    
    def __init__(self, model: str = "gpt-4o-mini") -> None:
        """Initialize scorer.
        
        Args:
            model: LLM model for scoring.
        """
        self.model = model
        self._client = None
    
    def _get_client(self) -> Any:
        """Get OpenAI client."""
        if self._client is None:
            from openai import OpenAI
            from app.config import get_settings
            settings = get_settings()
            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client
    
    async def score(
        self,
        query: str,
        answer: str,
        contexts: list[str],
    ) -> dict[str, Any]:
        """Score answer relevance.
        
        Args:
            query: User question.
            answer: Generated answer.
            contexts: Retrieved contexts.
            
        Returns:
            Relevance scores.
        """
        prompt = f"""Evaluate the answer relevance on these dimensions (1-10):

Query: {query}
Answer: {answer[:1000]}
Retrieved Contexts: {" ".join(contexts)[:500]}

Score on:
1. Directness: Does it directly answer the question?
2. Completeness: Does it cover all aspects of the question?
3. Accuracy: Is the information correct based on context?
4. Conciseness: Is it appropriately detailed without fluff?

Format:
Directness: [1-10]
Completeness: [1-10]
Accuracy: [1-10]
Conciseness: [1-10]
Overall: [1-10]"""

        try:
            client = self._get_client()
            
            response = await asyncio.to_thread(
                client.chat.completions.create,
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=200,
            )
            
            content = response.choices[0].message.content or ""
            
            # Parse scores
            scores = {}
            for line in content.split("\n"):
                if ":" in line:
                    key, val = line.split(":", 1)
                    try:
                        scores[key.strip().lower()] = float(val.strip())
                    except ValueError:
                        pass
            
            return {
                "scores": scores,
                "overall": scores.get("overall", sum(scores.values()) / len(scores) if scores else 0),
                "method": "llm_judge",
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "overall": 0.0,
                "method": "llm_judge",
            }
