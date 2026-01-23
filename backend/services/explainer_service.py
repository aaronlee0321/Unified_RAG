"""
Document Explainer service - generates detailed explanations from keyword queries.
Uses section-based chunk retrieval with sequential LLM processing for comprehensive results.
"""
from typing import List, Dict, Optional, Any, Tuple
import re
import time
from backend.storage.supabase_client import get_supabase_client
from backend.storage.keyword_storage import list_keyword_documents
from backend.services.search_service import keyword_search
from backend.services.llm_provider import SimpleLLMProvider
from backend.services.hyde_service import hyde_expand_query


def detect_query_language(text: str) -> str:
    """
    Detect if the query is in Vietnamese or English.

    Args:
        text: The query text

    Returns:
        'vietnamese' or 'english'
    """
    text_lower = text.lower()

    # Vietnamese characters (accented letters)
    vietnamese_chars = 'àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ'

    # Common Vietnamese words
    vietnamese_words = [
        'là', 'của', 'và', 'với', 'trong', 'cho', 'được', 'có', 'không', 'một',
        'các', 'này', 'đó', 'như', 'theo', 'từ', 'về', 'đến', 'nếu', 'khi',
        'thiết kế', 'mục đích', 'tương tác', 'thành phần', 'chức năng'
    ]

    # Check for Vietnamese characters
    has_vietnamese_chars = any(char in vietnamese_chars for char in text)

    # Check for Vietnamese words
    has_vietnamese_words = any(word in text_lower for word in vietnamese_words)

    # Count Vietnamese indicators
    vietnamese_score = 0
    if has_vietnamese_chars:
        vietnamese_score += 2
    if has_vietnamese_words:
        vietnamese_score += len([w for w in vietnamese_words if w in text_lower])

    # If there are clear Vietnamese indicators, return Vietnamese
    if vietnamese_score >= 2:
        return 'vietnamese'

    # Default to English
    return 'english'


def get_all_chunks_from_section(doc_id: str, section_heading: str) -> List[Dict[str, Any]]:
    """
    Get ALL chunks from a section (not just keyword matches).
    This ensures we get complete context even if information is split across chunks.

    Args:
        doc_id: Document ID
        section_heading: Section heading (can be None for chunks without section)

    Returns:
        List of chunks from the section, ordered by chunk_index
    """
    client = get_supabase_client()

    query = client.table('keyword_chunks').select(
        '*').eq('doc_id', doc_id).order('chunk_index')

    if section_heading:
        query = query.eq('section_heading', section_heading)
    else:
        query = query.is_('section_heading', 'null')

    result = query.execute()
    return result.data if result.data else []


def _add_citation_to_text(text: str, citation_number: int) -> str:
    """
    Add a citation number to the end of every paragraph in the text.

    Args:
        text: Explanation text
        citation_number: Citation number to add (1, 2, 3...)

    Returns:
        Text with citations added to the end of each paragraph (as HTML span elements)
    """
    if not text:
        return text

    # Convert citation number to circled number
    if 1 <= citation_number <= 20:
        citation_char = chr(0x2460 + citation_number - 1)  # ①-⑳
    else:
        citation_char = f"({citation_number})"

    # Wrap citation in HTML span with class and data attribute for click handling
    citation_html = f'<span class="citation-marker" data-citation-number="{citation_number}">{citation_char}</span>'

    # Split text into paragraphs (double newline)
    paragraphs = text.split('\n\n')
    cited_paragraphs = []

    for para in paragraphs:
        if not para.strip():
            cited_paragraphs.append(para)
            continue

        # Remove trailing whitespace and add citation at the end of the paragraph
        para = para.rstrip()
        cited_paragraphs.append(para + f" {citation_html}")

    return '\n\n'.join(cited_paragraphs)


def _filter_missing_info_statements(text: str) -> str:
    """
    Remove statements about missing information from the explanation.
    Removes lines containing missing information statements, and removes entire sections
    if they only contain such statements.

    Args:
        text: Explanation text

    Returns:
        Filtered text without statements about missing information
    """
    if not text:
        return text

    lines = text.split('\n')
    filtered_lines = []

    # Patterns to match statements about missing information
    missing_info_patterns = [
        r'the document does not specify',
        r'the document does not provide',
        r'the document does not contain',
        r'this chunk does not contain',
        r'no information.*provided',
        r'no information.*specified',
        r'information.*not.*available',
        r'information.*not.*specified',
        r'information.*not.*provided',
        r'the document.*does not.*mention',
        r'there is no information',
        r'does not provide.*information',
        r'does not specify.*information',
    ]

    current_section = []

    for line in lines:
        line_lower = line.lower().strip()

        # Check if this line is a section header (starts with number)
        is_section_header = re.match(r'^\d+\.', line.strip())

        # Check if line contains missing information statements
        contains_missing_info = any(re.search(pattern, line_lower)
                                    for pattern in missing_info_patterns) if line_lower else False

        if is_section_header:
            # Process previous section: check if it has real content
            if current_section:
                section_text = '\n'.join(current_section).lower()
                # Check if section has any non-missing-info content
                section_lines = section_text.split('\n')
                has_real_content = False
                for sec_line in section_lines:
                    if sec_line.strip() and not re.match(r'^\d+\.', sec_line.strip()):
                        if not any(re.search(pattern, sec_line) for pattern in missing_info_patterns):
                            has_real_content = True
                            break

                # Only add section if it has real content
                if has_real_content:
                    # Filter out missing info lines from section
                    filtered_section = []
                    for sec_line in current_section:
                        sec_line_lower = sec_line.lower().strip()
                        if not sec_line_lower or re.match(r'^\d+\.', sec_line.strip()):
                            filtered_section.append(sec_line)
                        elif not any(re.search(pattern, sec_line_lower) for pattern in missing_info_patterns):
                            filtered_section.append(sec_line)

                    if filtered_section:
                        filtered_lines.extend(filtered_section)
                        # Add blank line between sections
                        filtered_lines.append('')

            # Start new section
            current_section = [line]
        elif contains_missing_info:
            # Skip this line (missing info statement)
            continue
        else:
            # Regular content line
            if current_section:
                current_section.append(line)
            else:
                filtered_lines.append(line)

    # Process last section
    if current_section:
        section_text = '\n'.join(current_section).lower()
        section_lines = section_text.split('\n')
        has_real_content = False
        for sec_line in section_lines:
            if sec_line.strip() and not re.match(r'^\d+\.', sec_line.strip()):
                if not any(re.search(pattern, sec_line) for pattern in missing_info_patterns):
                    has_real_content = True
                    break

        if has_real_content:
            filtered_section = []
            for sec_line in current_section:
                sec_line_lower = sec_line.lower().strip()
                if not sec_line_lower or re.match(r'^\d+\.', sec_line.strip()):
                    filtered_section.append(sec_line)
                elif not any(re.search(pattern, sec_line_lower) for pattern in missing_info_patterns):
                    filtered_section.append(sec_line)

            if filtered_section:
                filtered_lines.extend(filtered_section)

    # Join and clean up multiple blank lines
    result = '\n'.join(filtered_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)  # Replace 3+ newlines with 2
    result = result.strip()

    return result


def select_chunks_for_answer(chunks: List[Dict]) -> List[Dict]:
    """
    Heuristic to decide how many chunks to feed into the answer prompt.
    Adapted from unified_rag_app's _select_chunks_for_answer.

    Args:
        chunks: List of chunks with relevance scores

    Returns:
        Selected chunks (1-5 based on score distribution)
    """
    if not chunks:
        return []

    scores = [float(c.get("relevance", 0.0) or 0.0) for c in chunks]
    s1 = scores[0] if scores else 0.0
    s2 = scores[1] if len(scores) > 1 else 0.0

    # If retrieval score itself is already ~1.0, use only the top chunk
    if s1 >= 0.999:
        n = 1
    # A: very strong, clearly dominant top chunk → 1 chunk
    elif s1 >= 0.6 and (s1 - s2) >= 0.15:
        n = 1
    # B: strong top chunk, close second → 2 chunks
    elif s1 >= 0.6 and s2 >= s1 - 0.15:
        n = min(2, len(chunks))
    # C: moderately strong → 3 chunks
    elif s1 >= 0.5:
        n = min(3, len(chunks))
    # D: weak/flat scores → up to 5 chunks
    else:
        n = min(5, len(chunks))

    return chunks[:n]


def _explain_single_section(
    keyword: str,
    doc_id: str,
    section_heading: Optional[str],
    hyde_query: str,
    doc_name_map: Dict[str, str],
    detected_language: str,
) -> Dict[str, Any]:
    """
    Generate explanation for a single section.

    Args:
        keyword: Original keyword query
        doc_id: Document ID
        section_heading: Section heading (can be None)
        hyde_query: HYDE-expanded query
        doc_name_map: Mapping of doc_id to document name
        detected_language: Detected language ('english' or 'vietnamese')

    Returns:
        Dict with 'explanation', 'source_chunks', 'citations', 'error', etc.
    """
    try:
        # Get all chunks from this section
        section_chunks = get_all_chunks_from_section(doc_id, section_heading)

        if not section_chunks:
            return {
                'explanation': None,
                'source_chunks': [],
                'citations': {},
                'error': f'No chunks found for section: {section_heading or "No section"}'
            }

        # Get keyword-matched chunks for relevance scoring
        matched_chunks = keyword_search(
            hyde_query, limit=20, doc_id_filter=doc_id)
        matched_in_section = [
            c for c in matched_chunks
            if c.get('section_heading') == section_heading or
            (section_heading is None and c.get('section_heading') is None)
        ]

        # Create a relevance map from matched chunks
        relevance_map = {c.get('chunk_id'): c.get('relevance', 0.0)
                         for c in matched_in_section}

        # Combine section chunks with relevance scores
        chunks_with_relevance = []
        for chunk in section_chunks:
            chunk_id = chunk.get('chunk_id')
            if chunk_id:
                chunk_with_relevance = dict(chunk)
                chunk_with_relevance['relevance'] = relevance_map.get(
                    chunk_id, 0.0)
                chunk_with_relevance['doc_id'] = doc_id
                if 'content' not in chunk_with_relevance or chunk_with_relevance.get('content') is None:
                    chunk_with_relevance['content'] = ''
                chunks_with_relevance.append(chunk_with_relevance)

        # Sort by chunk_index to maintain order
        chunks_with_relevance.sort(key=lambda x: x.get('chunk_index', 0))

        # Filter to only relevant chunks (relevance > 0.0)
        relevant_chunks = [
            c for c in chunks_with_relevance if c.get('relevance', 0.0) > 0.0]

        if relevant_chunks:
            # Sort by relevance (descending), then by chunk_index
            relevant_chunks.sort(
                key=lambda x: (-x.get('relevance', 0.0), x.get('chunk_index', 0)))
            # Limit chunks per section to avoid token overflow (max 10 chunks per section)
            selected_chunks = relevant_chunks[:10]
        else:
            # Fallback: use first few chunks if no keyword matches
            selected_chunks = chunks_with_relevance[:5]

        if not selected_chunks:
            return {
                'explanation': None,
                'source_chunks': [],
                'citations': {},
                'error': f'No relevant chunks found for section: {section_heading or "No section"}'
            }

        # Build prompt with chunk context
        # Sort chunks by chunk_id to match sidebar order (alphanumeric)
        selected_chunks_sorted = sorted(
            selected_chunks, key=lambda x: x.get('chunk_id', '') or '')

        chunk_texts_with_sections = []
        citation_map = {}

        for chunk in selected_chunks_sorted:
            if not chunk.get('doc_id') or chunk.get('content') is None:
                continue

            doc_name = doc_name_map.get(doc_id, doc_id)
            section_heading_val = chunk.get('section_heading')
            chunk_id = chunk.get('chunk_id', '')

            # Store citation info (will be set by caller)
            citation_map[chunk_id] = {
                'doc_id': doc_id,
                'doc_name': doc_name,
                'section_heading': section_heading_val,
                'chunk_id': chunk_id
            }

            section_info = f" [Section: {section_heading_val}]" if section_heading_val else " [No section]"
            content = chunk.get('content', '') or ''

            chunk_texts_with_sections.append(
                f"[Chunk from {doc_name}{section_info}]\n{content}"
            )

        chunk_texts_enhanced = "\n\n".join(chunk_texts_with_sections)

        # Determine response language instruction
        if detected_language == 'vietnamese':
            language_instruction = "IMPORTANT: Respond in Vietnamese (Tiếng Việt). Your entire answer must be in Vietnamese."
        else:
            language_instruction = "IMPORTANT: Respond in English. Your entire answer must be in English."

        # Build prompt (same format as before, but for single section)
        prompt = f"""Based on the following document chunks, provide a detailed explanation for: {keyword}

{language_instruction}

FOCUS REQUIREMENT:
- Focus ONLY on information directly related to: {keyword}
- If a chunk does not contain information about {keyword}, SKIP IT ENTIRELY. Do NOT include it in your response.
- Do NOT explain chunks that are irrelevant to the keyword query.
- Only include information that is directly relevant to explaining {keyword}.
- Do NOT include any statements about missing information such as "The document does not specify this" or "The document does not provide information about X".

Note:
- The information may be spread across multiple chunks.
- Each chunk MUST be output as a numbered section with the section name as the BOLDED heading, followed by a NEWLINE and paragraph explaining that chunk's content.
- Format each section EXACTLY as follows:

1. Section Title
Paragraph content explaining the information from this chunk.

2. Another Section Title
Paragraph content explaining the information from this chunk.

3. Third Section Title
Paragraph content explaining the information from this chunk.

OUTPUT FORMAT REQUIREMENTS:
- Start each section with a number (1., 2., 3., etc.) followed by a space, then the section title.
- The section title should be the section name from the chunk (remove hierarchical numbering like 4.2, a., i.).
- After the section title, add a blank line, then write a paragraph explaining that chunk's content.
- Each section must be separated by a blank line.
- Do NOT combine multiple chunks into one section.
- Only explain chunks that contain information relevant to {keyword}. If a chunk is irrelevant, SKIP IT COMPLETELY - do not include it in your response at all.

EXAMPLE OUTPUT FORMAT:
1. Tank Stats
The tank stats section displays the basic statistics of the tank. It includes the following attributes: HP, speed, rate of fire, and damage. Each statistic is presented using a progress bar.

2. Tank Customization
The tank customization allows players to modify various aspects of their tank, including weapons, armor, and special abilities.


STRICT RULES (NO HALLUCINATION):
- Do NOT add design intent, balance reasoning, or gameplay purpose unless explicitly stated in the document.
- Do NOT compare values or features (e.g., stronger, weaker, higher, lower) unless the document explicitly makes that comparison.
- Do NOT infer advantages, disadvantages, effectiveness, or player benefit.
- Do NOT explain why something exists unless the document states the reason.
- Avoid interpretive or analytical phrases such as:
"this suggests", "this indicates", "this implies",
"well-rounded", "effective", "designed to", "intended to".

EVIDENCE REQUIREMENT:
- Every factual claim must be directly supported by the provided chunks.
- Do NOT rely on external knowledge or assumptions.
- If information is missing or not stated in a chunk, SKIP THAT CHUNK entirely. Do NOT include statements like "The document does not specify this" or "The document does not provide information about X".

STAT HANDLING RULE:
- If the source content is a stat table or attribute list, only restate the values exactly as written.
- Do NOT rank, evaluate, or interpret stats.
- Do NOT convert qualitative stat labels into gameplay conclusions.

OUTPUT STYLE:
- Write in a neutral, factual, documentation-style tone.
- Describe only documented behavior, conditions, states, values, or rules.
- Do NOT add summaries that introduce new interpretations.
- Use the same font, header and spacing in the answer generation
- Prefer precise restatement over explanation.
- Remove all hierarchical numbering (e.g., 4.2, a., i.) from section titles and keep only the title text and replace it with 1. , 2.  to n.  sequentially

HIGHLIGHTING INSTRUCTIONS:
- When a word or phrase is a keypoint that needs to be highlighted (important keywords,   headings, or key concepts), wrap it with asterisks: *word* or *key phrase*
- Use this syntax for important terms, section names, or concepts that should stand out
- Example: "The *damage* system calculates *critical hits* based on *weapon type*"

Chunks:
{chunk_texts_enhanced}
"""

        # Generate explanation using LLM with max_tokens to ensure complete responses
        try:
            provider = SimpleLLMProvider()
            llm_start_time = time.perf_counter()
            explanation = provider.llm(
                prompt, temperature=0.3, max_tokens=3000)
            llm_end_time = time.perf_counter()
            section_timing = round(llm_end_time - llm_start_time, 2)

            # Post-process: Remove statements about missing information
            explanation = _filter_missing_info_statements(explanation)

            # Create section label for timing display
            doc_name = doc_name_map.get(doc_id, doc_id)
            section_label = f"{doc_name} → {section_heading or '(No section)'}"

            return {
                'explanation': explanation,
                'source_chunks': selected_chunks,
                'citations': citation_map,
                'section_timing': section_timing,
                'section_label': section_label,
                'error': None
            }
        except Exception as e:
            return {
                'explanation': None,
                'source_chunks': selected_chunks,
                'citations': citation_map,
                'error': f'LLM error: {str(e)}'
            }

    except Exception as e:
        return {
            'explanation': None,
            'source_chunks': [],
            'citations': {},
            'error': f'Error processing section: {str(e)}'
        }


def explain_keyword(
    keyword: str,
    selected_items: List[Dict[str, str]],
    use_hyde: bool = True,
    language: str = None,
) -> Dict[str, Any]:
    """
    Generate detailed explanation for a keyword from selected documents/sections.
    Processes each section separately and combines the results.

    Args:
        keyword: Keyword/query to explain
        selected_items: List of dicts with 'doc_id' and optional 'section_heading'
        use_hyde: Whether to use HYDE query expansion
        language: Language preference ('en' or 'vn'). If None, auto-detects from keyword.

    Returns:
        Dict with 'explanation', 'source_chunks', 'hyde_query', 'language', etc.
    """
    try:
        # Step 1: HYDE query expansion (optional)
        hyde_query = keyword
        hyde_timing = {}
        hyde_expansion_time = 0.0
        if use_hyde:
            hyde_start_time = time.perf_counter()
            hyde_query, hyde_timing = hyde_expand_query(keyword)
            hyde_end_time = time.perf_counter()
            hyde_expansion_time = round(hyde_end_time - hyde_start_time, 2)

        # Step 2: Group selected items by unique (doc_id, section_heading) combinations
        unique_sections = []
        seen_sections = set()

        for item in selected_items:
            doc_id = item['doc_id']
            section_heading = item.get('section_heading')
            section_key = (doc_id, section_heading)

            if section_key not in seen_sections:
                unique_sections.append({
                    'doc_id': doc_id,
                    'section_heading': section_heading
                })
                seen_sections.add(section_key)

        if not unique_sections:
            return {
                'explanation': 'No sections selected.',
                'source_chunks': [],
                'hyde_query': hyde_query,
                'language': 'english',
                'error': None
            }

        # Step 3: Get document name mapping for citations
        docs = list_keyword_documents()
        doc_name_map = {}
        for doc in docs:
            doc_id = doc.get('doc_id')
            if not doc_id:
                continue
            name = doc.get('name', doc_id)
            filename = name
            if '\\' in filename or '/' in filename:
                filename = filename.split('\\')[-1].split('/')[-1]
            if filename.lower().endswith('.pdf'):
                filename = filename[:-4]
            doc_name_map[doc_id] = filename

        # Step 4: Detect or use provided language
        if language and language in ['en', 'vn']:
            # Use provided language from toggle
            detected_language = 'vietnamese' if language == 'vn' else 'english'
        else:
            # Auto-detect from keyword
            detected_language = detect_query_language(keyword)

        # Step 5: Collect all chunks from all sections and sort by chunk_id
        # This ensures we process sections in sidebar order
        all_chunks_global = []
        for section in unique_sections:
            doc_id = section['doc_id']
            section_heading = section.get('section_heading')
            section_chunks = get_all_chunks_from_section(
                doc_id, section_heading)
            for chunk in section_chunks:
                chunk['_doc_id'] = doc_id
                chunk['_section_heading'] = section_heading
                all_chunks_global.append(chunk)

        # Sort all chunks globally by chunk_id to match sidebar order
        all_chunks_global.sort(key=lambda x: x.get('chunk_id', '') or '')

        # Step 6: Process each section sequentially, adding citations as we go
        section_results = []
        all_source_chunks = []
        all_citations = {}
        errors = []
        section_timings = []
        citation_counter = 1  # Global counter for citations

        # Group chunks by (doc_id, section_heading) to process sections
        chunks_by_section = {}
        for chunk in all_chunks_global:
            doc_id = chunk.get('_doc_id')
            section_heading = chunk.get('_section_heading')
            section_key = (doc_id, section_heading)
            if section_key not in chunks_by_section:
                chunks_by_section[section_key] = []
            chunks_by_section[section_key].append(chunk)

        # Process sections in order (sorted by first chunk's chunk_id in each section)
        sorted_sections = sorted(chunks_by_section.items(),
                                 key=lambda x: x[1][0].get('chunk_id', '') or '' if x[1] else '')

        for (doc_id, section_heading), section_chunks in sorted_sections:
            # Process this section
            result = _explain_single_section(
                keyword=keyword,
                doc_id=doc_id,
                section_heading=section_heading,
                hyde_query=hyde_query,
                doc_name_map=doc_name_map,
                detected_language=detected_language
            )

            if result.get('error'):
                errors.append(
                    f"{doc_name_map.get(doc_id, doc_id)} - {section_heading or 'No section'}: {result['error']}")

            if result.get('explanation'):
                # Add citation to this section's explanation
                explanation_with_citation = _add_citation_to_text(
                    result['explanation'], citation_counter)

                # Build citation map for this section (use first chunk for citation info)
                source_chunks = result.get('source_chunks', [])
                if source_chunks:
                    first_chunk = source_chunks[0]
                    all_citations[citation_counter] = {
                        'doc_id': doc_id,
                        'doc_name': doc_name_map.get(doc_id, doc_id),
                        'section_heading': first_chunk.get('section_heading'),
                        'chunk_id': first_chunk.get('chunk_id', '')
                    }

                section_results.append({
                    'doc_id': doc_id,
                    'section_heading': section_heading,
                    'explanation': explanation_with_citation,
                    'source_chunks': source_chunks
                })

                # Increment citation counter for next LLM call
                citation_counter += 1

            # Collect section timing if available
            if result.get('section_timing') is not None and result.get('section_label'):
                section_timings.append({
                    'label': result['section_label'],
                    'time': result['section_timing']
                })

            # Collect source chunks
            all_source_chunks.extend(result.get('source_chunks', []))

        # Step 6: Combine all section explanations
        if not section_results:
            error_msg = 'No explanations generated. '
            if errors:
                error_msg += 'Errors: ' + '; '.join(errors)
            return {
                'explanation': error_msg,
                'source_chunks': all_source_chunks,
                'hyde_query': hyde_query,
                'language': detected_language,
                'error': error_msg if errors else None
            }

        # Combine explanations: renumber sections sequentially
        # Use regex to find and renumber all section headers (format: "1. Section Title")
        formatting_start_time = time.perf_counter()
        section_number = 1
        combined_parts = []

        for section_result in section_results:
            explanation_text = section_result['explanation']

            # Pattern to match section headers: number followed by period and space
            # Example: "1. Section Title" or "2. Another Section"
            pattern = r'^(\d+)\.\s+(.+)$'

            lines = explanation_text.split('\n')
            processed_lines = []

            for line in lines:
                match = re.match(pattern, line.strip())
                if match:
                    # This is a section header - renumber it
                    section_title = match.group(2)
                    processed_lines.append(
                        f"{section_number}. {section_title}")
                    section_number += 1
                else:
                    # Regular content line - keep as is
                    processed_lines.append(line)

            # Add this section's explanation to combined parts
            if processed_lines:
                combined_parts.append('\n'.join(processed_lines))

        # Join all sections with double newlines
        final_explanation = '\n\n'.join(combined_parts)

        # Post-process: Remove statements about missing information from combined explanation
        final_explanation = _filter_missing_info_statements(final_explanation)
        formatting_end_time = time.perf_counter()
        formatting_time = round(formatting_end_time - formatting_start_time, 2)

        return {
            'explanation': final_explanation,
            'source_chunks': all_source_chunks,
            'hyde_query': hyde_query,
            'language': detected_language,
            'hyde_timing': hyde_timing,
            'chunks_used': len(all_source_chunks),
            'citations': all_citations,
            'error': '; '.join(errors) if errors else None,
            'timing_metadata': {
                'hyde_expansion_time': hyde_expansion_time,
                'section_timings': section_timings,
                'formatting_time': formatting_time
            }
        }

    except Exception as e:
        return {
            'explanation': None,
            'source_chunks': [],
            'hyde_query': keyword,
            'language': 'english',
            'error': f'Error generating explanation: {str(e)}'
        }
