"""
Markdown chunking module for document-based chunking strategy.

This module provides chunking functionality for markdown files using
a structure-first approach with recursive fallback for long sections.
"""

from gdd_rag_backbone.markdown_chunking.chunker import MarkdownChunk, MarkdownChunker
from gdd_rag_backbone.markdown_chunking.markdown_parser import MarkdownParser
from gdd_rag_backbone.markdown_chunking.metadata_extractor import MetadataExtractor
from gdd_rag_backbone.markdown_chunking.tokenizer_utils import count_tokens

__all__ = [
    "MarkdownChunker",
    "MarkdownChunk",
    "MarkdownParser",
    "MetadataExtractor",
    "count_tokens",
]
