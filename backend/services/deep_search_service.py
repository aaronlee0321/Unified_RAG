"""
Deep search service for keyword finder.
Uses LLM to generate translations and synonyms, then searches aliases and database.
"""

import json
import logging
import re
from typing import Any, Dict, List, Set

from backend.services.llm_provider import SimpleLLMProvider
from backend.services.search_service import keyword_search
from backend.storage.keyword_storage import (
    find_keyword_by_alias,
    get_all_keywords,
    list_all_aliases,
)

logger = logging.getLogger(__name__)


def detect_language(word: str) -> str:
    """
    Detect if word is English or Vietnamese using simple heuristics.
    Returns 'en' or 'vi'
    """
    # Vietnamese characters
    vietnamese_chars = re.compile(
        r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđĐ]", re.IGNORECASE
    )

    if vietnamese_chars.search(word):
        return "vi"
    return "en"


def generate_translation_and_synonyms(
    word: str, source_language: str, retry: bool = False
) -> Dict[str, List[str]]:
    """
    Use LLM to generate translation and synonyms.

    Args:
        word: The word to process
        source_language: 'en' or 'vi'
        retry: If True, generate different synonyms (for retry attempts)

    Returns:
        Dict with 'translation', 'synonyms_en', 'synonyms_vi'
    """
    try:
        provider = SimpleLLMProvider()

        target_language = "vi" if source_language == "en" else "en"

        retry_instruction = ""
        if retry:
            retry_instruction = "\n\nIMPORTANT: Generate DIFFERENT synonyms than before. Avoid common/obvious synonyms and provide alternative terms, related concepts, or variations that might be used in documents."

        prompt = f"""You are a translation and synonym assistant. For the word "{word}" (which is in {source_language}), provide:

1. Direct translation to {target_language}
2. Top 3 similar meaning words in {source_language} (synonyms)
3. Top 3 similar meaning words in {target_language}
{retry_instruction}

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
            max_tokens=200,
        )

        # Extract JSON from response
        response = response.strip()
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].split("```")[0].strip()

        result = json.loads(response)

        return {
            "translation": result.get("translation", ""),
            "synonyms_en": result.get("synonyms_en", [])
            if source_language == "en"
            else result.get("synonyms_en", []),
            "synonyms_vi": result.get("synonyms_vi", [])
            if source_language == "vi"
            else result.get("synonyms_vi", []),
        }

    except Exception:
        # Fallback: return empty results
        return {"translation": "", "synonyms_en": [], "synonyms_vi": []}


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
            keyword_list = [m["keyword"] for m in matches]
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
                    base_keyword = match["keyword"]
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
            keyword = alias_row.get("keyword", "").lower()
            alias = alias_row.get("alias", "").lower()

            if word_lower == keyword or word_lower == alias:
                matched_keywords_set.add(alias_row["keyword"])
                if word not in matches_by_word:
                    matches_by_word[word] = []
                if alias_row["keyword"] not in matches_by_word[word]:
                    matches_by_word[word].append(alias_row["keyword"])

        # Check against all keywords list
        for kw in all_keywords:
            if word_lower == kw.lower():
                matched_keywords_set.add(kw)
                if word not in matches_by_word:
                    matches_by_word[word] = []
                if kw not in matches_by_word[word]:
                    matches_by_word[word].append(kw)

    # Step 4: Verify that all matched keywords actually exist in the database
    # Only return keywords that have actual search results in the database
    # Use strict verification: keyword must appear in search results or be a verified alias
    verified_keywords = []
    verified_matches_by_word = {}

    for keyword in matched_keywords_set:
        keyword_lower = keyword.lower().strip()
        keyword_original = keyword.strip()

        # Check if keyword itself exists in database
        # Get more results to verify the keyword actually appears
        try:
            results = keyword_search(keyword_original, limit=10)
        except Exception as e:
            logger.error(
                f"[Deep Search Verification] Error searching for '{keyword_original}': {e}"
            )
            results = None

        if results and len(results) > 0:
            # Verify keyword actually appears in the content (not just fuzzy match)
            # Check if keyword appears in at least one result's content
            keyword_found = False
            for result in results:
                content = result.get("content", "").lower()
                # Check for exact word match (whole word, case-insensitive)
                # Use word boundary to match whole words only
                pattern = r"\b" + re.escape(keyword_lower) + r"\b"
                if re.search(pattern, content):
                    keyword_found = True
                    break

            if keyword_found:
                # Keyword exists in database - include it
                verified_keywords.append(keyword_original)
                continue

        # If keyword not found directly, check if it's an alias
        # If it's an alias, check if the base keyword exists in database
        alias_matches = find_keyword_by_alias(keyword_lower)
        if alias_matches:
            # This is an alias - check if base keyword exists
            for match in alias_matches:
                base_keyword = match.get("keyword", "").strip()
                if base_keyword:
                    # Verify base keyword exists in database
                    try:
                        base_results = keyword_search(base_keyword, limit=10)
                    except Exception as e:
                        logger.error(
                            f"[Deep Search Verification] Error searching for base keyword '{base_keyword}': {e}"
                        )
                        base_results = None

                    if base_results and len(base_results) > 0:
                        # Check if base keyword appears in results
                        base_keyword_lower = base_keyword.lower()
                        base_found = False
                        for result in base_results:
                            content = result.get("content", "").lower()
                            pattern = r"\b" + \
                                re.escape(base_keyword_lower) + r"\b"
                            if re.search(pattern, content):
                                base_found = True
                                break

                        if base_found:
                            # Base keyword exists - include the base keyword (not the alias)
                            if base_keyword not in verified_keywords:
                                verified_keywords.append(base_keyword)
                            break

    # Remove duplicates while preserving order
    verified_keywords = list(dict.fromkeys(verified_keywords))

    # Rebuild matches_by_word to only include verified keywords
    # Also map aliases to their base keywords
    for word, keyword_list in matches_by_word.items():
        verified_list = []
        for kw in keyword_list:
            # Check if keyword is verified
            if kw in verified_keywords:
                verified_list.append(kw)
            else:
                # Check if keyword is an alias for a verified base keyword
                alias_matches = find_keyword_by_alias(kw.lower())
                if alias_matches:
                    for match in alias_matches:
                        base_keyword = match.get("keyword", "")
                        if base_keyword in verified_keywords and base_keyword not in verified_list:
                            verified_list.append(base_keyword)

        if verified_list:
            # Remove duplicates
            verified_list = list(dict.fromkeys(verified_list))
            verified_matches_by_word[word] = verified_list

    return {
        "matched_keywords": sorted(verified_keywords),
        "matches_by_word": verified_matches_by_word,
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
        - 'progress_messages': List of progress messages
    """
    progress_messages = []

    if not word or not word.strip():
        return {
            "detected_language": "en",
            "translation": "",
            "all_words": [],
            "matched_keywords": [],
            "matches_by_word": {},
            "progress_messages": [],
        }

    word = word.strip()

    # Step 1: Detect language
    detected_lang = detect_language(word)
    progress_messages.append(
        "Generating synonyms, searching with synonyms now")

    # Step 2: Generate translation and synonyms (first attempt)
    llm_result = generate_translation_and_synonyms(
        word, detected_lang, retry=False)

    translation = llm_result.get("translation", "")
    synonyms_en = llm_result.get("synonyms_en", [])
    synonyms_vi = llm_result.get("synonyms_vi", [])

    # Build list of 6 words: 3 EN + 3 VI
    all_words = []

    # Add original word
    if detected_lang == "en":
        all_words.append(word)  # Original EN
        if translation:
            all_words.append(translation)  # Translated VI
    else:
        all_words.append(word)  # Original VI
        if translation:
            all_words.append(translation)  # Translated EN

    # Add synonyms (up to 3 each)
    if detected_lang == "en":
        all_words.extend(synonyms_en[:3])  # 3 EN synonyms
        all_words.extend(synonyms_vi[:3])  # 3 VI synonyms
    else:
        all_words.extend(synonyms_vi[:3])  # 3 VI synonyms
        all_words.extend(synonyms_en[:3])  # 3 EN synonyms

    # Remove duplicates and empty strings
    all_words = [w.strip() for w in all_words if w and w.strip()]
    # Preserve order, remove duplicates
    all_words = list(dict.fromkeys(all_words))

    # Step 3: Check against aliases and database
    check_result = check_words_against_aliases_and_database(all_words)

    # Step 4: If no verified keywords found, retry with different synonyms
    retry_performed = False
    if not check_result["matched_keywords"]:
        # Log retry attempt
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"Deep search: No matches found for '{word}', retrying with different synonyms..."
        )

        # Retry with different set of synonyms
        retry_performed = True
        llm_result_retry = generate_translation_and_synonyms(
            word, detected_lang, retry=True)

        translation_retry = llm_result_retry.get("translation", "")
        synonyms_en_retry = llm_result_retry.get("synonyms_en", [])
        synonyms_vi_retry = llm_result_retry.get("synonyms_vi", [])

        # Build new list of exactly 6 words: 3 EN + 3 VI (different from first attempt)
        # Always ensure we have 3 EN and 3 VI words, regardless of source language
        en_words = []
        vi_words = []

        if detected_lang == "en":
            # Source is EN: get 3 EN synonyms + 3 VI words (translation + 2 VI synonyms)
            en_words = synonyms_en_retry[:3]
            if translation_retry:
                vi_words.append(translation_retry)
            vi_words.extend(synonyms_vi_retry[:2])
            vi_words = vi_words[:3]
        else:
            # Source is VI: get 3 VI synonyms + 3 EN words (translation + 2 EN synonyms)
            vi_words = synonyms_vi_retry[:3]
            if translation_retry:
                en_words.append(translation_retry)
            en_words.extend(synonyms_en_retry[:2])
            en_words = en_words[:3]

        # Ensure we have exactly 3 of each (pad if needed)
        while len(en_words) < 3 and len(synonyms_en_retry) > len(en_words):
            en_words.append(synonyms_en_retry[len(en_words)])
        while len(vi_words) < 3 and len(synonyms_vi_retry) > len(vi_words):
            vi_words.append(synonyms_vi_retry[len(vi_words)])

        # Combine: exactly 3 EN + 3 VI
        all_words_retry = en_words[:3] + vi_words[:3]

        # Remove duplicates and empty strings
        all_words_retry = [w.strip()
                           for w in all_words_retry if w and w.strip()]
        all_words_retry = list(dict.fromkeys(
            all_words_retry))  # Remove duplicates

        # Check retry words against database
        check_result_retry = check_words_against_aliases_and_database(
            all_words_retry)

        # Use retry results if they found matches
        if check_result_retry["matched_keywords"]:
            return {
                "detected_language": detected_lang,
                "translation": translation_retry,
                "all_words": all_words_retry,
                "matched_keywords": check_result_retry["matched_keywords"],
                "matches_by_word": check_result_retry["matches_by_word"],
                "retry_performed": True,
                "progress_messages": progress_messages,
            }

    return {
        "detected_language": detected_lang,
        "translation": translation,
        "all_words": all_words,
        "matched_keywords": check_result["matched_keywords"],
        "matches_by_word": check_result["matches_by_word"],
        "retry_performed": retry_performed,
        "progress_messages": progress_messages,
    }
