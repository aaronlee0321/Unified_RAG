"""
LLM Provider abstractions and implementations.

This module provides pluggable interfaces for LLM and embedding providers,
allowing the system to work with multiple vendors (Qwen, Vertex AI, OpenAI, etc.).
"""

from gdd_rag_backbone.llm_providers.base import (
    EmbeddingProvider,
    LlmProvider,
    make_embedding_func,
    make_llm_model_func,
)
from gdd_rag_backbone.llm_providers.qwen_provider import QwenProvider
from gdd_rag_backbone.llm_providers.vertex_provider import VertexProvider
from gdd_rag_backbone.llm_providers.gemini_provider import GeminiProvider

__all__ = [
    "LlmProvider",
    "EmbeddingProvider",
    "make_llm_model_func",
    "make_embedding_func",
    "QwenProvider",
    "VertexProvider",
    "GeminiProvider",
]

