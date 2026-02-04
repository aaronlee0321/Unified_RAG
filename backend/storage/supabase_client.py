"""
Supabase client for vector storage
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Workaround: Mock storage3 if not available (we don't use it)
try:
    from supabase import Client, create_client
except ImportError as e:
    if "storage3" in str(e) or "pyiceberg" in str(e):
        # Create a minimal mock for storage3
        class MockStorageException(Exception):
            pass

        sys.modules["storage3"] = type(sys)("storage3")
        sys.modules["storage3"].utils = type(sys)("storage3.utils")
        sys.modules["storage3"].utils.StorageException = MockStorageException

        # Try importing again
        from supabase import Client, create_client
    else:
        raise

from backend.shared.config import SUPABASE_KEY, SUPABASE_SERVICE_KEY, SUPABASE_URL

# Initialize Supabase clients (separate for anon and service_role)
supabase_anon: Client = None
supabase_service: Client = None


def get_supabase_client(use_service_key: bool = False) -> Client:
    """
    Get Supabase client instance.
    Maintains separate clients for anon and service_role keys.

    Args:
        use_service_key: If True, use service key (for admin operations)

    Returns:
        Supabase client instance
    """
    import logging

    logger = logging.getLogger(__name__)

    global supabase_anon, supabase_service

    if use_service_key:
        # Use service_role key
        logger.info("Getting Supabase client with service_role key...")
        if supabase_service is None:
            if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
                logger.error(
                    "SUPABASE_URL or SUPABASE_SERVICE_KEY not configured")
                raise ValueError(
                    "Supabase URL and service key must be configured. Set SUPABASE_URL and SUPABASE_SERVICE_KEY in .env file."
                )
            logger.info(
                f"Creating service_role client with URL: {SUPABASE_URL[:30]}...")
            supabase_service = create_client(
                SUPABASE_URL, SUPABASE_SERVICE_KEY)
            logger.info("✅ Service_role client created successfully")
        return supabase_service
    else:
        # Use anon key
        logger.info("Getting Supabase client with anon key...")
        if supabase_anon is None:
            if not SUPABASE_URL or not SUPABASE_KEY:
                logger.error("SUPABASE_URL or SUPABASE_KEY not configured")
                raise ValueError(
                    "Supabase URL and key must be configured. Set SUPABASE_URL and SUPABASE_KEY in .env file."
                )
            logger.info("[SUPABASE CLIENT] Creating anon client")
            logger.info(
                f"[SUPABASE CLIENT] URL: {SUPABASE_URL[:50]}..."
                if SUPABASE_URL
                else "[SUPABASE CLIENT] URL: None"
            )
            logger.info(
                f"[SUPABASE CLIENT] Key starts with: {SUPABASE_KEY[:20]}..."
                if SUPABASE_KEY
                else "[SUPABASE CLIENT] Key: None"
            )
            try:
                supabase_anon = create_client(SUPABASE_URL, SUPABASE_KEY)
                logger.info(
                    "[SUPABASE CLIENT] ✅ Anon client created successfully")
            except Exception as e:
                logger.error(
                    f"[SUPABASE CLIENT] ❌ Failed to create anon client: {e}")
                logger.error(
                    f"[SUPABASE CLIENT] Exception type: {type(e).__name__}")
                import traceback

                logger.error(
                    f"[SUPABASE CLIENT] Traceback:\n{traceback.format_exc()}")
                raise
        logger.info("[SUPABASE CLIENT] Returning existing anon client")
        return supabase_anon


def vector_search_gdd_chunks(
    query_embedding: List[float],
    limit: int = 10,
    threshold: float = 0.7,
    doc_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Perform vector search on GDD chunks using Supabase pgvector.

    Args:
        query_embedding: Query vector embedding (1024 dimensions)
        limit: Maximum number of results
        threshold: Similarity threshold (0.0 to 1.0)
        doc_id: Optional document ID to filter by

    Returns:
        List of matching chunks with similarity scores
    """
    try:
        client = get_supabase_client()

        # Use keyword_chunks RPC function (assuming it exists) or fallback to direct query
        # Note: If match_keyword_chunks RPC doesn't exist, we'll need to create it or use direct query
        try:
            result = client.rpc(
                "match_keyword_chunks",  # Updated RPC function name
                {
                    "query_embedding": query_embedding,
                    "match_threshold": threshold,
                    "match_count": limit,
                    "doc_id_filter": doc_id,
                },
            ).execute()
        except Exception as e:
            # Fallback: if RPC doesn't exist, log warning and return empty
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(
                f"match_keyword_chunks RPC not found, falling back to empty result: {e}")
            return []

        return result.data if result.data else []
    except Exception as e:
        raise Exception(f"Error in GDD vector search: {e}")


def vector_search_code_chunks(
    query_embedding: List[float],
    limit: int = 10,
    threshold: float = 0.7,
    file_path: Optional[str] = None,
    chunk_type: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Perform vector search on code chunks using Supabase pgvector.

    Args:
        query_embedding: Query vector embedding (1024 dimensions)
        limit: Maximum number of results
        threshold: Similarity threshold (0.0 to 1.0)
        file_path: Optional file path to filter by
        chunk_type: Optional chunk type ('method' or 'class') to filter by

    Returns:
        List of matching chunks with similarity scores
    """
    try:
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            f"[Supabase Code Search] threshold={threshold}, limit={limit}, file_path={file_path}, chunk_type={chunk_type}"
        )

        client = get_supabase_client()

        # If file_path is provided, try multiple matching strategies
        if file_path:
            results = []
            strategy_used = None

            # Strategy 1: Try with the provided path
            result = client.rpc(
                "match_code_chunks",
                {
                    "query_embedding": query_embedding,
                    "match_threshold": threshold,
                    "match_count": limit,
                    "file_path_filter": file_path,
                    "chunk_type_filter": chunk_type,
                },
            ).execute()

            results = result.data if result.data else []
            if len(results) > 0:
                strategy_used = "Strategy 1 (provided path)"
                logger.info(
                    f"[Supabase Code Search] {strategy_used}: Found {len(results)} chunks with path '{file_path}'"
                )
            else:
                logger.info(
                    f"[Supabase Code Search] Strategy 1 (provided path): No chunks found with path '{file_path}'"
                )

            # Strategy 2: If no results, try with just the filename
            if len(results) == 0:
                filename = (
                    file_path.split("/")[-1]
                    if "/" in file_path
                    else (file_path.split("\\")[-1] if "\\" in file_path else file_path)
                )
                logger.info(
                    f"[Supabase Code Search] Trying Strategy 2 (filename only): '{filename}'"
                )
                result = client.rpc(
                    "match_code_chunks",
                    {
                        "query_embedding": query_embedding,
                        "match_threshold": threshold,
                        "match_count": limit,
                        "file_path_filter": filename,
                        "chunk_type_filter": chunk_type,
                    },
                ).execute()
                results = result.data if result.data else []
                if len(results) > 0:
                    strategy_used = f"Strategy 2 (filename: '{filename}')"
                    logger.info(
                        f"[Supabase Code Search] {strategy_used}: Found {len(results)} chunks"
                    )
                else:
                    logger.info(
                        "[Supabase Code Search] Strategy 2 (filename): No chunks found")

            # Strategy 3: If still no results, try last 2-3 path segments
            if len(results) == 0 and ("/" in file_path or "\\" in file_path):
                path_parts = file_path.replace("\\", "/").split("/")
                if len(path_parts) >= 2:
                    last_segments = "/".join(path_parts[-2:])
                    logger.info(
                        f"[Supabase Code Search] Trying Strategy 3 (last segments): '{last_segments}'"
                    )
                    result = client.rpc(
                        "match_code_chunks",
                        {
                            "query_embedding": query_embedding,
                            "match_threshold": threshold,
                            "match_count": limit,
                            "file_path_filter": last_segments,
                            "chunk_type_filter": chunk_type,
                        },
                    ).execute()
                    results = result.data if result.data else []
                    if len(results) > 0:
                        strategy_used = f"Strategy 3 (last segments: '{last_segments}')"
                        logger.info(
                            f"[Supabase Code Search] {strategy_used}: Found {len(results)} chunks"
                        )
                    else:
                        logger.info(
                            "[Supabase Code Search] Strategy 3 (last segments): No chunks found"
                        )

            # Final summary
            if len(results) > 0:
                logger.info(
                    f"[Supabase Code Search] SUCCESS: Found {len(results)} chunks using {strategy_used}"
                )
            elif file_path:
                logger.warning(
                    f"[Supabase Code Search] FAILED: No chunks found for path '{file_path}' after trying all strategies"
                )
        else:
            # No file filter - search all
            result = client.rpc(
                "match_code_chunks",
                {
                    "query_embedding": query_embedding,
                    "match_threshold": threshold,
                    "match_count": limit,
                    "file_path_filter": None,
                    "chunk_type_filter": chunk_type,
                },
            ).execute()
            results = result.data if result.data else []
            logger.info(
                f"[Supabase Code Search] No file filter: Found {len(results)} chunks")

        return results
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"[Supabase Code Search] Error: {e}")
        raise Exception(f"Error in Code vector search: {e}")


def insert_gdd_document(
    doc_id: str,
    name: str,
    file_path: Optional[str] = None,
    file_size: Optional[int] = None,
    markdown_content: Optional[str] = None,
    pdf_storage_path: Optional[str] = None,
    images: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Insert or update a GDD document.
    Uses keyword_documents table (shared with Keyword Finder feature).

    Args:
        doc_id: Unique document ID
        name: Document name
        file_path: Optional file path (for reference, not used for reading)
        file_size: Optional file size in bytes
        markdown_content: Optional full markdown content (stored as full_text in keyword_documents)
        pdf_storage_path: Optional PDF filename in Supabase Storage (gdd_pdfs bucket)
                      Note: This is stored in file_path if pdf_storage_path is provided
        images: Optional list of image metadata dicts: [{"filename": "...", "url": "...", "path": "doc_id/images/..."}]

    Returns:
        Inserted/updated document data
    """
    try:
        client = get_supabase_client(use_service_key=True)

        # Use keyword_documents table (shared table for both Keyword Finder and GDD RAG)
        # Map markdown_content to full_text (keyword_documents uses full_text)
        # Use pdf_storage_path as file_path if provided, otherwise use file_path parameter
        doc_data = {
            "doc_id": doc_id,
            "name": name,
            "file_path": pdf_storage_path if pdf_storage_path else file_path,
            "file_size": file_size,
            "full_text": markdown_content,  # Store markdown_content as full_text
        }
        if images is not None:
            doc_data["images"] = images

        result = client.table("keyword_documents").upsert(
            doc_data, on_conflict="doc_id").execute()

        return result.data[0] if result.data else {}
    except Exception as e:
        raise Exception(f"Error inserting GDD document: {e}")


def insert_gdd_chunks(chunks: List[Dict[str, Any]]) -> int:
    """
    Insert GDD chunks with embeddings into Supabase.
    Uses keyword_chunks table (shared with Keyword Finder feature).

    Args:
        chunks: List of chunk dictionaries with keys:
            - chunk_id: Unique chunk ID
            - doc_id: Document ID
            - content: Chunk content
            - embedding: Vector embedding (dimensions vary by model)
            - section_heading: Optional section heading (maps to section_heading in keyword_chunks)
            - chunk_index: Optional chunk index
            - metadata: Optional metadata dict (stored as JSONB if supported)

    Returns:
        Number of chunks inserted
    """
    try:
        client = get_supabase_client(use_service_key=True)

        # Prepare records for insertion
        records = []
        for chunk in chunks:
            embedding = chunk.get("embedding")

            # Ensure embedding is a list, not a string
            if embedding is not None:
                if isinstance(embedding, str):
                    # Try to parse string as JSON array
                    try:
                        import json

                        embedding = json.loads(embedding)
                    except Exception:
                        # If parsing fails, skip this chunk
                        print(
                            f"Warning: Could not parse embedding for chunk {chunk.get('chunk_id')}, skipping"
                        )
                        continue
                elif not isinstance(embedding, list):
                    print(
                        f"Warning: Embedding is not a list for chunk {chunk.get('chunk_id')}, skipping"
                    )
                    continue

                # Ensure all values are floats
                try:
                    embedding = [float(x) for x in embedding]
                except (ValueError, TypeError):
                    print(
                        f"Warning: Could not convert embedding to floats for chunk {chunk.get('chunk_id')}, skipping"
                    )
                    continue

                # Pad embeddings to match database schema (1536 dimensions)
                # Database expects vector(1536) but some models produce different dimensions:
                # - OpenAI text-embedding-3-small: 1536
                # - OpenAI text-embedding-3-large: 3072
                # - Ollama mxbai-embed-large: 1024
                # - Ollama nomic-embed-text: 768
                expected_dim = 1536  # keyword_chunks table uses vector(1536)
                current_dim = len(embedding)

                if current_dim < expected_dim:
                    # Pad with zeros to match expected dimension
                    padding_needed = expected_dim - current_dim
                    embedding = embedding + [0.0] * padding_needed
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.debug(
                        f"Padded embedding from {current_dim} to {expected_dim} dimensions for chunk {chunk.get('chunk_id')}"
                    )
                elif current_dim > expected_dim:
                    # Truncate if larger (shouldn't happen, but handle it)
                    embedding = embedding[:expected_dim]
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"Truncated embedding from {current_dim} to {expected_dim} dimensions for chunk {chunk.get('chunk_id')}"
                    )

            # Map to keyword_chunks table schema:
            # - chunk_id, doc_id, content, embedding, section_heading, chunk_index
            record = {
                "chunk_id": chunk["chunk_id"],
                "doc_id": chunk["doc_id"],
                "content": chunk["content"],
                "embedding": embedding,  # list[float] or None
            }

            # Map section_heading if available (keyword_chunks has section_heading field)
            if "section_heading" in chunk:
                record["section_heading"] = chunk["section_heading"]
            elif "section_title" in chunk:
                record["section_heading"] = chunk["section_title"]
            elif "subsection_title" in chunk:
                record["section_heading"] = chunk["subsection_title"]

            # Map chunk_index if available
            if "chunk_index" in chunk:
                record["chunk_index"] = chunk["chunk_index"]
            elif "section_index" in chunk:
                record["chunk_index"] = chunk["section_index"]
            elif "paragraph_index" in chunk:
                record["chunk_index"] = chunk["paragraph_index"]

            records.append(record)

        # Insert in batches (Supabase has limits)
        batch_size = 100
        total_inserted = 0

        for i in range(0, len(records), batch_size):
            batch = records[i: i + batch_size]
            # Use keyword_chunks table (shared with Keyword Finder feature)
            result = client.table("keyword_chunks").upsert(
                batch, on_conflict="chunk_id").execute()
            total_inserted += len(result.data) if result.data else 0

        return total_inserted
    except Exception as e:
        raise Exception(f"Error inserting GDD chunks: {e}")


def insert_code_file(file_path: str, file_name: str, normalized_path: str) -> Dict[str, Any]:
    """
    Insert or update a code file.

    Args:
        file_path: Full file path
        file_name: File name
        normalized_path: Normalized path for matching

    Returns:
        Inserted/updated file data
    """
    try:
        client = get_supabase_client(use_service_key=True)

        result = (
            client.table("code_files")
            .upsert(
                {
                    "file_path": file_path,
                    "file_name": file_name,
                    "normalized_path": normalized_path,
                },
                on_conflict="file_path",
            )
            .execute()
        )

        return result.data[0] if result.data else {}
    except Exception as e:
        raise Exception(f"Error inserting code file: {e}")


def insert_code_chunks(chunks: List[Dict[str, Any]]) -> int:
    """
    Insert code chunks (methods/classes) with embeddings into Supabase.

    Args:
        chunks: List of chunk dictionaries with keys:
            - file_path: File path
            - chunk_type: 'method' or 'class'
            - class_name: Class name
            - method_name: Method name (for methods)
            - source_code: Source code
            - code: Method code (for methods)
            - embedding: Vector embedding (1024 dimensions)
            - doc_comment: Optional doc comment
            - constructor_declaration: For classes
            - method_declarations: For classes
            - references: References
            - metadata: Optional metadata dict

    Returns:
        Number of chunks inserted
    """
    try:
        client = get_supabase_client(use_service_key=True)

        # Prepare records for insertion
        records = []
        for chunk in chunks:
            record = {
                "file_path": chunk["file_path"],
                "chunk_type": chunk["chunk_type"],
                "class_name": chunk.get("class_name"),
                "method_name": chunk.get("method_name"),
                "source_code": chunk["source_code"],
                "code": chunk.get("code"),
                "embedding": chunk.get("embedding"),
                "doc_comment": chunk.get("doc_comment", ""),
                "constructor_declaration": chunk.get("constructor_declaration", ""),
                "method_declarations": chunk.get("method_declarations", ""),
                "code_references": chunk.get(
                    "references", ""
                ),  # Maps from 'references' key to 'code_references' column
                "metadata": chunk.get("metadata", {}),
            }
            records.append(record)

        # Insert in batches
        batch_size = 100
        total_inserted = 0

        for i in range(0, len(records), batch_size):
            batch = records[i: i + batch_size]
            result = client.table("code_chunks").insert(batch).execute()
            total_inserted += len(result.data) if result.data else 0

        return total_inserted
    except Exception as e:
        raise Exception(f"Error inserting code chunks: {e}")


def get_gdd_documents() -> List[Dict[str, Any]]:
    """
    Get all GDD documents.
    Uses keyword_documents table (shared with Keyword Finder feature).

    Returns:
        List of document dictionaries
    """
    import logging

    logger = logging.getLogger(__name__)

    try:
        logger.info("get_gdd_documents() called")
        logger.info("Getting Supabase client...")
        client = get_supabase_client()
        logger.info(
            "Supabase client obtained, querying keyword_documents table...")

        result = client.table("keyword_documents").select(
            "*").order("name").execute()
        logger.info(
            f"Query executed, received {len(result.data) if result.data else 0} documents")

        if result.data and len(result.data) > 0:
            logger.info(
                f"Sample document: {result.data[0].get('name', 'N/A')}")

        return result.data if result.data else []
    except Exception as e:
        import traceback

        logger.error(f"❌ Error fetching GDD documents: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise Exception(f"Error fetching GDD documents: {e}")


def get_gdd_document_markdown(doc_id: str) -> Optional[str]:
    """
    Get full markdown content for a GDD document from Supabase.
    Uses keyword_documents table (markdown stored as full_text).

    Args:
        doc_id: Document ID

    Returns:
        Markdown content as string, or None if not found
    """
    try:
        client = get_supabase_client()
        # keyword_documents stores markdown as full_text
        result = (
            client.table("keyword_documents")
            .select("full_text")
            .eq("doc_id", doc_id)
            .limit(1)
            .execute()
        )

        if result.data and len(result.data) > 0:
            return result.data[0].get("full_text")
        return None
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error fetching markdown content for {doc_id}: {e}")
        return None


def upload_pdf_to_storage(pdf_path: Path, pdf_filename: str) -> bool:
    """
    Upload PDF file to Supabase Storage (gdd_pdfs bucket).

    Args:
        pdf_path: Path to the PDF file on disk
        pdf_filename: Filename to use in storage (should be sanitized)

    Returns:
        True if successful, False otherwise
    """
    try:
        client = get_supabase_client(use_service_key=True)
        bucket_name = "gdd_pdfs"

        # Read PDF file
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        # Upload to Supabase Storage
        client.storage.from_(bucket_name).upload(
            path=pdf_filename,
            file=pdf_bytes,
            file_options={
                "content-type": "application/pdf",
                "cache-control": "3600",
                "upsert": "true",  # Overwrite if exists
            },
        )

        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"✅ Uploaded PDF to storage: {pdf_filename}")
        return True
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"❌ Error uploading PDF to storage: {e}")
        return False


def upload_gdd_image_to_storage(
    doc_id: str, image_filename: str, image_bytes: bytes, content_type: str = "image/webp"
) -> Optional[str]:
    """
    Upload a single image to gdd_pdfs bucket under {doc_id}/images/{image_filename}.
    Returns the public URL for the uploaded image, or None on failure.

    Args:
        doc_id: Document ID (used as subfolder)
        image_filename: Filename to use in storage (e.g. "abc123_1_img.webp")
        image_bytes: Raw image bytes
        content_type: MIME type (default image/webp)

    Returns:
        Public URL string, or None if upload failed
    """
    try:
        client = get_supabase_client(use_service_key=True)
        bucket_name = "gdd_pdfs"
        storage_path = f"{doc_id}/images/{image_filename}"
        client.storage.from_(bucket_name).upload(
            path=storage_path,
            file=image_bytes,
            file_options={
                "content-type": content_type,
                "cache-control": "3600",
                "upsert": "true",
            },
        )
        url = client.storage.from_(bucket_name).get_public_url(storage_path)
        import logging

        logger = logging.getLogger(__name__)
        logger.info(f"Uploaded image to gdd_pdfs: {storage_path}")
        return url
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error uploading image to storage: {e}")
        return None


def get_gdd_image_public_url(doc_id: str, image_filename: str) -> str:
    """
    Get public URL for an image stored under gdd_pdfs/{doc_id}/images/{image_filename}.
    Does not verify that the file exists.
    """
    client = get_supabase_client()
    bucket_name = "gdd_pdfs"
    storage_path = f"{doc_id}/images/{image_filename}"
    return client.storage.from_(bucket_name).get_public_url(storage_path)


def get_gdd_document_pdf_url(doc_id: str) -> Optional[str]:
    """
    Get public URL for PDF from Supabase Storage.

    First checks the database for pdf_storage_path, then verifies file exists in storage.
    If exact match not found, tries fuzzy matching against files in bucket.

    Args:
        doc_id: Document ID

    Returns:
        Public URL to PDF, or None if not found
    """
    try:
        client = get_supabase_client()
        bucket_name = "gdd_pdfs"

        # Get pdf_storage_path from database (uses keyword_documents table)
        stored_filename = None
        result = None
        try:
            result = (
                client.table("keyword_documents")
                .select("file_path")
                .eq("doc_id", doc_id)
                .limit(1)
                .execute()
            )
            # keyword_documents uses file_path, which may contain the PDF path
            if result.data and result.data[0].get("file_path"):
                stored_filename = result.data[0]["file_path"]
                # If file_path is a full path, extract just the filename
                if "/" in stored_filename or "\\" in stored_filename:
                    stored_filename = stored_filename.replace(
                        "\\", "/").split("/")[-1]
        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.warning(f"Could not get file_path for doc_id {doc_id}: {e}")
            pass

        # List all files in the bucket to verify existence (use service key for listing)
        try:
            # Try with service key first (has admin permissions)
            try:
                service_client = get_supabase_client(use_service_key=True)
                files = service_client.storage.from_(bucket_name).list()
            except Exception:
                # Fallback to anon key if service key not available
                files = client.storage.from_(bucket_name).list()
            file_names = [f.get("name", "") for f in files] if files else []

            # Strategy 1: Try exact match with stored filename
            if stored_filename and stored_filename in file_names:
                url = client.storage.from_(
                    bucket_name).get_public_url(stored_filename)
                return url if url else None

            # Strategy 2: Try doc_id-based filename
            doc_id_filename = f"{doc_id}.pdf"
            if doc_id_filename in file_names:
                url = client.storage.from_(
                    bucket_name).get_public_url(doc_id_filename)
                return url if url else None

            # Strategy 3: Fuzzy matching - normalize and compare
            if stored_filename:
                # Normalize for comparison (remove spaces, underscores, dashes, case-insensitive)
                stored_normalized = (
                    stored_filename.lower()
                    .replace("_", "")
                    .replace("-", "")
                    .replace(" ", "")
                    .replace(".pdf", "")
                )
                doc_id_normalized = (
                    doc_id.lower().replace("_", "").replace("-", "").replace(" ", "")
                )

                for file_name in file_names:
                    file_normalized = (
                        file_name.lower()
                        .replace("_", "")
                        .replace("-", "")
                        .replace(" ", "")
                        .replace(".pdf", "")
                    )

                    # Check if stored filename matches
                    if stored_normalized and stored_normalized == file_normalized:
                        url = client.storage.from_(
                            bucket_name).get_public_url(file_name)
                        return url if url else None

                    # Check if doc_id matches file name
                    if doc_id_normalized and (
                        doc_id_normalized in file_normalized or file_normalized in doc_id_normalized
                    ):
                        url = client.storage.from_(
                            bucket_name).get_public_url(file_name)
                        return url if url else None

            # If no match found, return None
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(
                f"PDF not found in storage for {doc_id}. Stored path: {stored_filename}, Available files: {file_names[:5]}"
            )
            return None

        except Exception as e:
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"Error listing files in bucket for {doc_id}: {e}")
            # Fallback: try to construct URL anyway (might work if file exists)
            pdf_filename = stored_filename or f"{doc_id}.pdf"
            url = client.storage.from_(
                bucket_name).get_public_url(pdf_filename)
            return url if url else None

    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.debug(f"Error getting PDF URL for {doc_id}: {e}")
        return None


def get_code_files() -> List[Dict[str, Any]]:
    """
    Get all code files.

    Returns:
        List of file dictionaries
    """
    try:
        client = get_supabase_client()
        result = client.table("code_files").select(
            "*").order("file_name").execute()
        return result.data if result.data else []
    except Exception as e:
        raise Exception(f"Error fetching code files: {e}")


def delete_gdd_document(doc_id: str) -> bool:
    """
    Delete a GDD document and all its chunks.

    Args:
        doc_id: Document ID to delete

    Returns:
        True if successful
    """
    try:
        client = get_supabase_client(use_service_key=True)
        # Cascade delete will remove chunks automatically (from keyword_chunks table)
        # Uses keyword_documents table (shared with Keyword Finder feature)
        client.table("keyword_documents").delete().eq(
            "doc_id", doc_id).execute()
        return True
    except Exception as e:
        raise Exception(f"Error deleting GDD document: {e}")


def delete_code_file(file_path: str) -> bool:
    """
    Delete a code file and all its chunks.

    Args:
        file_path: File path to delete

    Returns:
        True if successful
    """
    try:
        client = get_supabase_client(use_service_key=True)
        # Cascade delete will remove chunks automatically
        client.table("code_files").delete().eq(
            "file_path", file_path).execute()
        return True
    except Exception as e:
        raise Exception(f"Error deleting code file: {e}")
