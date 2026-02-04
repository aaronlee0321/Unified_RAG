"""
Supabase storage adapter for GDD RAG
Replaces local JSON file storage with Supabase
"""

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.supabase_client import (  # noqa: E402
    get_gdd_documents,
    get_supabase_client,
    insert_gdd_chunks,
    insert_gdd_document,
)

# Import from local gdd_rag_backbone (now included in unified_rag_app)
from gdd_rag_backbone.llm_providers import make_embedding_func  # noqa: E402
from gdd_rag_backbone.rag_backend.chunk_qa import (  # noqa: E402
    ChunkRecord,
    _embed_texts,
    _extract_evidence_spans,
    _filter_chunks_by_evidence,
    _normalize_vector,
    _rerank_with_cross_encoder,
    _score_chunks,
    _select_top_chunks,
)

# Check if Supabase is configured
USE_SUPABASE = bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"))

# Log Supabase configuration status (using print for early logging)
if USE_SUPABASE:
    print(
        f"[INFO] Supabase configured: URL={os.getenv('SUPABASE_URL', '')[:30]}...")
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
    cleaned = re.sub(r"^\d+\.\d*\.?\s*", "", section_name)
    # Remove any remaining leading/trailing whitespace
    return cleaned.strip()


def load_gdd_chunks_from_supabase(
    doc_ids: List[str],
    section_path_filter: Optional[str] = None,
    content_type_filter: Optional[str] = None,
    numbered_header_filter: Optional[str] = None,
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

    logger.info(
        f"[load_gdd_chunks_from_supabase] Loading chunks for doc_ids: {doc_ids}")
    logger.info(
        f"[load_gdd_chunks_from_supabase] Filters - section_path: {section_path_filter}, content_type: {content_type_filter}, numbered_header: {numbered_header_filter}"
    )

    for doc_id in doc_ids:
        logger.info(
            f"[load_gdd_chunks_from_supabase] Querying doc_id: {doc_id}")

        # Build query with filters - using keyword_chunks table
        query = (
            client.table("keyword_chunks")
            .select("chunk_id, doc_id, content, section_heading, chunk_index")
            .eq("doc_id", doc_id)
        )

        # Apply section_heading filter (match by name only, ignore numbers)
        # NOTE: This is a soft filter - we load chunks and let vector search prioritize
        # Only apply if we don't have numbered_header_filter (to avoid double-filtering)
        if section_path_filter and not numbered_header_filter:
            # Strip numbers from filter to match by name only
            section_name_only = _strip_section_number(section_path_filter)
            logger.info(
                f"[load_gdd_chunks_from_supabase] Applying section_heading filter: {section_name_only}"
            )
            query = query.ilike("section_heading", f"%{section_name_only}%")
        elif section_path_filter and numbered_header_filter:
            # If both are set, prefer numbered_header_filter (more precise)
            # But still apply section_heading as a soft filter
            section_name_only = _strip_section_number(section_path_filter)
            logger.info(
                f"[load_gdd_chunks_from_supabase] Applying section_heading filter (with numbered_header): {section_name_only}"
            )
            query = query.ilike("section_heading", f"%{section_name_only}%")

        # Note: content_type filter removed - keyword_chunks doesn't have this field

        result = query.execute()
        logger.info(
            f"[load_gdd_chunks_from_supabase] Retrieved {len(result.data or [])} raw chunks from Supabase for doc_id: {doc_id}"
        )

        chunks_before_header_filter = 0
        chunks_after_header_filter = 0

        for row in result.data or []:
            chunk_id = row.get("chunk_id", "")
            content = row.get("content", "")
            result_doc_id = row.get("doc_id", "")
            section_heading = row.get("section_heading") or ""

            chunks_before_header_filter += 1

            # Apply numbered_header filter from section_heading if specified (match by name only, ignore numbers)
            if numbered_header_filter:
                # Strip numbers from both filter and header for name-only matching
                filter_name = _strip_section_number(
                    numbered_header_filter).lower().strip()
                section_heading_name = _strip_section_number(
                    str(section_heading)).lower().strip()
                # Match if filter name is in section heading OR section heading is in filter name (for partial matches)
                # Also check if they're equal (exact match after stripping numbers)
                # Make matching more lenient - remove spaces and special chars for comparison
                filter_clean = re.sub(r"[^\w]", "", filter_name.lower())
                section_clean = re.sub(
                    r"[^\w]", "", section_heading_name.lower())

                matches = (
                    filter_name == section_heading_name
                    or filter_name in section_heading_name
                    or section_heading_name in filter_name
                    or
                    # More lenient: compare cleaned versions
                    filter_clean == section_clean
                    or filter_clean in section_clean
                    or section_clean in filter_clean
                )

                # Log first 3 chunks to show filtering in action
                if chunks_before_header_filter <= 3:
                    logger.info(
                        f"[load_gdd_chunks_from_supabase] Chunk {chunks_before_header_filter}:"
                    )
                    logger.info(f"  - chunk_id: {chunk_id}")
                    logger.info(f"  - doc_id: {result_doc_id}")
                    logger.info(f"  - section_heading: {section_heading}")
                    logger.info(
                        f"  - filter_name: '{filter_name}' vs section_heading_name: '{section_heading_name}'"
                    )
                    logger.info(f"  - matches: {matches}")
                    logger.info(f"  - content preview: {content[:150]}...")

                if not matches:
                    if chunks_before_header_filter <= 3:
                        logger.info("  - ❌ FILTERED OUT")
                    continue

                if chunks_before_header_filter <= 3:
                    logger.info("  - ✓ KEPT")

            # Validate doc_id matches
            if result_doc_id == doc_id and content:
                all_chunks.append(
                    ChunkRecord(
                        chunk_id=chunk_id,  # Use full format to match vectors
                        doc_id=doc_id,
                        content=content,
                    )
                )
                chunks_after_header_filter += 1

        logger.info(
            f"[load_gdd_chunks_from_supabase] Doc {doc_id}: {chunks_before_header_filter} chunks before numbered_header filter -> {chunks_after_header_filter} chunks after"
        )

    logger.info(
        f"[load_gdd_chunks_from_supabase] Total chunks loaded: {len(all_chunks)}")
    return all_chunks


def load_gdd_vectors_from_supabase(
    doc_ids: List[str], normalize: bool = True
) -> Dict[str, List[float]]:
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
        result = (
            client.table("keyword_chunks")
            .select("chunk_id, doc_id, embedding")
            .eq("doc_id", doc_id)
            .execute()
        )

        for row in result.data or []:
            # Full format: {doc_id}_{chunk_id}
            chunk_id = row.get("chunk_id", "")
            result_doc_id = row.get("doc_id", "")
            embedding = row.get("embedding")

            if chunk_id and embedding and result_doc_id in allowed:
                try:
                    # Convert to float list
                    float_vector = [float(v) for v in embedding]
                    if normalize:
                        float_vector = _normalize_vector(float_vector)
                    # Use full format chunk_id
                    vectors[chunk_id] = float_vector
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

    metrics = {"query": question, "doc_ids": doc_ids, "timing": {}}

    if not USE_SUPABASE:
        raise ValueError(
            "Supabase is not configured. Set SUPABASE_URL and SUPABASE_KEY in .env")

    if not doc_ids:
        raise ValueError("At least one doc_id is required.")

    unique_ids = list(dict.fromkeys(doc_ids))

    # Step 1: Parse section targets from query
    parse_start = time.time()
    from backend.gdd_query_parser import (
        extract_numbered_section_from_query,
        map_english_to_vietnamese_section,
        parse_section_targets,
    )

    cleaned_query, query_filters = parse_section_targets(question)
    logger.info("[GDD Retrieval] ========== QUERY PARSING ==========")
    logger.info(f"[GDD Retrieval] Original question: {question}")
    logger.info(f"[GDD Retrieval] Cleaned query: {cleaned_query}")
    logger.info(f"[GDD Retrieval] Parsed filters: {query_filters}")

    # Check if user explicitly provided filters via @ syntax
    bool(query_filters.get("doc_id_filter"))
    has_explicit_section_filter = bool(
        query_filters.get("section_path_filter"))

    # Merge query filters with explicit filters
    if query_filters.get("section_path_filter") and not section_path_filter:
        # Strip numbers from section filter for name-only matching
        raw_section_filter = query_filters.get("section_path_filter")
        section_path_filter = _strip_section_number(raw_section_filter)
        logger.info(
            f"[GDD Retrieval] Raw section filter from query: '{raw_section_filter}' -> stripped: '{section_path_filter}'"
        )
    # NOTE: content_type_filter removed - @ syntax now only supports sections
    if query_filters.get("doc_id_filter"):
        # If query specifies a doc_id, filter doc_ids list
        # The doc_id_filter is already normalized by parse_section_targets using normalize_doc_id_for_matching()
        target_doc_id_normalized = query_filters.get("doc_id_filter").lower()

        # Try to match to existing doc_ids (normalize each doc_id for comparison)
        matched_doc_ids = []
        for doc_id in unique_ids:
            # Normalize the existing doc_id for comparison
            doc_id_normalized = doc_id.lower()
            # Try exact match first
            if doc_id_normalized == target_doc_id_normalized:
                matched_doc_ids = [doc_id]
                break

            # Fallback: normalize both by removing special chars for fuzzy matching
            def normalize_for_fuzzy(text):
                """Normalize text by removing special chars for fuzzy matching."""
                if not text:
                    return ""
                return (
                    text.lower()
                    .replace("_", "")
                    .replace("-", "")
                    .replace(" ", "")
                    .replace("(", "")
                    .replace(")", "")
                    .replace("[", "")
                    .replace("]", "")
                    .replace(",", "")
                )

            target_fuzzy = normalize_for_fuzzy(target_doc_id_normalized)
            doc_id_fuzzy = normalize_for_fuzzy(doc_id_normalized)

            # Try fuzzy match (removing special chars)
            if target_fuzzy == doc_id_fuzzy:
                matched_doc_ids.append(doc_id)
            # Fallback to substring match if exact match fails
            elif (
                target_doc_id_normalized in doc_id_normalized
                or doc_id_normalized in target_doc_id_normalized
            ):
                matched_doc_ids.append(doc_id)

        if matched_doc_ids:
            unique_ids = matched_doc_ids
            logger.info(
                f"[GDD Retrieval] ✓ Filtered to doc_id(s): {unique_ids} (matched from query filter: {target_doc_id_normalized})"
            )
        else:
            logger.warning(
                f"[GDD Retrieval] ❌ No doc_id matched filter: {target_doc_id_normalized} (available: {unique_ids})"
            )
            logger.warning(
                "[GDD Retrieval] This might cause wrong document content in the response!"
            )

    # CRITICAL: If user explicitly provided filters via @ syntax, ONLY use those filters
    # Do NOT apply any automatic filtering from query text
    if has_explicit_section_filter:
        logger.info(
            "[GDD Retrieval] User provided explicit section filter via @ syntax - skipping ALL automatic filtering"
        )
        # Only use the explicit section filter, no automatic extraction or mapping
    else:
        # Only apply automatic filtering if NO explicit @ section filter was provided
        # Extract numbered section from query (but strip numbers for name-only matching)
        numbered_section = extract_numbered_section_from_query(cleaned_query)
        if numbered_section and not numbered_header_filter:
            # Strip numbers to match by name only (e.g., "4. Thànhphần" -> "Thànhphần")
            numbered_header_filter = _strip_section_number(numbered_section)
            logger.info(
                f"[GDD Retrieval] Extracted numbered section: '{numbered_section}' -> stripped: '{numbered_header_filter}'"
            )

        # Map English section terms to Vietnamese (e.g., "components" -> "Thànhphần")
        # This helps when users query in English but documents use Vietnamese section names
        # NOTE: We do NOT translate the entire query - only map section names for filtering
        # IMPORTANT: We match by name only, ignoring numbers (e.g., "4. Thànhphần" matches "Thànhphần")
        # NOTE: We use this for boosting/prioritizing, but don't restrict too much - let vector search do the work
        vietnamese_section = map_english_to_vietnamese_section(cleaned_query)
        if vietnamese_section:
            # Strip any numbers from the mapped section name to ensure name-only matching
            vietnamese_section_clean = _strip_section_number(
                vietnamese_section)
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
            logger.info(
                f"[GDD Retrieval] Mapped English section term to Vietnamese (name only): {vietnamese_section_clean}, using numbered_header_filter={numbered_header_filter is not None}"
            )

    metrics["timing"]["query_parsing"] = round(time.time() - parse_start, 3)
    logger.info(
        f"[GDD Retrieval] Parsed query filters: section_path={section_path_filter}, content_type={content_type_filter}, numbered_header={numbered_header_filter}"
    )

    # Step 1.5: Language detection and translation (translate English queries to Vietnamese)
    translation_start = time.time()
    search_query = cleaned_query
    try:
        from backend.gdd_hyde import translate_query_if_needed

        vietnamese_query, detected_lang, translation_metrics = translate_query_if_needed(
            cleaned_query
        )
        search_query = vietnamese_query
        metrics["language_detection"] = translation_metrics
        metrics["timing"]["translation"] = round(
            time.time() - translation_start, 3)
        logger.info(
            f"[GDD Retrieval] Language detected: {detected_lang}, Query: {vietnamese_query[:100]}..."
        )
    except Exception as e:
        logger.warning(
            f"[GDD Retrieval] Translation failed, using original query: {e}")
        metrics["timing"]["translation"] = {"error": str(e)}

    # Step 2: HYDE query expansion (optional, now on Vietnamese query)
    # HYDE will expand the Vietnamese query for better retrieval
    if use_hyde:
        time.time()
        try:
            from backend.gdd_hyde import gdd_hyde_v1

            # Apply HYDE to the Vietnamese query (after translation)
            hyde_query, hyde_timing = gdd_hyde_v1(search_query)
            search_query = hyde_query
            metrics["timing"]["hyde"] = hyde_timing
            metrics["hyde_query"] = hyde_query
            logger.info(
                f"[GDD Retrieval] HYDE expanded query: {hyde_query[:100]}...")
        except Exception as e:
            logger.warning(
                f"[GDD Retrieval] HYDE failed, using translated query: {e}")
            metrics["timing"]["hyde"] = {"error": str(e)}

    # Step 3: Load ALL chunks with filters
    load_start = time.time()
    all_chunks = load_gdd_chunks_from_supabase(
        unique_ids,
        section_path_filter=section_path_filter,
        content_type_filter=content_type_filter,
        numbered_header_filter=numbered_header_filter,
    )
    metrics["timing"]["chunk_loading"] = round(time.time() - load_start, 3)
    metrics["chunks_loaded"] = len(all_chunks)
    logger.info(
        f"[GDD Retrieval] Loaded {len(all_chunks)} chunks (after filtering)")

    if not all_chunks:
        logger.error("=" * 80)
        logger.error("[GDD Retrieval] ❌ NO CHUNKS FOUND AFTER FILTERING!")
        logger.error(f"[GDD Retrieval] Doc IDs queried: {unique_ids}")
        logger.error(f"[GDD Retrieval] Section filter: {section_path_filter}")
        logger.error(
            f"[GDD Retrieval] Numbered header filter: {numbered_header_filter}")
        logger.error(
            f"[GDD Retrieval] Content type filter: {content_type_filter}")
        logger.error("=" * 80)

        # Try to load chunks WITHOUT filters to see if they exist
        logger.info(
            "[GDD Retrieval] Attempting to load chunks WITHOUT filters for debugging...")
        all_chunks_no_filter = load_gdd_chunks_from_supabase(unique_ids)
        logger.info(
            f"[GDD Retrieval] Found {len(all_chunks_no_filter)} chunks WITHOUT filters")
        if all_chunks_no_filter:
            # Show first chunk's metadata
            first_chunk = all_chunks_no_filter[0]
            logger.info(
                f"[GDD Retrieval] Sample chunk doc_id: {first_chunk.doc_id}")
            # We can't easily get section_path from ChunkRecord, but we can log it

        raise ValueError(
            "No chunks found for the selected documents. Verify they were indexed.")

    # Step 4: Embed the search query
    embed_start = time.time()
    question_embedding = None
    try:
        question_embedding = _embed_texts(
            provider, [search_query], use_cache=True)[0]
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
        use_rrf=use_rrf,
    )
    metrics["timing"]["scoring"] = round(time.time() - score_start, 3)
    metrics["chunks_scored"] = len(scored)
    logger.info(f"[GDD Retrieval] Scored {len(scored)} chunks")

    # Step 7: Apply evidence filtering
    evidence_start = time.time()
    if filter_by_evidence:
        scored = _filter_chunks_by_evidence(
            search_query, scored, min_evidence_score=0.15, keep_top_n=10
        )
        metrics["chunks_after_evidence"] = len(scored)
    metrics["timing"]["evidence_filtering"] = round(
        time.time() - evidence_start, 3)

    # Step 8: Re-rank with cross-encoder
    rerank_start = time.time()
    reranked = _rerank_with_cross_encoder(
        search_query, scored, provider=provider, top_n=min(12, len(scored))
    )
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
            meta_result = (
                client.table("keyword_chunks")
                .select("section_heading")
                .eq("chunk_id", record.chunk_id)
                .limit(1)
                .execute()
            )
            if meta_result.data:
                meta = meta_result.data[0]
                section_heading = meta.get("section_heading") or ""
                section_path = (
                    section_heading  # Use section_heading as section_path for compatibility
                )
                section_title = (
                    section_heading  # Use section_heading as section_title for compatibility
                )
                content_type = ""  # keyword_chunks doesn't have content_type
                numbered_header = (
                    section_heading  # Use section_heading as numbered_header for compatibility
                )
            else:
                section_path = section_title = content_type = numbered_header = ""
        except Exception:
            section_path = section_title = content_type = numbered_header = ""

        evidence_spans = _extract_evidence_spans(
            search_query, record.content, max_spans=3)
        results.append(
            {
                "doc_id": record.doc_id,
                "chunk_id": record.chunk_id,
                "content": record.content,
                "score": score,
                "evidence_spans": evidence_spans,
                "section_path": section_path,
                "section_title": section_title,
                "content_type": content_type,
                "numbered_header": numbered_header,
            }
        )

    # Group by section_path for metrics
    section_groups = {}
    for result in results:
        section = result.get("section_path", "Unknown")
        section_groups[section] = section_groups.get(section, 0) + 1
    metrics["section_distribution"] = section_groups

    metrics["timing"]["total"] = round(
        sum(v for v in metrics["timing"].values()
            if isinstance(v, (int, float))), 3
    )

    logger.info(
        f"[GDD Retrieval] Complete: {len(results)} chunks selected, {metrics['timing']['total']}s total"
    )

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
            logger.info(
                f"Sample document from Supabase: {docs[0].get('name', 'N/A')}")

        # Convert to expected format
        result = []
        for doc in docs:
            result.append(
                {
                    "doc_id": doc.get("doc_id", ""),
                    "file_path": doc.get("file_path", ""),
                    "chunks_count": doc.get("chunks_count", 0),
                    "name": doc.get("name", doc.get("doc_id", "")),
                    "updated_at": doc.get("updated_at"),
                    "status": "ready" if doc.get("chunks_count", 0) > 0 else "indexed",
                }
            )

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
    markdown_content: Optional[str] = None,
    pdf_storage_path: Optional[str] = None,
    images: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """
    Index GDD chunks to Supabase with embeddings.

    Args:
        doc_id: Document ID
        chunks: List of chunk dictionaries from MarkdownChunker
        provider: LLM provider for embeddings
        markdown_content: Optional full markdown content to store
        pdf_storage_path: Optional PDF filename in Supabase Storage (gdd_pdfs bucket)
        images: Optional list of image metadata dicts [{"filename", "url", "path"}] for keyword_documents.images

    Returns:
        True if successful
    """
    if not USE_SUPABASE:
        raise ValueError("Supabase is not configured")

    try:
        import logging
        import threading
        import time

        logger = logging.getLogger(__name__)

        # Create embedding function
        embedding_func = make_embedding_func(provider)

        def generate_embedding_with_timeout(content, timeout=30):
            """Generate embedding with timeout protection (cross-platform)."""
            result_container = [None]
            exception_container = [None]

            def embed_worker():
                try:
                    result_container[0] = embedding_func([content])[0]
                except Exception as e:
                    exception_container[0] = e

            thread = threading.Thread(target=embed_worker)
            thread.daemon = True
            thread.start()
            thread.join(timeout=timeout)

            if thread.is_alive():
                # Thread is still running - timeout occurred
                logger.error(
                    f"Embedding generation exceeded {timeout}s timeout")
                raise TimeoutError(
                    f"Embedding generation exceeded {timeout}s timeout")

            if exception_container[0]:
                raise exception_container[0]

            if result_container[0] is None:
                raise Exception("Embedding generation returned None")

            return result_container[0]

        # Prepare chunks for Supabase
        supabase_chunks = []
        failed_chunks = []

        logger.info(f"Generating embeddings for {len(chunks)} chunks...")

        for i, chunk in enumerate(chunks):
            # Handle both MarkdownChunk objects and dictionaries
            if hasattr(chunk, "chunk_id"):
                # MarkdownChunk object
                raw_chunk_id = chunk.chunk_id
                content = chunk.content
                chunk_metadata = chunk.metadata if hasattr(
                    chunk, "metadata") else {}
                chunk_section = (
                    chunk_metadata.get("section_header", "")
                    if isinstance(chunk_metadata, dict)
                    else ""
                )
            else:
                # Dictionary
                raw_chunk_id = chunk.get("chunk_id") or f"chunk_{i:03d}"
                content = chunk.get("content", "")
                chunk_metadata = chunk.get("metadata", {})
                chunk_section = chunk.get("section", "")

            # Make chunk_id globally unique by prepending doc_id: "{doc_id}_chunk_001"
            chunk_id = f"{doc_id}_{raw_chunk_id}"

            # Skip empty content
            if not content or not content.strip():
                logger.warning(
                    f"Skipping chunk {chunk_id} (index {i}): empty content")
                failed_chunks.append((i, chunk_id, "empty content"))
                continue

            # Generate embedding with retry and timeout
            embedding = None
            max_retries = 3
            timeout_seconds = 30  # 30 second timeout per embedding

            for attempt in range(max_retries):
                try:
                    if (i + 1) % 5 == 0:  # Log progress every 5 chunks
                        logger.info(
                            f"Processing chunk {i + 1}/{len(chunks)} (attempt {attempt + 1}/{max_retries})"
                        )

                    start_time = time.time()

                    # Generate embedding with timeout protection
                    embedding = generate_embedding_with_timeout(
                        content, timeout_seconds)

                    elapsed = time.time() - start_time
                    if elapsed > 5:  # Log slow embeddings
                        logger.warning(
                            f"Slow embedding generation: {elapsed:.2f}s for chunk {chunk_id}"
                        )

                    break  # Success, exit retry loop

                except TimeoutError:
                    elapsed = time.time() - start_time if "start_time" in locals() else 0
                    if attempt == max_retries - 1:
                        logger.error(
                            f"Timeout embedding chunk {chunk_id} (index {i}) after {max_retries} attempts"
                        )
                        failed_chunks.append(
                            (i, chunk_id, f"timeout after {elapsed:.2f}s"))
                        raise Exception(
                            f"Failed to embed chunk {chunk_id} (index {i}): timeout after {elapsed:.2f}s"
                        )
                    else:
                        wait_time = (2**attempt) * 1.0
                        logger.warning(
                            f"Embedding timeout for chunk {chunk_id} (index {i}), retrying in {wait_time:.1f}s..."
                        )
                        time.sleep(wait_time)

                except Exception as e:
                    elapsed = time.time() - start_time if "start_time" in locals() else 0
                    error_str = str(e)

                    # Check for quota/rate limit errors (429)
                    is_quota_error = (
                        "429" in error_str
                        or "quota" in error_str.lower()
                        or "insufficient_quota" in error_str.lower()
                        or "RateLimitError" in str(type(e).__name__)
                    )

                    if is_quota_error:
                        # Quota errors shouldn't be retried - they won't resolve quickly
                        error_msg = (
                            f"❌ OpenAI API Quota Exceeded (429 Error)\n\n"
                            f"Your OpenAI API key is valid, but you've exceeded your usage quota.\n\n"
                            f"To fix this:\n"
                            f"1. Add credits: https://platform.openai.com/account/billing\n"
                            f"2. Check usage: https://platform.openai.com/usage\n"
                            f"3. Wait for quota to reset (usually monthly)\n\n"
                            f"Error details: {error_str}\n\n"
                            f"Document indexing cannot continue without embeddings. "
                            f"Please add credits to your OpenAI account and try again."
                        )
                        logger.error(error_msg)
                        failed_chunks.append((i, chunk_id, "quota exceeded"))
                        raise Exception(error_msg)

                    if attempt == max_retries - 1:
                        # Last attempt failed
                        logger.error(
                            f"Failed to embed chunk {chunk_id} (index {i}) after {max_retries} attempts: {e}"
                        )
                        failed_chunks.append((i, chunk_id, str(e)))
                        # Don't skip - raise error to prevent silent data loss
                        raise Exception(
                            f"Failed to embed chunk {chunk_id} (index {i}): {e}. This indicates a critical indexing error."
                        )
                    else:
                        # Retry with exponential backoff (but not for quota errors)
                        wait_time = (2**attempt) * 1.0  # 1s, 2s, 4s
                        logger.warning(
                            f"Embedding attempt {attempt + 1} failed for chunk {chunk_id} (index {i}) after {elapsed:.2f}s, retrying in {wait_time:.1f}s... Error: {e}"
                        )
                        time.sleep(wait_time)

            if embedding is None:
                continue  # Should not reach here due to raise above, but safety check

            # ---- Extract section + metadata fields safely ----
            # chunk_metadata is already set above (dict for both object/dict paths)
            meta = chunk_metadata if isinstance(chunk_metadata, dict) else {}

            section_header = meta.get("section_header") or chunk_section or ""
            numbered_header = meta.get("numbered_header") or section_header
            content_type = meta.get("content_type") or ""
            doc_category = meta.get("doc_category") or "General"
            tags = meta.get("tags") if isinstance(
                meta.get("tags"), list) else None

            # Best-effort numeric indexes (keeps your UI ordering stable)
            # If your chunk ids look like "chunk_006", use that as section_index
            section_index = None
            m = re.search(r"chunk_(\d+)", str(raw_chunk_id))
            if m:
                try:
                    section_index = int(m.group(1))
                except Exception:
                    section_index = None
            if section_index is None:
                section_index = i + 1

            # paragraph_index: if chunker has part_number use it, otherwise default to 1
            paragraph_index = meta.get("part_number") or 1

            # Build clean metadata (do NOT nest metadata inside metadata)
            clean_metadata = dict(meta)
            clean_metadata.update(
                {
                    "chunk_index": i,
                    "original_chunk_id": raw_chunk_id,
                    "section_header": section_header,
                    "numbered_header": numbered_header,
                }
            )

            # ---- Supabase record with real columns populated ----
            supabase_chunks.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "content": content,
                    "embedding": embedding,
                    # IMPORTANT: populate DB columns for section targeting
                    "section_path": section_header,
                    "section_title": section_header,
                    "subsection_title": None,
                    "section_index": section_index,
                    "paragraph_index": paragraph_index,
                    "content_type": content_type,
                    "doc_category": doc_category,
                    "tags": tags,
                    # Keep metadata flat and useful
                    "metadata": clean_metadata,
                }
            )

        # Insert document metadata
        # Handle both MarkdownChunk objects and dictionaries
        if chunks:
            first_chunk = chunks[0]
            if hasattr(first_chunk, "metadata"):
                # MarkdownChunk object - no file_path attribute
                file_path = ""
            else:
                # Dictionary
                file_path = first_chunk.get("file_path", "")
        else:
            file_path = ""
        doc_name = Path(file_path).name if file_path else doc_id

        # Store markdown content, PDF path, and images in Supabase
        insert_gdd_document(
            doc_id=doc_id,
            name=doc_name,
            file_path=file_path,
            markdown_content=markdown_content,  # Store markdown content in Supabase
            pdf_storage_path=pdf_storage_path,  # Store PDF storage path
            # Store extracted image metadata (keyword_documents.images JSONB)
            images=images,
        )

        # Extract and store metadata - use full markdown content if available, otherwise use chunks
        try:
            from backend.services.gdd_metadata_extractor import (
                extract_metadata_from_chunks,
                extract_metadata_from_text,
            )
            from backend.storage.keyword_storage import update_document_metadata

            metadata = {"version": None, "author": None, "date": None}

            # Strategy 1: Use full markdown content if available (best for table extraction)
            if markdown_content:
                try:
                    # Extract from full markdown - this ensures we get the complete version table
                    metadata = extract_metadata_from_text(markdown_content)
                    logger.info(
                        f"[Metadata] Extracted from full markdown for {doc_id}: version={metadata.get('version')}, author={metadata.get('author')}, date={metadata.get('date')}"
                    )
                except Exception as e:
                    logger.warning(
                        f"[Metadata] Failed to extract from markdown_content for {doc_id}: {e}"
                    )

            # Strategy 2: Fallback to chunks if markdown_content not available or extraction failed
            if (
                not metadata.get("version")
                or not metadata.get("author")
                or not metadata.get("date")
            ) and chunks:
                try:
                    # Get first 5 chunks (increased from 3 to catch more of the version table)
                    chunk_dicts = []
                    for chunk in chunks[:5]:
                        if hasattr(chunk, "content"):
                            # MarkdownChunk object
                            chunk_dicts.append(
                                {
                                    "content": chunk.content,
                                    "chunk_index": getattr(chunk, "chunk_id", ""),
                                }
                            )
                        else:
                            # Already a dictionary
                            chunk_dicts.append(chunk)

                    if chunk_dicts:
                        chunk_metadata = extract_metadata_from_chunks(
                            chunk_dicts)
                        # Only update if we don't already have values from markdown extraction
                        if not metadata.get("version") and chunk_metadata.get("version"):
                            metadata["version"] = chunk_metadata.get("version")
                        if not metadata.get("author") and chunk_metadata.get("author"):
                            metadata["author"] = chunk_metadata.get("author")
                        if not metadata.get("date") and chunk_metadata.get("date"):
                            metadata["date"] = chunk_metadata.get("date")

                        logger.info(
                            f"[Metadata] Extracted from chunks for {doc_id}: version={metadata.get('version')}, author={metadata.get('author')}, date={metadata.get('date')}"
                        )
                except Exception as e:
                    logger.warning(
                        f"[Metadata] Failed to extract from chunks for {doc_id}: {e}")

            # Update document with extracted metadata (handles null cases)
            if metadata.get("version") or metadata.get("author") or metadata.get("date"):
                success = update_document_metadata(
                    doc_id=doc_id,
                    version=metadata.get("version"),
                    author=metadata.get("author"),
                    date=metadata.get("date"),
                )

                if success:
                    logger.info(
                        f"[Metadata] ✅ Updated metadata for {doc_id}: version={metadata.get('version')}, author={metadata.get('author')}, date={metadata.get('date')}"
                    )
                else:
                    logger.error(
                        f"[Metadata] ❌ Failed to update metadata in database for {doc_id}"
                    )
            else:
                logger.warning(f"[Metadata] ⚠️ No metadata found for {doc_id}")

            # Post-indexing verification: Double-check metadata was saved correctly
            # This ensures metadata is always correct even if there was a race condition
            try:
                client = get_supabase_client()
                verify_result = (
                    client.table("keyword_documents")
                    .select("gdd_version, gdd_author, gdd_date")
                    .eq("doc_id", doc_id)
                    .limit(1)
                    .execute()
                )

                if verify_result.data:
                    saved_meta = verify_result.data[0]
                    # If we extracted metadata but it's not in DB, try updating again
                    if metadata.get("version") and not saved_meta.get("gdd_version"):
                        logger.warning(
                            f"[Metadata] Verification failed: version not saved, retrying update for {doc_id}"
                        )
                        update_document_metadata(
                            doc_id=doc_id,
                            version=metadata.get("version"),
                            author=metadata.get("author"),
                            date=metadata.get("date"),
                        )
            except Exception as e:
                logger.warning(
                    f"[Metadata] Verification check failed for {doc_id}: {e}")

        except Exception as e:
            # Log error but don't fail the indexing - metadata extraction is optional
            logger.warning(
                f"[Metadata] ❌ Failed to extract metadata for {doc_id}: {e}", exc_info=True
            )
            import traceback

            logger.debug(traceback.format_exc())

        # Report any failed chunks before insertion
        if failed_chunks:
            logger.error(
                f"CRITICAL: {len(failed_chunks)} chunks failed embedding for document {doc_id}:"
            )
            for idx, chunk_id, error in failed_chunks[:10]:  # Show first 10
                logger.error(f"  - Chunk {idx} ({chunk_id}): {error}")
            if len(failed_chunks) > 10:
                logger.error(f"  ... and {len(failed_chunks) - 10} more")
            raise Exception(
                f"Failed to embed {len(failed_chunks)} out of {len(chunks)} chunks for document {doc_id}. Indexing aborted to prevent data loss."
            )

        # Insert chunks
        logger.info(f"Inserting {len(supabase_chunks)} chunks to Supabase...")
        inserted_count = insert_gdd_chunks(supabase_chunks)

        # Verify all chunks were inserted
        if inserted_count != len(supabase_chunks):
            logger.error(
                f"WARNING: Only {inserted_count} out of {len(supabase_chunks)} chunks were inserted for document {doc_id}"
            )

        # Use logger instead of print to handle Unicode characters properly
        try:
            logger.info(
                f"Indexed {inserted_count} chunks for document {doc_id} to Supabase")
        except UnicodeEncodeError:
            # Fallback if logger also has encoding issues
            logger.info(
                f"Indexed {inserted_count} chunks for document to Supabase")

        return True

    except Exception as e:
        raise Exception(f"Error indexing chunks to Supabase: {e}")
