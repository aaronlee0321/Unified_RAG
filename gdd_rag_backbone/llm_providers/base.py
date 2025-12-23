"""
Abstract base interfaces for LLM and embedding providers.

This module defines the protocols that all provider implementations must satisfy,
ensuring provider-agnostic code throughout the rest of the system.
"""
from typing import List, Protocol, Optional, Dict, Any


class LlmProvider(Protocol):
    """
    Protocol defining the interface for LLM providers.
    
    Any class implementing this protocol can be used as an LLM provider
    throughout the system.
    """
    
    def llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history_messages: Optional[List[Dict[str, str]]] = None,
        **kwargs: Any
    ) -> str:
        """
        Generate a text completion from the LLM.
        
        Args:
            prompt: The user prompt/message
            system_prompt: Optional system message to set behavior
            history_messages: Optional list of previous messages in format
                [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
            **kwargs: Additional provider-specific parameters
        
        Returns:
            The generated text response
        """
        ...


class EmbeddingProvider(Protocol):
    """
    Protocol defining the interface for embedding providers.
    
    Any class implementing this protocol can be used as an embedding provider
    throughout the system.
    """
    
    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.
        
        Args:
            texts: List of text strings to embed
        
        Returns:
            List of embedding vectors, where each vector is a list of floats
        """
        ...


def make_llm_model_func(provider: LlmProvider):
    """
    Create a function compatible with RAG-Anything's LLM interface.
    
    LightRAG wraps the LLM function with priority_limit_async_func_call, which
    expects an async function. We wrap the synchronous provider.llm() call here.
    
    Args:
        provider: An instance of LlmProvider
    
    Returns:
        An async function that matches LightRAG's expected LLM signature
    """
    async def llm_func(prompt: str, system_prompt: Optional[str] = None, **kwargs: Any) -> str:
        """
        Async wrapper function for RAG-Anything compatibility.
        
        LightRAG's priority_limit_async_func_call awaits this function, so it must
        be async. We wrap the synchronous provider.llm() call in asyncio.to_thread
        to avoid blocking the event loop.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            **kwargs: Additional parameters passed to the provider
        
        Returns:
            Generated text response
        """
        import asyncio
        # Run synchronous llm() in thread pool to avoid blocking
        return await asyncio.to_thread(
            provider.llm,
            prompt=prompt,
            system_prompt=system_prompt,
            **kwargs
        )
    
    return llm_func


def make_embedding_func(provider: EmbeddingProvider):
    """
    Create a function compatible with RAG-Anything's embedding interface.
    
    LightRAG expects an EmbeddingFunc instance (not a plain function) that wraps
    the actual embedding function and makes it async-compatible.
    
    Args:
        provider: An instance of EmbeddingProvider
    
    Returns:
        An EmbeddingFunc instance that matches LightRAG's expected interface
    """
    try:
        from lightrag.utils import EmbeddingFunc
    except ImportError:
        # Fallback if LightRAG not available - return plain function with embedding_dim
        def embedding_func(text_list: List[str]) -> List[List[float]]:
            """Wrapper function for RAG-Anything compatibility."""
            return provider.embed(text_list)
        
        embedding_func.embedding_dim = getattr(provider, 'embedding_dim', 1024)
        return embedding_func
    
    # Get embedding dimension from provider
    embedding_dim = getattr(provider, 'embedding_dim', 1024)
    
    # Create async wrapper function (EmbeddingFunc.__call__ awaits the function)
    async def async_embedding_func(text_list: List[str]) -> List[List[float]]:
        """
        Async wrapper function for the embedding provider.
        
        EmbeddingFunc expects an async function that it will await.
        We wrap the synchronous provider.embed() call here.
        
        Args:
            text_list: List of text strings to embed
        
        Returns:
            List of embedding vectors
        """
        import asyncio
        # Run synchronous embed() in thread pool to avoid blocking
        return await asyncio.to_thread(provider.embed, text_list)
    
    # Wrap in EmbeddingFunc class (makes it compatible with LightRAG)
    # lightrag-hku requires max_token_size parameter
    try:
        embedding_func = EmbeddingFunc(
            embedding_dim=embedding_dim,
            func=async_embedding_func,
            max_token_size=8192,  # Default token size for embeddings
        )
    except TypeError:
        # Fallback for different API versions
        embedding_func = EmbeddingFunc(
            embedding_dim=embedding_dim,
            func=async_embedding_func,
        )
    
    return embedding_func

