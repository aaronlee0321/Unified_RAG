"""
GDD Document Explainer backend functions.
EXACT COPY of logic from keyword_extractor - only adapted for Flask JSON responses.
"""
from typing import List, Dict, Optional, Any
from backend.services.search_service import keyword_search
from backend.services.explainer_service import explain_keyword
from backend.storage.keyword_storage import list_keyword_documents


def search_for_explainer(keyword: str) -> Dict[str, Any]:
    """
    Search for keyword and return results as checkboxes for selection.
    EXACT COPY from keyword_extractor - adapted to return dict instead of Gradio components.
    
    Args:
        keyword: Search keyword
    
    Returns:
        Dict with 'choices', 'store_data', 'status_msg', 'last_keyword'
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 80)
    logger.info(f"[SEARCH FOR EXPLAINER] Function called")
    logger.info(f"[SEARCH FOR EXPLAINER] Input keyword: '{keyword}' (type: {type(keyword)})")
    
    keyword_stripped = keyword.strip() if keyword else ""
    logger.info(f"[SEARCH FOR EXPLAINER] Stripped keyword: '{keyword_stripped}'")
    
    if not keyword or not keyword_stripped:
        logger.warning("[SEARCH FOR EXPLAINER] Empty keyword, returning empty response")
        return {
            'choices': [],
            'store_data': [],
            'status_msg': "Please enter a keyword to search.",
            'success': False
        }
    
    try:
        logger.info(f"[SEARCH FOR EXPLAINER] Calling keyword_search('{keyword_stripped}', limit=100)")
        results = keyword_search(keyword_stripped, limit=100)
        logger.info(f"[SEARCH FOR EXPLAINER] keyword_search returned: {type(results)}")
        logger.info(f"[SEARCH FOR EXPLAINER] Results is None: {results is None}")
        logger.info(f"[SEARCH FOR EXPLAINER] Results length: {len(results) if results else 'N/A'}")
        
        # Check if results is None or empty
        if results is None or not results or len(results) == 0:
            logger.info("[SEARCH FOR EXPLAINER] No results found, returning empty response")
            return {
                'choices': [],
                'store_data': [],
                'status_msg': "No results found. Try a different keyword or check if documents are indexed.",
                'success': True,  # Changed to True since no results is not an error
                'keyword': keyword_stripped
            }
        
        logger.info(f"[SEARCH FOR EXPLAINER] Processing {len(results)} results")
        
        # Group by document and section
        # Filter out items with no section (section_heading is None or empty)
        logger.info("[SEARCH FOR EXPLAINER] Grouping results by document and section")
        doc_sections = {}
        skipped_no_section = 0
        for idx, r in enumerate(results):
            try:
                doc_id = r.get('doc_id')
                doc_name = r.get('doc_name', 'Unknown Document')
                section = r.get('section_heading')
                content = r.get('content', '')
                
                # Skip items without a section heading
                if not section or section.strip() == '':
                    skipped_no_section += 1
                    continue
                
                # Create unique key for document-section pair
                key = (doc_id, doc_name, section)
                if key not in doc_sections:
                    doc_sections[key] = {
                        'doc_id': doc_id,
                        'doc_name': doc_name,
                        'section_heading': section,
                        'content': content,
                        'relevance': r.get('relevance', 0.0)
                    }
            except Exception as e:
                logger.error(f"[SEARCH FOR EXPLAINER] Error processing result {idx}: {e}")
                continue
        
        logger.info(f"[SEARCH FOR EXPLAINER] Grouped into {len(doc_sections)} unique doc-section pairs")
        logger.info(f"[SEARCH FOR EXPLAINER] Skipped {skipped_no_section} results without section headings")
        
        # Sort by relevance (highest first)
        logger.info("[SEARCH FOR EXPLAINER] Sorting by relevance")
        sorted_items = sorted(
            doc_sections.values(),
            key=lambda x: x['relevance'],
            reverse=True
        )
        logger.info(f"[SEARCH FOR EXPLAINER] Sorted {len(sorted_items)} items")
        
        # Create checkbox choices and store data
        logger.info("[SEARCH FOR EXPLAINER] Creating choices and store_data")
        choices = []
        store_data = []
        
        for idx, item in enumerate(sorted_items):
            try:
                # Extract filename for display (remove .pdf extension if present)
                display_name = item['doc_name']
                if '\\' in display_name:
                    display_name = display_name.split('\\')[-1]
                elif '/' in display_name:
                    display_name = display_name.split('/')[-1]
                
                # Remove .pdf extension for cleaner display
                if display_name.lower().endswith('.pdf'):
                    display_name = display_name[:-4]
                
                section_display = item['section_heading'] if item['section_heading'] else "(No section)"
                
                # Create choice label
                choice_label = f"{display_name} → {section_display}"
                choices.append(choice_label)
                
                # Store actual data including content for preview
                store_data.append({
                    'doc_id': item['doc_id'],
                    'doc_name': display_name,
                    'section_heading': item['section_heading'],
                    'content': item.get('content', '')
                })
            except Exception as e:
                logger.error(f"[SEARCH FOR EXPLAINER] Error creating choice for item {idx}: {e}")
                continue
        
        logger.info(f"[SEARCH FOR EXPLAINER] Created {len(choices)} choices and {len(store_data)} store_data entries")
        status_msg = f"✅ Found {len(sorted_items)} document/section combinations. Select which ones to explain."
        
        result_dict = {
            'choices': choices,
            'store_data': store_data,
            'status_msg': status_msg,
            'success': True,
            'keyword': keyword_stripped
        }
        
        logger.info(f"[SEARCH FOR EXPLAINER] Returning result with {len(choices)} choices")
        logger.info(f"[SEARCH FOR EXPLAINER] Result dict keys: {list(result_dict.keys())}")
        logger.info("=" * 80)
        return result_dict
        
    except Exception as e:
        logger.error("=" * 80)
        logger.error(f"[SEARCH FOR EXPLAINER] EXCEPTION: {str(e)}")
        logger.error(f"[SEARCH FOR EXPLAINER] Exception type: {type(e).__name__}")
        import traceback
        full_traceback = traceback.format_exc()
        logger.error(f"[SEARCH FOR EXPLAINER] Full traceback:\n{full_traceback}")
        logger.error("=" * 80)
        
        return {
            'choices': [],
            'store_data': [],
            'status_msg': f"❌ Error: {str(e)}",
            'success': False,
            'keyword': keyword_stripped if 'keyword_stripped' in locals() else ''
        }


def generate_explanation(keyword: str, selected_choices: List[str], stored_results: List[Dict]) -> Dict[str, Any]:
    """
    Generate explanation from selected items.
    EXACT COPY from keyword_extractor - adapted to return dict instead of Gradio components.
    
    Args:
        keyword: Search keyword
        selected_choices: List of selected choice labels
        stored_results: Stored search results data
    
    Returns:
        Dict with 'explanation', 'source_chunks', 'metadata', 'success'
    """
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
        docs_dict = {doc.get('doc_id'): doc.get('name', 'Unknown') for doc in docs}
        
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
                'section_heading': section
            }
            valid_choices.add(choice_label)
        
        # Filter selected_choices to only include valid ones
        # This prevents errors when search results change between searches
        valid_selected_choices = [c for c in selected_choices if c in valid_choices]
        
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
        
        # Generate explanation
        result = explain_keyword(keyword.strip(), selected_items, use_hyde=True)
        
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
        
        return {
            'explanation': explanation_text,
            'source_chunks': chunks_text,
            'metadata': metadata_text,
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




