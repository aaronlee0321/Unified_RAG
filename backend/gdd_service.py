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
    print("ERROR: Supabase storage not available. This app requires Supabase to function.")

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
    
    # Define directory paths (but don't create them - not needed for Render)
    DEFAULT_DOCS_DIR = PROJECT_ROOT / "docs"
    DEFAULT_WORKING_DIR = PROJECT_ROOT / "rag_storage"
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
    
    If markdown_content is not stored, reconstructs document from chunks.
    Falls back to reading from markdown file if available.
    
    Args:
        doc_id: Document ID
    
    Returns:
        Full document content as string, or error message if not found
    """
    if not SUPABASE_AVAILABLE:
        return f"Error: Supabase is not available. Cannot extract document '{doc_id}'."
    
    try:
        from backend.storage.supabase_client import get_gdd_document_markdown, get_gdd_document_pdf_url, get_supabase_client
        import logging
        logger = logging.getLogger(__name__)
        
        # PRIORITY 1: Check if PDF exists in Supabase Storage - if yes, return PDF embed
        try:
            pdf_url = get_gdd_document_pdf_url(doc_id)
            if pdf_url:
                logger.info(f"[Extract Full Doc] Returning PDF URL for {doc_id}")
                return f'**PDF Document: {doc_id}**\n\n[📄 View PDF]({pdf_url})\n\n<iframe src="{pdf_url}" width="100%" height="800px" style="border: 1px solid #ccc;"></iframe>'
        except Exception as e:
            logger.debug(f"[Extract Full Doc] PDF URL check failed: {e}")
        
        # PRIORITY 2: Try to get markdown content directly from gdd_documents table
        try:
            client = get_supabase_client()
            doc_result = client.table('gdd_documents').select('markdown_content, file_path').eq('doc_id', doc_id).limit(1).execute()
            
            if doc_result.data:
                doc = doc_result.data[0]
                markdown_content = doc.get('markdown_content')
                file_path = doc.get('file_path', '')
                
                if markdown_content:
                    logger.info(f"[Extract Full Doc] Returning markdown_content for {doc_id}")
                    return markdown_content
                
                # PRIORITY 2b: Try reading from file_path if markdown_content not stored
                if file_path:
                    try:
                        md_file = Path(file_path)
                        if md_file.exists():
                            content = md_file.read_text(encoding='utf-8')
                            logger.info(f"[Extract Full Doc] Read from file_path for {doc_id}")
                            return content
                    except Exception as e:
                        logger.debug(f"[Extract Full Doc] Failed to read from file_path: {e}")
        except Exception as e:
            logger.debug(f"[Extract Full Doc] Error getting markdown_content: {e}")
        
        # PRIORITY 3 (Fallback): Reconstruct document from chunks if markdown_content not stored
        try:
            client = get_supabase_client()
            
            # First check if document exists
            doc_result = client.table('gdd_documents').select('doc_id, file_path').eq('doc_id', doc_id).limit(1).execute()
            if not doc_result.data:
                # Last resort: try to find markdown file by doc_id
                markdown_dir = PROJECT_ROOT / "gdd_data" / "markdown"
                if markdown_dir.exists():
                    for md_file in markdown_dir.glob("*.md"):
                        if generate_md_doc_id(md_file) == doc_id:
                            try:
                                content = md_file.read_text(encoding='utf-8')
                                logger.info(f"[Extract Full Doc] Found and read markdown file for {doc_id}")
                                return content
                            except Exception as e:
                                logger.debug(f"[Extract Full Doc] Failed to read markdown file: {e}")
                
                return f"Error: Document '{doc_id}' not found in Supabase."
            
            # Get all chunks for this document, ordered by chunk_id
            result = client.table('gdd_chunks').select('content, chunk_id, section_path, metadata').eq('doc_id', doc_id).order('chunk_id').execute()
            
            if not result.data:
                # Try reading from file_path as last resort
                file_path = doc_result.data[0].get('file_path', '')
                if file_path:
                    try:
                        md_file = Path(file_path)
                        if md_file.exists():
                            content = md_file.read_text(encoding='utf-8')
                            logger.info(f"[Extract Full Doc] Read from file_path (no chunks) for {doc_id}")
                            return content
                    except Exception as e:
                        logger.debug(f"[Extract Full Doc] Failed to read from file_path: {e}")
                
                return f"Error: Document '{doc_id}' exists in Supabase but has no chunks and no markdown_content. Please re-index the document."
            
            # Reconstruct document from chunks
            # Group by section and combine content
            sections = {}
            for chunk in result.data:
                section_path = chunk.get('section_path', 'Unknown')
                content = chunk.get('content', '')
                
                if section_path not in sections:
                    sections[section_path] = []
                sections[section_path].append(content)
            
            # Build document
            doc_parts = []
            for section_path, contents in sorted(sections.items()):
                if section_path and section_path != 'Unknown':
                    doc_parts.append(f"## {section_path}\n")
                doc_parts.append('\n\n'.join(contents))
                doc_parts.append('\n\n')
            
            reconstructed = ''.join(doc_parts).strip()
            
            if reconstructed:
                logger.info(f"[Extract Full Doc] Reconstructed from chunks for {doc_id}")
                return reconstructed
            else:
                return f"Error: Document '{doc_id}' found but has no content in chunks."
                
        except Exception as e:
            logger.error(f"Error reconstructing document from chunks: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return f"Error: Document '{doc_id}' not found in Supabase or has no markdown content stored. Reconstruction from chunks also failed: {str(e)}"
            
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error reading document '{doc_id}' from Supabase: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
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
    Upload and index a PDF document using the complete Supabase pipeline.
    
    Workflow:
    1. Convert PDF → Markdown using Docling
    2. Upload PDF to Supabase Storage (gdd_pdfs bucket)
    3. Generate doc_id from filename
    4. Chunk the Markdown with MarkdownChunker
    5. Generate embeddings using QwenProvider
    6. Index chunks with embeddings to Supabase
    7. Store document metadata with pdf_storage_path and markdown_content
    
    Args:
        file_path: Path to the uploaded PDF file
    
    Returns:
        dict: Status and document ID
    """
    try:
        if file_path.suffix.lower() != ".pdf":
            return {
                'status': 'error',
                'message': 'Only PDF files are supported for upload in this version.'
            }
        
        if not SUPABASE_AVAILABLE:
            return {
                'status': 'error',
                'message': 'Supabase is not configured. Cannot index documents without Supabase.'
            }
        
        import tempfile
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"Starting upload and indexing for: {file_path.name}")
        
        # 1. Convert PDF → Markdown using Docling
        logger.info("Step 1: Converting PDF to Markdown...")
        try:
            from docling.document_converter import DocumentConverter
            from PDFtoMarkdown.pdf_to_markdown import clean_markdown
            
            converter = DocumentConverter()
            
            # Convert PDF to Markdown
            result = converter.convert(str(file_path))
            markdown_content = result.document.export_to_markdown()
            markdown_content = clean_markdown(markdown_content)
            
            logger.info(f"✅ Converted PDF to Markdown ({len(markdown_content)} characters)")
        except Exception as e:
            logger.error(f"❌ PDF conversion failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'Error converting PDF to Markdown: {str(e)}'
            }
        
        # 2. Generate doc_id from PDF filename
        doc_id = generate_md_doc_id(file_path)
        logger.info(f"Generated doc_id: {doc_id}")
        
        # 3. Sanitize PDF filename for storage (remove special chars, keep safe)
        from werkzeug.utils import secure_filename
        pdf_filename = secure_filename(file_path.name)
        # Replace spaces with underscores for consistency
        pdf_filename = pdf_filename.replace(' ', '_')
        
        # 4. Upload PDF to Supabase Storage
        logger.info(f"Step 2: Uploading PDF to Supabase Storage as '{pdf_filename}'...")
        try:
            from backend.storage.supabase_client import upload_pdf_to_storage
            upload_success = upload_pdf_to_storage(file_path, pdf_filename)
            if not upload_success:
                return {
                    'status': 'error',
                    'message': 'Failed to upload PDF to Supabase Storage.'
                }
            logger.info("✅ PDF uploaded to Supabase Storage")
        except Exception as e:
            logger.error(f"❌ PDF upload failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'Error uploading PDF to storage: {str(e)}'
            }
        
        # 5. Chunk the markdown
        logger.info("Step 3: Chunking Markdown...")
        try:
            chunker = MarkdownChunker()
            chunks = chunker.chunk_document(
                markdown_content=markdown_content,
                doc_id=doc_id,
                filename=file_path.name,
            )
            logger.info(f"✅ Created {len(chunks)} chunks")
        except Exception as e:
            logger.error(f"❌ Chunking failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'Error chunking document: {str(e)}'
            }
        
        # 6. Index chunks to Supabase with embeddings
        logger.info("Step 4: Generating embeddings and indexing to Supabase...")
        try:
            provider = QwenProvider()
            index_gdd_chunks_to_supabase(
                doc_id=doc_id,
                chunks=chunks,
                provider=provider,
                markdown_content=markdown_content,  # Store full markdown
                pdf_storage_path=pdf_filename  # Store PDF storage path
            )
            logger.info("✅ Indexed to Supabase")
        except Exception as e:
            logger.error(f"❌ Indexing failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'status': 'error',
                'message': f'Error indexing to Supabase: {str(e)}'
            }
        
        logger.info(f"✅ Successfully processed: {file_path.name} (doc_id: {doc_id})")
        return {
            'status': 'success',
            'message': f'Successfully uploaded, converted, chunked, and indexed: {file_path.name} (as {doc_id})',
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
    
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        from backend.storage.supabase_client import get_supabase_client
        client = get_supabase_client()
        
        logger.info(f"[get_document_sections] Querying chunks for doc_id: {doc_id}")
        
        # Get all unique sections for this document
        result = client.table('gdd_chunks').select(
            'section_path, section_title, metadata'
        ).eq('doc_id', doc_id).execute()
        
        raw_chunks = result.data or []
        logger.info(f"[get_document_sections] Found {len(raw_chunks)} chunks for doc_id: {doc_id}")
        
        if len(raw_chunks) == 0:
            # Try to find similar doc_ids (case-insensitive, fuzzy matching)
            logger.warning(f"[get_document_sections] No chunks found for exact doc_id: {doc_id}")
            logger.info(f"[get_document_sections] Attempting to find similar doc_ids...")
            
            # Get all unique doc_ids from chunks
            all_doc_ids_result = client.table('gdd_chunks').select('doc_id').execute()
            all_doc_ids = set()
            for row in (all_doc_ids_result.data or []):
                all_doc_ids.add(row.get('doc_id'))
            
            logger.info(f"[get_document_sections] Found {len(all_doc_ids)} unique doc_ids in database")
            
            # Try case-insensitive match
            all_doc_ids_lower = {d.lower(): d for d in all_doc_ids}
            doc_id_lower = doc_id.lower()
            
            if doc_id_lower in all_doc_ids_lower:
                actual_doc_id = all_doc_ids_lower[doc_id_lower]
                logger.info(f"[get_document_sections] Found case-insensitive match: {actual_doc_id}")
                # Retry with actual doc_id
                result = client.table('gdd_chunks').select(
                    'section_path, section_title, metadata'
                ).eq('doc_id', actual_doc_id).execute()
                raw_chunks = result.data or []
                logger.info(f"[get_document_sections] Found {len(raw_chunks)} chunks with corrected doc_id")
            else:
                # Try fuzzy matching
                def normalize_for_match(text):
                    """Normalize text for fuzzy matching."""
                    if not text:
                        return ""
                    return text.lower().replace('_', '').replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
                
                doc_id_normalized = normalize_for_match(doc_id)
                similar_doc_ids = []
                
                for existing_doc_id in all_doc_ids:
                    existing_normalized = normalize_for_match(existing_doc_id)
                    if doc_id_normalized == existing_normalized:
                        similar_doc_ids.append(existing_doc_id)
                    elif doc_id_normalized in existing_normalized or existing_normalized in doc_id_normalized:
                        similar_doc_ids.append(existing_doc_id)
                
                if similar_doc_ids:
                    logger.info(f"[get_document_sections] Found {len(similar_doc_ids)} similar doc_ids: {similar_doc_ids[:3]}")
                    # Use the first similar one
                    actual_doc_id = similar_doc_ids[0]
                    logger.info(f"[get_document_sections] Using similar doc_id: {actual_doc_id}")
                    result = client.table('gdd_chunks').select(
                        'section_path, section_title, metadata'
                    ).eq('doc_id', actual_doc_id).execute()
                    raw_chunks = result.data or []
                    logger.info(f"[get_document_sections] Found {len(raw_chunks)} chunks with similar doc_id")
                else:
                    logger.warning(f"[get_document_sections] No similar doc_ids found. Available doc_ids (sample): {list(all_doc_ids)[:5]}")
        
        sections_map = {}
        
        for row in raw_chunks:
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
            
            # If no section info at all, create a default section entry
            if not key:
                # Check if we should skip or create a default section
                # For now, we'll create a default "Document Content" section
                # This ensures documents with chunks but no sections still show up
                key = "Document Content"
                numbered_header = "Document Content"
                section_path = ""
                section_index = 999
                logger.debug(f"[get_document_sections] Chunk has no section info, using default section")
            
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
        
        logger.info(f"[get_document_sections] Returning {len(sections)} unique sections for doc_id: {doc_id}")
        
        return sections
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting sections for document {doc_id}: {e}")
        import traceback
        logger.error(traceback.format_exc())
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
            # Also handle cases where selected_doc might just be the doc_id or filename
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
                
                # Try exact match first
                if display_name == selected_doc:
                    target_doc_id = doc_id
                    break
                
                # Try matching without the suffix (for backward compatibility)
                display_name_no_suffix = display_name.split(" - ")[0]
                if display_name_no_suffix == selected_doc:
                    target_doc_id = doc_id
                    break
                
                # Try matching just the doc_id
                if doc_id == selected_doc:
                    target_doc_id = doc_id
                    break
                
                # Try matching filename
                if file_path:
                    file_name = Path(file_path).name
                    if file_name == selected_doc or file_name in selected_doc:
                        target_doc_id = doc_id
                        break
                
                # Try fuzzy matching (normalize both strings)
                def normalize_for_match(text: str) -> str:
                    """Normalize text for fuzzy matching."""
                    if not text:
                        return ""
                    normalized = text.lower()
                    normalized = normalized.replace("[", "").replace("]", "")
                    normalized = normalized.replace(",", "").replace("_", "")
                    normalized = normalized.replace("-", "").replace(" ", "")
                    normalized = normalized.replace("(", "").replace(")", "")
                    return normalized
                
                selected_normalized = normalize_for_match(selected_doc)
                doc_id_normalized = normalize_for_match(doc_id)
                display_normalized = normalize_for_match(display_name)
                display_no_suffix_normalized = normalize_for_match(display_name_no_suffix)
                
                if (doc_id_normalized in selected_normalized or 
                    selected_normalized in doc_id_normalized or
                    display_normalized == selected_normalized or
                    display_no_suffix_normalized == selected_normalized):
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
                
                # Normalize for comparison (remove special chars, keep core words)
                def normalize_for_match(text: str) -> str:
                    """Normalize text for fuzzy matching."""
                    if not text:
                        return ""
                    normalized = text.lower()
                    # Remove all special characters
                    normalized = normalized.replace("[", "").replace("]", "")
                    normalized = normalized.replace(",", "").replace("_", "")
                    normalized = normalized.replace("-", "").replace(" ", "")
                    normalized = normalized.replace("(", "").replace(")", "")
                    normalized = normalized.replace("&", "").replace(".", "")
                    return normalized
                
                doc_id_normalized = normalize_for_match(doc_id)
                message_normalized = normalize_for_match(message_lower)
                
                # Strategy 1: Check if doc_id appears in message (exact or partial)
                if doc_id_normalized in message_normalized or message_normalized in doc_id_normalized:
                    target_doc_id = doc_id
                    break
                
                # Strategy 1b: Check if key words from doc_id appear in message
                # Extract key words (remove common prefixes like "module", "tank", "war")
                # Split by removing underscores and common words
                doc_parts = doc_id_normalized.replace('_', ' ').split()
                doc_words = [w for w in doc_parts if len(w) > 3 and w not in ['module', 'tank', 'war', 'system', 'design', 'progression', 'monetization', 'character', 'combat', 'game', 'multiplayer', 'world']]
                if doc_words:
                    # Check if at least 2 key words match, or if a unique word matches
                    matching_words = sum(1 for word in doc_words if word in message_normalized)
                    unique_words = [w for w in doc_words if w in ['localization', 'latam', 'tổng', 'quan', 'artifact', 'onboarding', 'chưa', 'xong', 'elo', 'rank', 'leaderboard', 'elemental', 'class']]
                    if matching_words >= 2 or (unique_words and any(w in message_normalized for w in unique_words)):
                        target_doc_id = doc_id
                        break
                
                # Strategy 1c: Check if message contains partial doc_id (e.g., "localization_latam" matches full doc_id)
                # Remove common prefixes and check if remaining parts match
                message_clean = message_normalized
                for prefix in ['progression', 'module', 'tank', 'war', 'monetization', 'character', 'combat']:
                    message_clean = message_clean.replace(prefix, '')
                doc_clean = doc_id_normalized
                for prefix in ['progression', 'module', 'tank', 'war', 'monetization', 'character', 'combat']:
                    doc_clean = doc_clean.replace(prefix, '')
                
                if message_clean and doc_clean:
                    if message_clean in doc_clean or doc_clean in message_clean:
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
