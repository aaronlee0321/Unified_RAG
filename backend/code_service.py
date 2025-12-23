"""
Code Q&A Service
Extracted from code_qa/app.py - handles codebase queries with Supabase integration
"""

import os
import sys
import time
import re
import json
from pathlib import Path
from typing import List, Dict, Optional, Any
from openai import OpenAI

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import prompts (now included in unified_rag_app)
try:
    from backend.code_qa_prompts import (
        HYDE_SYSTEM_PROMPT,
        HYDE_V2_SYSTEM_PROMPT,
        CHAT_SYSTEM_PROMPT
    )
except ImportError:
    # Fallback: try importing as prompts module
    try:
        import code_qa_prompts as prompts
        HYDE_SYSTEM_PROMPT = prompts.HYDE_SYSTEM_PROMPT
        HYDE_V2_SYSTEM_PROMPT = prompts.HYDE_V2_SYSTEM_PROMPT
        CHAT_SYSTEM_PROMPT = prompts.CHAT_SYSTEM_PROMPT
    except ImportError:
        # Fallback prompts if file not found
        HYDE_SYSTEM_PROMPT = '''You are a code-search query rewriter for a code RAG system.
Your ONLY job is to transform a natural language query into a better search query over the existing codebase.'''
        
        HYDE_V2_SYSTEM_PROMPT = '''You are a code-search query refiner for a code RAG system.
Your task is to enhance the original query: {query}
using ONLY the information present in the provided context: {temp_context}
Rewrite the query to include precise method names, class names, file paths that appear in the context.'''
        
        CHAT_SYSTEM_PROMPT = '''You are a STRICTLY codebase-aware assistant.
You MUST answer ONLY using the following code context: {context}
Use ONLY information explicitly present in the context above.'''

# Try to import Supabase storage (optional)
try:
    from backend.storage.code_supabase_storage import (
        search_code_chunks_supabase,
        get_code_chunks_for_files,
        list_code_files_supabase,
        normalize_path_consistent as normalize_path_storage,
        USE_SUPABASE
    )
    SUPABASE_AVAILABLE = USE_SUPABASE
    # Use the normalize function from storage module
    normalize_path_consistent = normalize_path_storage
except ImportError:
    SUPABASE_AVAILABLE = False
    print("Warning: Supabase storage not available for Code Q&A")
    
    # Fallback normalize function
    def normalize_path_consistent(p: str) -> Optional[str]:
        if p is None:
            return None
        try:
            p_str = str(p).strip()
            if not p_str:
                return None
            abs_path = os.path.abspath(p_str)
            norm_path = os.path.normcase(abs_path)
            return norm_path
        except Exception:
            return None

# Import LLM providers
# Import from local gdd_rag_backbone (now included in unified_rag_app)
from gdd_rag_backbone.llm_providers import QwenProvider, make_embedding_func

# Initialize OpenAI client for HYDE and answer generation
api_key = os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("OPENAI_API_KEY")
if not api_key:
    raise ValueError("QWEN_API_KEY, DASHSCOPE_API_KEY, or OPENAI_API_KEY environment variable must be set")

# Use DashScope compatible base URL if using Qwen/DashScope
base_url = None
if os.environ.get("QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY"):
    base_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
else:
    base_url = None

client = OpenAI(api_key=api_key, base_url=base_url)

# Get LLM models from environment or use defaults
_hyde_model = os.environ.get("HYDE_MODEL", "qwen-plus")
_answer_model = os.environ.get("ANSWER_MODEL", "qwen-flash")


def parse_cs_file_filter(raw_query: str):
    """
    Parse @filename.cs or @path/file.cs directives from query.
    Returns (cleaned_query, list_of_file_paths)
    """
    # Pattern to match @filename.cs or @path/file.cs
    pattern = r'@([^\s@]+\.cs)'
    matches = re.findall(pattern, raw_query)
    
    if not matches:
        return raw_query, None
    
    # Remove @filename.cs from query
    cleaned = raw_query
    for match in matches:
        cleaned = cleaned.replace(f'@{match}', '').strip()
    
    # Resolve file paths (simplified - would need indexed_cs_files.json)
    file_paths = []
    for match in matches:
        # For now, just normalize the match
        # In full implementation, would look up in indexed_cs_files.json
        file_paths.append(match)
    
    return cleaned, file_paths if file_paths else None


def openai_hyde_v2(query: str, temp_context: str, hyde_query: str):
    """Generate HYDE v2 refined query using context"""
    start_time = time.time()
    
    stream = client.chat.completions.create(
        model=_hyde_model,
        messages=[
            {
                "role": "system",
                "content": HYDE_V2_SYSTEM_PROMPT.format(query=query, temp_context=temp_context)
            },
            {
                "role": "user",
                "content": f"Enhance the query: {hyde_query}",
            }
        ],
        stream=True
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
    token_rate = token_count / (total_time - first_token_time) if first_token_time and (total_time - first_token_time) > 0 else 0
    
    timing_data = {
        "total_time": round(total_time, 2),
        "ttft": round(first_token_time, 2) if first_token_time else None,
        "token_count": token_count,
        "token_rate": round(token_rate, 1) if token_rate > 0 else None,
        "response_length": len(full_response)
    }
    
    return full_response, timing_data


def openai_chat(query: str, context: str):
    """Generate answer using LLM with context"""
    start_time = time.time()
    
    # Use simple placeholder replacement instead of str.format to avoid
    # KeyError when the prompt itself contains braces in example code.
    system_prompt = CHAT_SYSTEM_PROMPT.replace("{context}", context)

    stream = client.chat.completions.create(
        model=_answer_model,
        messages=[
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": (
                    "You must answer the following question using ONLY the code "
                    "shown in the system context. If the answer is not present "
                    "in that code, explicitly say that it is not implemented or "
                    "cannot be determined from the available code.\n\n"
                    "IMPORTANT: When showing code snippets, ALWAYS format them in markdown code blocks "
                    "with triple backticks (```csharp\n[code]\n```) and preserve ALL whitespace, "
                    "indentation, and newlines exactly as they appear in the source code.\n\n"
                    f"Question: {query}"
                ),
            }
        ],
        stream=True,
        max_tokens=2000,
        temperature=0
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
    token_rate = token_count / (total_time - first_token_time) if first_token_time and (total_time - first_token_time) > 0 else 0
    
    timing_data = {
        "total_time": round(total_time, 2),
        "ttft": round(first_token_time, 2) if first_token_time else None,
        "token_count": token_count,
        "token_rate": round(token_rate, 1) if token_rate > 0 else None,
        "response_length": len(full_response)
    }
    
    return full_response, timing_data


def _filter_chunks_by_files(chunks: List[Dict], allowed_paths: Optional[List[str]]) -> List[Dict]:
    """Filter chunks to only those whose file_path is in allowed_paths"""
    if not allowed_paths:
        return chunks
    
    allowed_set = {normalize_path_consistent(p) for p in allowed_paths if normalize_path_consistent(p) is not None}
    if not allowed_set:
        return chunks
    
    filtered = []
    for chunk in chunks:
        file_path = chunk.get("file_path")
        if not file_path:
            continue
        norm_path = normalize_path_consistent(file_path)
        if norm_path and norm_path in allowed_set:
            filtered.append(chunk)
    
    return filtered


def generate_context_supabase(
    query: str,
    file_filters: Optional[List[str]] = None,
    provider = None
) -> tuple[str, Dict]:
    """
    Generate context from Supabase using vector search and HYDE v2.
    
    Args:
        query: User query
        file_filters: Optional list of file paths to filter by
        provider: LLM provider for embeddings
    
    Returns:
        (context_string, timing_info_dict)
    """
    if not SUPABASE_AVAILABLE:
        raise ValueError("Supabase is not configured for Code Q&A")
    
    start_time = time.time()
    timing_info = {
        "query": query
    }
    
    # Initialize provider if not provided
    if provider is None:
        provider = QwenProvider()
    
    embedding_func = make_embedding_func(provider)
    
    # Step 1: Initial search with original query
    search_start = time.time()
    query_embedding = embedding_func([query])[0]
    
    # Get initial chunks
    initial_methods = search_code_chunks_supabase(
        query=query,
        query_embedding=query_embedding,
        limit=20,
        threshold=0.2,
        file_paths=file_filters,
        chunk_type='method'
    )
    
    initial_classes = search_code_chunks_supabase(
        query=query,
        query_embedding=query_embedding,
        limit=20,
        threshold=0.2,
        file_paths=file_filters,
        chunk_type='class'
    )
    
    # Also do direct file lookup if filters are specified
    if file_filters:
        direct_methods = get_code_chunks_for_files(file_filters, chunk_type='method')
        direct_classes = get_code_chunks_for_files(file_filters, chunk_type='class')
        
        # Combine and deduplicate
        all_methods = {chunk.get('id'): chunk for chunk in initial_methods + direct_methods}
        all_classes = {chunk.get('id'): chunk for chunk in initial_classes + direct_classes}
        
        initial_methods = list(all_methods.values())
        initial_classes = list(all_classes.values())
    
    # Limit to top 5 for HYDE context
    method_docs = initial_methods[:5]
    class_docs = initial_classes[:5]
    
    # Step 2: Build temporary context for HYDE v2
    methods_text = "\n".join([doc.get('code', '') or doc.get('source_code', '') for doc in method_docs])
    classes_text = "\n".join([doc.get('source_code', '') for doc in class_docs])
    temp_context = methods_text + "\n" + classes_text
    temp_context = temp_context[:6000]  # Truncate for faster processing
    
    # Step 3: HYDE v2 query generation
    hyde_query_v2, hyde_v2_timing = openai_hyde_v2(query, temp_context, query)
    timing_info["hyde_v2_generation"] = hyde_v2_timing
    
    # Step 4: Final search with HYDE v2 refined query
    search_start = time.time()
    hyde_embedding = embedding_func([hyde_query_v2])[0]
    
    final_methods = search_code_chunks_supabase(
        query=hyde_query_v2,
        query_embedding=hyde_embedding,
        limit=10,
        threshold=0.2,
        file_paths=file_filters,
        chunk_type='method'
    )
    
    final_classes = search_code_chunks_supabase(
        query=hyde_query_v2,
        query_embedding=hyde_embedding,
        limit=10,
        threshold=0.2,
        file_paths=file_filters,
        chunk_type='class'
    )
    
    # Filter by files if specified
    method_docs = _filter_chunks_by_files(final_methods, file_filters)
    class_docs = _filter_chunks_by_files(final_classes, file_filters)
    
    search_time = time.time() - search_start
    timing_info["vector_search_time"] = round(search_time, 2)
    
    # Step 6: Combine top results
    top_3_methods = method_docs[:3]
    methods_combined = "\n\n".join(
        f"File: {doc['file_path']}\nCode:\n{doc.get('code', doc.get('source_code', ''))}"
        for doc in top_3_methods
    )
    
    top_3_classes = class_docs[:3]
    classes_combined = "\n\n".join(
        f"File: {doc['file_path']}\nClass Info:\n{doc.get('source_code', '')} References: \n{doc.get('code_references', '')}  \n END OF ROW {i}"
        for i, doc in enumerate(top_3_classes)
    )
    
    final_context = methods_combined + "\n below is class or constructor related code \n" + classes_combined
    
    total_time = time.time() - start_time
    timing_info["total_time"] = round(total_time, 2)
    timing_info["context_length"] = len(final_context)
    timing_info["results_count"] = {"methods": len(method_docs), "classes": len(class_docs)}
    
    return final_context, timing_info


def query_codebase(query: str, file_filters: list = None):
    """
    Query codebase using RAG with Supabase.
    
    Args:
        query: User query string
        file_filters: Optional list of file paths to filter by
    
    Returns:
        dict: Response with answer and metadata
    """
    try:
        if not query.strip():
            return {
                'response': 'Please provide a query.',
                'status': 'error'
            }
        
        # Parse @filename.cs filters from query
        cleaned_query, cs_file_filters = parse_cs_file_filter(query)
        file_filters = file_filters or cs_file_filters
        
        # Use Supabase if available
        if SUPABASE_AVAILABLE:
            try:
                provider = QwenProvider()
                
                # Generate context
                context, context_timing = generate_context_supabase(
                    query=cleaned_query,
                    file_filters=file_filters,
                    provider=provider
                )
                
                # Truncate context if needed
                context_for_llm = context[:8000]
                if len(context) > 8000:
                    context_for_llm = context[:8000]
                
                # Generate answer
                if context_for_llm.strip():
                    answer, answer_timing = openai_chat(cleaned_query, context_for_llm)
                else:
                    answer = "No relevant code chunks found in the codebase."
                
                return {
                    'response': answer,
                    'status': 'success',
                    'timing': {
                        'context': context_timing,
                        'answer': answer_timing
                    }
                }
                
            except Exception as e:
                return {
                    'response': f'Error querying codebase: {str(e)}',
                    'status': 'error'
                }
        else:
            return {
                'response': 'Supabase is not configured for Code Q&A. Please configure SUPABASE_URL and SUPABASE_KEY.',
                'status': 'error'
            }
            
    except Exception as e:
        return {
            'response': f'Error: {str(e)}',
            'status': 'error'
        }


def list_indexed_files():
    """
    List all indexed code files.
    Uses Supabase if available, otherwise falls back to indexed_cs_files.json.
    
    Returns:
        list: List of file metadata dictionaries
    """
    try:
        # Try Supabase first
        if SUPABASE_AVAILABLE:
            try:
                files = list_code_files_supabase()
                if files:
                    return files
            except Exception as e:
                print(f"Warning: Failed to load from Supabase, trying fallback: {e}")
        
        # Fallback: Load from indexed_cs_files.json (original code_qa format)
        indexed_cs_json = PROJECT_ROOT / "data" / "indexed_cs_files.json"
        if indexed_cs_json.exists():
            try:
                with open(indexed_cs_json, 'r', encoding='utf-8') as f:
                    indexed_files = json.load(f)
                
                # Convert to expected format
                files = []
                for entry in indexed_files:
                    files.append({
                        'file_name': entry.get('file_name', ''),
                        'file_path': entry.get('absolute_path', ''),
                        'normalized_path': normalize_path_consistent(entry.get('absolute_path', ''))
                    })
                return files
            except Exception as e:
                print(f"Error loading indexed_cs_files.json: {e}")
        
        return []
    except Exception as e:
        print(f"Error listing code files: {e}")
        return []
