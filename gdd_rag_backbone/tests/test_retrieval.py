"""
Tests for RAG retrieval and querying.
"""
import pytest
import asyncio
from gdd_rag_backbone.rag_backend import ask_question, debug_query


def test_ask_question_empty_doc_id():
    """Test that asking question with empty doc_id raises ValueError."""
    async def run_test():
        with pytest.raises(ValueError):
            await ask_question("", "test query")
    
    asyncio.run(run_test())


def test_ask_question_empty_query():
    """Test that asking empty question raises ValueError."""
    async def run_test():
        with pytest.raises(ValueError):
            await ask_question("test_doc", "")
    
    asyncio.run(run_test())


def test_ask_question_nonexistent_doc():
    """Test that asking question about nonexistent doc raises ValueError."""
    async def run_test():
        with pytest.raises(ValueError) as exc_info:
            await ask_question("nonexistent_doc", "test query")
        
        assert "No RAG instance found" in str(exc_info.value)
    
    asyncio.run(run_test())


def test_ask_question_structure():
    """Test that ask_question function exists and has correct signature."""
    import inspect
    from gdd_rag_backbone.rag_backend.query_engine import ask_question
    
    sig = inspect.signature(ask_question)
    
    # Check required parameters
    assert "doc_id" in sig.parameters
    assert "query" in sig.parameters
    
    # Check it's async
    assert inspect.iscoroutinefunction(ask_question)


def test_debug_query_structure():
    """Test that debug_query function exists and has correct signature."""
    import inspect
    from gdd_rag_backbone.rag_backend.query_engine import debug_query
    
    sig = inspect.signature(debug_query)
    
    # Check required parameters
    assert "doc_id" in sig.parameters
    assert "query" in sig.parameters
    
    # Check it's async
    assert inspect.iscoroutinefunction(debug_query)

