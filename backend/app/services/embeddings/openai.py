"""OpenAI embedding provider implementation."""

from __future__ import annotations

import asyncio
from typing import Any

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.services.embeddings.base import EmbeddingProvider
from app.config import get_settings


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI API embedding provider."""
    
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        dimensions: int | None = None,
        api_key: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize OpenAI embedding provider.
        
        Args:
            model: OpenAI model name (e.g., text-embedding-3-small, text-embedding-3-large).
            dimensions: Optional dimensions to truncate to.
            api_key: OpenAI API key (defaults to settings.OPENAI_API_KEY).
        """
        super().__init__(model, dimensions, **kwargs)
        self.api_key = api_key or get_settings().OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API key required")
    
    def _get_client(self) -> Any:
        """Get or create OpenAI client."""
        if self._client is None:
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key)
        return self._client
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using OpenAI API.
        
        Args:
            texts: List of text strings to embed.
            
        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []
        
        client = self._get_client()
        
        # Prepare request parameters
        params: dict[str, Any] = {
            "input": texts,
            "model": self.model,
        }
        if self.dimensions:
            params["dimensions"] = self.dimensions
        
        # Make API call
        response = await client.embeddings.create(**params)
        
        return [item.embedding for item in response.data]
    
    def get_model_name(self) -> str:
        """Return OpenAI model name."""
        return f"openai:{self.model}"
    
    def get_dimensions(self) -> int:
        """Return embedding dimensions."""
        if self.dimensions:
            return self.dimensions
        # Default dimensions for OpenAI models
        dimensions_map = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return dimensions_map.get(self.model, 1536)
    
    def health_check(self) -> bool:
        """Check OpenAI API availability."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.api_key)
            # Make a simple request to check connectivity
            client.embeddings.create(
                input=["test"],
                model=self.model,
                dimensions=1 if self.dimensions else None,
            )
            return True
        except Exception:
            return False
