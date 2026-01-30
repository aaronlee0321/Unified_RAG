"""
Code Q&A Service
Extracted from code_qa/app.py - handles codebase queries with Supabase integration
"""

from gdd_rag_backbone.llm_providers import make_embedding_func
import os
import sys
import time
import re
import json
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from openai import OpenAI

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Note: We no longer use CODEBASE_ROOT for local file access
# All file operations now use Supabase only (works on Render)


def _resolve_local_code_path(supabase_path: str) -> Optional[Path]:
    """
    DEPRECATED: This function is no longer used.
    All file operations now use Supabase only (works on Render).

    Returns None to indicate local file access is not supported.
    """
    # Local file access is disabled - all operations use Supabase
    return None


def _analyze_csharp_file_symbols(code_text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Analyze a C# file and extract methods, fields, and properties.
    Lightweight regex-based parser; good enough for listing names and locations.
    """
    methods: List[Dict[str, Any]] = []
    fields: List[Dict[str, Any]] = []
    properties: List[Dict[str, Any]] = []

    # Precompute line offsets for line numbers
    line_starts = [0]
    for m in re.finditer(r"\n", code_text):
        line_starts.append(m.end())

    def _line_number_for_pos(pos: int) -> int:
        # Binary search for line number
        import bisect
        return bisect.bisect_right(line_starts, pos)

    # Improved C# method pattern (attributes + optional modifiers + return type + name + params).
    # We no longer require the '{' on the same line so that styles like:
    #   protected override void Awake()
    #   {
    #   }
    # are still detected. Control-flow constructs (if/for/while/catch) don't match this
    # because they don't have a return type before the name.
    method_pattern = re.compile(
        r'^[ \t]*(?:\[[^\]]+\]\s*)*'                         # attributes
        r'(?:public|private|protected|internal)?\s*'
        r'(?:(?:static|async|override|virtual|abstract|sealed|partial|extern|unsafe|new)\s+)*'
        r'(?:void|[\w<>\[\],]+)\s+'                          # return type
        r'(?P<name>\w+)\s*'                                  # method name
        r'\([^)]*\)\s*'                                      # parameters
        # generic constraints
        r'(?:where\s+\w+\s*:\s*[^{=>]+)?\s*'
        # block or expression-bodied
        r'(?:\{|=>)',
        re.MULTILINE
    )

    # Field pattern: attributes + optional access + type + name;
    # Made more flexible to handle various field declarations
    # Must have at least one modifier (access or static/const/readonly) to avoid false positives
    field_pattern = re.compile(
        r'^[ \t]*(?:\[[^\]]*\]\s*)*'                          # attributes
        # optional access modifier
        r'(?:(?:public|private|protected|internal)\s+)?'
        # optional modifiers
        r'(?:(?:static|const|readonly)\s+)?'
        # type (must be present)
        r'[\w<>\[\],\s]+\s+'
        r'(?P<name>\w+)\s*'                                    # field name
        # optional initializer
        r'(?:=[^;]*)?;',
        re.MULTILINE
    )

    # Property pattern: attributes + access + type + name { get; ... } or => expression
    # Handles both traditional properties and expression-bodied properties
    property_pattern = re.compile(
        r'^[ \t]*(?:\[[^\]]*\]\s*)*'                          # attributes
        # optional access modifier
        r'(?:public|private|protected|internal)?\s*'
        r'(?:static|virtual|override|sealed|abstract)?\s*'   # optional modifiers
        r'[\w<>\[\],\s]+\s+'                                   # return type
        r'(?P<name>\w+)\s*'                                    # property name
        # { get; set; } or => expression
        r'(?:\{[^\}]*\}|=>[^;]+)',
        re.MULTILINE
    )

    for match in method_pattern.finditer(code_text):
        name = match.group("name")
        start = match.start()
        line_no = _line_number_for_pos(start)
        signature = match.group(0).strip()
        methods.append({
            "name": name,
            "line": line_no,
            "signature": signature,
        })

    for match in field_pattern.finditer(code_text):
        name = match.group("name")
        start = match.start()
        line_no = _line_number_for_pos(start)
        decl = match.group(0).strip()
        fields.append({
            "name": name,
            "line": line_no,
            "declaration": decl,
        })

    for match in property_pattern.finditer(code_text):
        name = match.group("name")
        start = match.start()
        line_no = _line_number_for_pos(start)
        decl = match.group(0).strip()
        properties.append({
            "name": name,
            "line": line_no,
            "declaration": decl,
        })

    return methods, fields, properties


def _extract_variables_from_methods(code_text: str, methods: List[Dict[str, Any]], selected_method_names: List[str]) -> List[Dict[str, Any]]:
    """
    Extract variables (local variables, parameters) from specific method bodies.

    Args:
        code_text: Full source code text
        methods: List of method dicts with 'name', 'line', 'signature'
        selected_method_names: List of method names to extract variables from

    Returns:
        List of variable dicts with 'name', 'line', 'method', 'declaration'
    """
    variables = []

    # Precompute line offsets
    line_starts = [0]
    for m in re.finditer(r"\n", code_text):
        line_starts.append(m.end())

    def _line_number_for_pos(pos: int) -> int:
        import bisect
        return bisect.bisect_right(line_starts, pos)

    # Find method bodies for selected methods
    method_pattern = re.compile(
        r'^[ \t]*(?:\[[^\]]+\]\s*)*'
        r'(?:public|private|protected|internal)?\s*'
        r'(?:(?:static|async|override|virtual|abstract|sealed|partial|extern|unsafe|new)\s+)*'
        r'(?:void|[\w<>\[\],]+)\s+'
        r'(?P<name>\w+)\s*'
        r'\([^)]*\)\s*'
        r'(?:where\s+\w+\s*:\s*[^{=>]+)?\s*'
        r'(?:\{|=>)',
        re.MULTILINE
    )

    # Pattern for local variable declarations within method bodies
    # Matches: type name; or type name = value;
    local_var_pattern = re.compile(
        r'^\s*(?:\[[^\]]*\]\s*)*'
        r'(?:var|[\w<>\[\],\s]+)\s+'
        r'(?P<name>\w+)\s*'
        r'(?:=[^;]*)?;',
        re.MULTILINE
    )

    # Find all methods and their positions
    method_matches = []
    for match in method_pattern.finditer(code_text):
        method_name = match.group("name")
        if method_name in selected_method_names:
            method_start = match.start()
            method_end = match.end()

            # Find the method body (from opening brace to matching closing brace)
            brace_count = 0
            body_start = None
            body_end = None

            # Find opening brace
            for i in range(method_end, len(code_text)):
                if code_text[i] == '{':
                    if body_start is None:
                        body_start = i + 1
                    brace_count += 1
                    break
                elif code_text[i] == '}':
                    # Method might be expression-bodied (=>)
                    break

            if body_start is not None:
                # Find matching closing brace
                for i in range(body_start, len(code_text)):
                    if code_text[i] == '{':
                        brace_count += 1
                    elif code_text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            body_end = i
                            break

                if body_end is not None:
                    method_body = code_text[body_start:body_end]

                    # Extract local variables from method body
                    for var_match in local_var_pattern.finditer(method_body):
                        var_name = var_match.group("name")
                        var_start = body_start + var_match.start()
                        var_line = _line_number_for_pos(var_start)
                        var_decl = var_match.group(0).strip()

                        variables.append({
                            "name": var_name,
                            "line": var_line,
                            "method": method_name,
                            "declaration": var_decl,
                        })

    return variables


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

    if not SUPABASE_AVAILABLE:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("Supabase is configured but USE_SUPABASE is False")
        logger.warning(
            "Check SUPABASE_URL and SUPABASE_KEY environment variables")

except ImportError as e:
    SUPABASE_AVAILABLE = False
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"Supabase storage not available for Code Q&A: {e}")
    logger.warning(
        "This is expected if the 'supabase' package is not installed locally.")
    logger.warning(
        "On Render, the package should be installed and this will work.")

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

# Initialize OpenAI client for HYDE and answer generation
api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get(
    "QWEN_API_KEY") or os.environ.get("DASHSCOPE_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY environment variable must be set")

base_url = None
client = OpenAI(api_key=api_key, base_url=base_url)

# Get LLM models from environment or use defaults
_hyde_model = os.environ.get("HYDE_MODEL", "gpt-4o-mini")
_answer_model = os.environ.get("ANSWER_MODEL", "gpt-4o-mini")


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
    token_rate = token_count / \
        (total_time - first_token_time) if first_token_time and (total_time -
                                                                 first_token_time) > 0 else 0

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
                    "IMPORTANT BEHAVIOR RULES:\n"
                    "- If the user asks to summarise, explain, or list methods/variables, "
                    "respond in natural language and DO NOT dump large blocks of code.\n"
                    "- For these summary-style questions, only include very small, focused snippets "
                    "(e.g., a single method signature or a few lines) **if absolutely necessary**.\n"
                    "- Only include full method/class code when the user explicitly asks you to "
                    "\"show\", \"extract\", \"paste\", or \"give the full code\" for something.\n\n"
                    "CODE FORMATTING:\n"
                    "- When showing code snippets, ALWAYS format them in markdown code blocks "
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
    token_rate = token_count / \
        (total_time - first_token_time) if first_token_time and (total_time -
                                                                 first_token_time) > 0 else 0

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

    allowed_set = {normalize_path_consistent(
        p) for p in allowed_paths if normalize_path_consistent(p) is not None}
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
    provider=None,
    prioritize_class_chunks: bool = False
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
        from backend.services.llm_provider import SimpleLLMProvider
        try:
            provider = SimpleLLMProvider()
        except:
            # Fallback to Qwen if OpenAI not available (for embeddings)
            from gdd_rag_backbone.llm_providers import QwenProvider
            provider = QwenProvider()

    embedding_func = make_embedding_func(provider)

    # Step 1: Initial search with original query
    search_start = time.time()
    query_embedding = embedding_func([query])[0]

    # Get initial chunks
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[Code Q&A] Starting search for query: {query[:100]}")
    logger.info(f"[Code Q&A] File filters: {file_filters}")

    initial_methods = search_code_chunks_supabase(
        query=query,
        query_embedding=query_embedding,
        limit=20,
        threshold=0.2,
        file_paths=file_filters,
        chunk_type='method'
    )
    logger.info(f"[Code Q&A] Initial methods found: {len(initial_methods)}")

    initial_classes = search_code_chunks_supabase(
        query=query,
        query_embedding=query_embedding,
        limit=20,
        threshold=0.2,
        file_paths=file_filters,
        chunk_type='class'
    )
    logger.info(f"[Code Q&A] Initial classes found: {len(initial_classes)}")

    # Also do direct file lookup if filters are specified
    if file_filters:
        direct_methods = get_code_chunks_for_files(
            file_filters, chunk_type='method')
        direct_classes = get_code_chunks_for_files(
            file_filters, chunk_type='class')

        # Combine and deduplicate
        all_methods = {
            chunk.get('id'): chunk for chunk in initial_methods + direct_methods}
        all_classes = {
            chunk.get('id'): chunk for chunk in initial_classes + direct_classes}

        initial_methods = list(all_methods.values())
        initial_classes = list(all_classes.values())

    # Limit to top 5 for HYDE context
    method_docs = initial_methods[:5]
    class_docs = initial_classes[:5]

    # Step 2: Build temporary context for HYDE v2
    methods_text = "\n".join([doc.get('code', '') or doc.get(
        'source_code', '') for doc in method_docs])
    classes_text = "\n".join([doc.get('source_code', '')
                             for doc in class_docs])
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
    logger.info(f"[Code Q&A] Final methods found: {len(final_methods)}")

    final_classes = search_code_chunks_supabase(
        query=hyde_query_v2,
        query_embedding=hyde_embedding,
        limit=10,
        threshold=0.2,
        file_paths=file_filters,
        chunk_type='class'
    )
    logger.info(f"[Code Q&A] Final classes found: {len(final_classes)}")

    # Filter by files if specified
    method_docs = _filter_chunks_by_files(final_methods, file_filters)
    class_docs = _filter_chunks_by_files(final_classes, file_filters)
    logger.info(
        f"[Code Q&A] After filtering - methods: {len(method_docs)}, classes: {len(class_docs)}")

    # If prioritizing class chunks (e.g., for global variables), get ALL class chunks directly
    if prioritize_class_chunks and file_filters:
        logger.info(
            "[Code Q&A] Prioritizing class chunks - retrieving all class chunks for file(s)")
        direct_class_chunks = get_code_chunks_for_files(
            file_filters, chunk_type='class')
        logger.info(
            f"[Code Q&A] Direct lookup found {len(direct_class_chunks)} class chunks")

        # Log details about retrieved chunks
        for i, chunk in enumerate(direct_class_chunks):
            source_code_len = len(chunk.get('source_code', ''))
            class_name = chunk.get('class_name', 'unknown')
            file_path = chunk.get('file_path', 'unknown')
            logger.info(
                f"[Code Q&A] Class chunk {i+1}: {class_name} from {file_path}, source_code length: {source_code_len}")
            if source_code_len == 0:
                logger.warning(
                    f"[Code Q&A] WARNING: Class chunk {i+1} has empty source_code!")
            elif source_code_len < 100:
                logger.warning(
                    f"[Code Q&A] WARNING: Class chunk {i+1} has very short source_code ({source_code_len} chars) - might be truncated")

        # Deduplicate by ID
        class_dict = {chunk.get('id'): chunk for chunk in class_docs}
        for chunk in direct_class_chunks:
            chunk_id = chunk.get('id')
            if chunk_id and chunk_id not in class_dict:
                class_dict[chunk_id] = chunk
        class_docs = list(class_dict.values())
        logger.info(
            f"[Code Q&A] Retrieved {len(class_docs)} total class chunks (including direct lookup)")

        # Final check: ensure we have class chunks with source_code
        valid_class_docs = [chunk for chunk in class_docs if chunk.get(
            'source_code', '').strip()]
        if len(valid_class_docs) < len(class_docs):
            logger.warning(
                f"[Code Q&A] WARNING: {len(class_docs) - len(valid_class_docs)} class chunks have empty source_code!")

        # If no valid class chunks found, log error (no local disk fallback - must use Supabase)
        if len(valid_class_docs) == 0 and file_filters:
            logger.error(
                f"[Code Q&A] ERROR: No class chunks found in Supabase for file(s): {file_filters}")
            logger.error(
                "[Code Q&A] These files may not be indexed. Please ensure all files are indexed in Supabase.")

        class_docs = valid_class_docs

    search_time = time.time() - search_start
    timing_info["vector_search_time"] = round(search_time, 2)

    # Step 6: Combine results
    # If prioritizing class chunks, include ALL class chunks, otherwise limit to top 3
    if prioritize_class_chunks:
        # Include all class chunks for global variable extraction
        top_methods = method_docs[:1] if method_docs else []  # Minimal methods
        all_classes = class_docs  # ALL class chunks
    else:
        top_methods = method_docs[:3]
        all_classes = class_docs[:3]

    methods_combined = "\n\n".join(
        f"File: {doc['file_path']}\nCode:\n{doc.get('code', doc.get('source_code', ''))}"
        for doc in top_methods
    )

    classes_combined = "\n\n".join(
        f"File: {doc['file_path']}\nClass: {doc.get('class_name', 'Unknown')}\nClass Info:\n{doc.get('source_code', '')} References: \n{doc.get('code_references', '')}  \n END OF ROW {i}"
        for i, doc in enumerate(all_classes)
    )

    # Log context summary for debugging
    if prioritize_class_chunks:
        logger.info(
            f"[Code Q&A] Context for global variables: {len(all_classes)} class chunks, total context length: {len(classes_combined)}")
        if len(classes_combined.strip()) == 0:
            logger.error(
                "[Code Q&A] ERROR: Class context is empty! Cannot extract global variables.")
        else:
            # Log first 500 chars of context to verify it contains class definitions
            logger.info(
                f"[Code Q&A] Context preview (first 500 chars): {classes_combined[:500]}")

    if prioritize_class_chunks:
        # Prioritize class chunks when extracting global variables
        final_context = classes_combined + "\n\n" + \
            (methods_combined if methods_combined else "")
    else:
        final_context = methods_combined + \
            "\n below is class or constructor related code \n" + classes_combined
    logger.info(
        f"[Code Q&A] Final context length: {len(final_context)} characters")
    if len(final_context.strip()) == 0:
        logger.warning(
            "[Code Q&A] WARNING: Final context is empty! No code chunks retrieved.")

    total_time = time.time() - start_time
    timing_info["total_time"] = round(total_time, 2)
    timing_info["context_length"] = len(final_context)
    timing_info["results_count"] = {"methods": len(
        method_docs), "classes": len(class_docs)}

    return final_context, timing_info


def extract_method_names_from_query(query: str, known_methods: List[str]) -> List[str]:
    q = query.lower()
    matched = []
    for m in known_methods:
        if re.search(rf'\b{re.escape(m.lower())}\b', q):
            matched.append(m)
    return matched


def query_codebase(query: str, file_filters: list = None, selected_methods: list = None):
    """
    Query codebase using RAG with Supabase.

    Args:
        query: User query string
        file_filters: Optional list of file paths to filter by
        selected_methods: Optional list of method names to extract variables from (for "list all variables")

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

        # Detect "extract full code" intent – skip LLM and return raw file code.
        # This triggers when:
        # - The user mentions extracting or showing code/chunk/file
        # - There is exactly one file filter selected
        extract_keywords = [
            "extract code chunk",
            "extract entire code",
            "extract full code",
            "extract full file",
            "show full code",
            "show entire file",
            "paste full code",
            "give full code",
            "show entire code chunk",
        ]
        lower_q = cleaned_query.lower()
        is_extract_request = any(kw in lower_q for kw in extract_keywords)

        if is_extract_request and file_filters and len(file_filters) == 1:
            # Use Supabase to get full file content instead of reading from local disk
            # This ensures it works on Render where files aren't on local disk
            try:
                if not SUPABASE_AVAILABLE:
                    # Fall back to normal RAG flow if Supabase not available
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        "[Code Q&A Extract Full Code] Supabase not available, falling through to RAG")
                    pass
                else:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(
                        f"[Code Q&A Extract Full Code] Getting all chunks for file: {file_filters[0]}")

                    # Get only class chunks for this file (simplified - focus on classes first)
                    all_class_chunks = get_code_chunks_for_files(
                        file_filters, chunk_type='class')
                    logger.info(
                        f"[Code Q&A Extract Full Code] Found {len(all_class_chunks)} class chunk(s)")

                    if not all_class_chunks:
                        logger.warning(
                            f"[Code Q&A Extract Full Code] No class chunks found in Supabase for {file_filters[0]}, falling through to RAG")
                        pass
                    else:
                        # Extract source code from each class chunk
                        full_code_parts = []
                        seen_content = set()  # For deduplication

                        for class_chunk in all_class_chunks:
                            source_code = class_chunk.get('source_code', '')
                            if not source_code:
                                continue

                            # Clean metadata headers while preserving indentation
                            lines = source_code.split('\n')
                            cleaned_lines = []
                            skip_next_empty = False
                            in_code = False

                            for line in lines:
                                stripped = line.strip()

                                # Skip "File: ..." lines
                                if stripped.startswith('File:'):
                                    skip_next_empty = True
                                    continue

                                # Skip empty line after "File:" line
                                if skip_next_empty and not stripped:
                                    skip_next_empty = False
                                    continue

                                # Skip metadata headers (Class:, Source Code:)
                                if stripped and any(stripped.startswith(prefix) for prefix in ['Class:', 'Source Code:']):
                                    skip_next_empty = True
                                    in_code = True  # Code starts after header
                                    continue

                                # Skip empty line after header
                                if skip_next_empty and not stripped and not in_code:
                                    skip_next_empty = False
                                    continue

                                skip_next_empty = False
                                in_code = True
                                # Preserve original line with indentation
                                cleaned_lines.append(line)

                            # Join and clean up leading/trailing whitespace (but preserve internal indentation)
                            cleaned_code = '\n'.join(cleaned_lines).strip()

                            # Deduplicate: only add if we haven't seen this content before
                            if cleaned_code and cleaned_code not in seen_content:
                                seen_content.add(cleaned_code)
                                full_code_parts.append(cleaned_code)

                        # Combine all class chunks with proper spacing
                        if full_code_parts:
                            # Join with double newline to separate classes, but preserve internal structure
                            code_text = "\n\n".join(full_code_parts)

                            # Add file path at the top (only once)
                            file_path_header = f"File: {file_filters[0]}\n\n"
                            code_text = file_path_header + code_text

                            logger.info(
                                f"[Code Q&A Extract Full Code] Reconstructed file from {len(full_code_parts)} class chunk(s), total length: {len(code_text)} chars")

                            # Wrap full file in a single code block
                            return {
                                "response": f"```csharp\n{code_text}\n```",
                                "status": "success",
                                "source_file": file_filters[0],
                            }

                    # If no chunks found, log and fall through to RAG
                    logger.warning(
                        f"[Code Q&A Extract Full Code] No chunks found in Supabase for {file_filters[0]}, falling through to RAG")
                    pass
            except Exception as e:
                # On any error, fall back to normal RAG flow
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"[Code Q&A Extract Full Code] Error extracting full code from Supabase, falling through to RAG: {e}")
                pass

        # 1b) Regex-based listing of methods / variables when exactly one file is selected.
        # This overrides RAG for deterministic answers.
        list_methods_keywords = [
            "list all methods",
            "list all functions",
            "what are the methods",
            "what are the functions",
        ]
        list_vars_keywords = [
            "list all variables",
            "list all fields",
            "list all properties",
            "what are the variables",
            "what are the fields",
            "what are the properties",
        ]

        is_list_methods = any(kw in lower_q for kw in list_methods_keywords)
        is_list_vars = any(kw in lower_q for kw in list_vars_keywords)
        single_file_selected = file_filters and len(file_filters) == 1

        # If selected_methods is provided, use RAG instead of regex
        # Skip regex override and go straight to RAG with enhanced query
        use_rag_for_variables = False
        if selected_methods and len(selected_methods) > 0 and is_list_vars:
            # Check if global variables are requested
            include_global = "__GLOBAL_VARIABLES__" in selected_methods
            actual_methods = [
                m for m in selected_methods if m != "__GLOBAL_VARIABLES__"]

            if include_global and actual_methods:
                # Both global vars and methods selected
                methods_str = ", ".join(actual_methods)
                enhanced_query = f"""Extract variables from the following methods: {methods_str}, AND extract all global/shared variables from this file.

FOR METHODS ({methods_str}):
Include: 1) Method parameters (with their types), 2) Local variables declared within the method body, 3) Class fields/properties accessed within the method.

FOR GLOBAL/SHARED VARIABLES:
INCLUDE:
- Fields declared at class or struct scope (NOT inside any method body)
- Private,constants, Static fields, instance fields, const and readonly fields
- Properties declared at class scope

EXCLUDE:
- Local variables, method parameters, lambda locals, pattern variables

EXTRACTION RULES:
- Only return variables declared directly in a class or struct body
- Ignore any declaration that appears between method braces {{ ... }}
- Do NOT infer or guess

Group the output by: Global Variables first, then by method name."""
            elif include_global:
                # Only global variables selected
                enhanced_query = """Extract ALL global/shared variables from the class definitions provided in the context.

GLOBAL/SHARED VARIABLES INCLUDE:
- Fields declared at class or struct scope (NOT inside any method body)
- Static fields (truly shared)
- Instance fields (shared across methods of an instance)
- Const and readonly fields
- Properties declared at class scope (with { get; set; } syntax)

GLOBAL/SHARED VARIABLES EXCLUDE:
- Local variables (declared inside method bodies)
- Method parameters
- Lambda locals
- Pattern variables (from pattern matching)
- Variables declared inside nested classes (only extract from the main class in the file)

EXTRACTION RULES:
1. Only return variables declared directly in a class or struct body (between the opening { and before any method declarations)
2. Ignore any declaration that appears between method braces { ... }
3. Do NOT infer or guess - only extract what is explicitly declared in the class body
4. Look for declarations that appear at the class level, before any method definitions
5. If no global variables exist, return "No global variables found"

For each global variable found, provide:
- Variable name
- Type (if visible)
- Access modifier (public, private, protected, internal, etc.)
- Modifiers (static, const, readonly, override, etc.)
- Initial value (if present)

Format the output as:
**Fields:**
- `variableName` (type) - access modifier, modifiers

**Properties:**
- `propertyName` (type) - access modifier, modifiers

If no global variables are found in the provided class definitions, respond with: "No global variables found"."""
            else:
                # Only methods selected (existing logic)
                methods_str = ", ".join(actual_methods)
                enhanced_query = f"List all variables used in the following methods: {methods_str}. Include local variables, parameters, and any fields/properties accessed within these methods. For each variable, show its name, type (if visible), and which method it belongs to."

            cleaned_query = enhanced_query
            use_rag_for_variables = True
            # Skip regex override, fall through to RAG

        if not use_rag_for_variables and single_file_selected and (is_list_methods or is_list_vars):
            # Use Supabase to get class and method chunks instead of reading from disk
            # This ensures it works on Render where files aren't on local disk
            try:
                if not SUPABASE_AVAILABLE:
                    # Fall through to RAG if Supabase not available
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        "[Code Q&A Regex Override] Supabase not available, falling through to RAG")
                    pass
                else:
                    # Get class chunks from Supabase to extract methods and global variables
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.info(
                        f"[Code Q&A Regex Override] Starting regex override for file: {file_filters[0]}")
                    logger.info(
                        f"[Code Q&A Regex Override] Query type: list_methods={is_list_methods}, list_vars={is_list_vars}")

                    class_chunks = get_code_chunks_for_files(
                        file_filters, chunk_type='class')
                    method_chunks = get_code_chunks_for_files(
                        file_filters, chunk_type='method')

                    logger.info(
                        f"[Code Q&A Regex Override] Found {len(class_chunks)} class chunks and {len(method_chunks)} method chunks from Supabase")

                    # Always try to extract methods and global variables, even if chunks are missing
                    # This allows us to show the method selection UI with whatever we can find
                    methods = []
                    fields = []
                    properties = []

                    if not class_chunks and not method_chunks:
                        # No chunks found in Supabase - try to diagnose why
                        import os
                        filename = os.path.basename(
                            file_filters[0]) if file_filters else "unknown"
                        logger.warning(
                            f"[Code Q&A Regex Override] No chunks found in Supabase for file: {file_filters[0]}")
                        logger.warning(
                            f"[Code Q&A Regex Override] Filename extracted: {filename}")
                        logger.warning(
                            f"[Code Q&A Regex Override] This file may not be indexed in Supabase, or the filename matching failed.")
                        logger.warning(
                            f"[Code Q&A Regex Override] Regex override requires source code from Supabase chunks - falling through to RAG")
                        logger.warning(
                            f"[Code Q&A Regex Override] NOTE: If this file should be indexed, please ensure it's been indexed in Supabase first.")
                        pass
                    else:
                        # Extract methods from method chunks
                        for method_chunk in method_chunks:
                            method_name = method_chunk.get('method_name')
                            if method_name:
                                # Try to extract line number from source_code if available
                                source_code = method_chunk.get(
                                    'code', '') or method_chunk.get('source_code', '')
                                line_num = 1  # Default if we can't determine
                                if source_code:
                                    # Try to find method name in source code to get approximate line
                                    try:
                                        lines = source_code.split('\n')
                                        for idx, line in enumerate(lines, 1):
                                            if method_name in line and ('(' in line or 'void' in line or any(rt in line for rt in ['int', 'string', 'bool', 'float', 'double', 'object'])):
                                                line_num = idx
                                                break
                                    except Exception:
                                        line_num = 1

                                methods.append({
                                    "name": method_name,
                                    "line": line_num
                                })
                                logger.debug(
                                    f"[Code Q&A Regex Override] Added method: {method_name} (line {line_num})")

                        # Extract fields and properties from class chunks
                        for i, class_chunk in enumerate(class_chunks):
                            source_code = class_chunk.get('source_code', '')
                            class_name = class_chunk.get(
                                'class_name', 'unknown')
                            file_path = class_chunk.get('file_path', 'unknown')
                            logger.info(
                                f"[Code Q&A Regex Override] Processing class chunk {i+1}/{len(class_chunks)}: {class_name} from {file_path}, source_code length: {len(source_code)}")

                            if source_code:
                                try:
                                    # Parse the class source_code to extract methods, fields, properties
                                    parsed_methods, parsed_fields, parsed_properties = _analyze_csharp_file_symbols(
                                        source_code)

                                    logger.info(
                                        f"[Code Q&A Regex Override] Parsed from {class_name}: {len(parsed_methods)} methods, {len(parsed_fields)} fields, {len(parsed_properties)} properties")

                                    # Log field and property names for debugging
                                    if parsed_fields:
                                        field_names = [f['name']
                                                       for f in parsed_fields]
                                        logger.info(
                                            f"[Code Q&A Regex Override] Fields found: {field_names}")
                                    if parsed_properties:
                                        prop_names = [p['name']
                                                      for p in parsed_properties]
                                        logger.info(
                                            f"[Code Q&A Regex Override] Properties found: {prop_names}")

                                    # Add methods (if not already added from method chunks)
                                    for m in parsed_methods:
                                        if not any(existing['name'] == m['name'] for existing in methods):
                                            # Preserve line number from parsed method if available
                                            methods.append({
                                                "name": m['name'],
                                                "line": m.get('line', 1)
                                            })

                                    # Add fields and properties
                                    fields.extend(parsed_fields)
                                    properties.extend(parsed_properties)
                                except Exception as e:
                                    logger.error(
                                        f"[Code Q&A Regex Override] Error parsing class chunk {class_name}: {e}")
                                    import traceback
                                    logger.error(
                                        f"[Code Q&A Regex Override] Traceback: {traceback.format_exc()}")
                            else:
                                logger.warning(
                                    f"[Code Q&A Regex Override] Class chunk {class_name} from {file_path} has empty source_code!")

                        logger.info(
                            f"[Code Q&A Regex Override] Final counts: {len(methods)} methods, {len(fields)} fields, {len(properties)} properties")

                        # Only proceed if we found something (methods, fields, or properties)
                        if not (methods or fields or properties):
                            # No methods, fields, or properties found - fall through to RAG
                            logger.warning(
                                f"[Code Q&A Regex Override] No methods/fields/properties extracted from chunks, falling through to RAG")
                            logger.warning(
                                f"[Code Q&A Regex Override] This might indicate: 1) Chunks have empty source_code, 2) Regex parsing failed, 3) File has no methods/fields/properties")
                            pass
                        else:
                            logger.info(
                                f"[Code Q&A Regex Override] Successfully extracted symbols - proceeding with regex override (NOT falling through to RAG)")
                            method_names = [m["name"] for m in methods]
                            requested_methods = extract_method_names_from_query(
                                cleaned_query, method_names)

                            lines: List[str] = []
                            file_name = file_filters[0].split(
                                '/')[-1] if file_filters else "Unknown"
                            lines.append(f"File: `{file_name}`")

                            if is_list_methods:
                                lines.append(
                                    "\n**Methods / Functions (all detected):**")
                                if methods:
                                    for m in methods:
                                        lines.append(
                                            f"- `{m['name']}` (line {m['line']})")
                                else:
                                    lines.append("- (no methods detected)")

                                return {
                                    "response": "\n".join(lines),
                                    "status": "success",
                                    "source_file": file_filters[0] if file_filters else None,
                                }

                            if is_list_vars:
                                # CASE 1: User specified methods in query text → use RAG to extract variables
                                if requested_methods:
                                    # Construct a query that asks RAG to extract variables from specified methods
                                    methods_str = ", ".join(requested_methods)
                                    enhanced_query = f"List all variables, fields, and properties used in the following methods: {methods_str}. Include local variables, parameters, and any fields/properties accessed within these methods. For each variable, show its name, type (if visible), and which method it belongs to."

                                    # Update cleaned_query and set flag to skip return and use RAG
                                    cleaned_query = enhanced_query
                                    use_rag_for_variables = True
                                    # Flag is set - code will fall through to RAG section after try block
                                    # The else block below won't execute because we're inside if is_list_vars

                                # CASE 2: Show UI if we have methods OR global variables (fields/properties)
                                # This ensures UI shows even if only methods exist (no class chunks) or only global variables exist (no methods)
                                elif methods or fields or properties:
                                    # Get global variables (fields + properties)
                                    global_vars = []
                                    for f in fields:
                                        global_vars.append({
                                            "name": f['name'],
                                            "line": f['line'],
                                            "type": "field"
                                        })
                                    for p in properties:
                                        global_vars.append({
                                            "name": p['name'],
                                            "line": p['line'],
                                            "type": "property"
                                        })

                                    import logging
                                    logger = logging.getLogger(__name__)
                                    logger.info(
                                        f"[Code Q&A Regex Override] Building UI: {len(methods)} methods, {len(global_vars)} global variables")
                                    logger.info(
                                        f"[Code Q&A Regex Override] Fields: {len(fields)}, Properties: {len(properties)}")

                                    # Return special response format that triggers method selection UI
                                    methods_list = [
                                        {"name": m["name"], "line": m["line"]} for m in methods]

                                    # Ensure global_variables is always a list (never None or undefined)
                                    # Build appropriate message based on what we have
                                    if methods and global_vars:
                                        message = (
                                            "You asked to list **all variables**.\n"
                                            "This file contains methods and global variables. Please select which method(s) you want to see variables for, or select 'Global Variables' to see class-level fields and properties."
                                        )
                                    elif methods:
                                        message = (
                                            "You asked to list **all variables**.\n"
                                            "This file contains methods. Please select which method(s) you want to see variables for."
                                        )
                                    elif global_vars:
                                        message = (
                                            "You asked to list **all variables**.\n"
                                            "This file contains global variables (fields and properties). Please select 'Global Variables' to see them."
                                        )
                                    else:
                                        message = (
                                            "You asked to list **all variables**.\n"
                                            "Please select which method(s) you want to see variables for."
                                        )

                                    response_data = {
                                        "response": message,
                                        "status": "success",
                                        "source_file": file_filters[0] if file_filters else None,
                                        "requires_method_selection": True,
                                        "methods": methods_list,
                                        "global_variables": global_vars if global_vars else [],  # Always a list, never None
                                        "file_path": file_filters[0] if file_filters else None,
                                    }

                                    logger.info(
                                        f"[Code Q&A Regex Override] Response includes {len(response_data['global_variables'])} global variables")
                                    return response_data
                            else:
                                # This should not happen since we check `elif methods or fields or properties`
                                # But keep as fallback: No methods, fields, or properties in this file.
                                # In this case, list all fields and properties directly.
                                lines.append(
                                    "\nThis file does not define any methods. Listing all "
                                    "fields/variables and properties in the file instead.\n"
                                )
                                lines.append(
                                    "\n**Fields / Variables (all detected):**")
                                if fields:
                                    for f in fields:
                                        lines.append(f"- `{f['name']}`")
                                else:
                                    lines.append("- (no fields detected)")

                                lines.append(
                                    "\n**Properties (all detected):**")
                                if properties:
                                    for p in properties:
                                        lines.append(f"- `{p['name']}`")
                                else:
                                    lines.append("- (no properties detected)")

                                return {
                                    "response": "\n".join(lines),
                                    "status": "success",
                                    "source_file": file_filters[0] if file_filters else None,
                                }
            except Exception as e:
                # Fall through to normal RAG flow on any error
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"[Code Q&A] Error in regex override, falling through to RAG: {e}")
                pass

        # Use Supabase if available
        if SUPABASE_AVAILABLE:
            try:
                from backend.services.llm_provider import SimpleLLMProvider
                provider = SimpleLLMProvider()

                # Generate context
                import logging
                logger = logging.getLogger(__name__)
                logger.info(f"[Code Q&A Query] Query: {cleaned_query[:100]}")
                logger.info(f"[Code Q&A Query] File filters: {file_filters}")

                # Check if this is a global variables query
                is_global_vars_query = (
                    use_rag_for_variables and
                    selected_methods and
                    "__GLOBAL_VARIABLES__" in selected_methods
                )

                context, context_timing = generate_context_supabase(
                    query=cleaned_query,
                    file_filters=file_filters,
                    provider=provider,
                    prioritize_class_chunks=is_global_vars_query
                )

                logger.info(
                    f"[Code Q&A Query] Context retrieved: {len(context)} chars")
                logger.info(
                    f"[Code Q&A Query] Context timing: {context_timing}")

                # Truncate context if needed
                context_for_llm = context[:8000]
                if len(context) > 8000:
                    context_for_llm = context[:8000]

                # Generate answer
                if context_for_llm.strip():
                    logger.info(
                        f"[Code Q&A Query] Generating answer with context length: {len(context_for_llm)}")
                    answer, answer_timing = openai_chat(
                        cleaned_query, context_for_llm)
                else:
                    logger.warning(
                        "[Code Q&A Query] Context is empty - returning 'No relevant code chunks' message")
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
    Uses Supabase ONLY - no local disk fallback (works on Render).

    Returns:
        list: List of file metadata dictionaries with keys: file_name, file_path, normalized_path
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        # Use Supabase only - no local disk fallback
        if not SUPABASE_AVAILABLE:
            logger.warning("Supabase not available - cannot list code files")
            logger.warning(
                "Set SUPABASE_URL and SUPABASE_KEY environment variables")
            return []

        logger.info("Fetching code files from Supabase...")
        files = list_code_files_supabase()

        if files:
            logger.info(f"✅ Retrieved {len(files)} code files from Supabase")
            # Ensure all files have the expected format
            formatted_files = []
            for file in files:
                formatted_files.append({
                    'file_name': file.get('file_name', ''),
                    'file_path': file.get('file_path', ''),
                    'normalized_path': file.get('normalized_path', file.get('file_path', ''))
                })
            return formatted_files
        else:
            logger.warning("⚠️  No code files found in Supabase")
            logger.warning("   This could mean:")
            logger.warning(
                "   1. The code_files table is empty (files haven't been indexed yet)")
            logger.warning("   2. There's a connection issue with Supabase")
            logger.warning("   3. RLS policies are blocking access")
            return []

    except Exception as e:
        logger.error(f"❌ Error listing code files from Supabase: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        return []
