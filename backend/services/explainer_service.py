"""
Document Explainer service - generates detailed explanations from keyword queries.
Follows unified_rag_app patterns with section-based chunk retrieval.
EXACT COPY from keyword_extractor - only imports updated.
"""
from typing import List, Dict, Optional, Any, Tuple
from backend.storage.supabase_client import get_supabase_client
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
    
    query = client.table('keyword_chunks').select('*').eq('doc_id', doc_id).order('chunk_index')
    
    if section_heading:
        query = query.eq('section_heading', section_heading)
    else:
        query = query.is_('section_heading', 'null')
    
    result = query.execute()
    return result.data if result.data else []


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


def explain_keyword(
    keyword: str,
    selected_items: List[Dict[str, str]],
    use_hyde: bool = True,
) -> Dict[str, Any]:
    """
    Generate detailed explanation for a keyword from selected documents/sections.
    
    Args:
        keyword: Keyword/query to explain
        selected_items: List of dicts with 'doc_id' and optional 'section_heading'
        use_hyde: Whether to use HYDE query expansion
    
    Returns:
        Dict with 'explanation', 'source_chunks', 'hyde_query', 'language', etc.
    """
    try:
        # Step 1: HYDE query expansion (optional)
        hyde_query = keyword
        hyde_timing = {}
        if use_hyde:
            hyde_query, hyde_timing = hyde_expand_query(keyword)
        
        # Step 2: Get all chunks from selected sections
        # Strategy: Get ALL chunks from each selected section to avoid missing split information
        all_chunks = []
        chunk_ids_seen = set()
        
        for item in selected_items:
            doc_id = item['doc_id']
            section_heading = item.get('section_heading')
            
            # Get all chunks from this section (not just keyword matches)
            section_chunks = get_all_chunks_from_section(doc_id, section_heading)
            
            # Also get keyword-matched chunks for relevance scoring
            matched_chunks = keyword_search(hyde_query, limit=20, doc_id_filter=doc_id)
            matched_in_section = [
                c for c in matched_chunks 
                if c.get('section_heading') == section_heading or 
                   (section_heading is None and c.get('section_heading') is None)
            ]
            
            # Create a relevance map from matched chunks
            relevance_map = {c.get('chunk_id'): c.get('relevance', 0.0) for c in matched_in_section}
            
            # Combine section chunks with relevance scores
            for chunk in section_chunks:
                chunk_id = chunk.get('chunk_id')
                if chunk_id and chunk_id not in chunk_ids_seen:
                    # Ensure chunk has required fields
                    chunk_with_relevance = dict(chunk)
                    chunk_with_relevance['relevance'] = relevance_map.get(chunk_id, 0.0)
                    chunk_with_relevance['doc_id'] = doc_id  # Ensure doc_id is present
                    # Ensure content field exists (can be empty string but not None)
                    if 'content' not in chunk_with_relevance:
                        chunk_with_relevance['content'] = ''
                    elif chunk_with_relevance.get('content') is None:
                        chunk_with_relevance['content'] = ''
                    all_chunks.append(chunk_with_relevance)
                    chunk_ids_seen.add(chunk_id)
            
            # Add any matched chunks that weren't in section_chunks (shouldn't happen, but safety)
            for chunk in matched_in_section:
                chunk_id = chunk.get('chunk_id')
                if chunk_id and chunk_id not in chunk_ids_seen:
                    # Ensure content field exists
                    if 'content' not in chunk:
                        chunk['content'] = ''
                    elif chunk.get('content') is None:
                        chunk['content'] = ''
                    all_chunks.append(chunk)
                    chunk_ids_seen.add(chunk_id)
        
        # Sort by doc_id, section_heading, then chunk_index to maintain order
        all_chunks.sort(key=lambda x: (
            x.get('doc_id', ''),
            x.get('section_heading') or '',
            x.get('chunk_index', 0)
        ))
        
        if not all_chunks:
            return {
                'explanation': 'No chunks found for the selected documents/sections.',
                'source_chunks': [],
                'hyde_query': hyde_query,
                'language': 'english',
                'error': None
            }
        
        # Step 3: Select chunks for answer (use heuristic, but include more if needed)
        # For section-based retrieval, we might want all chunks, but limit to reasonable number
        selected_chunks = all_chunks[:10] if len(all_chunks) > 10 else all_chunks
        
        # Step 4: Detect language
        detected_language = detect_query_language(keyword)
        
        # Step 5: Build prompt with chunk context
        chunk_texts_with_sections = []
        for i, chunk in enumerate(selected_chunks):
            # Skip chunks without required fields
            if not chunk.get('doc_id') or chunk.get('content') is None:
                continue
                
            section_info = ""
            section_heading = chunk.get('section_heading')
            if section_heading:
                section_info = f" [Section: {section_heading}]"
            else:
                section_info = " [No section]"
            
            content = chunk.get('content', '') or ''
            doc_id = chunk.get('doc_id', '')
            
            chunk_texts_with_sections.append(
                f"[Chunk {i+1} from {doc_id}{section_info}]\n{content}"
            )
        
        chunk_texts_enhanced = "\n\n".join(chunk_texts_with_sections)
        
        # Determine response language instruction
        if detected_language == 'vietnamese':
            language_instruction = "IMPORTANT: Respond in Vietnamese (Tiếng Việt). Your entire answer must be in Vietnamese."
        else:
            language_instruction = "IMPORTANT: Respond in English. Your entire answer must be in English."
        
        # Build prompt (following unified_rag pattern)
        prompt = f"""Based on the following document chunks, provide a detailed explanation for: {keyword}

{language_instruction}

Note:
- The information may be spread across multiple chunks.
- Synthesize information only when multiple chunks explicitly refer to the same feature, system, or concept.
- If chunks reference specific sections, mention those section names in your explanation.

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
- If information is missing or not stated, explicitly say: "The document does not specify this."

STAT HANDLING RULE:
- If the source content is a stat table or attribute list, only restate the values exactly as written.
- Do NOT rank, evaluate, or interpret stats.
- Do NOT convert qualitative stat labels into gameplay conclusions.

OUTPUT STYLE:
- Write in a neutral, factual, documentation-style tone.
- Describe only documented behavior, conditions, states, values, or rules.
- Do NOT add summaries that introduce new interpretations.
- Prefer precise restatement over explanation.

Chunks:
{chunk_texts_enhanced}
"""


        # Step 6: Generate explanation using LLM
        try:
            provider = SimpleLLMProvider()
            explanation = provider.llm(prompt, temperature=0.3)
        except Exception as e:
            return {
                'explanation': None,
                'source_chunks': selected_chunks,
                'hyde_query': hyde_query,
                'language': detected_language,
                'error': f'LLM error: {str(e)}'
            }
        
        return {
            'explanation': explanation,
            'source_chunks': selected_chunks,
            'hyde_query': hyde_query,
            'language': detected_language,
            'hyde_timing': hyde_timing,
            'chunks_used': len(selected_chunks),
            'error': None
        }
    
    except Exception as e:
        return {
            'explanation': None,
            'source_chunks': [],
            'hyde_query': keyword,
            'language': 'english',
            'error': f'Error generating explanation: {str(e)}'
        }


