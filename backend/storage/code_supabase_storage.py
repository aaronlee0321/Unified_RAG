"""
Supabase storage adapter for Code Q&A
Replaces LanceDB with Supabase for code chunk storage and retrieval
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Optional, Any

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.supabase_client import (
    vector_search_code_chunks,
    get_code_files,
    insert_code_file,
    insert_code_chunks,
)
# Import from local gdd_rag_backbone (now included in unified_rag_app)
from gdd_rag_backbone.llm_providers import QwenProvider, make_embedding_func

# Check if Supabase is configured
USE_SUPABASE = bool(os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_KEY'))


def normalize_path_consistent(path: str) -> Optional[str]:
    """
    Normalize file path consistently for matching.
    Same function as in code_qa/app.py - uses normcase for case-insensitive matching
    """
    if path is None:
        return None
    try:
        p_str = str(path).strip()
        if not p_str:
            return None
        # Always convert to absolute and normalize case (normcase)
        abs_path = os.path.abspath(p_str)
        norm_path = os.path.normcase(abs_path)
        return norm_path
    except Exception:
        return None


def search_code_chunks_supabase(
    query: str,
    query_embedding: List[float],
    limit: int = 20,
    threshold: float = 0.2,
    file_paths: Optional[List[str]] = None,
    chunk_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search code chunks in Supabase using vector search.
    
    Args:
        query: Original query text (for logging)
        query_embedding: Query vector embedding (1024 dimensions)
        limit: Maximum number of results
        threshold: Similarity threshold
        file_paths: Optional list of file paths to filter by
        chunk_type: Optional chunk type ('method' or 'class')
    
    Returns:
        List of matching chunks with similarity scores
    """
    if not USE_SUPABASE:
        raise ValueError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY in .env")
    
    # Search for each file path if filters are provided
    all_results = []
    
    if file_paths:
        # Normalize file paths for filtering
        normalized_paths = {normalize_path_consistent(p) for p in file_paths if normalize_path_consistent(p)}
        
        for file_path in normalized_paths:
            results = vector_search_code_chunks(
                query_embedding=query_embedding,
                limit=limit,
                threshold=threshold,
                file_path=file_path,
                chunk_type=chunk_type
            )
            all_results.extend(results)
        
        # Remove duplicates (same chunk might match multiple normalized paths)
        seen = set()
        unique_results = []
        for result in all_results:
            chunk_id = result.get('id')
            if chunk_id and chunk_id not in seen:
                seen.add(chunk_id)
                unique_results.append(result)
        all_results = unique_results
    else:
        # Search all files
        all_results = vector_search_code_chunks(
            query_embedding=query_embedding,
            limit=limit,
            threshold=threshold,
            file_path=None,
            chunk_type=chunk_type
        )
    
    # Sort by similarity (descending)
    all_results.sort(key=lambda x: x.get('similarity', 0.0), reverse=True)
    
    # Limit to requested number
    return all_results[:limit]


def get_code_chunks_for_files(
    file_paths: List[str],
    chunk_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get all chunks for specific files (direct lookup, not vector search).
    Useful for ensuring we get chunks from target files even if semantic search doesn't return them.
    
    Args:
        file_paths: List of file paths
        chunk_type: Optional chunk type filter
    
    Returns:
        List of chunks
    """
    if not USE_SUPABASE:
        return []
    
    try:
        from backend.storage.supabase_client import get_supabase_client
        
        client = get_supabase_client()
        all_chunks = []
        
        # Normalize paths
        normalized_paths = {normalize_path_consistent(p) for p in file_paths if normalize_path_consistent(p)}
        
        for norm_path in normalized_paths:
            query = client.table('code_chunks').select('*')
            
            # Filter by file_path
            query = query.eq('file_path', norm_path)
            
            # Filter by chunk_type if specified
            if chunk_type:
                query = query.eq('chunk_type', chunk_type)
            
            result = query.execute()
            
            if result.data:
                all_chunks.extend(result.data)
        
        return all_chunks
    except Exception as e:
        print(f"Error getting chunks for files: {e}")
        return []


def list_code_files_supabase() -> List[Dict[str, Any]]:
    """
    List all indexed code files from Supabase.
    
    Returns:
        List of file metadata dictionaries
    """
    if not USE_SUPABASE:
        return []
    
    try:
        files = get_code_files()
        return files
    except Exception as e:
        print(f"Error listing code files from Supabase: {e}")
        return []


def index_code_chunks_to_supabase(
    file_path: str,
    file_name: str,
    chunks: List[Dict],
    provider
) -> bool:
    """
    Index code chunks to Supabase with embeddings.
    
    Args:
        file_path: Full file path
        file_name: File name
        chunks: List of chunk dictionaries (methods or classes)
        provider: LLM provider for embeddings
    
    Returns:
        True if successful
    """
    if not USE_SUPABASE:
        raise ValueError("Supabase is not configured")
    
    try:
        # Normalize path
        normalized_path = normalize_path_consistent(file_path)
        
        # Insert file metadata
        insert_code_file(
            file_path=normalized_path or file_path,
            file_name=file_name,
            normalized_path=normalized_path or file_path
        )
        
        # Create embedding function
        embedding_func = make_embedding_func(provider)
        
        # Prepare chunks for Supabase
        supabase_chunks = []
        for chunk in chunks:
            chunk_type = chunk.get('chunk_type', 'method')  # 'method' or 'class'
            
            # Determine what to embed
            if chunk_type == 'method':
                text_to_embed = chunk.get('code', '') or chunk.get('source_code', '')
            else:  # class
                text_to_embed = chunk.get('source_code', '')
            
            if not text_to_embed:
                continue
            
            # Generate embedding
            try:
                embedding = embedding_func([text_to_embed])[0]
            except Exception as e:
                print(f"Warning: Failed to embed chunk: {e}")
                continue
            
            supabase_chunk = {
                "file_path": normalized_path or file_path,
                "chunk_type": chunk_type,
                "class_name": chunk.get('class_name'),
                "method_name": chunk.get('name') if chunk_type == 'method' else None,
                "source_code": chunk.get('source_code', ''),
                "code": chunk.get('code', '') if chunk_type == 'method' else None,
                "embedding": embedding,
                "doc_comment": chunk.get('doc_comment', ''),
                "constructor_declaration": chunk.get('constructor_declaration', ''),
                "method_declarations": chunk.get('method_declarations', ''),
                "code_references": chunk.get('references', ''),
                "metadata": {
                    "indexed_from": "code_qa",
                    "original_metadata": chunk.get('metadata', {})
                }
            }
            
            supabase_chunks.append(supabase_chunk)
        
        # Insert chunks
        inserted_count = insert_code_chunks(supabase_chunks)
        
        print(f"Indexed {inserted_count} code chunks for {file_name} to Supabase")
        return True
        
    except Exception as e:
        raise Exception(f"Error indexing code chunks to Supabase: {e}")

