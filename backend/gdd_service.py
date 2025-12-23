"""
GDD RAG Service
Extracted from gradio_app.py - handles GDD document queries
"""

import os
import sys
import asyncio
import shutil
from pathlib import Path

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
from gdd_rag_backbone.config import DEFAULT_DOCS_DIR, DEFAULT_WORKING_DIR
from gdd_rag_backbone.llm_providers import (
    QwenProvider,
    make_embedding_func,
)
from gdd_rag_backbone.rag_backend.markdown_chunk_qa import (
    get_markdown_top_chunks,
    list_markdown_indexed_docs,
)
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
    Uses Supabase if available, otherwise falls back to local storage.
    
    Returns:
        list: List of document metadata dictionaries
    """
    try:
        if SUPABASE_AVAILABLE:
            # Try Supabase first
            try:
                docs = list_gdd_documents_supabase()
                if docs:
                    print(f"Loaded {len(docs)} documents from Supabase")
                    return docs
                else:
                    print("Warning: Supabase returned empty list, trying local storage")
            except Exception as e:
                import traceback
                print(f"Warning: Failed to load from Supabase, trying local storage: {e}")
                traceback.print_exc()
        
        # Fallback to local storage (only if gdd_rag_backbone is available)
        if not GDD_RAG_BACKBONE_AVAILABLE:
            print("Warning: Cannot fallback to local storage - gdd_rag_backbone not available")
            return []
        
        print("Attempting to load from local storage...")
        markdown_docs = list_markdown_indexed_docs()
        
        documents = []
        for doc in sorted(markdown_docs, key=lambda x: x["doc_id"]):
            doc_id = doc["doc_id"]
            chunks_count = doc.get("chunks_count", 0)
            file_path = doc.get("file_path", "")
            file_name = Path(file_path).name if file_path else doc_id
            
            documents.append({
                'doc_id': doc_id,
                'name': file_name,
                'file_path': file_path,
                'chunks_count': chunks_count,
                'status': 'ready' if chunks_count > 0 else 'indexed'
            })
        
        print(f"Loaded {len(documents)} documents from local storage")
        return documents
    except Exception as e:
        import traceback
        print(f"Error listing documents: {e}")
        traceback.print_exc()
        return []


def get_document_options():
    """
    Get list of document options for dropdown.
    Uses Supabase if available, otherwise falls back to local storage.
    
    Returns:
        list: List of document option strings
    """
    try:
        # Use Supabase if available
        if SUPABASE_AVAILABLE:
            try:
                docs = list_gdd_documents_supabase()
                indexed_docs = [doc for doc in docs if doc.get("chunks_count", 0) > 0]
            except Exception as e:
                print(f"Warning: Failed to load from Supabase: {e}")
                if GDD_RAG_BACKBONE_AVAILABLE:
                    markdown_docs = list_markdown_indexed_docs()
                    indexed_docs = [doc for doc in markdown_docs if doc.get("chunks_count", 0) > 0]
                else:
                    indexed_docs = []
        else:
            if GDD_RAG_BACKBONE_AVAILABLE:
                markdown_docs = list_markdown_indexed_docs()
                indexed_docs = [doc for doc in markdown_docs if doc.get("chunks_count", 0) > 0]
            else:
                indexed_docs = []
        
        options = ["All Documents"]
        for doc in sorted(indexed_docs, key=lambda x: x.get("doc_id", "")):
            doc_id = doc.get("doc_id", "")
            file_path = doc.get("file_path", "")
            name = doc.get("name", "")
            
            if file_path:
                file_name = Path(file_path).name
                display_name = f"{file_name} ({doc_id})"
            elif name:
                display_name = f"{name} ({doc_id})"
            else:
                display_name = doc_id
            
            options.append(display_name)
        
        return options
    except Exception as e:
        print(f"Error getting document options: {e}")
        return ["All Documents"]


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
        
        # Get documents - use Supabase if available
        if SUPABASE_AVAILABLE:
            try:
                markdown_docs = list_gdd_documents_supabase()
            except Exception as e:
                print(f"Warning: Failed to load from Supabase, trying local storage: {e}")
                markdown_docs = list_markdown_indexed_docs()
        else:
            markdown_docs = list_markdown_indexed_docs()
        
        indexed_doc_ids = [doc.get("doc_id", "") for doc in markdown_docs if doc.get("chunks_count", 0) > 0]
        
        if not indexed_doc_ids:
            return {
                'response': 'No indexed markdown documents found. Please upload and index documents first.',
                'status': 'error'
            }
        
        # Handle document selection from dropdown
        target_doc_id = None
        if selected_doc and selected_doc != "All Documents":
            # Extract doc_id from selected_doc (format: "filename (doc_id)" or "name (doc_id)")
            for doc in markdown_docs:
                doc_id = doc.get("doc_id", "")
                file_path = doc.get("file_path", "")
                name = doc.get("name", "")
                
                # Try different display name formats
                if file_path:
                    file_name = Path(file_path).name
                    display_name = f"{file_name} ({doc_id})"
                elif name:
                    display_name = f"{name} ({doc_id})"
                else:
                    display_name = doc_id
                
                if display_name == selected_doc:
                    target_doc_id = doc_id
                    break
            
            if target_doc_id and target_doc_id in indexed_doc_ids:
                indexed_doc_ids = [target_doc_id]
        
        # Handle special queries
        message_lower = query.lower().strip()
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
            for doc_id in indexed_doc_ids:
                doc_id_normalized = doc_id.lower().replace("[", "").replace("]", "").replace(",", "").replace("_", "").replace("-", "").replace(" ", "")
                message_normalized = message_lower.replace("[", "").replace("]", "").replace(",", "").replace("_", "").replace("-", "").replace(" ", "")
                
                # Check if doc_id appears in message
                if doc_id_normalized in message_normalized or message_normalized in doc_id_normalized:
                    target_doc_id = doc_id
                    break
                
                # Also check file path
                file_path = markdown_status.get(doc_id, {}).get("file_path", "").lower()
                if file_path:
                    file_normalized = Path(file_path).stem.lower().replace("_", "").replace("-", "").replace(" ", "")
                    if file_normalized in message_normalized or any(word in file_normalized for word in message_normalized.split() if len(word) > 4):
                        target_doc_id = doc_id
                        break
        
        # If specific document found, query only that document
        if target_doc_id:
            indexed_doc_ids = [target_doc_id]
        
        # Create provider and query
        try:
            provider = QwenProvider()
        except Exception as e:
            return {
                'response': f'Error: Could not initialize LLM provider. Please check your API key in .env file.\n\nError: {str(e)}',
                'status': 'error'
            }
        
        # Query only markdown documents
        try:
            # Use Supabase if available, otherwise local storage
            if SUPABASE_AVAILABLE:
                try:
                    markdown_chunks = get_gdd_top_chunks_supabase(
                        doc_ids=indexed_doc_ids,
                        question=query,
                        provider=provider,
                        top_k=6,
                        per_doc_limit=2,
                    )
                except Exception as e:
                    print(f"Warning: Supabase query failed, falling back to local storage: {e}")
                    markdown_chunks = get_markdown_top_chunks(
                        doc_ids=indexed_doc_ids,
                        question=query,
                        provider=provider,
                        top_k=6,
                        per_doc_limit=2,
                    )
            else:
                # Use local storage
                markdown_chunks = get_markdown_top_chunks(
                    doc_ids=indexed_doc_ids,
                    question=query,
                    provider=provider,
                    top_k=6,
                    per_doc_limit=2,
                )
            
            # Generate answer from markdown chunks using LLM
            if markdown_chunks:
                selected_chunks = _select_chunks_for_answer(markdown_chunks)
                chunk_texts = "\n\n".join(
                    f"[Chunk {i+1} from {chunk['doc_id']}]\n{chunk['content']}"
                    for i, chunk in enumerate(selected_chunks)
                )
                
                # Detect question language and instruct LLM to respond in same language
                question_lang = _detect_question_language(query)
                language_instruction = "Vietnamese" if question_lang == 'vietnamese' else "English"
                
                prompt = f"""Based on the following document chunks, answer the question: {query}

Chunks:
{chunk_texts}

IMPORTANT: Please respond in {language_instruction} language. Match the language of the question exactly. Provide a clear, comprehensive answer based on the chunks above."""
                answer = provider.llm(prompt)
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
