"""Base interface for embedding providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers.
    
    All embedding providers must implement this interface.
    """
    
    def __init__(self, model: str, dimensions: int | None = None, **kwargs: Any) -> None:
        """Initialize the embedding provider.
        
        Args:
            model: The model name to use for embeddings.
            dimensions: Optional dimensions to truncate/embed to.
            **kwargs: Additional provider-specific configuration.
        """
        self.model = model
        self.dimensions = dimensions
        self._client: Any = None
    
    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts into vectors.
        
        Args:
            texts: List of text strings to embed.
            
        Returns:
            List of embedding vectors, one per input text.
        """
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model identifier string.
        
        Returns:
            Model name/identifier for this provider.
        """
        pass
    
    @abstractmethod
    def get_dimensions(self) -> int:
        """Return the embedding dimension size.
        
        Returns:
            Number of dimensions in embeddings from this provider.
        """
        pass
    
    def health_check(self) -> bool:
        """Check if the provider is healthy and available.
        
        Returns:
            True if provider is healthy, False otherwise.
        """
        return True
