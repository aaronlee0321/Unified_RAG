"""
GDD RAG Service
Extracted from gradio_app.py - handles GDD document queries
"""

import os
import sys
import asyncio
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Try to import Supabase storage (optional)
try:
    from backend.storage.gdd_supabase_storage import (
        get_gdd_top_chunks_supabase,
        list_gdd_documents_supabase,
        index_gdd_chunks_to_supabase,
        USE_SUPABASE
    )
    SUPABASE_AVAILABLE = USE_SUPABASE
except ImportError:
    SUPABASE_AVAILABLE = False
    print("Warning: Supabase storage not available, using local file storage")

# Import gdd_rag_backbone (now included in unified_rag_app)
try:
    from gdd_rag_backbone.config import DEFAULT_DOCS_DIR, DEFAULT_WORKING_DIR
    from gdd_rag_backbone.llm_providers import (
        QwenProvider,
        make_embedding_func,
    )
    # Removed get_markdown_top_chunks - using Supabase only, no local storage fallback
    from gdd_rag_backbone.scripts.chunk_markdown_files import (
        generate_doc_id as generate_md_doc_id,
        save_chunks as save_md_chunks,
    )
    from gdd_rag_backbone.scripts.index_markdown_chunks import index_chunks_for_doc
    from gdd_rag_backbone.markdown_chunking import MarkdownChunker
    GDD_RAG_BACKBONE_AVAILABLE = True
    
    # Ensure directories exist (relative to unified_rag_app)
    DEFAULT_DOCS_DIR = PROJECT_ROOT / "docs"
    DEFAULT_WORKING_DIR = PROJECT_ROOT / "rag_storage"
    DEFAULT_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_WORKING_DIR.mkdir(parents=True, exist_ok=True)
except ImportError as e:
    import sys
    import traceback
    print(f"[ERROR] Failed to import gdd_rag_backbone: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    GDD_RAG_BACKBONE_AVAILABLE = False
    # Set defaults to avoid NameError
    DEFAULT_DOCS_DIR = PROJECT_ROOT / "docs"
    DEFAULT_WORKING_DIR = PROJECT_ROOT / "rag_storage"

# Markdown directory path
MARKDOWN_DIR = PROJECT_ROOT / "gdd_data" / "markdown"


def _generate_doc_id_from_filename(filename: Path) -> str:
    """
    Generate document ID from filename (same logic as chunk_markdown_files.py).
    
    Args:
        filename: Markdown file path
    
    Returns:
        Document ID (sanitized filename without extension)
    """
    # Remove extension and sanitize
    doc_id = filename.stem
    # Replace spaces and special chars with underscores
    doc_id = doc_id.replace(" ", "_").replace("[", "").replace("]", "")
    doc_id = doc_id.replace("-", "_").replace(",", "_")
    # Remove multiple underscores
    while "__" in doc_id:
        doc_id = doc_id.replace("__", "_")
    return doc_id.strip("_")


def _find_markdown_file_from_doc_id(doc_id: str) -> Optional[Path]:
    """
    DEPRECATED: No longer uses local files. Always returns None.
    Markdown content is now stored in Supabase.
    
    Args:
        doc_id: Document ID
    
    Returns:
        None (local files are no longer used)
    """
    # Local files are no longer used - all content is in Supabase
    return None


def list_documents_from_markdown() -> List[Dict[str, Any]]:
    """
    List all documents from Supabase (no local file dependency).
    Uses Supabase as the only source of truth.
    
    Returns:
        List of document metadata dictionaries
    """
    # Get documents directly from Supabase (no local file scanning)
    if not SUPABASE_AVAILABLE:
        return []
    
    try:
        supabase_docs_list = list_gdd_documents_supabase()
        documents = []
        
        for doc in supabase_docs_list:
            doc_id = doc.get("doc_id", "")
            chunks_count = doc.get("chunks_count", 0)
            name = doc.get("name", doc_id)
            file_path = doc.get("file_path")  # May be None, that's OK
            
            documents.append({
                'doc_id': doc_id,
                'name': name,
                'file_path': file_path,  # May be None - stored for reference only
                'chunks_count': chunks_count,
                'status': 'ready' if chunks_count > 0 else 'indexed'
            })
        
        return documents
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Warning: Could not load documents from Supabase: {e}")
        return []


def extract_full_document(doc_id: str) -> str:
    """
    Extract full document content from Supabase (no local file dependency).
    
    Args:
        doc_id: Document ID
    
    Returns:
        Full document content as string, or error message if not found
    """
    if not SUPABASE_AVAILABLE:
        return f"Error: Supabase is not available. Cannot extract document '{doc_id}'."
    
    try:
        from backend.storage.supabase_client import get_gdd_document_markdown
        content = get_gdd_document_markdown(doc_id)
        
        if content:
            return content
        else:
            return f"Error: Document '{doc_id}' not found in Supabase or has no markdown content stored."
    except Exception as e:
        return f"Error reading document '{doc_id}' from Supabase: {str(e)}"


def _detect_question_language(text: str) -> str:
    """
    Detect if the question is in Vietnamese or English.
    
    Args:
        text: The question text
    
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


def _select_chunks_for_answer(chunks):
    """
    Heuristic to decide how many top chunks to feed into the answer prompt.

    Special case:
    - If the top chunk score is already ~1.0, we assume it alone is enough.

    Otherwise:
    - A: very strong, clearly dominant top chunk → 1 chunk
    - B: strong top chunk, close second → 2 chunks
    - C: moderately strong → 3 chunks
    - D: weak/flat scores → up to 5 chunks
    """
    if not chunks:
        return []

    scores = [float(c.get("score", 0.0) or 0.0) for c in chunks]
    s1 = scores[0]
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


def upload_and_index_document(file_path: Path):
    """
    Upload and index a PDF document using the new markdown pipeline.
    
    Workflow:
    1. Save uploaded PDF into DEFAULT_DOCS_DIR
    2. Convert PDF → Markdown using the PDFtoMarkdown/pdf_to_markdown.py helper
    3. Chunk the resulting Markdown with MarkdownChunker into rag_storage_md/
    4. Index the chunks with embeddings into rag_storage_md_indexed/
    
    Args:
        file_path: Path to the uploaded file
    
    Returns:
        dict: Status and document ID
    """
    try:
        if file_path.suffix.lower() != ".pdf":
            return {
                'status': 'error',
                'message': 'Only PDF files are supported for upload in this version.'
            }
        
        # 1. Save PDF into docs directory (for reference/backups)
        target_path = DEFAULT_DOCS_DIR / file_path.name
        shutil.copy(str(file_path), str(target_path))
        
        # 2. Convert PDF → Markdown (for now, skip PDF conversion - documents should be pre-converted)
        # TODO: Add PDF to Markdown conversion capability if needed
        # For now, assume documents are already in markdown format or skip this step
        pdf_md_dir = PROJECT_ROOT / "markdown"
        pdf_md_dir.mkdir(parents=True, exist_ok=True)
        
        # Skip PDF conversion for now - return error if PDF upload is attempted
        return {
            'status': 'error',
            'message': 'PDF upload is not yet supported in the unified app. Please use pre-converted markdown files or implement PDF conversion.'
        }
        
        # Use the existing CLI helper's convert_all function
        md_paths = pdf2md.convert_all(
            input_path=target_path,
            output_dir=pdf_md_dir,
            ocr_langs=None,
            overwrite=True,
        )
        if not md_paths:
            return {
                'status': 'error',
                'message': 'Error: PDF to Markdown conversion failed (no output files).'
            }
        
        md_path = md_paths[0]
        
        # 3. Chunk the markdown into rag_storage_md/
        markdown_content = md_path.read_text(encoding="utf-8")
        doc_id = generate_md_doc_id(md_path)
        
        chunker = MarkdownChunker()
        chunks = chunker.chunk_document(
            markdown_content=markdown_content,
            doc_id=doc_id,
            filename=str(md_path),
        )
        
        md_output_dir = PROJECT_ROOT / "rag_storage_md" / doc_id
        save_md_chunks(chunks, doc_id, md_output_dir)
        
        # 4. Index chunks - use Supabase if available, otherwise local storage
        provider = QwenProvider()
        
        if SUPABASE_AVAILABLE:
            # Index to Supabase
            try:
                index_gdd_chunks_to_supabase(
                    doc_id=doc_id,
                    chunks=chunks,
                    provider=provider
                )
                return {
                    'status': 'success',
                    'message': f'Successfully converted, chunked, and indexed to Supabase: {file_path.name} (as {doc_id})',
                    'doc_id': doc_id
                }
            except Exception as e:
                # Fallback to local storage if Supabase fails
                print(f"Warning: Supabase indexing failed, falling back to local storage: {e}")
                embedding_func = make_embedding_func(provider)
                asyncio.run(index_chunks_for_doc(
                    doc_id=doc_id,
                    embedding_func=embedding_func,
                    dry_run=False,
                ))
                return {
                    'status': 'success',
                    'message': f'Successfully converted, chunked, and indexed (local storage): {file_path.name} (as {doc_id})',
                    'doc_id': doc_id
                }
        else:
            # Use local storage
            embedding_func = make_embedding_func(provider)
            asyncio.run(index_chunks_for_doc(
                doc_id=doc_id,
                embedding_func=embedding_func,
                dry_run=False,
            ))
            return {
                'status': 'success',
                'message': f'Successfully converted, chunked, and indexed: {file_path.name} (as {doc_id})',
                'doc_id': doc_id
            }
    except Exception as e:
        return {
            'status': 'error',
            'message': f'Error: {str(e)}'
        }


def list_documents():
    """
    List all indexed GDD documents.
    Uses markdown directory as source of truth, with Supabase for chunk counts.
    
    Returns:
        list: List of document metadata dictionaries
    """
    import logging
    logger = logging.getLogger(__name__)
    
    logger.info("=" * 60)
    logger.info("list_documents() called")
    logger.info(f"SUPABASE_AVAILABLE: {SUPABASE_AVAILABLE}")
    
    try:
        # Get documents from Supabase (no local file dependency)
        documents = list_documents_from_markdown()
        logger.info(f"✅ Loaded {len(documents)} documents from Supabase")
        logger.info("=" * 60)
        return documents
    except Exception as e:
        import traceback
        logger.error(f"❌ Error listing documents: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        logger.info("=" * 60)
        return []


def get_document_options():
    """
    Get list of document options for dropdown.
    Uses markdown directory as source of truth.
    Shows ALL documents from markdown directory, not just indexed ones.
    
    Returns:
        list: List of document option strings
    """
    try:
        # Get ALL documents from markdown directory (not just indexed)
        docs = list_documents_from_markdown()
        
        options = ["All Documents"]
        for doc in sorted(docs, key=lambda x: x.get("doc_id", "")):
            doc_id = doc.get("doc_id", "")
            file_path = doc.get("file_path", "")
            name = doc.get("name", "")
            chunks_count = doc.get("chunks_count", 0)
            
            if file_path:
                file_name = Path(file_path).name
                # Show chunk count in display name
                if chunks_count > 0:
                    display_name = f"{file_name} ({doc_id}) - {chunks_count} chunks"
                else:
                    display_name = f"{file_name} ({doc_id}) - not indexed"
            elif name:
                if chunks_count > 0:
                    display_name = f"{name} ({doc_id}) - {chunks_count} chunks"
                else:
                    display_name = f"{name} ({doc_id}) - not indexed"
            else:
                if chunks_count > 0:
                    display_name = f"{doc_id} - {chunks_count} chunks"
                else:
                    display_name = f"{doc_id} - not indexed"
            
            options.append(display_name)
        
        return options
    except Exception as e:
        print(f"Error getting document options: {e}")
        return ["All Documents"]


def get_document_sections(doc_id: str) -> List[Dict[str, str]]:
    """
    Get all unique sections/headers for a document from Supabase.
    
    Returns sections sorted by section_index, with numbered_header as the display name.
    
    Args:
        doc_id: Document ID
    
    Returns:
        List of section dictionaries with:
        - section_name: Display name (numbered_header or section_path)
        - section_path: Full section path
        - numbered_header: Numbered header (e.g., "4. Thànhphần")
        - section_index: Numeric index for sorting
    """
    if not SUPABASE_AVAILABLE:
        return []
    
    try:
        from backend.storage.supabase_client import get_supabase_client
        client = get_supabase_client()
        
        # Get all unique sections for this document
        result = client.table('gdd_chunks').select(
            'section_path, section_title, metadata'
        ).eq('doc_id', doc_id).execute()
        
        sections_map = {}
        
        for row in (result.data or []):
            metadata = row.get('metadata', {})
            if isinstance(metadata, dict):
                numbered_header = metadata.get('numbered_header', '')
                section_index = metadata.get('section_index', 999)
            else:
                numbered_header = ''
                section_index = 999
            
            section_path = row.get('section_path', '')
            section_title = row.get('section_title', '')
            
            # Use numbered_header as key if available, otherwise section_path
            key = numbered_header if numbered_header else section_path
            if not key:
                continue
            
            # Store section with best available info
            if key not in sections_map:
                sections_map[key] = {
                    'section_name': numbered_header if numbered_header else section_path,
                    'section_path': section_path,
                    'numbered_header': numbered_header,
                    'section_index': section_index
                }
            else:
                # Update if we have a better numbered_header or lower section_index
                existing = sections_map[key]
                if numbered_header and not existing['numbered_header']:
                    existing['numbered_header'] = numbered_header
                    existing['section_name'] = numbered_header
                if section_index < existing['section_index']:
                    existing['section_index'] = section_index
        
        # Convert to list and sort by section_index
        sections = list(sections_map.values())
        sections.sort(key=lambda x: (x['section_index'], x['section_name']))
        
        return sections
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting sections for document {doc_id}: {e}")
        return []


def query_gdd_documents(query: str, selected_doc: str = None):
    """
    Query GDD documents using RAG.
    
    Args:
        query: User query string
        selected_doc: Optional document selection (format: "filename (doc_id)" or "All Documents")
    
    Returns:
        dict: Response with answer and metadata
    """
    try:
        if not query.strip():
            return {
                'response': 'Please provide a query.',
                'status': 'error'
            }
        
        # Get documents from markdown directory
        markdown_docs = list_documents_from_markdown()
        
        # Get indexed doc IDs (documents with chunks in Supabase)
        indexed_doc_ids = [doc.get("doc_id", "") for doc in markdown_docs if doc.get("chunks_count", 0) > 0]
        
        # If no indexed documents, return helpful message
        if not indexed_doc_ids:
            total_docs = len(markdown_docs)
            return {
                'response': f'No indexed markdown documents found in Supabase. Found {total_docs} markdown files, but none are indexed yet. Please index documents in Supabase first.',
                'status': 'error'
            }
        
        # Handle document selection from dropdown
        target_doc_id = None
        if selected_doc and selected_doc != "All Documents":
            # Extract doc_id from selected_doc (format: "filename (doc_id) - X chunks" or "filename (doc_id) - not indexed")
            for doc in markdown_docs:
                doc_id = doc.get("doc_id", "")
                file_path = doc.get("file_path", "")
                name = doc.get("name", "")
                chunks_count = doc.get("chunks_count", 0)
                
                # Try different display name formats (with chunk count suffix)
                if file_path:
                    file_name = Path(file_path).name
                    if chunks_count > 0:
                        display_name = f"{file_name} ({doc_id}) - {chunks_count} chunks"
                    else:
                        display_name = f"{file_name} ({doc_id}) - not indexed"
                elif name:
                    if chunks_count > 0:
                        display_name = f"{name} ({doc_id}) - {chunks_count} chunks"
                    else:
                        display_name = f"{name} ({doc_id}) - not indexed"
                else:
                    if chunks_count > 0:
                        display_name = f"{doc_id} - {chunks_count} chunks"
                    else:
                        display_name = f"{doc_id} - not indexed"
                
                # Also try matching without the suffix (for backward compatibility)
                display_name_no_suffix = display_name.split(" - ")[0]
                if display_name == selected_doc or display_name_no_suffix == selected_doc:
                    target_doc_id = doc_id
                    break
            
            # If specific document selected, store it for later use
            # We'll check if it's indexed when needed
            pass
        
        # Check for reserved keyword "extract entire doc" early
        message_lower = query.lower().strip()
        extract_keywords = [
            "extract entire doc",
            "extract entire document",
            "extract all doc",
            "extract all document",
        ]
        is_extract_request = any(kw in message_lower for kw in extract_keywords)
        
        # If extract request and we have a specific document, return full content (override RAG)
        if is_extract_request and target_doc_id:
            full_content = extract_full_document(target_doc_id)
            return {
                'response': f"**Full Document: {target_doc_id}**\n\n{full_content}",
                'status': 'success'
            }
        
        # Handle special queries
        if "what are the files" in message_lower or "list documents" in message_lower or "show documents" in message_lower:
            doc_list = []
            for doc in markdown_docs[:20]:  # Limit to 20
                doc_id = doc["doc_id"]
                chunks_count = doc.get("chunks_count", 0)
                file_path = doc.get("file_path", "")
                file_name = Path(file_path).name if file_path else doc_id
                doc_list.append(f"- 📝 {file_name} ({chunks_count} chunks)")
            
            response = f"**Indexed Markdown Documents ({len(indexed_doc_ids)} total):**\n\n" + "\n".join(doc_list)
            if len(indexed_doc_ids) > 20:
                response += f"\n\n... and {len(indexed_doc_ids) - 20} more documents."
            
            return {
                'response': response,
                'status': 'success'
            }
        
        # If no specific document selected, check if user is asking about a specific document in message
        if not selected_doc or selected_doc == "All Documents":
            markdown_status = {doc["doc_id"]: doc for doc in markdown_docs}
            
            # First, try to find exact document ID match in message
            # Check ALL documents (not just indexed) to find the target
            for doc in markdown_docs:
                doc_id = doc.get("doc_id", "")
                file_name = doc.get("name", "")
                file_path = doc.get("file_path", "")
                
                # Normalize for comparison
                doc_id_normalized = doc_id.lower().replace("[", "").replace("]", "").replace(",", "").replace("_", "").replace("-", "").replace(" ", "")
                message_normalized = message_lower.replace("[", "").replace("]", "").replace(",", "").replace("_", "").replace("-", "").replace(" ", "")
                
                # Strategy 1: Check if doc_id appears in message
                if doc_id_normalized in message_normalized or message_normalized in doc_id_normalized:
                    target_doc_id = doc_id
                    break
                
                # Strategy 2: Check file name (stem)
                if file_name:
                    file_name_normalized = file_name.lower().replace("[", "").replace("]", "").replace(",", "").replace("_", "").replace("-", "").replace(" ", "")
                    if file_name_normalized in message_normalized or any(word in file_name_normalized for word in message_normalized.split() if len(word) > 4):
                        target_doc_id = doc_id
                        break
                
                # Strategy 3: Check file path
                if file_path:
                    file_stem = Path(file_path).stem.lower().replace("_", "").replace("-", "").replace(" ", "")
                    if file_stem in message_normalized or any(word in file_stem for word in message_normalized.split() if len(word) > 4):
                        target_doc_id = doc_id
                        break
        
        # Check for reserved keyword "extract entire doc" (after document selection)
        # This overrides RAG and returns the full markdown document
        message_lower = query.lower().strip()
        extract_keywords = [
            "extract entire doc",
            "extract entire document",
            "extract all doc",
            "extract all document",
        ]
        
        is_extract_request = any(kw in message_lower for kw in extract_keywords)
        
        # If extract request and we have a specific document, return full content (override RAG)
        if is_extract_request and target_doc_id:
            full_content = extract_full_document(target_doc_id)
            return {
                'response': f"**Full Document: {target_doc_id}**\n\n{full_content}",
                'status': 'success'
            }
        
        # If extract request but no specific document, try to find one from query
        if is_extract_request and not target_doc_id:
            # Try to find document from query text
            for doc_id in indexed_doc_ids:
                doc_id_normalized = doc_id.lower().replace("[", "").replace("]", "").replace(",", "").replace("_", "").replace("-", "").replace(" ", "")
                message_normalized = message_lower.replace("[", "").replace("]", "").replace(",", "").replace("_", "").replace("-", "").replace(" ", "")
                
                if doc_id_normalized in message_normalized or message_normalized in doc_id_normalized:
                    full_content = extract_full_document(doc_id)
                    return {
                        'response': f"**Full Document: {doc_id}**\n\n{full_content}",
                        'status': 'success'
                    }
            
            # If still no match, return error
            return {
                'response': 'Please specify which document to extract. You can select a document from the dropdown or mention the document name in your query.',
                'status': 'error'
            }
        
        # For all other queries, use the normal RAG system (chunk-based retrieval)
        # Check if we have indexed documents to query
        if not indexed_doc_ids:
            # Check if a document was selected but not indexed
            if target_doc_id:
                return {
                    'response': f'Document "{target_doc_id}" is not indexed in Supabase. Please index it first before querying. You can use "extract entire doc" or "extract all doc" to view the full document without indexing.',
                    'status': 'error'
                }
            else:
                return {
                    'response': 'No indexed documents available for querying. Please ensure documents are indexed in Supabase.',
                    'status': 'error'
                }
        
        # Create provider and query
        try:
            provider = QwenProvider()
        except Exception as e:
            return {
                'response': f'Error: Could not initialize LLM provider. Please check your API key in .env file.\n\nError: {str(e)}',
                'status': 'error'
            }
        
        # Query only markdown documents using RAG (chunk-based retrieval)
        # Use Supabase only - no local storage fallback
        try:
            if not SUPABASE_AVAILABLE:
                return {
                    'response': 'Supabase is not configured. Please configure SUPABASE_URL and SUPABASE_KEY in your .env file.',
                    'status': 'error'
                }
            
            # Determine which documents to query
            import logging
            logger = logging.getLogger(__name__)
            logger.info("="*80)
            logger.info("[GDD SERVICE] Starting retrieval")
            logger.info(f"[GDD SERVICE] Query: {query}")
            logger.info(f"[GDD SERVICE] target_doc_id (from @ syntax or dropdown): {target_doc_id}")
            logger.info(f"[GDD SERVICE] indexed_doc_ids (all available): {indexed_doc_ids[:5]}... (total: {len(indexed_doc_ids)})")
            
            # If target_doc_id is specified, use only that document
            if target_doc_id:
                logger.info(f"[GDD SERVICE] ✓ Using only target_doc_id: {target_doc_id}")
                doc_ids_to_query = [target_doc_id]
            else:
                logger.info(f"[GDD SERVICE] Using all indexed_doc_ids: {len(indexed_doc_ids)} documents")
                doc_ids_to_query = indexed_doc_ids
            
            logger.info(f"[GDD SERVICE] Final doc_ids_to_query: {doc_ids_to_query}")
            logger.info("="*80)
            
            # Enhanced retrieval with HYDE and section targeting
            markdown_chunks, retrieval_metrics = get_gdd_top_chunks_supabase(
                doc_ids=doc_ids_to_query,
                question=query,
                provider=provider,
                top_k=6,
                per_doc_limit=2,
                use_hyde=True,  # Enable HYDE query expansion
            )
            
            logger.info(f"[GDD Query] Retrieved {len(markdown_chunks)} chunks")
            logger.info(f"[GDD Query] Retrieval metrics: {retrieval_metrics.get('timing', {})}")
            if markdown_chunks:
                logger.info(f"[GDD Query] Chunk doc_ids: {[c.get('doc_id') for c in markdown_chunks]}")
                logger.info(f"[GDD Query] Section distribution: {retrieval_metrics.get('section_distribution', {})}")
            
            # Validate chunks belong to requested documents
            valid_chunks = []
            for chunk in markdown_chunks:
                chunk_doc_id = chunk.get('doc_id', '')
                if chunk_doc_id in doc_ids_to_query:
                    valid_chunks.append(chunk)
                else:
                    logger.warning(f"[GDD Query] WARNING: Chunk from doc_id '{chunk_doc_id}' not in requested list {doc_ids_to_query}. Filtering out.")
            
            markdown_chunks = valid_chunks
            logger.info(f"[GDD Query] After validation: {len(markdown_chunks)} valid chunks")
            
            # Generate answer from markdown chunks using LLM with enhanced section information
            if markdown_chunks:
                selected_chunks = _select_chunks_for_answer(markdown_chunks)
                
                # Detect language from retrieval metrics or fallback to detection function
                detected_language = None
                if retrieval_metrics and 'language_detection' in retrieval_metrics:
                    lang_info = retrieval_metrics.get('language_detection', {})
                    detected_language = lang_info.get('detected_language', None)
                
                # Fallback to language detection function if not in metrics
                if not detected_language:
                    detected_language = _detect_question_language(query)
                    # Convert to 'en' or 'vi' format to match retrieval metrics
                    if detected_language == 'english':
                        detected_language = 'en'
                    elif detected_language == 'vietnamese':
                        detected_language = 'vi'
                
                # Determine response language instruction
                if detected_language == 'vi' or detected_language == 'vietnamese':
                    language_instruction = "IMPORTANT: Respond in Vietnamese (Tiếng Việt). Your entire answer must be in Vietnamese."
                else:
                    language_instruction = "IMPORTANT: Respond in English. Your entire answer must be in English."
                
                # Enhanced prompt with section information
                chunk_texts_with_sections = []
                for i, chunk in enumerate(selected_chunks):
                    section_info = ""
                    if chunk.get('numbered_header'):
                        section_info = f" [Section: {chunk.get('numbered_header')}]"
                    elif chunk.get('section_path'):
                        section_info = f" [Section: {chunk.get('section_path')}]"
                    
                    chunk_texts_with_sections.append(
                        f"[Chunk {i+1} from {chunk['doc_id']}{section_info}]\n{chunk['content']}"
                    )
                
                chunk_texts_enhanced = "\n\n".join(chunk_texts_with_sections)
                
                # Use enhanced prompt format with section context and language instruction
                prompt = f"""Based on the following document chunks, answer the question: {query}

{language_instruction}

Chunks:
{chunk_texts_enhanced}

Provide a clear, comprehensive answer based on the chunks above. If chunks reference specific sections (e.g., "4.1 DanhsáchTanks"), mention those section numbers in your answer."""
                answer = provider.llm(prompt)
            else:
                # Detect language for error message
                detected_language = None
                if retrieval_metrics and 'language_detection' in retrieval_metrics:
                    lang_info = retrieval_metrics.get('language_detection', {})
                    detected_language = lang_info.get('detected_language', None)
                
                if not detected_language:
                    detected_language = _detect_question_language(query)
                    if detected_language == 'english':
                        detected_language = 'en'
                    elif detected_language == 'vietnamese':
                        detected_language = 'vi'
                
                if detected_language == 'vi' or detected_language == 'vietnamese':
                    answer = "Không tìm thấy đoạn tài liệu liên quan trong các tài liệu markdown."
                else:
                    answer = "No relevant chunks found in markdown documents."
            
            return {
                'response': answer,
                'status': 'success'
            }
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "API key" in error_msg or "authentication" in error_msg.lower():
                return {
                    'response': f'API Key Error: Please check your Qwen/DashScope API key in the .env file.\n\nFound {len(indexed_doc_ids)} indexed markdown documents ready to query once API key is configured.\n\nError details: {error_msg}',
                    'status': 'error'
                }
            else:
                return {
                    'response': f'Error querying documents: {error_msg}',
                    'status': 'error'
                }
        
    except Exception as e:
        return {
            'response': f'Error: {str(e)}',
            'status': 'error'
        }
