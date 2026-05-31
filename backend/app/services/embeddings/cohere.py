"""Cohere embedding provider implementation."""

from __future__ import annotations

import asyncio
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.services.embeddings.base import EmbeddingProvider


class CohereEmbeddingProvider(EmbeddingProvider):
    """Cohere API embedding provider."""
    
    def __init__(
        self,
        model: str = "embed-english-v3",
        dimensions: int | None = None,
        api_key: str | None = None,
        input_type: str = "search_document",
        **kwargs: Any,
    ) -> None:
        """Initialize Cohere embedding provider.
        
        Args:
            model: Cohere model name (embed-english-v3, embed-multilingual-v3).
            dimensions: Optional dimensions (not supported by Cohere, for interface compatibility).
            api_key: Cohere API key.
            input_type: Input type for embedding (search_document, search_query, classification, clustering).
        """
        super().__init__(model, dimensions, **kwargs)
        self.api_key = api_key
        self.input_type = input_type
        if not self.api_key:
            raise ValueError("Cohere API key required")
    
    def _get_client(self) -> Any:
        """Get or create Cohere client."""
        if self._client is None:
            import cohere
            self._client = cohere.Client(api_key=self.api_key)
        return self._client
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using Cohere API.
        
        Args:
            texts: List of text strings to embed.
            
        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []
        
        client = self._get_client()
        
        # Make API call
        response = await asyncio.to_thread(
            client.embed,
            texts=texts,
            model=self.model,
            input_type=self.input_type,
        )
        
        return response.embeddings
    
    def get_model_name(self) -> str:
        """Return Cohere model name."""
        return f"cohere:{self.model}"
    
    def get_dimensions(self) -> int:
        """Return embedding dimensions."""
        # Cohere embed-v3 models return 1024 dimensions
        dimensions_map = {
            "embed-english-v3": 1024,
            "embed-multilingual-v3": 1024,
            "embed-english-light-v3": 384,
            "embed-multilingual-light-v3": 384,
        }
        return dimensions_map.get(self.model, 1024)
    
    def health_check(self) -> bool:
        """Check Cohere API availability."""
        try:
            client = self._get_client()
            # Simple embedding to check connectivity
            client.embed(texts=["test"], model=self.model)
            return True
        except Exception:
            return False
