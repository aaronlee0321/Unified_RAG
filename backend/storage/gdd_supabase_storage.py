"""
Supabase storage adapter for GDD RAG
Replaces local JSON file storage with Supabase
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Optional, Any
import json

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.supabase_client import (
    get_supabase_client,
    vector_search_gdd_chunks,
    insert_gdd_document,
    insert_gdd_chunks,
    get_gdd_documents,
    delete_gdd_document
)
# Import from local gdd_rag_backbone (now included in unified_rag_app)
from gdd_rag_backbone.llm_providers import QwenProvider, make_embedding_func
from gdd_rag_backbone.rag_backend.chunk_qa import (
    ChunkRecord,
    _embed_texts,
    _normalize_vector,
    _score_chunks,
    _rerank_with_cross_encoder,
    _select_top_chunks,
    _extract_evidence_spans,
    _filter_chunks_by_evidence,
)

# Check if Supabase is configured
USE_SUPABASE = bool(os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_KEY'))


def get_gdd_top_chunks_supabase(
    doc_ids: List[str],
    question: str,
    provider,
    top_k: int = 8,
    per_doc_limit: Optional[int] = None,
    use_rrf: bool = True,
    filter_by_evidence: bool = True,
) -> List[Dict[str, Any]]:
    """
    Get top chunks from Supabase for a question.
    
    This replaces get_markdown_top_chunks but uses Supabase instead of JSON files.
    """
    if not USE_SUPABASE:
        raise ValueError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY in .env")
    
    if not doc_ids:
        raise ValueError("At least one doc_id is required.")
    
    unique_ids = list(dict.fromkeys(doc_ids))
    
    # Embed the question
    try:
        question_embedding = _embed_texts(provider, [question], use_cache=True)[0]
        question_embedding = _normalize_vector(question_embedding)
    except Exception as e:
        raise Exception(f"Failed to embed question: {e}")
    
    # Search Supabase for each document
    all_chunks = []
    all_scored = []
    
    for doc_id in unique_ids:
        # Use Supabase vector search
        # Use low threshold - reranking will filter quality later
        search_results = vector_search_gdd_chunks(
            query_embedding=question_embedding,
            limit=top_k * 2,  # Get more for filtering
            threshold=0.2,  # Low threshold - reranking will filter quality later
            doc_id=doc_id
        )
        
        # Convert results to ChunkRecord format with similarity scores
        for result in search_results:
            chunk_id = result.get('chunk_id', f"{doc_id}_{len(all_chunks)}")
            content = result.get('content', '')
            similarity = result.get('similarity', 0.0)
            
            chunk = ChunkRecord(
                chunk_id=chunk_id,
                doc_id=doc_id,
                content=content
            )
            
            all_chunks.append(chunk)
            all_scored.append((similarity, chunk))
    
    if not all_scored:
        return []
    
    # Use similarity scores from Supabase directly
    scored = all_scored
    
    # Apply evidence filtering
    if filter_by_evidence:
        scored = _filter_chunks_by_evidence(question, scored, min_evidence_score=0.15, keep_top_n=10)
    
    # Re-rank with cross-encoder
    reranked = _rerank_with_cross_encoder(question, scored, provider=provider, top_n=min(12, len(scored)))
    
    # Select top chunks
    selected = _select_top_chunks(
        reranked,
        top_k=top_k,
        per_doc_limit=per_doc_limit or (2 if len(unique_ids) > 1 else None),
    )
    
    # Add evidence spans to results
    results = []
    for score, record in selected:
        evidence_spans = _extract_evidence_spans(question, record.content, max_spans=3)
        results.append({
            "doc_id": record.doc_id,
            "chunk_id": record.chunk_id,
            "content": record.content,
            "score": score,
            "evidence_spans": evidence_spans,
        })
    
    return results


def list_gdd_documents_supabase() -> List[Dict[str, Any]]:
    """
    List all GDD documents from Supabase.
    
    Returns:
        List of document metadata dictionaries
    """
    if not USE_SUPABASE:
        return []
    
    try:
        docs = get_gdd_documents()
        # Convert to expected format
        result = []
        for doc in docs:
            result.append({
                "doc_id": doc.get("doc_id", ""),
                "file_path": doc.get("file_path", ""),
                "chunks_count": doc.get("chunks_count", 0),
                "name": doc.get("name", doc.get("doc_id", "")),
                "updated_at": doc.get("updated_at"),
                "status": "ready" if doc.get("chunks_count", 0) > 0 else "indexed"
            })
        return result
    except Exception as e:
        print(f"Error listing GDD documents from Supabase: {e}")
        return []


def index_gdd_chunks_to_supabase(
    doc_id: str,
    chunks: List[Dict],
    provider
) -> bool:
    """
    Index GDD chunks to Supabase with embeddings.
    
    Args:
        doc_id: Document ID
        chunks: List of chunk dictionaries from MarkdownChunker
        provider: LLM provider for embeddings
    
    Returns:
        True if successful
    """
    if not USE_SUPABASE:
        raise ValueError("Supabase is not configured")
    
    try:
        # Create embedding function
        embedding_func = make_embedding_func(provider)
        
        # Prepare chunks for Supabase
        supabase_chunks = []
        for i, chunk in enumerate(chunks):
            chunk_id = chunk.get("chunk_id") or f"{doc_id}_chunk_{i}"
            content = chunk.get("content", "")
            
            # Generate embedding
            try:
                embedding = embedding_func([content])[0]
            except Exception as e:
                print(f"Warning: Failed to embed chunk {chunk_id}: {e}")
                continue
            
            supabase_chunks.append({
                "chunk_id": chunk_id,
                "doc_id": doc_id,
                "content": content,
                "embedding": embedding,
                "metadata": {
                    "chunk_index": i,
                    "section": chunk.get("section", ""),
                    "metadata": chunk.get("metadata", {})
                }
            })
        
        # Insert document metadata
        file_path = chunks[0].get("file_path", "") if chunks else ""
        doc_name = Path(file_path).name if file_path else doc_id
        
        insert_gdd_document(
            doc_id=doc_id,
            name=doc_name,
            file_path=file_path
        )
        
        # Insert chunks
        inserted_count = insert_gdd_chunks(supabase_chunks)
        
        print(f"Indexed {inserted_count} chunks for document {doc_id} to Supabase")
        return True
        
    except Exception as e:
        raise Exception(f"Error indexing chunks to Supabase: {e}")

