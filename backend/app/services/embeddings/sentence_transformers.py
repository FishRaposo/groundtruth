"""Sentence Transformers local embedding provider implementation."""

from __future__ import annotations

import asyncio
from typing import Any

from app.services.embeddings.base import EmbeddingProvider


class SentenceTransformersProvider(EmbeddingProvider):
    """Local sentence-transformers embedding provider.
    
    This provider runs entirely locally using HuggingFace sentence-transformers models.
    No API key required.
    """
    
    def __init__(
        self,
        model: str = "all-MiniLM-L6-v2",
        dimensions: int | None = None,
        device: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize Sentence Transformers provider.
        
        Args:
            model: Model name from HuggingFace (all-MiniLM-L6-v2, all-mpnet-base-v2, etc.).
            dimensions: Optional dimensions (for interface compatibility).
            device: Device to run on (cpu, cuda, etc.). Auto-detected if None.
        """
        super().__init__(model, dimensions, **kwargs)
        self.device = device
        self._model: Any = None
    
    def _get_model(self) -> Any:
        """Get or load the sentence-transformers model."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            
            device = self.device
            if device is None:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            
            self._model = SentenceTransformer(self.model, device=device)
        return self._model
    
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using local sentence-transformers model.
        
        Args:
            texts: List of text strings to embed.
            
        Returns:
            List of embedding vectors.
        """
        if not texts:
            return []
        
        model = self._get_model()
        
        # Run in thread pool to not block event loop
        embeddings = await asyncio.to_thread(
            model.encode,
            texts,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        
        return embeddings.tolist()
    
    def get_model_name(self) -> str:
        """Return model name."""
        return f"sentence-transformers:{self.model}"
    
    def get_dimensions(self) -> int:
        """Return embedding dimensions based on model."""
        dimensions_map = {
            "all-MiniLM-L6-v2": 384,
            "all-MiniLM-L12-v2": 384,
            "all-mpnet-base-v2": 768,
            "paraphrase-multilingual-MiniLM-L12-v2": 384,
            "paraphrase-multilingual-mpnet-base-v2": 768,
        }
        return self.dimensions or dimensions_map.get(self.model, 384)
    
    def health_check(self) -> bool:
        """Check if model can be loaded."""
        try:
            self._get_model()
            return True
        except Exception:
            return False
