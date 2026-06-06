"""Query expansion using LLM for improved retrieval recall.

Expands user queries with synonyms, related terms, and variations
to improve recall without sacrificing precision.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.config import get_settings


class QueryExpander:
    """LLM-based query expansion for improved retrieval.
    
    Uses LLM to generate query variations and expansions that capture
the user's intent more completely.
    """
    
    def __init__(self, model: str | None = None) -> None:
        """Initialize query expander.
        
        Args:
            model: LLM model to use for expansion.
        """
        settings = get_settings()
        self.model = model or getattr(settings, "EXPANSION_MODEL", "gpt-4o-mini")
        self._client: Any = None
    
    def _get_client(self) -> Any:
        """Get or create OpenAI client."""
        if self._client is None:
            from openai import AsyncOpenAI
            settings = get_settings()
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client
    
    async def expand(
        self,
        query: str,
        num_expansions: int = 3,
        include_original: bool = True,
    ) -> list[str]:
        """Expand a query into multiple variations.
        
        Args:
            query: Original user query.
            num_expansions: Number of expansion variations to generate.
            include_original: Whether to include original query in results.
            
        Returns:
            List of query variations including original if specified.
        """
        if not query.strip():
            return [query] if include_original else []
        
        try:
            expansions = await self._llm_expand(query, num_expansions)
        except Exception:
            # Fallback to simple expansion on error
            expansions = self._simple_expand(query, num_expansions)
        
        if include_original:
            # Ensure original is first
            if query not in expansions:
                expansions.insert(0, query)
            else:
                expansions.remove(query)
                expansions.insert(0, query)
        
        return expansions
    
    async def _llm_expand(self, query: str, num_expansions: int) -> list[str]:
        """Use LLM to generate query expansions.
        
        Args:
            query: Original query.
            num_expansions: Number of variations to generate.
            
        Returns:
            List of expanded queries.
        """
        client = self._get_client()
        
        prompt = f"""Generate {num_expansions} alternative phrasings of the following search query.
These should capture the same intent but use different keywords, synonyms, or rephrasings.

Original query: "{query}"

Requirements:
- Each variation should be 1-2 sentences max
- Use synonyms and related terms
- Maintain the original intent
- Make each one different enough to potentially match different documents

Output ONLY the variations, one per line, no numbering or prefixes:"""

        response = await client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "You are a search query expansion assistant. Generate alternative phrasings that capture the same search intent."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=200,
        )
        
        content = response.choices[0].message.content or ""
        
        # Parse expansions
        expansions = [
            line.strip()
            for line in content.split("\n")
            if line.strip() and not line.strip().startswith("-")
        ]
        
        # Limit to requested number
        return expansions[:num_expansions]
    
    def _simple_expand(self, query: str, num_expansions: int) -> list[str]:
        """Simple rule-based expansion as fallback.
        
        Args:
            query: Original query.
            num_expansions: Number of variations.
            
        Returns:
            List of simple expansions.
        """
        # Common synonym mappings
        synonyms = {
            "how to": ["how do I", "steps to", "guide for"],
            "what is": ["definition of", "explain", "describe"],
            "best": ["top", "recommended", "optimal"],
            "vs": ["versus", "compared to", "difference between"],
            "setup": ["configure", "install", "deploy"],
            "fix": ["solve", "resolve", "troubleshoot"],
            "error": ["issue", "problem", "bug"],
        }
        
        expansions = []
        query_lower = query.lower()
        
        for key, variations in synonyms.items():
            if key in query_lower:
                for var in variations[:num_expansions]:
                    expansion = query_lower.replace(key, var)
                    if expansion != query_lower:
                        expansions.append(expansion)
        
        return expansions[:num_expansions]
    
    async def generate_synonyms(self, terms: list[str]) -> dict[str, list[str]]:
        """Generate synonyms for key terms.
        
        Args:
            terms: List of terms to find synonyms for.
            
        Returns:
            Dict mapping each term to its synonyms.
        """
        client = self._get_client()
        
        terms_str = ", ".join(terms)
        
        prompt = f"""For each of the following terms, provide 3-5 synonyms or related terms:

Terms: {terms_str}

Format your response as:
term1: synonym1, synonym2, synonym3
term2: synonym1, synonym2, synonym3
..."""

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt},
                ],
                temperature=0.5,
                max_tokens=300,
            )
            
            content = response.choices[0].message.content or ""
            
            # Parse synonym mappings
            synonyms = {}
            for line in content.split("\n"):
                if ":" in line:
                    term, syns = line.split(":", 1)
                    synonyms[term.strip()] = [
                        s.strip() for s in syns.split(",") if s.strip()
                    ]
            
            return synonyms
            
        except Exception:
            # Return empty dict on error
            return {term: [] for term in terms}


class HyDENetwork:
    """Hypothetical Document Embedding (HyDE) query expansion.
    
    Generates a hypothetical ideal document that would answer the query,
then uses that document's embedding for retrieval.
    """
    
    def __init__(self, model: str | None = None) -> None:
        """Initialize HyDE network.
        
        Args:
            model: LLM model to generate hypothetical documents.
        """
        settings = get_settings()
        self.model = model or getattr(settings, "HYDE_MODEL", "gpt-4o-mini")
        self._client: Any = None
    
    def _get_client(self) -> Any:
        """Get or create OpenAI client."""
        if self._client is None:
            from openai import AsyncOpenAI
            settings = get_settings()
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client
    
    async def generate_hypothetical_document(self, query: str) -> str:
        """Generate a hypothetical document that answers the query.
        
        Args:
            query: User query.
            
        Returns:
            Generated hypothetical document text.
        """
        client = self._get_client()
        
        prompt = f"""Write a short passage that would answer or address the following query.
This should be written as if it were a document from a knowledge base.

Query: {query}

Requirements:
- 3-5 sentences
- Directly addresses the query
- Written in informational/knowledge base style
- Include key terms and concepts related to the query

Passage:"""

        try:
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_tokens=200,
            )
            
            return response.choices[0].message.content or query
            
        except Exception:
            # Return original query on error
            return query
