"""
Supabase client for vector storage
"""

import os
import sys
from typing import List, Dict, Optional, Any

# Workaround: Mock storage3 if not available (we don't use it)
try:
    from supabase import create_client, Client
except ImportError as e:
    if 'storage3' in str(e) or 'pyiceberg' in str(e):
        # Create a minimal mock for storage3
        class MockStorageException(Exception):
            pass
        
        sys.modules['storage3'] = type(sys)('storage3')
        sys.modules['storage3'].utils = type(sys)('storage3.utils')
        sys.modules['storage3'].utils.StorageException = MockStorageException
        
        # Try importing again
        from supabase import create_client, Client
    else:
        raise

from backend.shared.config import SUPABASE_URL, SUPABASE_KEY, SUPABASE_SERVICE_KEY

# Initialize Supabase clients (separate for anon and service_role)
supabase_anon: Client = None
supabase_service: Client = None

def get_supabase_client(use_service_key: bool = False) -> Client:
    """
    Get Supabase client instance.
    Maintains separate clients for anon and service_role keys.
    
    Args:
        use_service_key: If True, use service key (for admin operations)
    
    Returns:
        Supabase client instance
    """
    import logging
    logger = logging.getLogger(__name__)
    
    global supabase_anon, supabase_service
    
    if use_service_key:
        # Use service_role key
        logger.info("Getting Supabase client with service_role key...")
        if supabase_service is None:
            if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
                logger.error("SUPABASE_URL or SUPABASE_SERVICE_KEY not configured")
                raise ValueError("Supabase URL and service key must be configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env file.")
            logger.info(f"Creating service_role client with URL: {SUPABASE_URL[:30]}...")
            supabase_service = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            logger.info("✅ Service_role client created successfully")
        return supabase_service
    else:
        # Use anon key
        logger.info("Getting Supabase client with anon key...")
        if supabase_anon is None:
            if not SUPABASE_URL or not SUPABASE_KEY:
                logger.error("SUPABASE_URL or SUPABASE_KEY not configured")
                raise ValueError("Supabase URL and key must be configured. Set SUPABASE_URL and SUPABASE_KEY in .env file.")
            logger.info(f"Creating anon client with URL: {SUPABASE_URL[:30]}...")
            logger.info(f"Using anon key starting with: {SUPABASE_KEY[:20]}...")
            supabase_anon = create_client(SUPABASE_URL, SUPABASE_KEY)
            logger.info("✅ Anon client created successfully")
        return supabase_anon

def vector_search_gdd_chunks(
    query_embedding: List[float],
    limit: int = 10,
    threshold: float = 0.7,
    doc_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Perform vector search on GDD chunks using Supabase pgvector.
    
    Args:
        query_embedding: Query vector embedding (1024 dimensions)
        limit: Maximum number of results
        threshold: Similarity threshold (0.0 to 1.0)
        doc_id: Optional document ID to filter by
    
    Returns:
        List of matching chunks with similarity scores
    """
    try:
        client = get_supabase_client()
        
        result = client.rpc(
            'match_gdd_chunks',
            {
                'query_embedding': query_embedding,
                'match_threshold': threshold,
                'match_count': limit,
                'doc_id_filter': doc_id
            }
        ).execute()
        
        return result.data if result.data else []
    except Exception as e:
        raise Exception(f"Error in GDD vector search: {e}")

def vector_search_code_chunks(
    query_embedding: List[float],
    limit: int = 10,
    threshold: float = 0.7,
    file_path: Optional[str] = None,
    chunk_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Perform vector search on code chunks using Supabase pgvector.
    
    Args:
        query_embedding: Query vector embedding (1024 dimensions)
        limit: Maximum number of results
        threshold: Similarity threshold (0.0 to 1.0)
        file_path: Optional file path to filter by
        chunk_type: Optional chunk type ('method' or 'class') to filter by
    
    Returns:
        List of matching chunks with similarity scores
    """
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[Supabase Code Search] threshold={threshold}, limit={limit}, file_path={file_path}, chunk_type={chunk_type}")
        
        client = get_supabase_client()
        
        # If file_path is provided, try multiple matching strategies
        if file_path:
            results = []
            strategy_used = None
            
            # Strategy 1: Try with the provided path
            result = client.rpc(
                'match_code_chunks',
                {
                    'query_embedding': query_embedding,
                    'match_threshold': threshold,
                    'match_count': limit,
                    'file_path_filter': file_path,
                    'chunk_type_filter': chunk_type
                }
            ).execute()
            
            results = result.data if result.data else []
            if len(results) > 0:
                strategy_used = "Strategy 1 (provided path)"
                logger.info(f"[Supabase Code Search] {strategy_used}: Found {len(results)} chunks with path '{file_path}'")
            else:
                logger.info(f"[Supabase Code Search] Strategy 1 (provided path): No chunks found with path '{file_path}'")
            
            # Strategy 2: If no results, try with just the filename
            if len(results) == 0:
                filename = file_path.split('/')[-1] if '/' in file_path else (file_path.split('\\')[-1] if '\\' in file_path else file_path)
                logger.info(f"[Supabase Code Search] Trying Strategy 2 (filename only): '{filename}'")
                result = client.rpc(
                    'match_code_chunks',
                    {
                        'query_embedding': query_embedding,
                        'match_threshold': threshold,
                        'match_count': limit,
                        'file_path_filter': filename,
                        'chunk_type_filter': chunk_type
                    }
                ).execute()
                results = result.data if result.data else []
                if len(results) > 0:
                    strategy_used = f"Strategy 2 (filename: '{filename}')"
                    logger.info(f"[Supabase Code Search] {strategy_used}: Found {len(results)} chunks")
                else:
                    logger.info(f"[Supabase Code Search] Strategy 2 (filename): No chunks found")
            
            # Strategy 3: If still no results, try last 2-3 path segments
            if len(results) == 0 and ('/' in file_path or '\\' in file_path):
                path_parts = file_path.replace('\\', '/').split('/')
                if len(path_parts) >= 2:
                    last_segments = '/'.join(path_parts[-2:])
                    logger.info(f"[Supabase Code Search] Trying Strategy 3 (last segments): '{last_segments}'")
                    result = client.rpc(
                        'match_code_chunks',
                        {
                            'query_embedding': query_embedding,
                            'match_threshold': threshold,
                            'match_count': limit,
                            'file_path_filter': last_segments,
                            'chunk_type_filter': chunk_type
                        }
                    ).execute()
                    results = result.data if result.data else []
                    if len(results) > 0:
                        strategy_used = f"Strategy 3 (last segments: '{last_segments}')"
                        logger.info(f"[Supabase Code Search] {strategy_used}: Found {len(results)} chunks")
                    else:
                        logger.info(f"[Supabase Code Search] Strategy 3 (last segments): No chunks found")
            
            # Final summary
            if len(results) > 0:
                logger.info(f"[Supabase Code Search] SUCCESS: Found {len(results)} chunks using {strategy_used}")
            elif file_path:
                logger.warning(f"[Supabase Code Search] FAILED: No chunks found for path '{file_path}' after trying all strategies")
        else:
            # No file filter - search all
            result = client.rpc(
                'match_code_chunks',
                {
                    'query_embedding': query_embedding,
                    'match_threshold': threshold,
                    'match_count': limit,
                    'file_path_filter': None,
                    'chunk_type_filter': chunk_type
                }
            ).execute()
            results = result.data if result.data else []
            logger.info(f"[Supabase Code Search] No file filter: Found {len(results)} chunks")
        
        return results
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"[Supabase Code Search] Error: {e}")
        raise Exception(f"Error in Code vector search: {e}")

def insert_gdd_document(doc_id: str, name: str, file_path: Optional[str] = None, file_size: Optional[int] = None) -> Dict[str, Any]:
    """
    Insert or update a GDD document.
    
    Args:
        doc_id: Unique document ID
        name: Document name
        file_path: Optional file path
        file_size: Optional file size in bytes
    
    Returns:
        Inserted/updated document data
    """
    try:
        client = get_supabase_client(use_service_key=True)
        
        result = client.table('gdd_documents').upsert({
            'doc_id': doc_id,
            'name': name,
            'file_path': file_path,
            'file_size': file_size
        }, on_conflict='doc_id').execute()
        
        return result.data[0] if result.data else {}
    except Exception as e:
        raise Exception(f"Error inserting GDD document: {e}")

def insert_gdd_chunks(chunks: List[Dict[str, Any]]) -> int:
    """
    Insert GDD chunks with embeddings into Supabase.
    
    Args:
        chunks: List of chunk dictionaries with keys:
            - chunk_id: Unique chunk ID
            - doc_id: Document ID
            - content: Chunk content
            - embedding: Vector embedding (1024 dimensions)
            - metadata: Optional metadata dict
    
    Returns:
        Number of chunks inserted
    """
    try:
        client = get_supabase_client(use_service_key=True)
        
        # Prepare records for insertion
        records = []
        for chunk in chunks:
            embedding = chunk.get('embedding')
            
            # Ensure embedding is a list, not a string
            if embedding is not None:
                if isinstance(embedding, str):
                    # Try to parse string as JSON array
                    try:
                        import json
                        embedding = json.loads(embedding)
                    except:
                        # If parsing fails, skip this chunk
                        print(f"Warning: Could not parse embedding for chunk {chunk.get('chunk_id')}, skipping")
                        continue
                elif not isinstance(embedding, list):
                    print(f"Warning: Embedding is not a list for chunk {chunk.get('chunk_id')}, skipping")
                    continue
                
                # Ensure all values are floats
                try:
                    embedding = [float(x) for x in embedding]
                except (ValueError, TypeError):
                    print(f"Warning: Could not convert embedding to floats for chunk {chunk.get('chunk_id')}, skipping")
                    continue
            
            record = {
                'chunk_id': chunk['chunk_id'],
                'doc_id': chunk['doc_id'],
                'content': chunk['content'],
                'embedding': embedding,  # Now guaranteed to be a list of floats or None
                'metadata': chunk.get('metadata', {})
            }
            records.append(record)
        
        # Insert in batches (Supabase has limits)
        batch_size = 100
        total_inserted = 0
        
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            result = client.table('gdd_chunks').upsert(
                batch,
                on_conflict='chunk_id'
            ).execute()
            total_inserted += len(result.data) if result.data else 0
        
        return total_inserted
    except Exception as e:
        raise Exception(f"Error inserting GDD chunks: {e}")

def insert_code_file(file_path: str, file_name: str, normalized_path: str) -> Dict[str, Any]:
    """
    Insert or update a code file.
    
    Args:
        file_path: Full file path
        file_name: File name
        normalized_path: Normalized path for matching
    
    Returns:
        Inserted/updated file data
    """
    try:
        client = get_supabase_client(use_service_key=True)
        
        result = client.table('code_files').upsert({
            'file_path': file_path,
            'file_name': file_name,
            'normalized_path': normalized_path
        }, on_conflict='file_path').execute()
        
        return result.data[0] if result.data else {}
    except Exception as e:
        raise Exception(f"Error inserting code file: {e}")

def insert_code_chunks(chunks: List[Dict[str, Any]]) -> int:
    """
    Insert code chunks (methods/classes) with embeddings into Supabase.
    
    Args:
        chunks: List of chunk dictionaries with keys:
            - file_path: File path
            - chunk_type: 'method' or 'class'
            - class_name: Class name
            - method_name: Method name (for methods)
            - source_code: Source code
            - code: Method code (for methods)
            - embedding: Vector embedding (1024 dimensions)
            - doc_comment: Optional doc comment
            - constructor_declaration: For classes
            - method_declarations: For classes
            - references: References
            - metadata: Optional metadata dict
    
    Returns:
        Number of chunks inserted
    """
    try:
        client = get_supabase_client(use_service_key=True)
        
        # Prepare records for insertion
        records = []
        for chunk in chunks:
            record = {
                'file_path': chunk['file_path'],
                'chunk_type': chunk['chunk_type'],
                'class_name': chunk.get('class_name'),
                'method_name': chunk.get('method_name'),
                'source_code': chunk['source_code'],
                'code': chunk.get('code'),
                'embedding': chunk.get('embedding'),
                'doc_comment': chunk.get('doc_comment', ''),
                'constructor_declaration': chunk.get('constructor_declaration', ''),
                'method_declarations': chunk.get('method_declarations', ''),
                'code_references': chunk.get('references', ''),  # Maps from 'references' key to 'code_references' column
                'metadata': chunk.get('metadata', {})
            }
            records.append(record)
        
        # Insert in batches
        batch_size = 100
        total_inserted = 0
        
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            result = client.table('code_chunks').insert(batch).execute()
            total_inserted += len(result.data) if result.data else 0
        
        return total_inserted
    except Exception as e:
        raise Exception(f"Error inserting code chunks: {e}")

def get_gdd_documents() -> List[Dict[str, Any]]:
    """
    Get all GDD documents.
    
    Returns:
        List of document dictionaries
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        logger.info("get_gdd_documents() called")
        logger.info("Getting Supabase client...")
        client = get_supabase_client()
        logger.info("Supabase client obtained, querying gdd_documents table...")
        
        result = client.table('gdd_documents').select('*').order('name').execute()
        logger.info(f"Query executed, received {len(result.data) if result.data else 0} documents")
        
        if result.data and len(result.data) > 0:
            logger.info(f"Sample document: {result.data[0].get('name', 'N/A')}")
        
        return result.data if result.data else []
    except Exception as e:
        import traceback
        logger.error(f"❌ Error fetching GDD documents: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise Exception(f"Error fetching GDD documents: {e}")

def get_code_files() -> List[Dict[str, Any]]:
    """
    Get all code files.
    
    Returns:
        List of file dictionaries
    """
    try:
        client = get_supabase_client()
        result = client.table('code_files').select('*').order('file_name').execute()
        return result.data if result.data else []
    except Exception as e:
        raise Exception(f"Error fetching code files: {e}")

def delete_gdd_document(doc_id: str) -> bool:
    """
    Delete a GDD document and all its chunks.
    
    Args:
        doc_id: Document ID to delete
    
    Returns:
        True if successful
    """
    try:
        client = get_supabase_client(use_service_key=True)
        # Cascade delete will remove chunks automatically
        result = client.table('gdd_documents').delete().eq('doc_id', doc_id).execute()
        return True
    except Exception as e:
        raise Exception(f"Error deleting GDD document: {e}")

def delete_code_file(file_path: str) -> bool:
    """
    Delete a code file and all its chunks.
    
    Args:
        file_path: File path to delete
    
    Returns:
        True if successful
    """
    try:
        client = get_supabase_client(use_service_key=True)
        # Cascade delete will remove chunks automatically
        result = client.table('code_files').delete().eq('file_path', file_path).execute()
        return True
    except Exception as e:
        raise Exception(f"Error deleting code file: {e}")
