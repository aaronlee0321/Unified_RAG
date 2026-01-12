"""
HYDE (Hypothetical Document Embeddings) query expansion for keyword extractor.
Adapted from unified_rag_app's gdd_hyde.py
"""
import os
import time
from typing import Tuple, Dict, Optional

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    OpenAI = None

# Get API key and base URL
api_key = os.getenv('QWEN_API_KEY') or os.getenv('DASHSCOPE_API_KEY') or os.getenv('OPENAI_API_KEY')
if api_key and OPENAI_AVAILABLE:
    base_url = None
    if os.getenv('QWEN_API_KEY') or os.getenv('DASHSCOPE_API_KEY'):
        base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    client = OpenAI(api_key=api_key, base_url=base_url)
else:
    client = None

# HYDE model
_hyde_model = os.getenv('HYDE_MODEL', 'qwen-plus')

# HYDE System Prompt (adapted for general document search)
HYDE_SYSTEM_PROMPT = '''You are a document search query rewriter for a RAG system.

Your ONLY job is to transform a natural language query into a better search query over documents.

Think in terms of:
- Concepts, terms, and terminology used in the documents
- Key phrases and technical terms
- Topics, subjects, and themes

Instructions:
1. Analyze the query carefully.
2. Rewrite it to include relevant terminology, key phrases, or concepts
   that a search engine could match against document content.
3. Use ONLY concepts that are plausibly present in the documents
   (do NOT invent new concepts or terminology).
4. Do NOT suggest improvements or hypothetical content.
5. Do NOT generate code; generate a plain-text search query focused on document content.

Output format: 
- Provide only the rewritten search query.
- Do not include explanations, comments, or code blocks.'''


def hyde_expand_query(query: str) -> Tuple[str, Dict]:
    """
    Generate HYDE expanded query for better retrieval.
    
    Args:
        query: Original user query
    
    Returns:
        (expanded_query, timing_info)
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
                    "content": HYDE_SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": f"Rewrite this query for searching documents: {query}"
                }
            ],
            stream=True,
            temperature=0.3
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
            "response_length": len(full_response)
        }
        
        return full_response.strip(), timing_data
    except Exception as e:
        # Fallback to original query on error
        return query, {"total_time": 0, "error": str(e)}



