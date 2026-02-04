"""
GDD-Specific HYDE Query Expansion
==================================
Generates design-oriented search descriptions for game design documents.
"""

import os
import re
import time
from typing import Dict, Tuple

# Try to import OpenAI client for HYDE
try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

# Get API key and base URL
api_key = (
    os.environ.get("OPENAI_API_KEY")
    or os.environ.get("QWEN_API_KEY")
    or os.environ.get("DASHSCOPE_API_KEY")
)
if api_key:
    base_url = None
    client = OpenAI(api_key=api_key, base_url=base_url) if OPENAI_AVAILABLE else None
else:
    client = None

# HYDE model
_hyde_model = os.environ.get("HYDE_MODEL", "gpt-4o-mini")

# GDD-Specific HYDE System Prompt
GDD_HYDE_SYSTEM_PROMPT = """You are a game design document search query rewriter for a GDD RAG system.

Your ONLY job is to transform a natural language query into a better search query over game design documents.

Think in terms of:
- Game systems, mechanics, and flows
- UI screens, interfaces, and user interactions
- Character classes, stats, and abilities
- Monetization, economy, and progression systems
- Design patterns, components, and features

Instructions:
1. Analyze the query carefully.
2. Rewrite it to include relevant design terminology, system names, screen names, or feature names
   that a vector/search engine could match against the GDD content.
3. Use ONLY concepts that are plausibly present in game design documents
   (do NOT invent new game mechanics, Unity patterns, or external services).
4. Do NOT suggest improvements, best practices, or hypothetical implementations.
5. Do NOT generate code; generate a plain-text search query focused on design content.

Output format:
- Provide only the rewritten search query.
- Do not include explanations, comments, or code blocks."""

GDD_HYDE_V2_SYSTEM_PROMPT = """You are a game design document query refiner for a GDD RAG system.

Your task is to enhance the original query: {query}
using ONLY the information present in the provided context:
{temp_context}

Instructions:
1. Analyze the query and the context thoroughly.
2. Rewrite the query to include precise section names, screen names, system names,
   and other design identifiers that ALREADY APPEAR in the context.
3. Do NOT invent new systems, screens, or features.
4. Do NOT suggest improvements, refactors, or best practices.
5. Do NOT guess based on game design conventions; stay strictly within the context.
6. Keep the query focused and concise, suitable for a vector/search engine over the same GDD content.

Output format:
- Provide only the refined search query.
- Do not include explanations, comments, or code blocks."""


def gdd_hyde_v1(query: str) -> Tuple[str, Dict]:
    """
    Generate HYDE v1 refined query for GDD (simple expansion).

    Args:
        query: Original user query

    Returns:
        (refined_query, timing_info)
    """
    if not client:
        return query, {"total_time": 0, "error": "OpenAI client not available"}

    start_time = time.time()

    try:
        stream = client.chat.completions.create(
            model=_hyde_model,
            messages=[
                {"role": "system", "content": GDD_HYDE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Rewrite this query for searching game design documents: {query}",
                },
            ],
            stream=True,
            temperature=0.3,
        )

        first_token_time = None
        token_count = 0
        full_response = ""

        for chunk in stream:
            if chunk.choices[0].delta.content:
                if first_token_time is None:
                    first_token_time = time.time() - start_time
                token_count += 1
                full_response += chunk.choices[0].delta.content

        total_time = time.time() - start_time

        timing_data = {
            "total_time": round(total_time, 2),
            "ttft": round(first_token_time, 2) if first_token_time else None,
            "token_count": token_count,
            "response_length": len(full_response),
        }

        return full_response.strip(), timing_data
    except Exception as e:
        return query, {"total_time": 0, "error": str(e)}


def gdd_hyde_v2(query: str, temp_context: str) -> Tuple[str, Dict]:
    """
    Generate HYDE v2 refined query for GDD (context-aware expansion).

    Args:
        query: Original user query
        temp_context: Temporary context from initial search

    Returns:
        (refined_query, timing_info)
    """
    if not client:
        return query, {"total_time": 0, "error": "OpenAI client not available"}

    start_time = time.time()

    try:
        stream = client.chat.completions.create(
            model=_hyde_model,
            messages=[
                {
                    "role": "system",
                    "content": GDD_HYDE_V2_SYSTEM_PROMPT.format(
                        query=query, temp_context=temp_context
                    ),
                },
                {"role": "user", "content": f"Enhance the query: {query}"},
            ],
            stream=True,
            temperature=0.3,
        )

        first_token_time = None
        token_count = 0
        full_response = ""

        for chunk in stream:
            if chunk.choices[0].delta.content:
                if first_token_time is None:
                    first_token_time = time.time() - start_time
                token_count += 1
                full_response += chunk.choices[0].delta.content

        total_time = time.time() - start_time

        timing_data = {
            "total_time": round(total_time, 2),
            "ttft": round(first_token_time, 2) if first_token_time else None,
            "token_count": token_count,
            "response_length": len(full_response),
        }

        return full_response.strip(), timing_data
    except Exception as e:
        return query, {"total_time": 0, "error": str(e)}


# Vietnamese character pattern for language detection
VIETNAMESE_CHARS = re.compile(
    r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", re.IGNORECASE
)


def detect_language(text: str) -> str:
    """
    Detect if text is in Vietnamese or English.

    Simple heuristic-based detection:
    - If contains Vietnamese diacritics → Vietnamese
    - If contains common Vietnamese words → Vietnamese
    - Otherwise → English

    Args:
        text: Text to detect language for

    Returns:
        "vi" for Vietnamese, "en" for English
    """
    text_lower = text.lower()

    # Check for Vietnamese diacritics
    if VIETNAMESE_CHARS.search(text):
        return "vi"

    # Check for common Vietnamese words (without diacritics)
    vietnamese_words = [
        "la",
        "cua",
        "va",
        "voi",
        "cho",
        "trong",
        "tren",
        "duoi",
        "ve",
        "thanh",
        "phan",
        "tuong",
        "tac",
        "muc",
        "dich",
        "tieu",
        "tai",
        "lieu",
        "thiet",
        "ke",
        "giaodien",
        "manhinh",
        "nguoi",
        "choi",
        "khi",
        "nhu",
        "tho",
        "hay",
        "can",
    ]

    # Count Vietnamese word matches
    vn_word_count = sum(1 for word in vietnamese_words if word in text_lower)

    # If we have 2+ Vietnamese word matches, consider it Vietnamese
    if vn_word_count >= 2:
        return "vi"

    # Default to English
    return "en"


def translate_to_vietnamese(text: str, preserve_technical_terms: bool = True) -> Tuple[str, Dict]:
    """
    Translate English text to Vietnamese using LLM.

    Args:
        text: English text to translate
        preserve_technical_terms: If True, preserve technical terms (Movejoystick, Skillbutton, etc.)

    Returns:
        (translated_text, timing_info)
    """
    if not client:
        return text, {"total_time": 0, "error": "OpenAI client not available"}

    start_time = time.time()

    try:
        preservation_instruction = ""
        if preserve_technical_terms:
            preservation_instruction = "\nIMPORTANT: Keep ALL technical terms, game-specific names, and English proper nouns unchanged (e.g., Movejoystick, Skillbutton, HP, DPS, Tank, Skill, etc.)."

        translation_prompt = f"""Translate the following English text to Vietnamese.{preservation_instruction}

English text: {text}

Vietnamese translation:"""

        stream = client.chat.completions.create(
            model=_hyde_model,
            messages=[
                {
                    "role": "system",
                    "content": f"You are a professional translator. Translate English to Vietnamese.{preservation_instruction}",
                },
                {"role": "user", "content": translation_prompt},
            ],
            stream=True,
            temperature=0.3,
        )

        first_token_time = None
        token_count = 0
        full_response = ""

        for chunk in stream:
            if chunk.choices[0].delta.content:
                if first_token_time is None:
                    first_token_time = time.time() - start_time
                token_count += 1
                full_response += chunk.choices[0].delta.content

        total_time = time.time() - start_time

        timing_data = {
            "total_time": round(total_time, 2),
            "ttft": round(first_token_time, 2) if first_token_time else None,
            "token_count": token_count,
            "response_length": len(full_response),
        }

        return full_response.strip(), timing_data
    except Exception as e:
        return text, {"total_time": 0, "error": str(e)}


def translate_query_if_needed(query: str) -> Tuple[str, str, Dict]:
    """
    Detect query language and translate to Vietnamese if needed.

    This ensures English queries are translated to Vietnamese before embedding,
    improving matching quality against Vietnamese chunks.

    Args:
        query: User query string

    Returns:
        (final_query, detected_language, metrics)
        - final_query: Vietnamese query (translated if needed, or original if already Vietnamese)
        - detected_language: "en" or "vi"
        - metrics: Detection and translation timing info
    """
    detected_lang = detect_language(query)

    metrics = {"detected_language": detected_lang, "original_query": query, "translation": {}}

    if detected_lang == "en":
        # Translate English to Vietnamese
        translated, translation_metrics = translate_to_vietnamese(
            query, preserve_technical_terms=True
        )
        metrics["translation"] = translation_metrics
        metrics["translated_query"] = translated
        return translated, detected_lang, metrics
    else:
        # Already Vietnamese, return as-is
        metrics["translation"] = {"skipped": True, "reason": "Already Vietnamese"}
        metrics["translated_query"] = query
        return query, detected_lang, metrics
