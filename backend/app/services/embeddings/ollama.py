"""Ollama local embedding provider implementation."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from app.services.embeddings.base import EmbeddingProvider


class OllamaEmbeddingProvider(EmbeddingProvider):
    """Ollama local embedding provider for self-hosted models."""
    
    def __init__(
        self,
        model: str = "nomic-embed-text",
        dimensions: int | None = None,
        base_url: str = "http://localhost:11434",
        **kwargs: Any,
    ) -> None:
        """Initialize Ollama embedding provider.
        
        Args:
            model: Ollama model name (nomic-embed-text, mxbai-embed-large, etc.).
            dimensions: Optional dimensions (depends on model).
            base_url: Ollama server URL.
        """
        super().__init__(model, dimensions, **kwargs)
        self.base_url = base_url.rstrip("/")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
    )
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using local Ollama server.
        
        Args:
            texts: List of text strings to embed.
            
        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []
        
        embeddings: list[list[float]] = []
        
        # Ollama embeds one at a time
        async with httpx.AsyncClient() as client:
            for text in texts:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": self.model,
                        "prompt": text,
                    },
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()
                embeddings.append(data["embedding"])
        
        return embeddings
    
    def get_model_name(self) -> str:
        """Return Ollama model name."""
        return f"ollama:{self.model}"
    
    def get_dimensions(self) -> int:
        """Return embedding dimensions based on model."""
        dimensions_map = {
            "nomic-embed-text": 768,
            "mxbai-embed-large": 1024,
            "snowflake-arctic-embed": 1024,
            "bge-large": 1024,
            "bge-m3": 1024,
        }
        return self.dimensions or dimensions_map.get(self.model, 768)
    
    def health_check(self) -> bool:
        """Check Ollama server availability."""
        try:
            import httpx
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False
