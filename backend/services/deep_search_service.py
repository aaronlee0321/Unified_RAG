"""
Deep search service for keyword finder.
Uses LLM to generate translations and synonyms, then searches aliases and database.
"""
import json
import re
from typing import List, Dict, Any, Set
from backend.services.llm_provider import SimpleLLMProvider
from backend.storage.keyword_storage import (
    find_keyword_by_alias,
    list_all_aliases,
    get_all_keywords
)
from backend.services.search_service import keyword_search


def detect_language(word: str) -> str:
    """
    Detect if word is English or Vietnamese using simple heuristics.
    Returns 'en' or 'vi'
    """
    # Vietnamese characters
    vietnamese_chars = re.compile(r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđĐ]', re.IGNORECASE)
    
    if vietnamese_chars.search(word):
        return 'vi'
    return 'en'


def generate_translation_and_synonyms(word: str, source_language: str) -> Dict[str, List[str]]:
    """
    Use LLM to generate translation and synonyms.
    
    Args:
        word: The word to process
        source_language: 'en' or 'vi'
    
    Returns:
        Dict with 'translation', 'synonyms_en', 'synonyms_vi'
    """
    try:
        provider = SimpleLLMProvider()
        
        target_language = 'vi' if source_language == 'en' else 'en'
        
        prompt = f"""You are a translation and synonym assistant. For the word "{word}" (which is in {source_language}), provide:

1. Direct translation to {target_language}
2. Top 3 similar meaning words in {source_language} (synonyms)
3. Top 3 similar meaning words in {target_language}

Return ONLY a JSON object with this exact structure:
{{
    "translation": "translated_word",
    "synonyms_{source_language}": ["synonym1", "synonym2", "synonym3"],
    "synonyms_{target_language}": ["synonym1", "synonym2", "synonym3"]
}}

Be concise and return only relevant words. Return ONLY the JSON, no other text."""

        response = provider.llm(
            prompt,
            system_prompt="You are a helpful translation assistant. Return only valid JSON.",
            temperature=0.3,
            max_tokens=200
        )
        
        # Extract JSON from response
        response = response.strip()
        if '```json' in response:
            response = response.split('```json')[1].split('```')[0].strip()
        elif '```' in response:
            response = response.split('```')[1].split('```')[0].strip()
        
        result = json.loads(response)
        
        return {
            'translation': result.get('translation', ''),
            'synonyms_en': result.get('synonyms_en', []) if source_language == 'en' else result.get('synonyms_en', []),
            'synonyms_vi': result.get('synonyms_vi', []) if source_language == 'vi' else result.get('synonyms_vi', [])
        }
        
    except Exception as e:
        # Fallback: return empty results
        return {
            'translation': '',
            'synonyms_en': [],
            'synonyms_vi': []
        }


def check_words_against_aliases_and_database(words: List[str]) -> Dict[str, Any]:
    """
    Check a list of words against aliases table and database.
    
    Args:
        words: List of words to check
    
    Returns:
        Dict with:
        - 'matched_keywords': List of base keywords that matched
        - 'matches_by_word': Dict mapping word -> list of matched keywords
    """
    matched_keywords_set: Set[str] = set()
    matches_by_word: Dict[str, List[str]] = {}
    
    # Step 1: Check against aliases table
    for word in words:
        if not word or not word.strip():
            continue
        
        word_lower = word.strip().lower()
        matches = find_keyword_by_alias(word_lower)
        
        if matches:
            keyword_list = [m['keyword'] for m in matches]
            matched_keywords_set.update(keyword_list)
            matches_by_word[word] = keyword_list
    
    # Step 2: Check against database using keyword_search
    # If a word returns search results, it means it exists in the database
    for word in words:
        if not word or not word.strip():
            continue
        
        word_clean = word.strip()
        results = keyword_search(word_clean, limit=5)
        
        if results:
            # Word found in database - check if it has an alias mapping
            alias_matches = find_keyword_by_alias(word_clean.lower())
            
            if alias_matches:
                # Word is an alias - get the base keyword
                for match in alias_matches:
                    base_keyword = match['keyword']
                    matched_keywords_set.add(base_keyword)
                    if word not in matches_by_word:
                        matches_by_word[word] = []
                    if base_keyword not in matches_by_word[word]:
                        matches_by_word[word].append(base_keyword)
            else:
                # Word itself might be a keyword (no alias mapping found)
                # Add it as a potential keyword
                matched_keywords_set.add(word_clean.lower())
                if word not in matches_by_word:
                    matches_by_word[word] = []
                if word_clean.lower() not in matches_by_word[word]:
                    matches_by_word[word].append(word_clean.lower())
    
    # Step 3: Also check all existing keywords/aliases for partial matches
    all_aliases = list_all_aliases()
    all_keywords = get_all_keywords()
    
    for word in words:
        if not word or not word.strip():
            continue
        
        word_lower = word.strip().lower()
        
        # Check if word matches any keyword or alias (case-insensitive)
        for alias_row in all_aliases:
            keyword = alias_row.get('keyword', '').lower()
            alias = alias_row.get('alias', '').lower()
            
            if word_lower == keyword or word_lower == alias:
                matched_keywords_set.add(alias_row['keyword'])
                if word not in matches_by_word:
                    matches_by_word[word] = []
                if alias_row['keyword'] not in matches_by_word[word]:
                    matches_by_word[word].append(alias_row['keyword'])
        
        # Check against all keywords list
        for kw in all_keywords:
            if word_lower == kw.lower():
                matched_keywords_set.add(kw)
                if word not in matches_by_word:
                    matches_by_word[word] = []
                if kw not in matches_by_word[word]:
                    matches_by_word[word].append(kw)
    
    return {
        'matched_keywords': sorted(list(matched_keywords_set)),
        'matches_by_word': matches_by_word
    }


def deep_search_keyword(word: str) -> Dict[str, Any]:
    """
    Perform deep search for a keyword:
    1. Detect language
    2. Generate translation and synonyms (6 words total: 3 EN + 3 VI)
    3. Check against aliases and database
    4. Return matched keywords
    
    Args:
        word: The search word
    
    Returns:
        Dict with:
        - 'detected_language': 'en' or 'vi'
        - 'translation': Translated word
        - 'all_words': List of 6 words to check
        - 'matched_keywords': List of base keywords that matched
        - 'matches_by_word': Dict showing which words matched which keywords
    """
    if not word or not word.strip():
        return {
            'detected_language': 'en',
            'translation': '',
            'all_words': [],
            'matched_keywords': [],
            'matches_by_word': {}
        }
    
    word = word.strip()
    
    # Step 1: Detect language
    detected_lang = detect_language(word)
    
    # Step 2: Generate translation and synonyms
    llm_result = generate_translation_and_synonyms(word, detected_lang)
    
    translation = llm_result.get('translation', '')
    synonyms_en = llm_result.get('synonyms_en', [])
    synonyms_vi = llm_result.get('synonyms_vi', [])
    
    # Build list of 6 words: 3 EN + 3 VI
    all_words = []
    
    # Add original word
    if detected_lang == 'en':
        all_words.append(word)  # Original EN
        if translation:
            all_words.append(translation)  # Translated VI
    else:
        all_words.append(word)  # Original VI
        if translation:
            all_words.append(translation)  # Translated EN
    
    # Add synonyms (up to 3 each)
    if detected_lang == 'en':
        all_words.extend(synonyms_en[:3])  # 3 EN synonyms
        all_words.extend(synonyms_vi[:3])  # 3 VI synonyms
    else:
        all_words.extend(synonyms_vi[:3])  # 3 VI synonyms
        all_words.extend(synonyms_en[:3])  # 3 EN synonyms
    
    # Remove duplicates and empty strings
    all_words = [w.strip() for w in all_words if w and w.strip()]
    all_words = list(dict.fromkeys(all_words))  # Preserve order, remove duplicates
    
    # Step 3: Check against aliases and database
    check_result = check_words_against_aliases_and_database(all_words)
    
    return {
        'detected_language': detected_lang,
        'translation': translation,
        'all_words': all_words,
        'matched_keywords': check_result['matched_keywords'],
        'matches_by_word': check_result['matches_by_word']
    }

