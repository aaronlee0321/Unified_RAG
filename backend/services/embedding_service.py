"""
Embedding service (optional) for keyword extractor.
Computes embeddings for chunks and stores them in pgvector column.
EXACT COPY from keyword_extractor - adapted for unified_rag_app.
"""

import os
from typing import Dict, List, Optional

from backend.storage.supabase_client import get_supabase_client

try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore


def _get_openai_client() -> Optional["OpenAI"]:
    """
    Build OpenAI client (or compatible) from environment.
    Supports:
    - OPENAI_API_KEY (direct OpenAI)
    - OPENAI_COMPATIBLE_BASE_URL_EMBEDDING + OPENAI_COMPATIBLE_API_KEY_EMBEDDING
    """
    if OpenAI is None:
        return None

    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_COMPATIBLE_BASE_URL_EMBEDDING")
    alt_key = os.getenv("OPENAI_COMPATIBLE_API_KEY_EMBEDDING")

    if base_url and alt_key:
        return OpenAI(api_key=alt_key, base_url=base_url)
    if api_key:
        return OpenAI(api_key=api_key)
    return None


def _pad_to_1536(vec: List[float]) -> List[float]:
    """keyword_chunks.embedding is vector(1536) in the default schema."""
    if vec is None:
        return vec
    if len(vec) == 1536:
        return vec
    if len(vec) > 1536:
        return vec[:1536]
    return vec + [0.0] * (1536 - len(vec))


def embed_document_chunks(doc_id: str, model: Optional[str] = None, batch_size: int = 64) -> int:
    """
    Compute embeddings for all chunks of a document and store in 'embedding' column.
    EXACT LOGIC from keyword_extractor.

    Args:
        doc_id: Document ID
        model: Embedding model (default: text-embedding-3-small)
        batch_size: Number of chunks per API call

    Returns:
        Number of chunks embedded
    """
    client = get_supabase_client(use_service_key=True)

    # Use OpenAI-compatible embeddings
    openai_client = _get_openai_client()
    if not openai_client:
        return 0
    from backend.shared.config import DEFAULT_EMBEDDING_MODEL

    embedding_model = model or os.getenv("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL

    # Fetch chunks without embeddings (or re-embed all)
    # Note: Supabase python client doesn't support vector IS NULL directly; fetch content+ids
    resp = (
        client.table("keyword_chunks")
        .select("id, chunk_id, content")
        .eq("doc_id", doc_id)
        .execute()
    )
    chunks: List[Dict] = resp.data or []
    if not chunks:
        return 0

    total_embedded = 0

    # Batch process
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i : i + batch_size]
        texts = [c["content"] for c in batch]

        # Call embedding API
        emb = openai_client.embeddings.create(model=embedding_model, input=texts)
        vectors = [e.embedding for e in emb.data]

        # Upsert embeddings back per row
        update_rows = []
        for c, vec in zip(batch, vectors):
            # Ensure dimension matches vector(1536)
            update_rows.append({"id": c["id"], "embedding": _pad_to_1536(vec)})

        client.table("keyword_chunks").upsert(update_rows).execute()
        total_embedded += len(update_rows)

    return total_embedded
