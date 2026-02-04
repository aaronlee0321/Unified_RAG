"""
Document indexing functionality using RAG-Anything.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Union

from gdd_rag_backbone.config import DEFAULT_OUTPUT_DIR, DEFAULT_WORKING_DIR
from gdd_rag_backbone.rag_backend.rag_config import get_rag_instance

# Global registry to store RAG instances per doc_id
_rag_instances: dict[str, object] = {}


async def index_document(
    doc_path: Union[str, Path],
    doc_id: str,
    *,
    llm_func: Optional[Callable] = None,
    embedding_func: Optional[Callable] = None,
    working_dir: Optional[Union[Path, str]] = None,
    output_dir: Optional[Union[Path, str]] = None,
    parser: Optional[str] = None,
    parse_method: Optional[str] = None,
    **parser_kwargs,
) -> None:
    """
    Index a document using RAG-Anything.

    This function parses, chunks, embeds, and indexes the document,
    storing the results in the specified output directory.

    Args:
        doc_path: Path to the document file (PDF, DOCX, etc.)
        doc_id: Unique identifier for the document
        llm_func: Optional LLM function for RAG (required for querying later)
        embedding_func: Optional embedding function (required for indexing and querying)
        working_dir: Working directory for RAG storage (defaults to DEFAULT_WORKING_DIR)
        output_dir: Output directory for parsed content (defaults to DEFAULT_OUTPUT_DIR/{doc_id})
        parser: Parser choice - "mineru" or "docling" (defaults to config default)
        parse_method: Parse method - "auto", "layout", "ocr", etc. (defaults to config default)
        **parser_kwargs: Additional parser parameters (lang, device, start_page, end_page, etc.)

    Raises:
        FileNotFoundError: If doc_path does not exist
        ValueError: If doc_id is empty
    """
    doc_path = Path(doc_path)

    if not doc_path.exists():
        raise FileNotFoundError(f"Document not found: {doc_path}")

    if not doc_id:
        raise ValueError("doc_id cannot be empty")

    # Set up output directory
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR / doc_id
    elif isinstance(output_dir, str):
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Create or get RAG instance for this document
    # Use the same working_dir to ensure we can query it later
    # Use doc_id as workspace to isolate each document's data
    if working_dir is None:
        working_dir = DEFAULT_WORKING_DIR

    rag = get_rag_instance(
        llm_func=llm_func,
        embedding_func=embedding_func,
        working_dir=working_dir,
        workspace=doc_id,  # Isolate each document in its own workspace
        parser=parser,
        parse_method=parse_method,
    )

    # Store the instance for later querying
    _rag_instances[doc_id] = rag

    # Process the document completely (parse, chunk, embed, index)
    print(f"Indexing document {doc_id} from {doc_path}...")

    await rag.process_document_complete(
        file_path=str(doc_path.absolute()),
        output_dir=str(output_dir.absolute()),
        parse_method=parse_method,
        doc_id=doc_id,
        **parser_kwargs,
    )

    # Save document status to global status file so it appears in the document list
    # With workspace isolation, status is stored per-workspace, but we need it in the global file
    _save_document_status(doc_id, doc_path, working_dir)

    print(f"Document {doc_id} indexed successfully. Output: {output_dir}")


def get_rag_instance_for_doc(doc_id: str) -> Optional[object]:
    """
    Get the RAG instance for a specific document ID.

    Args:
        doc_id: Document ID

    Returns:
        RAGAnything instance if found, None otherwise
    """
    return _rag_instances.get(doc_id)


def clear_rag_instance(doc_id: str) -> None:
    """
    Clear a RAG instance from the registry.

    Args:
        doc_id: Document ID
    """
    if doc_id in _rag_instances:
        del _rag_instances[doc_id]


def _save_document_status(doc_id: str, doc_path: Path, working_dir: Path) -> None:
    """
    Save document status to the global status file so it appears in the document list.

    This is needed because with workspace isolation, LightRAG stores status per-workspace,
    but the frontend reads from a global status file.

    Args:
        doc_id: Document ID (also used as workspace name)
        doc_path: Path to the document file
        working_dir: Working directory where status file is stored
    """
    global_status_path = working_dir / "kv_store_doc_status.json"
    workspace_status_path = working_dir / doc_id / "kv_store_doc_status.json"

    # Load existing global status or create empty dict
    # IMPORTANT: Always preserve existing data - never overwrite with empty dict
    if global_status_path.exists():
        try:
            content = global_status_path.read_text(encoding="utf-8")
            if content.strip():  # Only parse if file has content
                global_status_data = json.loads(content)
                # Ensure it's a dict (not a list or other type)
                if not isinstance(global_status_data, dict):
                    print("Warning: Global status file is not a dict, creating new dict")
                    global_status_data = {}
            else:
                # Empty file - start with empty dict but preserve any existing entries
                global_status_data = {}
        except json.JSONDecodeError as e:
            print(f"Warning: Could not parse global status file (JSON error): {e}")
            # Try to preserve existing data by reading as text and attempting recovery
            try:
                content = global_status_path.read_text(encoding="utf-8")
                # If file has some content but is malformed, log it
                print(f"File content (first 200 chars): {content[:200]}")
            except Exception:
                pass
            global_status_data = {}
        except Exception as e:
            print(f"Warning: Could not read global status file: {e}")
            global_status_data = {}
    else:
        global_status_data = {}

    # Try to read from workspace-specific doc_status (where LightRAG actually stores it)
    chunks_count = 0
    chunks_list = []
    file_name = doc_path.name
    created_at = datetime.now(timezone.utc).isoformat()
    updated_at = created_at

    if workspace_status_path.exists():
        try:
            workspace_data = json.loads(workspace_status_path.read_text())
            if doc_id in workspace_data:
                ws_meta = workspace_data[doc_id]
                chunks_count = ws_meta.get("chunks_count", 0)
                chunks_list = ws_meta.get("chunks_list", [])
                file_name = ws_meta.get("file_path", file_name)
                # Extract filename from path if it's a full path
                if "/" in file_name or "\\" in file_name:
                    file_name = Path(file_name).name
                created_at = ws_meta.get("created_at", created_at)
                updated_at = ws_meta.get("updated_at", updated_at)
        except (json.JSONDecodeError, Exception) as e:
            print(f"Warning: Could not read workspace status: {e}")

    # Update or create status entry in global file
    now = datetime.now(timezone.utc).isoformat()
    global_status_data[doc_id] = {
        "doc_id": doc_id,
        "file_path": str(doc_path.absolute()),
        "file_name": file_name,
        "status": "indexed",  # Map LightRAG's "processed" to "indexed"
        "doc_type": "gdd",  # Default to GDD for uploaded documents
        "created_at": global_status_data.get(doc_id, {}).get("created_at", created_at),
        "updated_at": updated_at or now,
        "chunks_count": chunks_count,
        "chunks_list": chunks_list,
    }

    # Save updated global status
    # IMPORTANT: Ensure we preserve all existing entries - only update the current doc_id
    global_status_path.parent.mkdir(parents=True, exist_ok=True)

    # Double-check: Make sure we're not losing any existing entries
    existing_count = len(global_status_data)
    if existing_count == 0 and global_status_path.exists():
        print(
            "WARNING: About to overwrite global status file with empty dict! Existing file exists."
        )

    # Write with atomic operation: write to temp file first, then rename
    temp_file = global_status_path.with_suffix(".json.tmp")
    try:
        json_content = json.dumps(global_status_data, indent=2, ensure_ascii=False)
        temp_file.write_text(json_content, encoding="utf-8")
        # Atomic rename (works on Windows too)
        temp_file.replace(global_status_path)
        print(
            f"Saved document status for {doc_id} to global status file (total entries: {existing_count})"
        )
    except Exception as e:
        print(f"Error saving global status file with atomic write: {e}")
        # Fallback: try direct write
        try:
            json_content = json.dumps(global_status_data, indent=2, ensure_ascii=False)
            global_status_path.write_text(json_content, encoding="utf-8")
            print(
                f"Saved document status for {doc_id} using fallback method (total entries: {existing_count})"
            )
        except Exception as e2:
            print(f"Fatal error: Could not save global status file: {e2}")
            raise
