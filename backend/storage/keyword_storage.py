"""
Storage adapter for keyword tables (keyword_documents, keyword_chunks).
This routes keyword_extractor services to use unified_rag_app's Supabase connection.
"""
from typing import List, Dict, Optional, Any
from backend.storage.supabase_client import get_supabase_client


def list_keyword_documents() -> List[Dict[str, Any]]:
    """
    List all keyword documents.
    Equivalent to keyword_extractor's storage_service.list_documents()
    
    Returns:
        List of document metadata dictionaries
    """
    client = get_supabase_client()
    
    result = client.table('keyword_documents').select('*').order('name').execute()
    return result.data if result.data else []


def insert_document(
    doc_id: str,
    name: str,
    file_path: Optional[str] = None,
    file_size: Optional[int] = None,
    full_text: Optional[str] = None
) -> Dict[str, Any]:
    """
    Insert or update a keyword document.
    Equivalent to keyword_extractor's storage_service.insert_document()
    
    Args:
        doc_id: Document ID
        name: Document name
        file_path: Optional file path
        file_size: Optional file size
        full_text: Optional full text content
    
    Returns:
        Inserted/updated document dict
    """
    client = get_supabase_client(use_service_key=True)
    
    result = client.table('keyword_documents').upsert({
        'doc_id': doc_id,
        'name': name,
        'file_path': file_path,
        'file_size': file_size,
        'full_text': full_text,
    }).execute()
    
    return result.data[0] if result.data else None


def insert_chunks(
    doc_id: str,
    chunks: List[Dict[str, Any]]
) -> int:
    """
    Insert keyword chunks for a document.
    Equivalent to keyword_extractor's storage_service.insert_chunks()
    
    Args:
        doc_id: Document ID
        chunks: List of dicts with keys: chunk_id, content, section_heading, chunk_index
    
    Returns:
        Number of chunks inserted
    """
    client = get_supabase_client(use_service_key=True)
    
    # Delete existing chunks for this document
    client.table('keyword_chunks').delete().eq('doc_id', doc_id).execute()
    
    # Insert new chunks
    if chunks:
        result = client.table('keyword_chunks').insert(chunks).execute()
        return len(result.data) if result.data else 0
    return 0


def delete_document(doc_id: str) -> bool:
    """
    Delete a keyword document and all its chunks.
    Equivalent to keyword_extractor's storage_service.delete_document()
    
    Args:
        doc_id: Document ID
    
    Returns:
        True if deleted successfully
    """
    client = get_supabase_client(use_service_key=True)
    
    result = client.table('keyword_documents').delete().eq('doc_id', doc_id).execute()
    return len(result.data) > 0 if result.data else False


# ============================================================================
# Keyword Aliases Functions
# ============================================================================

def insert_alias(keyword: str, alias: str, language: str = 'en') -> Dict[str, Any]:
    """
    Add an alias for a keyword.
    
    Args:
        keyword: Main keyword (e.g., "tank")
        alias: Alias term (e.g., "xe tăng", "armor")
        language: Language code ('en', 'vi', 'EN', 'VN')
    
    Returns:
        Inserted alias record
    """
    client = get_supabase_client(use_service_key=True)
    
    # Normalize language to lowercase
    lang_normalized = language.lower() if language else 'en'
    
    result = client.table('keyword_aliases').insert({
        'keyword': keyword.strip(),
        'alias': alias.strip(),
        'language': lang_normalized
    }).execute()
    
    return result.data[0] if result.data else None


def get_aliases_for_keyword(keyword: str) -> List[str]:
    """
    Get all aliases for a keyword (bidirectional lookup).
    Returns aliases where keyword matches, and also keywords where alias matches.
    
    Args:
        keyword: The keyword to find aliases for
    
    Returns:
        List of alias strings
    """
    client = get_supabase_client()
    keyword_lower = keyword.strip().lower()
    
    aliases = []
    
    # Find aliases where keyword matches
    result = client.table('keyword_aliases').select('alias').eq('keyword', keyword_lower).execute()
    aliases.extend([row['alias'] for row in (result.data or [])])
    
    # Also find reverse: where alias matches keyword
    result2 = client.table('keyword_aliases').select('keyword').eq('alias', keyword_lower).execute()
    aliases.extend([row['keyword'] for row in (result2.data or [])])
    
    return list(set(aliases))  # Remove duplicates


def find_keyword_by_alias(alias: str) -> List[Dict[str, Any]]:
    """
    Find all keywords that have this alias.
    
    Args:
        alias: The alias to search for
    
    Returns:
        List of dicts with keyword, alias, and language info
    """
    client = get_supabase_client()
    alias_lower = alias.strip().lower()
    
    # Find keywords where alias matches
    result = client.table('keyword_aliases').select('keyword, alias, language').eq('alias', alias_lower).execute()
    keywords = []
    
    if result.data:
        for row in result.data:
            keywords.append({
                'keyword': row['keyword'],
                'alias': row['alias'],
                'language': row['language']
            })
    
    # Also check if alias itself is a keyword (reverse lookup)
    result2 = client.table('keyword_aliases').select('keyword, alias, language').eq('keyword', alias_lower).execute()
    if result2.data:
        for row in result2.data:
            keywords.append({
                'keyword': row['alias'],  # Reverse: alias becomes keyword
                'alias': row['keyword'],
                'language': row['language']
            })
    
    # Remove duplicates based on keyword
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw['keyword'] not in seen:
            seen.add(kw['keyword'])
            unique_keywords.append(kw)
    
    return unique_keywords


def list_all_aliases(filter_language: Optional[str] = None, search_term: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List all keyword-alias mappings with optional filtering.
    
    Args:
        filter_language: Optional language filter ('en', 'vi', 'EN', 'VN')
        search_term: Optional search term to filter by keyword or alias
    
    Returns:
        List of alias records
    """
    client = get_supabase_client()
    
    query = client.table('keyword_aliases').select('*')
    
    if filter_language:
        # Normalize language for comparison
        lang_normalized = filter_language.lower()
        query = query.eq('language', lang_normalized)
    
    if search_term:
        search_lower = search_term.lower()
        # Search in both keyword and alias fields using OR
        query = query.or_(f'keyword.ilike.%{search_lower}%,alias.ilike.%{search_lower}%')
    
    result = query.order('keyword').execute()
    return result.data if result.data else []


def delete_alias(keyword: str, alias: str) -> bool:
    """
    Delete a specific alias.
    
    Args:
        keyword: The keyword
        alias: The alias to delete
    
    Returns:
        True if deleted successfully
    """
    if not keyword or not alias:
        return False
    
    client = get_supabase_client(use_service_key=True)
    
    keyword_clean = keyword.strip()
    alias_clean = alias.strip()
    
    try:
        # Strategy 1: Try exact match first (case-sensitive, fastest)
        result = client.table('keyword_aliases').delete().eq('keyword', keyword_clean).eq('alias', alias_clean).execute()
        if result.data and len(result.data) > 0:
            return True
        
        # Strategy 2: If exact match failed, find with case-insensitive search
        # Get all aliases for this keyword (case-insensitive)
        all_aliases = list_all_aliases()
        
        # Find matching record (case-insensitive)
        for row in all_aliases:
            if row['keyword'].lower() == keyword_clean.lower() and row['alias'].lower() == alias_clean.lower():
                # Delete using exact values from database
                exact_keyword = row['keyword']
                exact_alias = row['alias']
                result = client.table('keyword_aliases').delete().eq('keyword', exact_keyword).eq('alias', exact_alias).execute()
                return len(result.data) > 0 if result.data else False
        
        # No match found
        return False
        
    except Exception as e:
        # Log error but don't raise - return False to indicate failure
        import logging
        logging.error(f"Error deleting alias '{alias}' for keyword '{keyword}': {e}")
        return False


def get_all_keywords() -> List[str]:
    """
    Get list of all unique keywords (for dropdown/autocomplete).
    
    Returns:
        Sorted list of unique keyword strings
    """
    client = get_supabase_client()
    result = client.table('keyword_aliases').select('keyword').execute()
    keywords = list(set([row['keyword'] for row in (result.data or [])]))
    return sorted(keywords)


def list_aliases_grouped() -> Dict[str, Dict[str, Any]]:
    """
    List all aliases grouped by keyword (for frontend display).
    Returns data in the format expected by the frontend.
    
    Returns:
        Dict mapping keyword names to keyword objects with aliases
    """
    client = get_supabase_client()
    result = client.table('keyword_aliases').select('*').order('keyword').execute()
    
    if not result.data:
        return {}
    
    # Group by keyword
    grouped = {}
    for row in result.data:
        keyword = row['keyword']
        if keyword not in grouped:
            grouped[keyword] = {
                'id': f"keyword-{hash(keyword)}",  # Generate consistent ID
                'name': keyword,
                'language': row['language'].upper(),  # Match frontend format (EN/VN)
                'aliases': [],
                'createdAt': row['created_at']
            }
        
        grouped[keyword]['aliases'].append({
            'id': str(row['id']),
            'name': row['alias'],
            'createdAt': row['created_at']
        })
    
    return grouped

