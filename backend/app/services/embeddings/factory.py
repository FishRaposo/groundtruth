"""Factory for creating embedding providers."""

from __future__ import annotations

from typing import Any

from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.openai import OpenAIEmbeddingProvider
from app.services.embeddings.cohere import CohereEmbeddingProvider
from app.services.embeddings.ollama import OllamaEmbeddingProvider
from app.services.embeddings.sentence_transformers import SentenceTransformersProvider
from app.config import get_settings


# Registry of available providers
PROVIDER_REGISTRY: dict[str, type[EmbeddingProvider]] = {
    "openai": OpenAIEmbeddingProvider,
    "cohere": CohereEmbeddingProvider,
    "ollama": OllamaEmbeddingProvider,
    "sentence-transformers": SentenceTransformersProvider,
    "local": SentenceTransformersProvider,  # Alias for local models
}


def get_embedding_provider(
    provider_name: str | None = None,
    **kwargs: Any,
) -> EmbeddingProvider:
    """Create an embedding provider instance.
    
    Args:
        provider_name: Provider identifier (openai, cohere, ollama, sentence-transformers).
                      Defaults to settings.EMBEDDING_PROVIDER.
        **kwargs: Additional provider-specific configuration.
        
    Returns:
        Configured embedding provider instance.
        
    Raises:
        ValueError: If provider_name is not recognized.
    """
    settings = get_settings()
    
    # Use default from settings if not specified
    provider = provider_name or getattr(settings, "EMBEDDING_PROVIDER", "openai")
    
    # Normalize provider name
    provider = provider.lower().replace("_", "-")
    
    # Get provider class from registry
    provider_class = PROVIDER_REGISTRY.get(provider)
    if provider_class is None:
        available = ", ".join(PROVIDER_REGISTRY.keys())
        raise ValueError(
            f"Unknown embedding provider: {provider}. "
            f"Available providers: {available}"
        )
    
    # Get default configuration from settings
    model = kwargs.pop("model", None) or getattr(settings, "EMBEDDING_MODEL", None)
    dimensions = kwargs.pop("dimensions", None) or getattr(settings, "EMBEDDING_DIMENSIONS", None)
    
    # Provider-specific defaults
    if provider == "openai":
        api_key = kwargs.pop("api_key", None) or getattr(settings, "OPENAI_API_KEY", None)
        return provider_class(model=model or "text-embedding-3-small", dimensions=dimensions, api_key=api_key, **kwargs)
    
    elif provider == "cohere":
        api_key = kwargs.pop("api_key", None) or getattr(settings, "COHERE_API_KEY", None)
        return provider_class(model=model or "embed-english-v3", dimensions=dimensions, api_key=api_key, **kwargs)
    
    elif provider == "ollama":
        base_url = kwargs.pop("base_url", None) or getattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
        return provider_class(model=model or "nomic-embed-text", dimensions=dimensions, base_url=base_url, **kwargs)
    
    elif provider in ("sentence-transformers", "local"):
        device = kwargs.pop("device", None) or getattr(settings, "EMBEDDING_DEVICE", None)
        return provider_class(model=model or "all-MiniLM-L6-v2", dimensions=dimensions, device=device, **kwargs)
    
    # Fallback for any other provider
    return provider_class(model=model, dimensions=dimensions, **kwargs)


def list_available_providers() -> list[str]:
    """List all available embedding provider names.
    
    Returns:
        List of provider identifiers.
    """
    return list(PROVIDER_REGISTRY.keys())


def get_provider_info(provider_name: str) -> dict[str, Any]:
    """Get information about an embedding provider.
    
    Args:
        provider_name: Provider identifier.
        
    Returns:
        Provider information including supported models, dimensions, requirements.
    """
    info: dict[str, Any] = {
        "openai": {
            "name": "OpenAI",
            "requires_api_key": True,
            "models": ["text-embedding-3-small", "text-embedding-3-large", "text-embedding-ada-002"],
            "default_dimensions": 1536,
            "cloud": True,
        },
        "cohere": {
            "name": "Cohere",
            "requires_api_key": True,
            "models": ["embed-english-v3", "embed-multilingual-v3", "embed-english-light-v3", "embed-multilingual-light-v3"],
            "default_dimensions": 1024,
            "cloud": True,
        },
        "ollama": {
            "name": "Ollama",
            "requires_api_key": False,
            "models": ["nomic-embed-text", "mxbai-embed-large", "snowflake-arctic-embed", "bge-large"],
            "default_dimensions": 768,
            "cloud": False,
            "local_server": True,
        },
        "sentence-transformers": {
            "name": "Sentence Transformers",
            "requires_api_key": False,
            "models": ["all-MiniLM-L6-v2", "all-mpnet-base-v2", "paraphrase-multilingual-MiniLM-L12-v2"],
            "default_dimensions": 384,
            "cloud": False,
            "local": True,
        },
    }
    
    return info.get(provider_name, {"name": provider_name, "unknown": True})
