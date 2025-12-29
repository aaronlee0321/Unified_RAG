"""
Supabase storage adapter for GDD RAG
Replaces local JSON file storage with Supabase
"""

import os
import sys
import re
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
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

# Log Supabase configuration status (using print for early logging)
if USE_SUPABASE:
    print(f"[INFO] Supabase configured: URL={os.getenv('SUPABASE_URL', '')[:30]}...")
else:
    print("[WARNING] Supabase not configured - SUPABASE_URL or SUPABASE_KEY missing")


def _strip_section_number(section_name: str) -> str:
    """
    Strip numbers and dots from section names for name-only matching.
    
    Examples:
    - "4. Thànhphần" -> "Thànhphần"
    - "7.3 Tankhạngnặng" -> "Tankhạngnặng"
    - "Thànhphần" -> "Thànhphần"
    """
    # Remove leading numbers, dots, and spaces
    cleaned = re.sub(r'^\d+\.\d*\.?\s*', '', section_name)
    # Remove any remaining leading/trailing whitespace
    return cleaned.strip()


def load_gdd_chunks_from_supabase(
    doc_ids: List[str],
    section_path_filter: Optional[str] = None,
    content_type_filter: Optional[str] = None,
    numbered_header_filter: Optional[str] = None
) -> List[ChunkRecord]:
    """
    Load ALL chunks for given doc_ids from Supabase with optional filters.
    Matches load_markdown_doc_chunks() logic but uses Supabase.
    
    IMPORTANT: chunk_id in Supabase is stored as full format: {doc_id}_{chunk_id}
    This matches the local storage format where keys are {doc_id}_{chunk_id}
    
    Args:
        doc_ids: List of document IDs
        section_path_filter: Optional section path to filter by (ILIKE match)
        content_type_filter: Optional content type to filter by
        numbered_header_filter: Optional numbered header to filter by (from metadata)
    
    Returns:
        List of ChunkRecord objects with chunk_id in full format
    """
    import logging
    logger = logging.getLogger(__name__)
    
    if not USE_SUPABASE:
        return []
    
    client = get_supabase_client()
    all_chunks = []
    
    logger.info(f"[load_gdd_chunks_from_supabase] Loading chunks for doc_ids: {doc_ids}")
    logger.info(f"[load_gdd_chunks_from_supabase] Filters - section_path: {section_path_filter}, content_type: {content_type_filter}, numbered_header: {numbered_header_filter}")
    
    for doc_id in doc_ids:
        logger.info(f"[load_gdd_chunks_from_supabase] Querying doc_id: {doc_id}")
        
        # Build query with filters
        query = client.table('gdd_chunks').select('chunk_id, doc_id, content, section_path, content_type, metadata').eq('doc_id', doc_id)
        
        # Apply section_path filter (match by name only, ignore numbers)
        # NOTE: This is a soft filter - we load chunks and let vector search prioritize
        # Only apply if we don't have numbered_header_filter (to avoid double-filtering)
        if section_path_filter and not numbered_header_filter:
            # Strip numbers from filter to match by name only
            section_name_only = _strip_section_number(section_path_filter)
            logger.info(f"[load_gdd_chunks_from_supabase] Applying section_path filter: {section_name_only}")
            query = query.ilike('section_path', f'%{section_name_only}%')
        elif section_path_filter and numbered_header_filter:
            # If both are set, prefer numbered_header_filter (more precise)
            # But still apply section_path as a soft filter
            section_name_only = _strip_section_number(section_path_filter)
            logger.info(f"[load_gdd_chunks_from_supabase] Applying section_path filter (with numbered_header): {section_name_only}")
            query = query.ilike('section_path', f'%{section_name_only}%')
        
        # Apply content_type filter
        if content_type_filter:
            logger.info(f"[load_gdd_chunks_from_supabase] Applying content_type filter: {content_type_filter}")
            query = query.eq('content_type', content_type_filter)
        
        result = query.execute()
        logger.info(f"[load_gdd_chunks_from_supabase] Retrieved {len(result.data or [])} raw chunks from Supabase for doc_id: {doc_id}")
        
        chunks_before_header_filter = 0
        chunks_after_header_filter = 0
        
        for row in (result.data or []):
            chunk_id = row.get('chunk_id', '')
            content = row.get('content', '')
            result_doc_id = row.get('doc_id', '')
            section_path = row.get('section_path', '')
            
            chunks_before_header_filter += 1
            
            # Apply numbered_header filter from metadata if specified (match by name only, ignore numbers)
            if numbered_header_filter:
                metadata = row.get('metadata', {})
                numbered_header = metadata.get('numbered_header', '') if isinstance(metadata, dict) else ''
                # Strip numbers from both filter and header for name-only matching
                filter_name = _strip_section_number(numbered_header_filter).lower().strip()
                header_name = _strip_section_number(str(numbered_header)).lower().strip()
                # Also check section_path as fallback
                section_path_name = _strip_section_number(section_path).lower().strip()
                # Match if filter name is in header name OR header name is in filter name (for partial matches)
                # Also check if they're equal (exact match after stripping numbers)
                # Make matching more lenient - remove spaces and special chars for comparison
                filter_clean = re.sub(r'[^\w]', '', filter_name.lower())
                header_clean = re.sub(r'[^\w]', '', header_name.lower())
                section_clean = re.sub(r'[^\w]', '', section_path_name.lower())
                
                matches = (
                    filter_name == header_name or
                    filter_name in header_name or
                    header_name in filter_name or
                    filter_name == section_path_name or
                    filter_name in section_path_name or
                    section_path_name in filter_name or
                    # More lenient: compare cleaned versions
                    filter_clean == header_clean or
                    filter_clean in header_clean or
                    header_clean in filter_clean or
                    filter_clean == section_clean or
                    filter_clean in section_clean or
                    section_clean in filter_clean
                )
                
                # Log first 3 chunks to show filtering in action
                if chunks_before_header_filter <= 3:
                    logger.info(f"[load_gdd_chunks_from_supabase] Chunk {chunks_before_header_filter}:")
                    logger.info(f"  - chunk_id: {chunk_id}")
                    logger.info(f"  - doc_id: {result_doc_id}")
                    logger.info(f"  - section_path: {section_path}")
                    logger.info(f"  - numbered_header: {numbered_header}")
                    logger.info(f"  - filter_name: '{filter_name}' vs header_name: '{header_name}' vs section_name: '{section_path_name}'")
                    logger.info(f"  - matches: {matches}")
                    logger.info(f"  - content preview: {content[:150]}...")
                
                if not matches:
                    if chunks_before_header_filter <= 3:
                        logger.info(f"  - ❌ FILTERED OUT")
                    continue
                
                if chunks_before_header_filter <= 3:
                    logger.info(f"  - ✓ KEPT")
            
            # Validate doc_id matches
            if result_doc_id == doc_id and content:
                all_chunks.append(ChunkRecord(
                    chunk_id=chunk_id,  # Use full format to match vectors
                    doc_id=doc_id,
                    content=content
                ))
                chunks_after_header_filter += 1
        
        logger.info(f"[load_gdd_chunks_from_supabase] Doc {doc_id}: {chunks_before_header_filter} chunks before numbered_header filter -> {chunks_after_header_filter} chunks after")
    
    logger.info(f"[load_gdd_chunks_from_supabase] Total chunks loaded: {len(all_chunks)}")
    return all_chunks


def load_gdd_vectors_from_supabase(doc_ids: List[str], normalize: bool = True) -> Dict[str, List[float]]:
    """
    Load ALL vectors for given doc_ids from Supabase.
    Matches load_markdown_chunk_vectors() logic but uses Supabase.
    
    IMPORTANT: chunk_id in Supabase is stored as full format: {doc_id}_{chunk_id}
    This matches the local storage format where __id__ is {doc_id}_{chunk_id}
    
    Args:
        doc_ids: List of document IDs
        normalize: If True, pre-normalize vectors
    
    Returns:
        Dictionary mapping chunk_id (full format) to vector
    """
    if not USE_SUPABASE:
        return {}
    
    client = get_supabase_client()
    vectors = {}
    allowed = set(doc_ids)
    
    for doc_id in doc_ids:
        # Get all chunks with embeddings for this doc_id
        result = client.table('gdd_chunks').select('chunk_id, doc_id, embedding').eq('doc_id', doc_id).execute()
        
        for row in (result.data or []):
            chunk_id = row.get('chunk_id', '')  # Full format: {doc_id}_{chunk_id}
            result_doc_id = row.get('doc_id', '')
            embedding = row.get('embedding')
            
            if chunk_id and embedding and result_doc_id in allowed:
                try:
                    # Convert to float list
                    float_vector = [float(v) for v in embedding]
                    if normalize:
                        float_vector = _normalize_vector(float_vector)
                    vectors[chunk_id] = float_vector  # Use full format chunk_id
                except (ValueError, TypeError):
                    continue
    
    return vectors


def get_gdd_top_chunks_supabase(
    doc_ids: List[str],
    question: str,
    provider,
    top_k: int = 8,
    per_doc_limit: Optional[int] = None,
    use_rrf: bool = True,
    filter_by_evidence: bool = True,
    use_hyde: bool = True,
    section_path_filter: Optional[str] = None,
    content_type_filter: Optional[str] = None,
    numbered_header_filter: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Get top chunks from Supabase for a question with enhanced retrieval.
    
    Enhanced pipeline:
    1. Parse section targets from query (@Result Screen, etc.)
    2. HYDE query expansion (optional)
    3. Load ALL chunks for doc_ids with filters
    4. Load ALL vectors for doc_ids
    5. Score chunks using _score_chunks() with RRF
    6. Filter by evidence
    7. Rerank with cross-encoder
    8. Select top chunks
    9. Group by section_path
    
    Args:
        doc_ids: List of document IDs
        question: User question
        provider: LLM provider
        top_k: Number of top chunks to return
        per_doc_limit: Maximum chunks per document
        use_rrf: Whether to use RRF fusion
        filter_by_evidence: Whether to filter by evidence score
        use_hyde: Whether to use HYDE query expansion
        section_path_filter: Optional section path filter
        content_type_filter: Optional content type filter
        numbered_header_filter: Optional numbered header filter
    
    Returns:
        (results_list, metrics_dict)
    """
    import logging
    import time
    logger = logging.getLogger(__name__)
    
    metrics = {
        "query": question,
        "doc_ids": doc_ids,
        "timing": {}
    }
    
    if not USE_SUPABASE:
        raise ValueError("Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY in .env")
    
    if not doc_ids:
        raise ValueError("At least one doc_id is required.")
    
    unique_ids = list(dict.fromkeys(doc_ids))
    
    # Step 1: Parse section targets from query
    parse_start = time.time()
    from backend.gdd_query_parser import (
        parse_section_targets, 
        extract_numbered_section_from_query,
        map_english_to_vietnamese_section
    )
    
    cleaned_query, query_filters = parse_section_targets(question)
    logger.info(f"[GDD Retrieval] ========== QUERY PARSING ==========")
    logger.info(f"[GDD Retrieval] Original question: {question}")
    logger.info(f"[GDD Retrieval] Cleaned query: {cleaned_query}")
    logger.info(f"[GDD Retrieval] Parsed filters: {query_filters}")
    
    # Check if user explicitly provided filters via @ syntax
    has_explicit_doc_filter = bool(query_filters.get('doc_id_filter'))
    has_explicit_section_filter = bool(query_filters.get('section_path_filter'))
    
    # Merge query filters with explicit filters
    if query_filters.get('section_path_filter') and not section_path_filter:
        # Strip numbers from section filter for name-only matching
        raw_section_filter = query_filters.get('section_path_filter')
        section_path_filter = _strip_section_number(raw_section_filter)
        logger.info(f"[GDD Retrieval] Raw section filter from query: '{raw_section_filter}' -> stripped: '{section_path_filter}'")
    # NOTE: content_type_filter removed - @ syntax now only supports sections
    if query_filters.get('doc_id_filter'):
        # If query specifies a doc_id, filter doc_ids list
        # The doc_id_filter is already normalized by parse_section_targets using normalize_doc_id_for_matching()
        target_doc_id_normalized = query_filters.get('doc_id_filter').lower()
        
        # Try to match to existing doc_ids (normalize each doc_id for comparison)
        matched_doc_ids = []
        for doc_id in unique_ids:
            # Normalize the existing doc_id for comparison
            doc_id_normalized = doc_id.lower()
            # Try exact match first
            if doc_id_normalized == target_doc_id_normalized:
                matched_doc_ids = [doc_id]
                break
            # Fallback to substring match if exact match fails
            elif target_doc_id_normalized in doc_id_normalized or doc_id_normalized in target_doc_id_normalized:
                matched_doc_ids.append(doc_id)
        
        if matched_doc_ids:
            unique_ids = matched_doc_ids
            logger.info(f"[GDD Retrieval] ✓ Filtered to doc_id(s): {unique_ids} (matched from query filter: {target_doc_id_normalized})")
        else:
            logger.warning(f"[GDD Retrieval] ❌ No doc_id matched filter: {target_doc_id_normalized} (available: {unique_ids})")
            logger.warning(f"[GDD Retrieval] This might cause wrong document content in the response!")
    
    # CRITICAL: If user explicitly provided filters via @ syntax, ONLY use those filters
    # Do NOT apply any automatic filtering from query text
    if has_explicit_section_filter:
        logger.info(f"[GDD Retrieval] User provided explicit section filter via @ syntax - skipping ALL automatic filtering")
        # Only use the explicit section filter, no automatic extraction or mapping
    else:
        # Only apply automatic filtering if NO explicit @ section filter was provided
        # Extract numbered section from query (but strip numbers for name-only matching)
        numbered_section = extract_numbered_section_from_query(cleaned_query)
        if numbered_section and not numbered_header_filter:
            # Strip numbers to match by name only (e.g., "4. Thànhphần" -> "Thànhphần")
            numbered_header_filter = _strip_section_number(numbered_section)
            logger.info(f"[GDD Retrieval] Extracted numbered section: '{numbered_section}' -> stripped: '{numbered_header_filter}'")
        
        # Map English section terms to Vietnamese (e.g., "components" -> "Thànhphần")
        # This helps when users query in English but documents use Vietnamese section names
        # NOTE: We do NOT translate the entire query - only map section names for filtering
        # IMPORTANT: We match by name only, ignoring numbers (e.g., "4. Thànhphần" matches "Thànhphần")
        # NOTE: We use this for boosting/prioritizing, but don't restrict too much - let vector search do the work
        vietnamese_section = map_english_to_vietnamese_section(cleaned_query)
        if vietnamese_section:
            # Strip any numbers from the mapped section name to ensure name-only matching
            vietnamese_section_clean = _strip_section_number(vietnamese_section)
            # Use Vietnamese section name for filtering by numbered_header or section_path
            # But don't set both - prefer numbered_header for more precise matching
            if not numbered_header_filter:
                # Match by name only (will match "4. Thànhphần", "7. Thànhphần", etc.)
                numbered_header_filter = vietnamese_section_clean
            # Don't set section_path_filter if we already have numbered_header_filter
            # This avoids double-filtering which might be too restrictive
            if not section_path_filter and not numbered_header_filter:
                # Only set section_path_filter as fallback if numbered_header_filter wasn't set
                section_path_filter = vietnamese_section_clean
            logger.info(f"[GDD Retrieval] Mapped English section term to Vietnamese (name only): {vietnamese_section_clean}, using numbered_header_filter={numbered_header_filter is not None}")
    
    metrics["timing"]["query_parsing"] = round(time.time() - parse_start, 3)
    logger.info(f"[GDD Retrieval] Parsed query filters: section_path={section_path_filter}, content_type={content_type_filter}, numbered_header={numbered_header_filter}")
    
    # Step 1.5: Language detection and translation (translate English queries to Vietnamese)
    translation_start = time.time()
    search_query = cleaned_query
    try:
        from backend.gdd_hyde import translate_query_if_needed
        vietnamese_query, detected_lang, translation_metrics = translate_query_if_needed(cleaned_query)
        search_query = vietnamese_query
        metrics["language_detection"] = translation_metrics
        metrics["timing"]["translation"] = round(time.time() - translation_start, 3)
        logger.info(f"[GDD Retrieval] Language detected: {detected_lang}, Query: {vietnamese_query[:100]}...")
    except Exception as e:
        logger.warning(f"[GDD Retrieval] Translation failed, using original query: {e}")
        metrics["timing"]["translation"] = {"error": str(e)}
    
    # Step 2: HYDE query expansion (optional, now on Vietnamese query)
    # HYDE will expand the Vietnamese query for better retrieval
    if use_hyde:
        hyde_start = time.time()
        try:
            from backend.gdd_hyde import gdd_hyde_v1
            # Apply HYDE to the Vietnamese query (after translation)
            hyde_query, hyde_timing = gdd_hyde_v1(search_query)
            search_query = hyde_query
            metrics["timing"]["hyde"] = hyde_timing
            metrics["hyde_query"] = hyde_query
            logger.info(f"[GDD Retrieval] HYDE expanded query: {hyde_query[:100]}...")
        except Exception as e:
            logger.warning(f"[GDD Retrieval] HYDE failed, using translated query: {e}")
            metrics["timing"]["hyde"] = {"error": str(e)}
    
    # Step 3: Load ALL chunks with filters
    load_start = time.time()
    all_chunks = load_gdd_chunks_from_supabase(
        unique_ids,
        section_path_filter=section_path_filter,
        content_type_filter=content_type_filter,
        numbered_header_filter=numbered_header_filter
    )
    metrics["timing"]["chunk_loading"] = round(time.time() - load_start, 3)
    metrics["chunks_loaded"] = len(all_chunks)
    logger.info(f"[GDD Retrieval] Loaded {len(all_chunks)} chunks (after filtering)")
    
    if not all_chunks:
        logger.error("="*80)
        logger.error("[GDD Retrieval] ❌ NO CHUNKS FOUND AFTER FILTERING!")
        logger.error(f"[GDD Retrieval] Doc IDs queried: {unique_ids}")
        logger.error(f"[GDD Retrieval] Section filter: {section_path_filter}")
        logger.error(f"[GDD Retrieval] Numbered header filter: {numbered_header_filter}")
        logger.error(f"[GDD Retrieval] Content type filter: {content_type_filter}")
        logger.error("="*80)
        
        # Try to load chunks WITHOUT filters to see if they exist
        logger.info("[GDD Retrieval] Attempting to load chunks WITHOUT filters for debugging...")
        all_chunks_no_filter = load_gdd_chunks_from_supabase(unique_ids)
        logger.info(f"[GDD Retrieval] Found {len(all_chunks_no_filter)} chunks WITHOUT filters")
        if all_chunks_no_filter:
            # Show first chunk's metadata
            first_chunk = all_chunks_no_filter[0]
            logger.info(f"[GDD Retrieval] Sample chunk doc_id: {first_chunk.doc_id}")
            # We can't easily get section_path from ChunkRecord, but we can log it
        
        raise ValueError("No chunks found for the selected documents. Verify they were indexed.")
    
    # Step 4: Embed the search query
    embed_start = time.time()
    question_embedding = None
    try:
        question_embedding = _embed_texts(provider, [search_query], use_cache=True)[0]
        question_embedding = _normalize_vector(question_embedding)
        metrics["timing"]["embedding"] = round(time.time() - embed_start, 3)
    except Exception as e:
        logger.warning(f"[GDD Retrieval] Embedding failed: {e}")
        metrics["timing"]["embedding"] = {"error": str(e)}
    
    # Step 5: Load ALL vectors from Supabase
    vector_start = time.time()
    vectors = load_gdd_vectors_from_supabase(unique_ids, normalize=True)
    metrics["timing"]["vector_loading"] = round(time.time() - vector_start, 3)
    metrics["vectors_loaded"] = len(vectors)
    logger.info(f"[GDD Retrieval] Loaded {len(vectors)} vectors")
    
    # Step 6: Score chunks using RRF
    score_start = time.time()
    scored = _score_chunks(
        question_embedding,
        all_chunks,
        vectors,
        provider,
        question_text=search_query,
        use_rrf=use_rrf
    )
    metrics["timing"]["scoring"] = round(time.time() - score_start, 3)
    metrics["chunks_scored"] = len(scored)
    logger.info(f"[GDD Retrieval] Scored {len(scored)} chunks")
    
    # Step 7: Apply evidence filtering
    evidence_start = time.time()
    if filter_by_evidence:
        scored = _filter_chunks_by_evidence(search_query, scored, min_evidence_score=0.15, keep_top_n=10)
        metrics["chunks_after_evidence"] = len(scored)
    metrics["timing"]["evidence_filtering"] = round(time.time() - evidence_start, 3)
    
    # Step 8: Re-rank with cross-encoder
    rerank_start = time.time()
    reranked = _rerank_with_cross_encoder(search_query, scored, provider=provider, top_n=min(12, len(scored)))
    metrics["timing"]["reranking"] = round(time.time() - rerank_start, 3)
    metrics["chunks_after_rerank"] = len(reranked)
    logger.info(f"[GDD Retrieval] Reranked to {len(reranked)} chunks")
    
    # Step 9: Select top chunks
    select_start = time.time()
    selected = _select_top_chunks(
        reranked,
        top_k=top_k,
        per_doc_limit=per_doc_limit or (2 if len(unique_ids) > 1 else None),
    )
    metrics["timing"]["selection"] = round(time.time() - select_start, 3)
    metrics["chunks_selected"] = len(selected)
    
    # Step 10: Load metadata for selected chunks and add to results
    results = []
    client = get_supabase_client()
    
    for score, record in selected:
        # Get full metadata from Supabase
        try:
            meta_result = client.table('gdd_chunks').select('section_path, section_title, content_type, metadata').eq('chunk_id', record.chunk_id).limit(1).execute()
            if meta_result.data:
                meta = meta_result.data[0]
                section_path = meta.get('section_path', '')
                section_title = meta.get('section_title', '')
                content_type = meta.get('content_type', '')
                chunk_metadata = meta.get('metadata', {})
                numbered_header = chunk_metadata.get('numbered_header', '') if isinstance(chunk_metadata, dict) else ''
            else:
                section_path = section_title = content_type = numbered_header = ''
        except Exception:
            section_path = section_title = content_type = numbered_header = ''
        
        evidence_spans = _extract_evidence_spans(search_query, record.content, max_spans=3)
        results.append({
            "doc_id": record.doc_id,
            "chunk_id": record.chunk_id,
            "content": record.content,
            "score": score,
            "evidence_spans": evidence_spans,
            "section_path": section_path,
            "section_title": section_title,
            "content_type": content_type,
            "numbered_header": numbered_header,
        })
    
    # Group by section_path for metrics
    section_groups = {}
    for result in results:
        section = result.get('section_path', 'Unknown')
        section_groups[section] = section_groups.get(section, 0) + 1
    metrics["section_distribution"] = section_groups
    
    metrics["timing"]["total"] = round(sum(v for v in metrics["timing"].values() if isinstance(v, (int, float))), 3)
    
    logger.info(f"[GDD Retrieval] Complete: {len(results)} chunks selected, {metrics['timing']['total']}s total")
    
    return results, metrics


def list_gdd_documents_supabase() -> List[Dict[str, Any]]:
    """
    List all GDD documents from Supabase.
    
    Returns:
        List of document metadata dictionaries
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info("list_gdd_documents_supabase() called")
    logger.info(f"USE_SUPABASE: {USE_SUPABASE}")
    
    if not USE_SUPABASE:
        logger.warning("USE_SUPABASE is False, returning empty list")
        return []
    
    try:
        logger.info("Calling get_gdd_documents() from supabase_client...")
        docs = get_gdd_documents()
        logger.info(f"get_gdd_documents() returned {len(docs)} documents")
        
        if docs:
            logger.info(f"Sample document from Supabase: {docs[0].get('name', 'N/A')}")
        
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
        
        logger.info(f"✅ Converted {len(result)} documents to expected format")
        return result
    except Exception as e:
        import traceback
        logger.error(f"❌ Error listing GDD documents from Supabase: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return []


def index_gdd_chunks_to_supabase(
    doc_id: str,
    chunks: List[Dict],
    provider,
    markdown_content: Optional[str] = None
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
        
        # Store markdown content in Supabase (passed as parameter or None)
        insert_gdd_document(
            doc_id=doc_id,
            name=doc_name,
            file_path=file_path,
            markdown_content=markdown_content  # Store markdown content in Supabase
        )
        
        # Insert chunks
        inserted_count = insert_gdd_chunks(supabase_chunks)
        
        print(f"Indexed {inserted_count} chunks for document {doc_id} to Supabase")
        return True
        
    except Exception as e:
        raise Exception(f"Error indexing chunks to Supabase: {e}")

