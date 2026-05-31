"""Query intent classification for retrieval strategy selection.

Classifies queries by intent (factual, procedural, comparison, etc.)
to select optimal retrieval strategies and models.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from typing import Any

from app.config import get_settings


class QueryIntent(Enum):
    """Types of query intents."""
    
    FACTUAL = "factual"  # "What is X?", "Who is Y?"
    PROCEDURAL = "procedural"  # "How do I X?", "Steps to Y"
    COMPARISON = "comparison"  # "X vs Y", "Difference between"
    ANALYTICAL = "analytical"  # "Why is X?", "Causes of Y"
    DEFINITION = "definition"  # "Define X", "Meaning of Y"
    LISTING = "listing"  # "List of X", "Examples of Y"
    TROUBLESHOOTING = "troubleshooting"  # "Error X", "Fix Y"
    OPINION = "opinion"  # "Best X", "Should I Y"
    CONVERSATIONAL = "conversational"  # "Hello", "Thanks"
    UNKNOWN = "unknown"


class QueryClassifier:
    """LLM-based query intent classifier.
    
    Classifies queries to optimize retrieval strategy selection.
    Different intents benefit from different retrieval approaches.
    """
    
    # Keywords that indicate specific intents
    INTENT_KEYWORDS = {
        QueryIntent.PROCEDURAL: [
            "how to", "how do", "steps", "guide", "tutorial", "instructions",
            "setup", "install", "configure", "deploy", "implement",
        ],
        QueryIntent.COMPARISON: [
            "vs", "versus", "compare", "difference", "better than",
            "which is", "or", "alternative", "pros and cons",
        ],
        QueryIntent.ANALYTICAL: [
            "why", "causes", "reasons", "explanation", "analyze",
            "impact", "effect", "consequences", "implications",
        ],
        QueryIntent.DEFINITION: [
            "what is", "define", "meaning", "definition", "explain",
            "describe", "overview", "introduction",
        ],
        QueryIntent.TROUBLESHOOTING: [
            "error", "bug", "issue", "problem", "fix", "solve",
            "troubleshoot", "debug", "exception", "failed",
        ],
        QueryIntent.LISTING: [
            "list", "examples", "types", "categories", "features",
            "options", "alternatives", "variants",
        ],
        QueryIntent.OPINION: [
            "best", "recommended", "should", "good", "better",
            "optimal", "ideal", "top", "worst",
        ],
        QueryIntent.CONVERSATIONAL: [
            "hello", "hi", "hey", "thanks", "thank you", "bye",
            "goodbye", "help", "?",
        ],
    }
    
    def __init__(self, model: str | None = None, use_llm: bool = True) -> None:
        """Initialize query classifier.
        
        Args:
            model: LLM model for classification.
            use_llm: Whether to use LLM (True) or rule-based (False).
        """
        settings = get_settings()
        self.model = model or getattr(settings, "CLASSIFIER_MODEL", "gpt-4o-mini")
        self.use_llm = use_llm
        self._client: Any = None
    
    def _get_client(self) -> Any:
        """Get or create OpenAI client."""
        if self._client is None:
            from openai import OpenAI
            settings = get_settings()
            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client
    
    def classify_rule_based(self, query: str) -> QueryIntent:
        """Classify query using keyword rules.
        
        Args:
            query: User query text.
            
        Returns:
            Detected query intent.
        """
        query_lower = query.lower()
        
        # Check each intent's keywords
        for intent, keywords in self.INTENT_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    return intent
        
        # Default to factual
        return QueryIntent.FACTUAL
    
    async def classify(self, query: str) -> QueryIntent:
        """Classify query intent using LLM or rules.
        
        Args:
            query: User query.
            
        Returns:
            Classified intent.
        """
        if not self.use_llm:
            return self.classify_rule_based(query)
        
        try:
            return await self._classify_llm(query)
        except Exception:
            # Fallback to rule-based on error
            return self.classify_rule_based(query)
    
    async def _classify_llm(self, query: str) -> QueryIntent:
        """Use LLM to classify query intent.
        
        Args:
            query: User query.
            
        Returns:
            Classified intent.
        """
        client = self._get_client()
        
        intent_options = ", ".join([i.value for i in QueryIntent if i != QueryIntent.UNKNOWN])
        
        prompt = f"""Classify the following query into one of these categories:
{intent_options}

Query: "{query}"

Respond with ONLY the category name (one word), nothing else:"""

        response = await asyncio.to_thread(
            client.chat.completions.create,
            model=self.model,
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=20,
        )
        
        result = response.choices[0].message.content or "unknown"
        result = result.strip().lower()
        
        # Map to enum
        try:
            return QueryIntent(result)
        except ValueError:
            return QueryIntent.UNKNOWN
    
    def get_retrieval_strategy(self, intent: QueryIntent) -> dict[str, Any]:
        """Get optimal retrieval strategy for an intent.
        
        Args:
            intent: Classified query intent.
            
        Returns:
            Strategy configuration dict.
        """
        strategies = {
            QueryIntent.FACTUAL: {
                "description": "Direct factual lookup",
                "use_bm25": True,
                "use_vector": True,
                "bm25_weight": 0.4,
                "vector_weight": 0.6,
                "rerank": True,
                "expand_query": False,
                "top_k": 5,
            },
            QueryIntent.PROCEDURAL: {
                "description": "Step-by-step instructions",
                "use_bm25": True,
                "use_vector": True,
                "bm25_weight": 0.5,
                "vector_weight": 0.5,
                "rerank": True,
                "expand_query": True,
                "top_k": 7,
            },
            QueryIntent.COMPARISON: {
                "description": "Compare multiple items",
                "use_bm25": True,
                "use_vector": True,
                "bm25_weight": 0.6,
                "vector_weight": 0.4,
                "rerank": True,
                "expand_query": True,
                "top_k": 8,
            },
            QueryIntent.ANALYTICAL: {
                "description": "Deep analysis and explanation",
                "use_bm25": True,
                "use_vector": True,
                "bm25_weight": 0.3,
                "vector_weight": 0.7,
                "rerank": True,
                "expand_query": True,
                "top_k": 6,
            },
            QueryIntent.DEFINITION: {
                "description": "Define or explain concept",
                "use_bm25": True,
                "use_vector": True,
                "bm25_weight": 0.5,
                "vector_weight": 0.5,
                "rerank": True,
                "expand_query": False,
                "top_k": 5,
            },
            QueryIntent.TROUBLESHOOTING: {
                "description": "Solve error or problem",
                "use_bm25": True,
                "use_vector": True,
                "bm25_weight": 0.7,
                "vector_weight": 0.3,
                "rerank": True,
                "expand_query": True,
                "top_k": 10,
            },
            QueryIntent.LISTING: {
                "description": "List items or examples",
                "use_bm25": True,
                "use_vector": True,
                "bm25_weight": 0.6,
                "vector_weight": 0.4,
                "rerank": False,
                "expand_query": False,
                "top_k": 15,
            },
            QueryIntent.OPINION: {
                "description": "Recommendations and opinions",
                "use_bm25": True,
                "use_vector": True,
                "bm25_weight": 0.4,
                "vector_weight": 0.6,
                "rerank": True,
                "expand_query": True,
                "top_k": 6,
            },
            QueryIntent.CONVERSATIONAL: {
                "description": "Social/chat queries",
                "use_bm25": False,
                "use_vector": True,
                "bm25_weight": 0.0,
                "vector_weight": 1.0,
                "rerank": False,
                "expand_query": False,
                "top_k": 3,
            },
            QueryIntent.UNKNOWN: {
                "description": "Unknown intent - use defaults",
                "use_bm25": True,
                "use_vector": True,
                "bm25_weight": 0.5,
                "vector_weight": 0.5,
                "rerank": True,
                "expand_query": False,
                "top_k": 5,
            },
        }
        
        return strategies.get(intent, strategies[QueryIntent.UNKNOWN])
    
    async def analyze(self, query: str) -> dict[str, Any]:
        """Full query analysis with intent and strategy.
        
        Args:
            query: User query.
            
        Returns:
            Analysis result with intent, strategy, and confidence.
        """
        intent = await self.classify(query)
        strategy = self.get_retrieval_strategy(intent)
        
        # Determine confidence
        rule_intent = self.classify_rule_based(query)
        confidence = 0.9 if intent == rule_intent else 0.7
        
        return {
            "query": query,
            "intent": intent.value,
            "confidence": confidence,
            "strategy": strategy,
            "keywords_matched": self._get_matched_keywords(query, intent),
        }
    
    def _get_matched_keywords(self, query: str, intent: QueryIntent) -> list[str]:
        """Get keywords that matched for this intent.
        
        Args:
            query: User query.
            intent: Classified intent.
            
        Returns:
            List of matched keywords.
        """
        query_lower = query.lower()
        keywords = self.INTENT_KEYWORDS.get(intent, [])
        return [kw for kw in keywords if kw in query_lower]
