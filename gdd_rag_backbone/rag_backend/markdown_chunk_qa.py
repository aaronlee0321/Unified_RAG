"""
Query functions for markdown chunks stored in separate storage.

This module provides query functionality for markdown chunks that are stored
in rag_storage_md_indexed/ (separate from the main rag_storage/).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Optional, Sequence

from gdd_rag_backbone.config import PROJECT_ROOT
from gdd_rag_backbone.rag_backend.chunk_qa import (
    ChunkRecord,
    _embed_texts,
    _load_chunk_vectors,
    _score_chunks,
    _rerank_with_cross_encoder,
    _select_top_chunks,
    _extract_evidence_spans,
    _filter_chunks_by_evidence,
    _normalize_vector,
)

# Markdown chunks storage paths
MARKDOWN_WORKING_DIR = PROJECT_ROOT / "rag_storage_md_indexed"
MARKDOWN_CHUNKS_PATH = MARKDOWN_WORKING_DIR / "kv_store_text_chunks.json"
MARKDOWN_VDB_PATH = MARKDOWN_WORKING_DIR / "vdb_chunks.json"
MARKDOWN_STATUS_PATH = MARKDOWN_WORKING_DIR / "kv_store_doc_status.json"


def load_markdown_doc_chunks(doc_id: str) -> List[ChunkRecord]:
    """
    Load chunks for a markdown document from markdown storage.
    
    Args:
        doc_id: Document ID
    
    Returns:
        List of ChunkRecord objects
    """
    if not MARKDOWN_CHUNKS_PATH.exists():
        return []
    
    try:
        with open(MARKDOWN_CHUNKS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return []
    
    records: List[ChunkRecord] = []
    for chunk_id, payload in data.items():
        if (
            isinstance(payload, dict)
            and payload.get("full_doc_id") == doc_id
            and payload.get("content")
        ):
            records.append(
                ChunkRecord(
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    content=payload["content"],
                )
            )
    return records


def load_markdown_chunk_vectors(doc_ids: Sequence[str], normalize: bool = True) -> Dict[str, List[float]]:
    """
    Load chunk vectors from markdown storage.
    
    Args:
        doc_ids: Document IDs to load vectors for
        normalize: If True, pre-normalize vectors
    
    Returns:
        Dictionary mapping chunk_id to vector
    """
    if not MARKDOWN_VDB_PATH.exists():
        return {}
    
    try:
        with open(MARKDOWN_VDB_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return {}
    
    allowed = set(doc_ids)
    vectors: Dict[str, List[float]] = {}
    
    for entry in data.get("data", []):
        doc_id = entry.get("full_doc_id")
        chunk_id = entry.get("__id__") or entry.get("id")
        vector = entry.get("vector") or entry.get("embedding")
        
        if chunk_id and vector and doc_id in allowed:
            # Convert to float list
            try:
                float_vector = [float(v) for v in vector]
                if normalize:
                    float_vector = _normalize_vector(float_vector)
                vectors[chunk_id] = float_vector
            except (ValueError, TypeError):
                continue
    
    return vectors


def get_markdown_top_chunks(
    doc_ids: Sequence[str],
    question: str,
    *,
    provider,
    top_k: int = 8,
    per_doc_limit: Optional[int] = None,
    use_rrf: bool = True,
    filter_by_evidence: bool = True,
) -> List[Dict[str, object]]:
    """
    Get top chunks from markdown storage for a question.
    
    This function mirrors get_top_chunks from chunk_qa.py but uses
    the markdown storage paths.
    
    Args:
        doc_ids: Document IDs to query
        question: Question text
        provider: LLM/Embedding provider
        top_k: Number of top chunks to return
        per_doc_limit: Maximum chunks per document
        use_rrf: Whether to use Reciprocal Rank Fusion
        filter_by_evidence: Whether to filter by evidence score
    
    Returns:
        List of chunk dictionaries with scores and evidence spans
    """
    if not doc_ids:
        raise ValueError("At least one doc_id is required.")
    
    unique_ids = list(dict.fromkeys(doc_ids))
    all_chunks: List[ChunkRecord] = []
    
    for doc_id in unique_ids:
        all_chunks.extend(load_markdown_doc_chunks(doc_id))
    
    if not all_chunks:
        raise ValueError("No chunks found for the selected documents. Verify they were indexed.")
    
    # Try to embed the question
    question_embedding = None
    try:
        question_embedding = _embed_texts(provider, [question], use_cache=True)[0]
        question_embedding = _normalize_vector(question_embedding)
    except Exception:
        # Embedding failed - will use text-based scoring
        pass
    
    # Load vectors from markdown storage
    vectors = load_markdown_chunk_vectors(unique_ids, normalize=True)
    
    # Score chunks
    scored = _score_chunks(
        question_embedding,
        all_chunks,
        vectors,
        provider,
        question_text=question,
        use_rrf=use_rrf
    )
    
    # Apply evidence filtering
    if filter_by_evidence:
        scored = _filter_chunks_by_evidence(question, scored, min_evidence_score=0.15, keep_top_n=10)
    
    # Re-rank with cross-encoder
    reranked = _rerank_with_cross_encoder(question, scored, provider=provider, top_n=min(12, len(scored)))
    
    # Select top chunks
    selected = _select_top_chunks(
        reranked,
        top_k=top_k,
        per_doc_limit=per_doc_limit or (2 if len(unique_ids) > 1 else None),
    )
    
    # Add evidence spans to results
    results = []
    for score, record in selected:
        evidence_spans = _extract_evidence_spans(question, record.content, max_spans=3)
        results.append({
            "doc_id": record.doc_id,
            "chunk_id": record.chunk_id,
            "content": record.content,
            "score": score,
            "evidence_spans": evidence_spans,
        })
    
    return results


def list_markdown_indexed_docs() -> List[dict]:
    """
    List all indexed markdown documents.
    
    Returns:
        List of document metadata dictionaries
    """
    if not MARKDOWN_STATUS_PATH.exists():
        return []
    
    try:
        with open(MARKDOWN_STATUS_PATH, 'r', encoding='utf-8') as f:
            status = json.load(f)
    except Exception:
        return []
    
    docs: List[dict] = []
    for doc_id, meta in status.items():
        if isinstance(meta, dict):
            docs.append({
                "doc_id": doc_id,
                "file_path": meta.get("file_path", ""),
                "updated_at": meta.get("updated_at"),
                "status": meta.get("status", ""),
                "chunks_count": meta.get("chunks_count", 0),
            })
    
    docs.sort(key=lambda item: item["doc_id"])
    return docs

