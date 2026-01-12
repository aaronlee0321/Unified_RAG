"""
Search service for keyword extractor - shared by Tab 1 and Tab 2.
Uses keyword_search_documents RPC function.
"""
from typing import List, Dict, Optional, Any
from backend.storage.supabase_client import get_supabase_client


def keyword_search(
    keyword: str,
    limit: int = 100,
    doc_id_filter: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search keyword documents using PostgreSQL full-text search.
    This is shared by both Tab 1 (GDD RAG) and Tab 2 (Document Explainer).
    
    Args:
        keyword: Search keyword
        limit: Maximum number of results
        doc_id_filter: Optional document ID to filter by
    
    Returns:
        List of search results with doc_id, doc_name, content, section_heading, relevance
    """
    if not keyword or not keyword.strip():
        return []
    
    client = get_supabase_client()
    
    # Use the PostgreSQL function for keyword search
    result = client.rpc(
        'keyword_search_documents',
        {
            'search_query': keyword.strip(),
            'match_count': limit,
            'doc_id_filter': doc_id_filter
        }
    ).execute()
    
    return result.data if result.data else []



