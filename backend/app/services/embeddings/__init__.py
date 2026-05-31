"""Embedding providers for multiple backends."""

from app.services.embeddings.base import EmbeddingProvider
from app.services.embeddings.openai import OpenAIEmbeddingProvider
from app.services.embeddings.anthropic import AnthropicEmbeddingProvider
from app.services.embeddings.cohere import CohereEmbeddingProvider
from app.services.embeddings.ollama import OllamaEmbeddingProvider
from app.services.embeddings.sentence_transformers import SentenceTransformersProvider
from app.services.embeddings.factory import (
    get_embedding_provider,
    list_available_providers,
    get_provider_info,
    PROVIDER_REGISTRY,
)

__all__ = [
    "EmbeddingProvider",
    "OpenAIEmbeddingProvider",
    "AnthropicEmbeddingProvider",
    "CohereEmbeddingProvider",
    "OllamaEmbeddingProvider",
    "SentenceTransformersProvider",
    "get_embedding_provider",
    "list_available_providers",
    "get_provider_info",
    "PROVIDER_REGISTRY",
]
