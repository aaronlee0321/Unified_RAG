"""
Tests for document parsing and indexing.
"""
import pytest
import asyncio
from pathlib import Path
from gdd_rag_backbone.config import DEFAULT_DOCS_DIR
from gdd_rag_backbone.rag_backend import index_document


def test_index_document_missing_file():
    """Test that indexing a missing file raises FileNotFoundError."""
    async def run_test():
        with pytest.raises(FileNotFoundError):
            await index_document(
                doc_path="nonexistent.pdf",
                doc_id="test_doc",
            )
    
    asyncio.run(run_test())


def test_index_document_empty_doc_id():
    """Test that empty doc_id raises ValueError."""
    async def run_test():
        # Create a temporary file
        test_file = Path("/tmp/test_gdd_empty_id.pdf")
        test_file.touch()
        
        try:
            with pytest.raises(ValueError):
                await index_document(
                    doc_path=str(test_file),
                    doc_id="",
                )
        finally:
            if test_file.exists():
                test_file.unlink()
    
    asyncio.run(run_test())


def test_index_document_structure():
    """Test that index_document function exists and has correct signature."""
    import inspect
    from gdd_rag_backbone.rag_backend.indexing import index_document
    
    sig = inspect.signature(index_document)
    
    # Check required parameters
    assert "doc_path" in sig.parameters
    assert "doc_id" in sig.parameters
    
    # Check it's async
    assert inspect.iscoroutinefunction(index_document)

