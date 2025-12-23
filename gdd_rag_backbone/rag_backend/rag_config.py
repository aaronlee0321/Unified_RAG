"""
RAG-Anything configuration and instance factory.
"""
from __future__ import annotations

# Import patch FIRST, before any raganything imports
from gdd_rag_backbone.rag_backend import lightrag_patch  # noqa: F401

from pathlib import Path
from typing import Callable, Optional, Union
from raganything import RAGAnything, RAGAnythingConfig
from gdd_rag_backbone.config import (
    DEFAULT_WORKING_DIR,
    DEFAULT_PARSER,
    DEFAULT_PARSE_METHOD,
    DEFAULT_ENABLE_IMAGE_PROCESSING,
    DEFAULT_ENABLE_TABLE_PROCESSING,
    DEFAULT_ENABLE_EQUATION_PROCESSING,
)


def get_rag_instance(
    llm_func: Optional[Callable] = None,
    embedding_func: Optional[Callable] = None,
    vision_model_func: Optional[Callable] = None,
    working_dir: Optional[Union[Path, str]] = None,
    workspace: Optional[str] = None,
    parser: Optional[str] = None,
    parse_method: Optional[str] = None,
    enable_image_processing: Optional[bool] = None,
    enable_table_processing: Optional[bool] = None,
    enable_equation_processing: Optional[bool] = None,
    **lightrag_kwargs
) -> RAGAnything:
    """
    Create and configure a RAGAnything instance.
    
    Args:
        llm_func: LLM function for text generation (compatible with RAG-Anything)
        embedding_func: Embedding function for vector generation (compatible with RAG-Anything)
        vision_model_func: Optional vision model function for image understanding
        working_dir: Working directory for RAG storage (defaults to DEFAULT_WORKING_DIR)
        parser: Parser choice - "mineru" or "docling" (defaults to DEFAULT_PARSER)
        parse_method: Parse method - "auto", "layout", "ocr", etc. (defaults to DEFAULT_PARSE_METHOD)
        enable_image_processing: Whether to process images (defaults to DEFAULT_ENABLE_IMAGE_PROCESSING)
        enable_table_processing: Whether to process tables (defaults to DEFAULT_ENABLE_TABLE_PROCESSING)
        enable_equation_processing: Whether to process equations (defaults to DEFAULT_ENABLE_EQUATION_PROCESSING)
        **lightrag_kwargs: Additional keyword arguments passed to LightRAG initialization
    
    Returns:
        Configured RAGAnything instance
    """
    # Note: embedding_dim is configured in raganything's LightRAG call via patch
    # The patch automatically uses self.embedding_dim from the EmbeddingFunc
    # Remove vector_db_storage_cls_kwargs from lightrag_kwargs since RAGAnything doesn't accept it
    # (it's handled inside raganything's LightRAG initialization)
    lightrag_kwargs.pop('vector_db_storage_cls_kwargs', None)
    
    # Convert working_dir to Path if string
    if working_dir is None:
        working_dir = DEFAULT_WORKING_DIR
    elif isinstance(working_dir, str):
        working_dir = Path(working_dir)
    
    # Ensure working directory exists
    working_dir.mkdir(parents=True, exist_ok=True)
    
    # Create RAGAnythingConfig instance with all configuration parameters
    rag_config = RAGAnythingConfig(
        working_dir=str(working_dir),
        parser=parser or DEFAULT_PARSER,
        parse_method=parse_method or DEFAULT_PARSE_METHOD,
        enable_image_processing=enable_image_processing if enable_image_processing is not None else DEFAULT_ENABLE_IMAGE_PROCESSING,
        enable_table_processing=enable_table_processing if enable_table_processing is not None else DEFAULT_ENABLE_TABLE_PROCESSING,
        enable_equation_processing=enable_equation_processing if enable_equation_processing is not None else DEFAULT_ENABLE_EQUATION_PROCESSING,
    )
    
    # Pass workspace to LightRAG via lightrag_kwargs (workspace is a LightRAG parameter, not RAGAnything)
    if workspace:
        lightrag_kwargs['workspace'] = workspace
    
    # Create RAGAnything instance with config object
    # Note: embedding_dim is now set in raganything's LightRAG call via patch
    # Workspace is passed to LightRAG via lightrag_kwargs for document isolation
    # Pass lightrag_kwargs as a named parameter (not unpacked) since it's a RAGAnything field
    rag = RAGAnything(
        config=rag_config,
        llm_model_func=llm_func,
        embedding_func=embedding_func,
        vision_model_func=vision_model_func,
        lightrag_kwargs=lightrag_kwargs,
    )
    
    return rag

