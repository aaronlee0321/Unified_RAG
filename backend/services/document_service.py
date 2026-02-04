"""
Document service for uploading and indexing documents.
EXACT COPY from keyword_extractor - adapted for unified_rag_app.
"""

import json
import os
import re
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from backend.services.embedding_service import embed_document_chunks
from backend.shared.config import CHUNK_SIZE
from backend.storage.keyword_storage import insert_chunks, insert_document
from backend.utils.text_utils import normalize_spacing, split_by_sections


# Debug logging helper
def _debug_log(location: str, message: str, data: dict, hypothesis_id: str = ""):
    """Write debug log entry."""
    log_path = r"c:\Users\CPU12391\Desktop\unified_rag_app\.cursor\debug.log"
    entry = {
        "sessionId": "debug-session",
        "runId": "run1",
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "timestamp": __import__("time").time() * 1000,
        **data,
    }
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


# Control characters to clean from markdown
_CONTROL_CHARS = {
    *[c for c in map(chr, range(0x00, 0x20)) if c not in ("\t", "\n", "\r")],
    chr(0x7F),
    "\ufffd",  # Replacement character
}
_CONTROL_TRANSLATION = {ord(c): None for c in _CONTROL_CHARS}


def clean_markdown(text: str) -> str:
    """Remove non-printable/control artifacts while preserving content & layout."""
    cleaned = text.translate(_CONTROL_TRANSLATION)
    return cleaned.encode("utf-8", "ignore").decode("utf-8")


def pdf_to_markdown(pdf_bytes: bytes) -> str:
    """
    Convert PDF bytes to markdown using Docling.
    Preserves structure and headings for better section detection.

    Args:
        pdf_bytes: PDF file bytes

    Returns:
        Markdown text with preserved structure
    """
    try:
        from docling.document_converter import DocumentConverter

        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(pdf_bytes)
            tmp_path = tmp_file.name

        try:
            # Convert to markdown
            converter = DocumentConverter()

            # #region agent log
            _debug_log(
                "document_service.py:72",
                "Before Docling convert",
                {
                    "pdf_size_bytes": len(pdf_bytes),
                    "temp_path": tmp_path,
                },
                "A",
            )
            # #endregion

            result = converter.convert(tmp_path)

            # #region agent log
            # Check document structure before export
            doc = result.document
            _debug_log(
                "document_service.py:79",
                "After Docling convert, before export",
                {
                    "has_document": doc is not None,
                    "document_type": type(doc).__name__ if doc else None,
                },
                "A",
            )
            # #endregion

            markdown_raw = result.document.export_to_markdown()

            # #region agent log
            # More detailed spacing analysis
            sample = markdown_raw[:500] if markdown_raw else ""
            space_count = sample.count(" ") if sample else 0
            newline_count = sample.count("\n") if sample else 0
            # Check for ASCII 1 (0x01) being used as space character by Docling
            ascii1_count = sample.count("\x01") if sample else 0

            _debug_log(
                "document_service.py:96",
                "After Docling export_to_markdown (RAW OUTPUT)",
                {
                    "sample": sample,
                    "sample_length": len(sample),
                    "has_spaces": " " in sample,
                    "space_count_in_sample": space_count,
                    "ascii1_count_in_sample": ascii1_count,
                    "newline_count_in_sample": newline_count,
                    "sample_repr": repr(sample[:100]),  # Show exact characters
                },
                "A",
            )
            # #endregion

            # CRITICAL FIX: Docling uses ASCII 1 (0x01) as space characters instead of actual spaces
            # Replace \x01 with actual space BEFORE clean_markdown removes it
            markdown_raw = markdown_raw.replace("\x01", " ")

            # #region agent log
            _debug_log(
                "document_service.py:118",
                "After replacing \\x01 with spaces",
                {
                    "sample": markdown_raw[:300] if markdown_raw else "",
                    "space_count": markdown_raw[:500].count(" ") if markdown_raw else 0,
                },
                "A",
            )
            # #endregion

            markdown_cleaned = clean_markdown(markdown_raw)

            # #region agent log
            sample_clean = markdown_cleaned[:500] if markdown_cleaned else ""
            space_count_clean = sample_clean.count(" ") if sample_clean else 0
            _debug_log(
                "document_service.py:109",
                "After clean_markdown",
                {
                    "sample": sample_clean,
                    "has_spaces": " " in sample_clean,
                    "space_count": space_count_clean,
                    "changed_from_raw": markdown_raw[:500] != sample_clean
                    if markdown_raw
                    else False,
                    "sample_repr": repr(sample_clean[:100]),
                },
                "B",
            )
            # #endregion

            # Apply spacing normalization early to fix any spacing issues from Docling
            # This happens BEFORE heading detection, but we'll preserve heading patterns
            markdown_normalized = normalize_spacing(markdown_cleaned)

            # #region agent log
            sample_norm = markdown_normalized[:
                                              500] if markdown_normalized else ""
            space_count_norm = sample_norm.count(" ") if sample_norm else 0
            _debug_log(
                "document_service.py:123",
                "After first normalize_spacing",
                {
                    "sample": sample_norm,
                    "has_spaces": " " in sample_norm,
                    "space_count": space_count_norm,
                    "changed_from_cleaned": markdown_cleaned[:500] != sample_norm
                    if markdown_cleaned
                    else False,
                    "sample_repr": repr(sample_norm[:100]),
                },
                "C",
            )
            # #endregion

            return markdown_normalized
        finally:
            # Clean up temp file
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except ImportError:
        # Fallback to simple text extraction if docling not available
        from PyPDF2 import PdfReader

        pdf_file = BytesIO(pdf_bytes)
        reader = PdfReader(pdf_file)
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text())
        text = "\n\n".join(text_parts)
        # Apply spacing normalization to fallback extraction too
        return normalize_spacing(text)
    except Exception as e:
        # Fallback on any error
        print(f"Warning: Docling conversion failed, using fallback: {e}")
        from PyPDF2 import PdfReader

        pdf_file = BytesIO(pdf_bytes)
        reader = PdfReader(pdf_file)
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text())
        text = "\n\n".join(text_parts)
        # Apply spacing normalization to fallback extraction too
        return normalize_spacing(text)


def generate_doc_id(filename: str) -> str:
    """
    Generate document ID from filename.

    Args:
        filename: Original filename

    Returns:
        Sanitized document ID
    """
    doc_id = Path(filename).stem
    doc_id = doc_id.replace(" ", "_").replace("[", "").replace("]", "")
    doc_id = doc_id.replace("-", "_").replace(",", "_")
    while "__" in doc_id:
        doc_id = doc_id.replace("__", "_")
    return doc_id.strip("_")


def upload_and_index_document(
    pdf_bytes: bytes, filename: str, progress_callback: Optional[Callable[[str], None]] = None
) -> Dict[str, Any]:
    """
    Upload and index a PDF document for keyword search.
    EXACT LOGIC from keyword_extractor.

    Args:
        pdf_bytes: PDF file bytes
        filename: Original filename
        progress_callback: Optional callback for progress updates

    Returns:
        Dict with status, message, doc_id
    """
    try:
        # Step 1: Convert PDF to markdown (preserves structure)
        if progress_callback:
            progress_callback("Converting PDF to markdown...")

        text = pdf_to_markdown(pdf_bytes)

        # #region agent log
        _debug_log(
            "document_service.py:132",
            "Text received from pdf_to_markdown",
            {
                "sample": text[:300] if text else "",
                "has_spaces": " " in (text[:500] if text else ""),
                "concatenated_example": "word1word2" in (text[:500] if text else ""),
            },
            "D",
        )
        # #endregion

        if not text or len(text.strip()) < 10:
            return {"status": "error", "message": "Failed to extract text from PDF or PDF is empty"}

        # Step 2: Generate document ID
        doc_id = generate_doc_id(filename)

        # Step 3: Split into sections first, then chunk each section
        if progress_callback:
            progress_callback(
                "Splitting document into sections, then chunking each section...")

        # First split into sections, then chunk each section using size-based chunking
        chunks_with_headings = split_by_sections(text, chunk_size=CHUNK_SIZE)

        # #region agent log
        if chunks_with_headings:
            first_chunk_sample = (
                chunks_with_headings[0][0][:200] if chunks_with_headings[0][0] else ""
            )
            _debug_log(
                "document_service.py:145",
                "After split_by_sections - first chunk",
                {
                    "sample": first_chunk_sample,
                    "has_spaces": " " in first_chunk_sample,
                    "concatenated_example": "word1word2" in first_chunk_sample,
                    "chunk_count": len(chunks_with_headings),
                },
                "E",
            )
        # #endregion

        if not chunks_with_headings:
            return {"status": "error", "message": "No chunks created from document"}

        # Debug: Log chunk count
        unique_sections = set(h for _, h in chunks_with_headings if h)
        print(
            f"Created {len(chunks_with_headings)} chunks from {len(unique_sections)} unique sections"
        )

        # Step 4: Prepare chunks for database
        if progress_callback:
            progress_callback("Preparing chunks for indexing...")

        chunk_records = []
        for idx, (chunk_text, section_heading) in enumerate(chunks_with_headings):
            # #region agent log
            if idx == 0:  # Log first chunk only
                _debug_log(
                    "document_service.py:159",
                    "Before final cleanup - first chunk",
                    {
                        "sample": chunk_text[:200] if chunk_text else "",
                        "has_spaces": " " in (chunk_text[:500] if chunk_text else ""),
                        "concatenated_example": "word1word2"
                        in (chunk_text[:500] if chunk_text else ""),
                    },
                    "F",
                )
            # #endregion

            # Final spacing cleanup for each chunk to ensure proper spacing for PostgreSQL FTS
            # This is a safety net to catch any remaining spacing issues
            chunk_text_before = chunk_text
            # Normalize all whitespace to single space
            chunk_text = re.sub(r"\s+", " ", chunk_text)
            chunk_text = chunk_text.strip()

            # #region agent log
            if idx == 0:  # Log first chunk only
                _debug_log(
                    "document_service.py:167",
                    "After final cleanup - first chunk",
                    {
                        "sample": chunk_text[:200] if chunk_text else "",
                        "has_spaces": " " in (chunk_text[:500] if chunk_text else ""),
                        "concatenated_example": "word1word2"
                        in (chunk_text[:500] if chunk_text else ""),
                        "changed": chunk_text_before != chunk_text,
                    },
                    "G",
                )
            # #endregion

            chunk_id = f"{doc_id}_{idx}"
            chunk_records.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "content": chunk_text,
                    "section_heading": section_heading,
                    "chunk_index": idx,
                    "metadata": {},
                }
            )

        # Step 5: Upload original PDF to Supabase storage (gdd_pdfs bucket)
        if progress_callback:
            progress_callback("Uploading PDF to storage...")

        try:
            from werkzeug.utils import secure_filename

            from backend.storage.supabase_client import get_supabase_client

            client = get_supabase_client(use_service_key=True)
            bucket_name = "gdd_pdfs"
            pdf_filename = secure_filename(filename).replace(" ", "_")

            client.storage.from_(bucket_name).upload(
                path=pdf_filename,
                file=pdf_bytes,
                file_options={
                    "content-type": "application/pdf",
                    "cache-control": "3600",
                    "upsert": "true",
                },
            )
            pdf_storage_path = pdf_filename  # Store the actual filename used in storage
            print(f"✅ Successfully uploaded PDF to storage: {pdf_filename}")
        except Exception as e:
            # Log error but continue - PDF storage is optional
            print(f"Warning: Failed to upload PDF to storage: {e}")
            import traceback

            traceback.print_exc()
            pdf_storage_path = None

        # Step 6: Store document and chunks
        if progress_callback:
            progress_callback("Storing document and chunks in database...")

        # Store the storage filename (not the original path) so we can retrieve it later
        insert_document(
            doc_id=doc_id,
            name=filename,
            file_path=pdf_storage_path
            or filename,  # Use storage filename if available, otherwise original filename
            file_size=len(pdf_bytes),
            full_text=text,
        )

        chunks_inserted = insert_chunks(doc_id, chunk_records)

        # Step 7: Optional embeddings
        if progress_callback:
            progress_callback("Embedding chunks (optional)...")
        try:
            embedded = embed_document_chunks(doc_id)
        except Exception:
            embedded = 0

        if progress_callback:
            progress_callback("Completed")

        return {
            "status": "success",
            "message": f"Document indexed successfully. {chunks_inserted} chunks created. {embedded} embedded.",
            "doc_id": doc_id,
            "chunks_count": chunks_inserted,
        }

    except Exception as e:
        return {"status": "error", "message": f"Error indexing document: {str(e)}"}
