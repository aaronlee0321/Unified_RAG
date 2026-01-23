"""
GDD Document Explainer backend functions for keyword-based document search and explanation generation.
"""
import json
import logging
import traceback
from typing import List, Dict, Optional, Any, Generator
from backend.services.search_service import keyword_search
from backend.services.explainer_service import explain_keyword
from backend.storage.keyword_storage import list_keyword_documents, find_keyword_by_alias, get_aliases_for_keyword
from backend.storage.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def _create_search_response(keyword: str, choices: List[str] = None, store_data: List[Dict] = None,
                            status_msg: str = "", success: bool = True,
                            progress_messages: List[str] = None, translation_info: Dict[str, str] = None) -> Dict[str, Any]:
    """Create standardized search response structure."""
    return {
        'choices': choices or [],
        'store_data': store_data or [],
        'status_msg': status_msg,
        'success': success,
        'keyword': keyword,
        'progress_messages': progress_messages or [],
        'translation_info': translation_info
    }


def _log_search_step(step_num: str, description: str, success: bool = None, count: int = None):
    """Log search step with consistent formatting."""
    if success is None:
        logger.info(f"[MAIN SEARCH] STEP {step_num}: {description}")
    elif success:
        logger.info(
            f"[MAIN SEARCH] ✓ STEP {step_num} succeeded with {count} results")
    else:
        logger.info(f"[MAIN SEARCH] ✗ STEP {step_num} found no results")


def _extract_display_name(doc_name: str) -> str:
    """Extract clean display name from full document path."""
    display_name = doc_name
    if '\\' in display_name:
        display_name = display_name.split('\\')[-1]
    elif '/' in display_name:
        display_name = display_name.split('/')[-1]

    if display_name.lower().endswith('.pdf'):
        display_name = display_name[:-4]

    return display_name


def _update_section_chunk_id(doc_sections: Dict, key: tuple, chunk_id: str) -> None:
    """Update section's chunk_id to keep the alphabetically lowest one."""
    if not chunk_id:
        return

    existing_chunk_id = doc_sections[key].get('chunk_id', '')
    if not existing_chunk_id or chunk_id < existing_chunk_id:
        doc_sections[key]['chunk_id'] = chunk_id


def _create_section_entry(result: Dict) -> Dict:
    """Create a section entry from a search result."""
    return {
        'doc_id': result.get('doc_id'),
        'doc_name': result.get('doc_name', 'Unknown Document'),
        'section_heading': result.get('section_heading'),
        'content': result.get('content', ''),
        'relevance': result.get('relevance', 0.0),
        'chunk_id': result.get('chunk_id', '')
    }


def _process_search_results(results: List[Dict], keyword: str, progress_messages: List[str] = None, translation_info: Dict[str, str] = None) -> Dict[str, Any]:
    """Process search results into the expected format."""
    doc_sections = {}

    for result in results:
        try:
            section = result.get('section_heading')
            if not section or not section.strip():
                continue

            doc_id = result.get('doc_id')
            doc_name = result.get('doc_name', 'Unknown Document')
            key = (doc_id, doc_name, section)
            chunk_id = result.get('chunk_id', '')

            if key in doc_sections:
                _update_section_chunk_id(doc_sections, key, chunk_id)
                # Merge matching keywords if they exist
                if '_matching_keywords' in result:
                    existing_keywords = doc_sections[key].get(
                        '_matching_keywords', set())
                    if not isinstance(existing_keywords, set):
                        existing_keywords = set(
                            existing_keywords) if existing_keywords else set()
                    existing_keywords.update(
                        result.get('_matching_keywords', []))
                    doc_sections[key]['_matching_keywords'] = existing_keywords
            else:
                section_entry = _create_section_entry(result)
                # Preserve matching keywords if they exist
                if '_matching_keywords' in result:
                    section_entry['_matching_keywords'] = set(
                        result['_matching_keywords'])
                doc_sections[key] = section_entry
        except Exception as e:
            logger.error(f"Error processing result: {e}", exc_info=True)
            continue

    sorted_items = sorted(
        doc_sections.values(),
        key=lambda x: x['relevance'],
        reverse=True
    )

    choices = []
    store_data = []

    for item in sorted_items:
        try:
            display_name = _extract_display_name(item['doc_name'])
            section_display = item['section_heading'] or "(No section)"
            choice_label = f"{display_name} → {section_display}"

            choices.append(choice_label)
            store_item = {
                'doc_id': item['doc_id'],
                'doc_name': display_name,
                'section_heading': item['section_heading'],
                'content': item.get('content', ''),
                'chunk_id': item.get('chunk_id', '')
            }
            # Preserve matching keywords if they exist (for explanation generation)
            if '_matching_keywords' in item:
                store_item['_matching_keywords'] = list(
                    item['_matching_keywords'])
            store_data.append(store_item)
        except Exception as e:
            logger.error(f"Error creating choice: {e}", exc_info=True)
            continue

    if progress_messages is not None:
        progress_messages.append(
            f"✅ Found {len(sorted_items)} document/section combinations!")

    return {
        'choices': choices,
        'store_data': store_data,
        'status_msg': f"✅ Found {len(sorted_items)} document/section combinations. Select which ones to explain.",
        'success': True,
        'keyword': keyword,
        'progress_messages': progress_messages or [],
        'translation_info': translation_info
    }


def search_for_explainer(keyword: str) -> Dict[str, Any]:
    """
    Search for keyword and return results as checkboxes for selection.
    Includes automatic translation and synonym finding before falling back to LLM.

    Args:
        keyword: Search keyword

    Returns:
        Dict with 'choices', 'store_data', 'status_msg', 'keyword', 'progress_messages'
    """
    keyword_stripped = keyword.strip() if keyword else ""

    if not keyword_stripped:
        return _create_search_response(
            keyword_stripped,
            status_msg="Please enter a keyword to search.",
            success=False
        )

    try:
        progress_messages = []
        logger.info("=" * 80)
        logger.info(f"[MAIN SEARCH] Starting search for: '{keyword_stripped}'")
        logger.info("=" * 80)

        # Define search strategies to try in order
        translation_info = None

        # First step: try translation search (returns tuple: results, translation_info)
        _log_search_step("1", "Searching with translation")
        results, translation_info = _search_with_translation(
            keyword_stripped, progress_messages)

        if results:
            _log_search_step("1", "Searching with translation",
                             success=True, count=len(results))
            return _process_search_results(results, keyword_stripped, progress_messages, translation_info)

        _log_search_step("1", "Searching with translation", success=False)

        # Other search strategies
        search_steps = [
            ("2", "Searching aliases", lambda: _search_aliases(
                keyword_stripped, progress_messages)),
            ("2b", "Checking aliases for translation", lambda: _check_translated_aliases(
                keyword_stripped, progress_messages)),
            ("3", "Generating and searching with synonyms", lambda: _try_translation_and_synonyms(
                keyword_stripped, progress_messages, add_progress=True)),
            ("4", "LLM deep search (final fallback)", lambda: _try_llm_deep_search(
                keyword_stripped, progress_messages)),
        ]

        # Execute remaining search steps
        for step_num, description, search_func in search_steps:
            _log_search_step(step_num, description)
            results = search_func()

            if results:
                _log_search_step(step_num, description,
                                 success=True, count=len(results))
                return _process_search_results(results, keyword_stripped, progress_messages, translation_info)

            _log_search_step(step_num, description, success=False)

        # No results found after all attempts
        logger.info(
            "[MAIN SEARCH] ✗✗✗ NO RESULTS FOUND after all attempts ✗✗✗")
        progress_messages.append("No results found after all search attempts")
        return _create_search_response(
            keyword_stripped,
            status_msg="No results found even after trying translation, synonyms, and LLM search.",
            success=True,
            progress_messages=progress_messages
        )

    except Exception as e:
        logger.error(f"Exception in search_for_explainer: {e}", exc_info=True)
        return _create_search_response(
            keyword_stripped,
            status_msg=f"❌ Error: {str(e)}",
            success=False
        )


def generate_explanation(keyword: str, selected_choices: List[str], stored_results: List[Dict], language: str = 'en') -> Dict[str, Any]:
    """
    Generate explanation from selected items.
    EXACT COPY from keyword_extractor - adapted to return dict instead of Gradio components.

    Args:
        keyword: Search keyword
        selected_choices: List of selected choice labels
        stored_results: Stored search results data
        language: Language preference ('en' or 'vn')

    Returns:
        Dict with 'explanation', 'source_chunks', 'metadata', 'success'
    """
    import time

    if not keyword or not keyword.strip():
        return {
            'explanation': "Please enter a keyword first.",
            'source_chunks': '',
            'metadata': '',
            'success': False
        }

    if not stored_results or len(stored_results) == 0:
        return {
            'explanation': "Please search for a keyword first.",
            'source_chunks': '',
            'metadata': '',
            'success': False
        }

    try:
        # Time the validation step
        validation_start_time = time.perf_counter()

        # Get selected items based on checkbox selection
        selected_items = []

        # Handle None or empty selected_choices
        if not selected_choices:
            selected_choices = []

        # Build choice label to item mapping from stored_results
        # This creates the valid choices set for validation
        choice_to_item = {}
        valid_choices = set()

        docs = list_keyword_documents()
        docs_dict = {doc.get('doc_id'): doc.get(
            'name', 'Unknown') for doc in docs}

        for item in stored_results:
            doc_id = item.get('doc_id')
            section = item.get('section_heading')

            # Get doc_name from database for display
            doc_name = docs_dict.get(doc_id, 'Unknown')

            # Extract filename (same logic as search_for_explainer)
            display_name = doc_name
            if '\\' in display_name:
                display_name = display_name.split('\\')[-1]
            elif '/' in display_name:
                display_name = display_name.split('/')[-1]

            # Remove .pdf extension for cleaner display (must match search_for_explainer)
            if display_name.lower().endswith('.pdf'):
                display_name = display_name[:-4]

            section_display = section if section else "(No section)"
            choice_label = f"{display_name} → {section_display}"
            choice_to_item[choice_label] = {
                'doc_id': doc_id,
                'section_heading': section,
                # Preserve matching keywords
                '_matching_keywords': item.get('_matching_keywords', [])
            }
            valid_choices.add(choice_label)

        # Filter selected_choices to only include valid ones
        # This prevents errors when search results change between searches
        valid_selected_choices = [
            c for c in selected_choices if c in valid_choices]

        if not valid_selected_choices:
            return {
                'explanation': "Please select at least one document/section to explain. (Note: Previous selections were cleared due to new search results.)",
                'source_chunks': '',
                'metadata': '',
                'success': False
            }

        # Map valid selected choices to items
        for choice in valid_selected_choices:
            if choice in choice_to_item:
                selected_items.append(choice_to_item[choice])

        if not selected_items:
            return {
                'explanation': "Please select at least one document/section to explain.",
                'source_chunks': '',
                'metadata': '',
                'success': False
            }

        validation_end_time = time.perf_counter()
        validation_time = round(validation_end_time - validation_start_time, 2)

        # Check if we need to generate explanations for multiple keywords per section
        # Group selected items by section and check for multiple matching keywords
        # Maps (doc_id, section) -> list of keywords to explain
        section_keywords_map = {}
        has_multi_keyword_sections = False

        for choice in valid_selected_choices:
            if choice in choice_to_item:
                item = choice_to_item[choice]
                doc_id = item['doc_id']
                section = item.get('section_heading')
                section_key = (doc_id, section)

                matching_keywords = item.get('_matching_keywords', [])
                if matching_keywords and len(matching_keywords) > 0:
                    # Multiple keywords matched this section - explain each
                    section_keywords_map[section_key] = matching_keywords
                    if len(matching_keywords) > 1:
                        has_multi_keyword_sections = True
                else:
                    # No matching keywords info - use the original keyword
                    section_keywords_map[section_key] = [keyword.strip()]

        # Only use multi-keyword logic if we actually have sections with multiple keywords
        if has_multi_keyword_sections:
            # Generate explanations for each keyword-section combination
            all_section_results = []
            for section_key, keywords_to_explain in section_keywords_map.items():
                doc_id, section = section_key

                # Only process multiple keywords, skip single keyword sections handled normally
                if len(keywords_to_explain) > 1:
                    for kw in keywords_to_explain:
                        # Create selected_items for this specific keyword-section
                        keyword_selected_items = [{
                            'doc_id': doc_id,
                            'section_heading': section
                        }]

                        # Generate explanation for this keyword in this section
                        section_result = explain_keyword(
                            kw, keyword_selected_items, use_hyde=True, language=language)

                        if section_result and not section_result.get('error'):
                            all_section_results.append({
                                'keyword': kw,
                                'section_key': section_key,
                                'result': section_result
                            })

            # If we have multi-keyword results, combine them with single-keyword sections
            if all_section_results:
                # Get single-keyword sections and generate normally
                single_keyword_sections = [
                    {'doc_id': doc_id, 'section_heading': section}
                    for (doc_id, section), keywords in section_keywords_map.items()
                    if len(keywords) == 1
                ]

                if single_keyword_sections:
                    # Generate explanation for single-keyword sections normally
                    single_result = explain_keyword(
                        keyword.strip(), single_keyword_sections, use_hyde=True, language=language)
                    if single_result and not single_result.get('error'):
                        # Add as a combined result
                        all_section_results.append({
                            'keyword': keyword.strip(),
                            'section_key': None,  # Multiple sections
                            'result': single_result
                        })

                # Use combined result path below
                result = None  # Will be set in combined logic
            else:
                # No multi-keyword results, use normal flow
                result = explain_keyword(
                    keyword.strip(), selected_items, use_hyde=True, language=language)
        else:
            # No multi-keyword sections, use normal behavior
            result = explain_keyword(
                keyword.strip(), selected_items, use_hyde=True, language=language)
            all_section_results = []  # Initialize for consistency

        # Combine all explanations if we have multi-keyword results
        if has_multi_keyword_sections and all_section_results:
            # Combine explanations from all keyword-section combinations
            combined_explanations = []
            all_source_chunks = []
            all_citations = {}
            citation_offset = 0
            hyde_query = keyword.strip()
            detected_language = 'english'

            for section_data in all_section_results:
                section_result = section_data['result']
                kw = section_data['keyword']

                explanation = section_result.get('explanation', '')
                if explanation:
                    # Prefix with keyword for clarity
                    combined_explanations.append(
                        f"**Explanation for '{kw}':**\n\n{explanation}")

                # Collect source chunks and citations
                chunks = section_result.get('source_chunks', [])
                all_source_chunks.extend(chunks)

                citations = section_result.get('citations', {})
                for citation_num, citation_info in citations.items():
                    all_citations[citation_offset +
                                  citation_num] = citation_info
                citation_offset += len(citations)

                # Use first non-empty values
                if section_result.get('hyde_query'):
                    hyde_query = section_result['hyde_query']
                if section_result.get('language'):
                    detected_language = section_result['language']

            # Combine all explanations
            final_explanation = '\n\n---\n\n'.join(combined_explanations)

            # Create combined result
            timing_metadata_combined = {}
            for section_data in all_section_results:
                section_timing = section_data['result'].get(
                    'timing_metadata', {})
                if section_timing:
                    # Merge timing metadata (could be improved to sum properly)
                    if not timing_metadata_combined:
                        timing_metadata_combined = section_timing.copy()
                    else:
                        # Sum section timings
                        existing_sections = timing_metadata_combined.get(
                            'section_timings', [])
                        new_sections = section_timing.get(
                            'section_timings', [])
                        timing_metadata_combined['section_timings'] = existing_sections + new_sections

            result = {
                'explanation': final_explanation,
                'source_chunks': all_source_chunks,
                'hyde_query': hyde_query,
                'language': detected_language,
                'hyde_timing': {},
                'chunks_used': len(all_source_chunks),
                'citations': all_citations,
                'error': None,
                'timing_metadata': timing_metadata_combined
            }

        if result.get('error'):
            return {
                'explanation': f"❌ Error: {result['error']}",
                'source_chunks': '',
                'metadata': '',
                'success': False
            }

        # Build explanation output
        explanation_text = f"## Explanation\n\n{result.get('explanation', 'No explanation generated.')}"

        # Build source chunks output
        source_chunks = result.get('source_chunks', [])
        chunks_text = f"### Source Chunks ({len(source_chunks)} chunks used)\n\n"
        for i, chunk in enumerate(source_chunks, 1):  # Show all chunks (no limit)
            section = chunk.get('section_heading') or 'No section'
            content = chunk.get('content') or ''
            content_preview = content[:200] if content else '(Empty chunk)'
            chunks_text += f"**Chunk {i}** (Section: {section})\n"
            chunks_text += f"{content_preview}...\n\n"

        # Build metadata output
        metadata_text = "### Metadata\n\n"
        metadata_text += f"- **HYDE Query:** {result.get('hyde_query', keyword)}\n"
        metadata_text += f"- **Language Detected:** {result.get('language', 'english')}\n"
        metadata_text += f"- **Chunks Used:** {result.get('chunks_used', 0)}\n"
        if result.get('hyde_timing'):
            timing = result['hyde_timing']
            if 'total_time' in timing:
                metadata_text += f"- **HYDE Timing:** {timing['total_time']}s\n"

        # Collect timing metadata and calculate total
        timing_metadata = result.get('timing_metadata', {})
        if timing_metadata:
            timing_metadata['validation_time'] = validation_time
            total_time = (
                validation_time +
                timing_metadata.get('hyde_expansion_time', 0.0) +
                sum(s.get('time', 0.0) for s in timing_metadata.get('section_timings', [])) +
                timing_metadata.get('formatting_time', 0.0)
            )
            timing_metadata['total_time'] = round(total_time, 2)
        else:
            timing_metadata = {
                'validation_time': validation_time,
                'hyde_expansion_time': 0.0,
                'section_timings': [],
                'formatting_time': 0.0,
                'total_time': validation_time
            }

        return {
            'explanation': explanation_text,
            'source_chunks': chunks_text,
            'metadata': metadata_text,
            'timing_metadata': timing_metadata,
            'citations': result.get('citations', {}),
            'success': True
        }

    except Exception as e:
        import traceback
        return {
            'explanation': f"❌ Error generating explanation: {str(e)}\n\n{traceback.format_exc()}",
            'source_chunks': '',
            'metadata': '',
            'success': False
        }


def select_all_items(stored_results: List[Dict]) -> Dict[str, Any]:
    """
    Select all items - return all choice labels.
    EXACT COPY from keyword_extractor - adapted to return dict instead of Gradio components.

    Args:
        stored_results: Stored search results data

    Returns:
        Dict with 'choices' list
    """
    if not stored_results or len(stored_results) == 0:
        return {'choices': []}

    # Get document names from database
    docs = list_keyword_documents()
    docs_dict = {doc.get('doc_id'): doc.get('name', 'Unknown') for doc in docs}

    choices = []
    for item in stored_results:
        doc_id = item.get('doc_id')
        section = item.get('section_heading')

        doc_name = docs_dict.get(doc_id, 'Unknown')

        # Extract filename (same logic as search_for_explainer)
        display_name = doc_name
        if '\\' in display_name:
            display_name = display_name.split('\\')[-1]
        elif '/' in display_name:
            display_name = display_name.split('/')[-1]

        # Remove .pdf extension for cleaner display (must match search_for_explainer)
        if display_name.lower().endswith('.pdf'):
            display_name = display_name[:-4]

        section_display = section if section else "(No section)"
        choice_label = f"{display_name} → {section_display}"
        choices.append(choice_label)

    return {'choices': choices}


def select_none_items() -> Dict[str, Any]:
    """
    Deselect all items - return empty list.
    EXACT COPY from keyword_extractor - adapted to return dict instead of Gradio components.

    Returns:
        Dict with empty 'choices' list
    """
    return {'choices': []}


def _check_translated_aliases(keyword: str, progress_messages: List[str] = None) -> List[Dict]:
    """Check aliases for translated keyword. Returns results if found, empty list otherwise."""
    try:
        from backend.services.translation_synonym_service import translate_with_google
        trans_result = translate_with_google(keyword)

        if trans_result.get('success'):
            translation = trans_result.get('translated_text', '')
            if translation and translation.lower() != keyword.lower():
                logger.info(
                    f"[TRANSLATED ALIASES] Checking for: '{translation}'")
                return _search_aliases(translation, progress_messages)
    except Exception as e:
        logger.warning(f"[TRANSLATED ALIASES] Error: {e}")

    return []


def _search_aliases(keyword: str, progress_messages: List[str] = None, emit: Optional[callable] = None) -> List[Dict]:
    """Search using alias dictionary. Returns results if found, empty list otherwise.

    When a keyword matches an alias group (either as main keyword or child alias),
    searches for ALL terms in that group: main keyword + all child aliases.
    """
    msg = f"Searching aliases for {keyword}"
    if emit:
        emit(msg)
    if progress_messages is not None:
        progress_messages.append(msg)

    alias_matches = find_keyword_by_alias(keyword.lower())

    # Collect all main keywords from matches
    main_keywords = set()
    if alias_matches:
        for match in alias_matches:
            base_keyword = match.get('keyword', '')
            if base_keyword:
                main_keywords.add(base_keyword.lower())

    # Always check if the search term itself is a main keyword
    # (check if it exists as a keyword in the database and has aliases)
    all_aliases_for_term = get_aliases_for_keyword(keyword)
    if all_aliases_for_term:
        # If the term has aliases, it means it's a main keyword itself
        main_keywords.add(keyword.lower())

    # Also check directly if the term exists as a keyword (even without aliases yet)
    # This handles the case where someone searches for a main keyword that exists
    client = get_supabase_client()
    keyword_lower = keyword.strip().lower()
    result = client.table('keyword_aliases').select(
        'keyword').eq('keyword', keyword_lower).limit(1).execute()
    if result.data and len(result.data) > 0:
        main_keywords.add(keyword_lower)

    if not main_keywords:
        return []

    # For each main keyword, get all its aliases and build complete search set
    # Use ordered structure: main keywords first, then aliases
    main_search_terms = []
    alias_search_terms = []
    seen_keywords = set()

    for main_kw in main_keywords:
        if main_kw in seen_keywords:
            continue
        seen_keywords.add(main_kw)

        # Add the main keyword itself (search these first)
        main_search_terms.append(main_kw)

        # Get all aliases for this main keyword
        aliases = get_aliases_for_keyword(main_kw)
        for alias in aliases:
            alias_lower = alias.lower()
            if alias_lower not in alias_search_terms and alias_lower != main_kw:
                alias_search_terms.append(alias_lower)

    # Combine: main keywords first, then aliases
    all_search_terms = main_search_terms + alias_search_terms

    if not all_search_terms:
        return []

    # Search database for each term sequentially and combine results
    # Track which keywords matched each chunk for explanation generation
    all_results = []
    # Maps (doc_id, section) -> set of matching keywords
    result_keywords_map = {}

    for search_term in all_search_terms:
        msg = f"Searching database for {search_term}"
        if emit:
            emit(msg)
        if progress_messages is not None:
            progress_messages.append(msg)

        results = keyword_search(search_term, limit=100)

        if not results:
            continue

        # Combine and deduplicate results, tracking which keywords matched
        for result in results:
            doc_id = result.get('doc_id', '') or ''
            # Keep None as None for proper deduplication
            section = result.get('section_heading')
            result_key = (doc_id, section)

            # Track keywords that matched this chunk
            if result_key not in result_keywords_map:
                result_keywords_map[result_key] = set()
            result_keywords_map[result_key].add(search_term)

            # Only add result once (deduplicate)
            if result_key not in {r.get('_result_key') for r in all_results if '_result_key' in r}:
                result_with_key = dict(result)
                result_with_key['_result_key'] = result_key
                all_results.append(result_with_key)

    # Attach matching keywords to each result for explanation generation
    for result in all_results:
        result_key = result.get('_result_key')
        if result_key in result_keywords_map:
            result['_matching_keywords'] = list(
                result_keywords_map[result_key])
        result.pop('_result_key', None)  # Remove temporary key

    if all_results:
        msg = f"Found {len(all_results)} unique results for alias group (searched {len(all_search_terms)} terms)"
        if emit:
            emit(msg)
        if progress_messages is not None:
            progress_messages.append(msg)
        logger.info(
            f"[ALIAS SEARCH] Combined {len(all_results)} results from {len(all_search_terms)} search terms: {all_search_terms}")
        return all_results

    return []


def _search_database(keyword: str, progress_messages: List[str] = None, emit: Optional[callable] = None) -> List[Dict]:
    """Search database directly. Returns results if found, empty list otherwise."""
    logger.info(f"[DB SEARCH] Searching database for: '{keyword}'")

    msg = f"Searching database for {keyword}"
    if emit:
        emit(msg)
    if progress_messages is not None:
        progress_messages.append(msg)

    results = keyword_search(keyword, limit=100)
    if results:
        logger.info(
            f"[DB SEARCH] ✓ Found {len(results)} results for '{keyword}'")

        # Tag each result with the keyword that matched it
        for r in results:
            if '_matching_keywords' not in r:
                r['_matching_keywords'] = []
            if keyword not in r['_matching_keywords']:
                r['_matching_keywords'].append(keyword)

        msg = f"Found for {keyword}"
        if emit:
            emit(msg)
        if progress_messages is not None:
            progress_messages.append(msg)
        return results

    logger.info(f"[DB SEARCH] ✗ No results found for '{keyword}'")
    return []


def _search_with_translation(keyword: str, progress_messages: List[str] = None, emit: Optional[callable] = None) -> tuple:
    """Search for both original keyword and its translation. Returns combined, deduplicated results.

    Always searches both the original term and its translation (if available) to ensure
    comprehensive results regardless of language. Results are deduplicated by (doc_id, section_heading).

    Returns:
        tuple: (results: List[Dict], translation_info: Dict[str, str])
        translation_info contains 'original' and 'translation' keys
    """
    results_map = {}  # Map (doc_id, section_heading) -> result object
    translation = None
    detected_lang = None

    logger.info("=" * 80)
    logger.info(f"[SEARCH] Starting search for keyword: '{keyword}'")

    # Step 1: Try to detect language and translate
    search_terms = [keyword]

    try:
        from backend.services.translation_synonym_service import translate_with_google, detect_language_local

        detected_lang = detect_language_local(keyword)
        logger.info(f"[SEARCH] Detected language: {detected_lang}")

        trans_result = translate_with_google(keyword)
        if trans_result.get('success'):
            translation = trans_result.get('translated_text', '')
            if translation and translation.strip():
                translation_clean = translation.strip()
                if translation_clean.lower() != keyword.lower():
                    search_terms.append(translation_clean)

        else:
            logger.warning(
                f"[SEARCH] Translation failed: {trans_result.get('error', 'Unknown error')}")
    except Exception as e:
        logger.warning(f"[SEARCH] Translation exception: {e}")

    # Build message
    msg = f"Searching for '{search_terms[0]}'" + \
        (f" and '{search_terms[1]}'" if len(search_terms) > 1 else "")
    if emit:
        emit(msg)
    if progress_messages is not None:
        progress_messages.append(msg)

    # Step 2: Search for each term and combine results (with keyword merging)
    for search_term in search_terms:
        results = _search_database(search_term, progress_messages, emit)
        if results:
            for r in results:
                doc_id = r.get('doc_id', '') or ''
                section = r.get('section_heading')
                key = (doc_id, section)

                if key in results_map:
                    # Merge matching keywords
                    existing = results_map[key]
                    new_keywords = r.get('_matching_keywords', [])
                    if '_matching_keywords' not in existing:
                        existing['_matching_keywords'] = []
                    for kw in new_keywords:
                        if kw not in existing['_matching_keywords']:
                            existing['_matching_keywords'].append(kw)
                else:
                    results_map[key] = r

    # Step 3: Check aliases
    alias_results = _search_aliases(keyword, progress_messages, emit)
    if alias_results:
        for r in alias_results:
            doc_id = r.get('doc_id', '') or ''
            section = r.get('section_heading')
            key = (doc_id, section)

            if key in results_map:
                existing = results_map[key]
                new_keywords = r.get('_matching_keywords', [])
                if '_matching_keywords' not in existing:
                    existing['_matching_keywords'] = []
                for kw in new_keywords:
                    if kw not in existing['_matching_keywords']:
                        existing['_matching_keywords'].append(kw)
            else:
                results_map[key] = r

    all_results = list(results_map.values())
    logger.info(
        f"[SEARCH] Final combined result: {len(all_results)} unique combinations")

    # Return results and translation info
    translation_info = {
        'original': keyword,
        'translation': translation.strip() if translation and translation.strip() and translation.strip().lower() != keyword.lower() else None
    }

    return all_results, translation_info


def _try_translation_and_synonyms(keyword: str, progress_messages: List[str] = None, emit: Optional[callable] = None, add_progress: bool = False) -> List[Dict]:
    """Try searching with synonyms (translation already done earlier). Returns results if found, empty list otherwise."""
    try:
        from backend.services.translation_synonym_service import auto_translate_and_find_synonyms

        if add_progress and progress_messages is not None:
            progress_messages.append(
                "Generating synonyms, searching with synonyms now")

        logger.info("=" * 80)
        logger.info(f"[SYNONYM SEARCH] Generating synonyms for: '{keyword}'")

        trans_result = auto_translate_and_find_synonyms(keyword)

        if not trans_result.get('success'):
            error_msg = trans_result.get('error', 'Translation failed')
            logger.warning(
                f"[SYNONYM SEARCH] Translation/synonym service failed: {error_msg}")
            return []

        translation = trans_result.get('translation', '')
        synonyms_original = trans_result.get('synonyms_original', [])
        synonyms_translated = trans_result.get('synonyms_translated', [])

        logger.info(
            f"[SYNONYM SEARCH] Translation: '{keyword}' -> '{translation}'")
        logger.info(
            f"[SYNONYM SEARCH] Synonyms (original language): {synonyms_original}")
        logger.info(
            f"[SYNONYM SEARCH] Synonyms (translated language): {synonyms_translated}")

        # Try synonyms (translation already searched in _search_with_translation)
        all_synonyms = synonyms_original + synonyms_translated
        if all_synonyms:
            logger.info(
                f"[SYNONYM SEARCH] Total synonyms to try: {len(all_synonyms)}")
            # Search with each synonym
            for i, synonym in enumerate(all_synonyms, 1):
                if not synonym or synonym == keyword or synonym == translation:
                    logger.info(
                        f"[SYNONYM SEARCH] Skipping synonym {i}: '{synonym}' (duplicate or empty)")
                    continue

                logger.info(
                    f"[SYNONYM SEARCH] Trying synonym {i}/{len(all_synonyms)}: '{synonym}'")

                results = _search_aliases(synonym, progress_messages, emit)
                if results:
                    logger.info(
                        f"[SYNONYM SEARCH] ✓ Found results with synonym '{synonym}' in aliases!")
                    return results

                results = _search_database(synonym, progress_messages, emit)
                if results:
                    logger.info(
                        f"[SYNONYM SEARCH] ✓ Found results with synonym '{synonym}' in database!")
                    return results

                logger.info(
                    f"[SYNONYM SEARCH] ✗ No results with synonym '{synonym}'")
        else:
            logger.info(f"[SYNONYM SEARCH] No synonyms generated")

        logger.info(f"[SYNONYM SEARCH] No results found with any synonyms")
        return []

    except Exception as e:
        logger.error(
            f"[SYNONYM SEARCH] Error in synonym step: {e}", exc_info=True)
        return []


def _try_llm_deep_search(keyword: str, progress_messages: List[str] = None, emit: Optional[callable] = None) -> List[Dict]:
    """Try LLM-based deep search as final fallback. Returns results if found, empty list otherwise."""
    try:
        from backend.services.deep_search_service import deep_search_keyword

        msg = "Not found... Searching deeper with LLM"
        if emit:
            emit(msg)
        if progress_messages is not None:
            progress_messages.append(msg)

        # Deep search uses LLM to generate translations and synonyms
        result = deep_search_keyword(keyword)

        if result.get('found'):
            selected_keyword = result.get('selected_keyword', '')
            if selected_keyword:
                msg = f"LLM found potential match: {selected_keyword}"
                if emit:
                    emit(msg)
                if progress_messages is not None:
                    progress_messages.append(msg)

                # Search with the LLM-suggested keyword
                search_results = _search_aliases(
                    selected_keyword, progress_messages, emit)
                if search_results:
                    return search_results

                search_results = _search_database(
                    selected_keyword, progress_messages, emit)
                if search_results:
                    return search_results

        return []

    except Exception as e:
        logger.error(f"Error in LLM deep search: {e}", exc_info=True)
        return []


def search_for_explainer_stream(keyword: str) -> Generator[str, None, None]:
    """
    Stream search progress using Server-Sent Events (SSE).
    Yields messages one at a time as the search progresses.

    Args:
        keyword: Search keyword

    Yields:
        SSE-formatted messages
    """
    def emit(msg: str):
        """Emit a message in SSE format."""
        yield f"data: {json.dumps({'message': msg})}\n\n"

    keyword_stripped = keyword.strip() if keyword else ""

    if not keyword_stripped:
        yield from emit("Please enter a keyword.")
        yield from emit("__DONE__")
        return

    try:
        # Use a list to collect messages for emit callback
        message_list = []

        def emit_callback(msg: str):
            """Callback that collects messages for immediate yielding."""
            message_list.append(msg)

        # Step 1: Search database for original keyword AND its translation immediately
        translation_result = _search_with_translation(
            keyword_stripped, emit=emit_callback)
        while message_list:
            yield from emit(message_list.pop(0))

        # Handle tuple return from _search_with_translation
        if isinstance(translation_result, tuple) and len(translation_result) == 2:
            results, _ = translation_result
        else:
            results = translation_result if translation_result else []

        if results:
            yield from emit("__DONE__")
            return

        # Step 2: Search aliases for both original and translated keywords
        results = _search_aliases(keyword_stripped, emit=emit_callback)
        while message_list:
            yield from emit(message_list.pop(0))

        if results:
            yield from emit("__DONE__")
            return

        # Also check aliases for translated keyword
        try:
            from backend.services.translation_synonym_service import translate_with_google, detect_language_local
            trans_result = translate_with_google(keyword_stripped)
            if trans_result.get('success'):
                translation = trans_result.get('translated_text', '')
                if translation and translation.lower() != keyword_stripped.lower():
                    results = _search_aliases(translation, emit=emit_callback)
                    while message_list:
                        yield from emit(message_list.pop(0))
                    if results:
                        yield from emit("__DONE__")
                        return
        except Exception:
            pass

        # Step 3: Try automatic translation and synonyms
        yield from emit("Generating synonyms, searching with synonyms now")

        results = _try_translation_and_synonyms(
            keyword_stripped, emit=emit_callback)
        while message_list:
            yield from emit(message_list.pop(0))

        if results:
            yield from emit("__DONE__")
            return

        # Step 4: Try LLM deep search as final fallback
        results = _try_llm_deep_search(keyword_stripped, emit=emit_callback)
        while message_list:
            yield from emit(message_list.pop(0))

        if results:
            yield from emit("__DONE__")
            return

        # Step 5: No results found
        yield from emit("No results found after all search attempts")
        yield from emit("__DONE__")

    except Exception as e:
        logger.error(
            f"Exception in search_for_explainer_stream: {e}", exc_info=True)
        yield from emit(f"❌ Error: {str(e)}")
        yield from emit("__DONE__")
