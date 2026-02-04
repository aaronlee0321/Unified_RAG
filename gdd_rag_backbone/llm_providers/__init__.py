"""
LLM Provider abstractions and implementations.

This module provides pluggable interfaces for LLM and embedding providers,
allowing the system to work with multiple vendors (Qwen, OpenAI, etc.).
"""

from gdd_rag_backbone.llm_providers.base import (
    EmbeddingProvider,
    LlmProvider,
    make_embedding_func,
    make_llm_model_func,
)
from gdd_rag_backbone.llm_providers.qwen_provider import QwenProvider

__all__ = [
    "LlmProvider",
    "EmbeddingProvider",
    "make_llm_model_func",
    "make_embedding_func",
    "QwenProvider",
]
