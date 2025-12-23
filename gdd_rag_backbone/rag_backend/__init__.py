"""
RAG Backend - Integration with RAG-Anything for document indexing and querying.
"""

# Use lazy imports to avoid RAG-Anything import errors when not needed
# This allows the evaluation script to run without importing RAG-Anything

__all__ = [
    "index_document",
    "ask_question",
    "debug_query",
    "get_rag_instance",
    "RAGAnythingConfig",
]

# Lazy imports - only import when actually used
# This prevents ImportError when RAG-Anything isn't needed (e.g., evaluation script)
def __getattr__(name):
    """Lazy import for RAG-Anything related modules."""
    if name == "index_document":
        from gdd_rag_backbone.rag_backend.indexing import index_document
        return index_document
    elif name == "ask_question":
        from gdd_rag_backbone.rag_backend.query_engine import ask_question
        return ask_question
    elif name == "debug_query":
        from gdd_rag_backbone.rag_backend.query_engine import debug_query
        return debug_query
    elif name == "get_rag_instance":
        # Apply patch before importing RAG-Anything
        from gdd_rag_backbone.rag_backend import lightrag_patch  # noqa: F401
        from gdd_rag_backbone.rag_backend.rag_config import get_rag_instance
        return get_rag_instance
    elif name == "RAGAnythingConfig":
        # Apply patch before importing RAG-Anything
        from gdd_rag_backbone.rag_backend import lightrag_patch  # noqa: F401
        from gdd_rag_backbone.rag_backend.rag_config import RAGAnythingConfig
        return RAGAnythingConfig
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

