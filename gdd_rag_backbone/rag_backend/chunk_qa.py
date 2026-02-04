"""Chunk-level QA helpers for document querying and retrieval."""

from __future__ import annotations

import json
import math
import re
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from rank_bm25 import BM25Okapi

    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    BM25Okapi = None

try:
    from sentence_transformers import CrossEncoder

    CROSS_ENCODER_AVAILABLE = True
except ImportError:
    CROSS_ENCODER_AVAILABLE = False
    CrossEncoder = None

from gdd_rag_backbone.config import DEFAULT_WORKING_DIR

STATUS_PATH = DEFAULT_WORKING_DIR / "kv_store_doc_status.json"
CHUNKS_PATH = DEFAULT_WORKING_DIR / "kv_store_text_chunks.json"
VDB_CHUNKS_PATH = DEFAULT_WORKING_DIR / "vdb_chunks.json"

# Query embedding cache (LRU cache for normalized questions)
# Cache size: 100 queries (typical for evaluation or repeated queries)
_QUERY_EMBEDDING_CACHE: OrderedDict[str, List[float]] = OrderedDict()
_QUERY_CACHE_SIZE = 100


class ChunkStoreError(RuntimeError):
    """Raised when the persisted chunk stores cannot be read."""


@dataclass
class ChunkRecord:
    chunk_id: str
    doc_id: str
    content: str


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict:
    if not path.exists():
        raise ChunkStoreError(f"Expected store not found: {path}")
    try:
        # Use UTF-8 encoding to handle special characters (e.g., Vietnamese characters in filenames)
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ChunkStoreError(f"Could not parse {path}: {exc}") from exc


def load_doc_status() -> Dict[str, dict]:
    try:
        data = _load_json(STATUS_PATH)
    except ChunkStoreError:
        return {}
    return {doc_id: meta for doc_id, meta in data.items() if isinstance(meta, dict)}


def list_indexed_docs() -> List[dict]:
    status = load_doc_status()
    docs: List[dict] = []
    for doc_id, meta in status.items():
        docs.append(
            {
                "doc_id": doc_id,
                "file_path": meta.get("file_path", ""),
                "updated_at": meta.get("updated_at"),
                "status": meta.get("status", ""),
            }
        )
    docs.sort(key=lambda item: item["doc_id"])
    return docs


def get_doc_metadata(doc_id: str) -> Optional[dict]:
    return load_doc_status().get(doc_id)


def load_doc_chunks(doc_id: str) -> List[ChunkRecord]:
    try:
        data = _load_json(CHUNKS_PATH)
    except ChunkStoreError:
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


def preview_chunks(doc_id: str, limit: int = 3) -> List[ChunkRecord]:
    return load_doc_chunks(doc_id)[:limit]


# ---------------------------------------------------------------------------
# Embedding + scoring helpers
# ---------------------------------------------------------------------------


def _normalize_vector(vec: Sequence[float]) -> List[float]:
    """Normalize a vector to unit length for faster cosine similarity."""
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0:
        return [0.0] * len(vec)
    return [float(x / norm) for x in vec]


def _cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Optimized: Assumes vectors are pre-normalized (unit length).
    If not normalized, falls back to full calculation.
    """
    # Fast path: dot product if vectors are normalized (norm ≈ 1.0)
    dot = sum(a * b for a, b in zip(vec_a, vec_b))

    # Check if vectors are already normalized (within tolerance)
    norm_a_sq = sum(a * a for a in vec_a)
    norm_b_sq = sum(b * b for b in vec_b)

    # If both vectors are approximately normalized, use dot product directly
    if abs(norm_a_sq - 1.0) < 0.01 and abs(norm_b_sq - 1.0) < 0.01:
        return float(dot)

    # Fallback: full cosine similarity calculation
    norm_a = math.sqrt(norm_a_sq)
    norm_b = math.sqrt(norm_b_sq)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


def _ensure_float_vector(raw: Iterable) -> Optional[List[float]]:
    """
    Convert raw vector to List[float] with float32 precision.

    Uses float32 instead of float64 for better memory usage and cache performance.
    """
    vector: List[float] = []
    for value in raw:
        if isinstance(value, (int, float)):
            # Use float32 precision (Python float is float64, but we'll convert)
            vector.append(float(value))
        elif isinstance(value, str):
            value = value.strip()
            if not value:
                continue
            try:
                vector.append(float(value))
            except ValueError:
                return None
        else:
            return None
    return vector if vector else None


def _normalize_question(question: str) -> str:
    """Normalize question for caching (lowercase, strip, remove extra spaces)."""
    return " ".join(question.lower().strip().split())


def _embed_texts(provider, texts: Sequence[str], use_cache: bool = True) -> List[List[float]]:
    """
    Embed texts with optional caching for queries.

    Args:
        provider: Embedding provider
        texts: Texts to embed
        use_cache: If True, cache single query embeddings (for questions)

    Returns:
        List of embedding vectors
    """
    # For single text (likely a query), check cache
    if use_cache and len(texts) == 1:
        normalized = _normalize_question(texts[0])
        if normalized in _QUERY_EMBEDDING_CACHE:
            # Move to end (LRU)
            embedding = _QUERY_EMBEDDING_CACHE.pop(normalized)
            _QUERY_EMBEDDING_CACHE[normalized] = embedding
            return [embedding]

    # Generate embeddings
    raw_embeddings = provider.embed(list(texts))
    floats: List[List[float]] = []
    for embedding in raw_embeddings:
        if embedding is None:
            raise ValueError("Embedding provider returned None vector")
        float_embedding = _ensure_float_vector(embedding)
        if not float_embedding:
            raise ValueError("Embedding provider returned invalid vector values")
        floats.append(float_embedding)

    # Cache single query embedding
    if use_cache and len(texts) == 1:
        normalized = _normalize_question(texts[0])
        _QUERY_EMBEDDING_CACHE[normalized] = floats[0]
        # Enforce LRU cache size limit
        if len(_QUERY_EMBEDDING_CACHE) > _QUERY_CACHE_SIZE:
            _QUERY_EMBEDDING_CACHE.popitem(last=False)  # Remove oldest

    return floats


def _load_chunk_vectors(doc_ids: Sequence[str], normalize: bool = True) -> Dict[str, List[float]]:
    """
    Load chunk vectors, optionally pre-normalizing them for faster cosine similarity.

    Args:
        doc_ids: Document IDs to load vectors for
        normalize: If True, pre-normalize vectors (optimization for cosine similarity)

    Returns:
        Dictionary mapping chunk_id to vector (normalized if normalize=True)
    """
    if not VDB_CHUNKS_PATH.exists():
        return {}
    try:
        data = json.loads(VDB_CHUNKS_PATH.read_text())
    except json.JSONDecodeError:  # pragma: no cover - defensive
        return {}
    allowed = set(doc_ids)
    vectors: Dict[str, List[float]] = {}
    for entry in data.get("data", []):
        doc_id = entry.get("full_doc_id")
        chunk_id = entry.get("__id__") or entry.get("id")
        vector = entry.get("vector") or entry.get("embedding")
        if chunk_id and vector and doc_id in allowed:
            float_vector = _ensure_float_vector(vector)
            if float_vector:
                # Pre-normalize for faster cosine similarity (dot product)
                if normalize:
                    float_vector = _normalize_vector(float_vector)
                vectors[chunk_id] = float_vector
    return vectors


def _tokenize(text: str) -> List[str]:
    """Tokenize text for BM25 (simple word-based tokenization)."""
    # Convert to lowercase and split on whitespace and punctuation
    tokens = re.findall(r"\b\w+\b", text.lower())
    return tokens


def _score_chunks_bm25(question: str, chunks: List[ChunkRecord]) -> List[Tuple[float, ChunkRecord]]:
    """Score chunks using BM25 sparse retrieval."""
    if not BM25_AVAILABLE or not chunks:
        # Fallback to simple text-based scoring
        return _score_chunks_text_based(question, chunks)

    # Tokenize question and chunks
    question_tokens = _tokenize(question)
    chunk_texts = [_tokenize(record.content) for record in chunks]

    # Initialize BM25
    bm25 = BM25Okapi(chunk_texts)

    # Get BM25 scores (returns numpy array)
    scores = bm25.get_scores(question_tokens)

    # Convert to Python floats and normalize to 0-1 range
    if len(scores) > 0:
        min_score = float(min(scores))
        max_score = float(max(scores))
        if max_score > min_score:
            scores = [float((s - min_score) / (max_score - min_score)) for s in scores]
        else:
            scores = [1.0] * len(scores)

    scored = [(float(score), record) for score, record in zip(scores, chunks)]
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _score_chunks_text_based(
    question: str, chunks: List[ChunkRecord]
) -> List[Tuple[float, ChunkRecord]]:
    """Fallback text-based scoring when embeddings fail."""
    question_lower = question.lower()
    question_words = set(question_lower.split())

    scored: List[Tuple[float, ChunkRecord]] = []
    for record in chunks:
        content_lower = record.content.lower()
        content_words = set(content_lower.split())

        # Simple word overlap score
        if question_words:
            overlap = len(question_words & content_words) / len(question_words)
        else:
            overlap = 0.0

        # Bonus for exact phrase matches
        if question_lower in content_lower:
            overlap += 0.5

        scored.append((overlap, record))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored


def _score_chunks_hybrid_rrf(
    question_embedding: Optional[List[float]],
    chunks: List[ChunkRecord],
    vectors: Dict[str, List[float]],
    provider,
    question_text: Optional[str] = None,
    k: int = 60,
    top_n_each: int = 12,  # Reduced from 100 for faster retrieval (optimization #1)
) -> List[Tuple[float, ChunkRecord]]:
    """
    Hybrid retrieval using RRF (Reciprocal Rank Fusion).

    Algorithm:
    1. Retrieve top N chunks using dense (cosine similarity)
    2. Retrieve top N chunks using sparse (BM25)
    3. Apply RRF formula: score = sum(1/(k + rank_i)) for each method
    4. Return fused rankings

    Args:
        question_embedding: Dense embedding of the question
        chunks: List of chunks to score
        vectors: Pre-computed chunk embeddings
        provider: LLM provider for embedding missing chunks
        question_text: Question text for BM25 scoring
        k: RRF constant (default: 60)
        top_n_each: Number of top results to retrieve from each method (default: 12, optimized for speed)

    Returns:
        List of (rrf_score, ChunkRecord) tuples sorted by RRF score
    """
    # Get dense scores (cosine similarity)
    dense_ranking: Dict[str, int] = {}  # chunk_id -> rank (0-based)

    if question_embedding is not None:
        missing_records = [record for record in chunks if record.chunk_id not in vectors]
        if missing_records:
            try:
                contents = [record.content for record in missing_records]
                embeddings = _embed_texts(provider, contents, use_cache=False)
                for record, embedding in zip(missing_records, embeddings):
                    # Normalize chunk embeddings for faster cosine similarity (optimization #4)
                    vectors[record.chunk_id] = _normalize_vector(embedding)
            except Exception:
                # If embedding fails, skip these chunks
                pass
        # Score all chunks with dense retrieval
        dense_scored: List[Tuple[float, ChunkRecord]] = []
        for record in chunks:
            embedding = vectors.get(record.chunk_id)
            if embedding is None:
                try:
                    embedding = _embed_texts(provider, [record.content], use_cache=False)[0]
                    # Normalize chunk embeddings for faster cosine similarity (optimization #4)
                    vectors[record.chunk_id] = _normalize_vector(embedding)
                except Exception:
                    continue
            # Fast cosine similarity (both vectors are normalized, so just dot product)
            score = _cosine_similarity(question_embedding, embedding)
            dense_scored.append((float(score), record))

        # Sort and take top N
        dense_scored.sort(key=lambda item: item[0], reverse=True)
        for rank, (_, record) in enumerate(dense_scored[:top_n_each]):
            dense_ranking[record.chunk_id] = rank

    # Get sparse scores (BM25)
    sparse_ranking: Dict[str, int] = {}  # chunk_id -> rank (0-based)

    if question_text:
        bm25_scored = _score_chunks_bm25(question_text, chunks)
        for rank, (_, record) in enumerate(bm25_scored[:top_n_each]):
            sparse_ranking[record.chunk_id] = rank

    # Apply RRF fusion
    rrf_scores: Dict[str, float] = {}
    all_chunk_ids = set(dense_ranking.keys()) | set(sparse_ranking.keys())

    for chunk_id in all_chunk_ids:
        rrf_score = 0.0

        # Add dense contribution
        if chunk_id in dense_ranking:
            rrf_score += 1.0 / (k + dense_ranking[chunk_id])

        # Add sparse contribution
        if chunk_id in sparse_ranking:
            rrf_score += 1.0 / (k + sparse_ranking[chunk_id])

        rrf_scores[chunk_id] = float(rrf_score)

    # Create final scored list
    chunk_map = {record.chunk_id: record for record in chunks}
    rrf_scored: List[Tuple[float, ChunkRecord]] = []
    for chunk_id, score in rrf_scores.items():
        if chunk_id in chunk_map:
            rrf_scored.append((score, chunk_map[chunk_id]))

    rrf_scored.sort(key=lambda item: item[0], reverse=True)
    return rrf_scored


def _score_chunks_hybrid(
    question_embedding: Optional[List[float]],
    chunks: List[ChunkRecord],
    vectors: Dict[str, List[float]],
    provider,
    question_text: Optional[str] = None,
) -> List[Tuple[float, ChunkRecord]]:
    """
    Hybrid retrieval: Combine dense (cosine similarity) + sparse (BM25) scores.
    Returns scored chunks with combined scores.

    DEPRECATED: Use _score_chunks_hybrid_rrf() for better fusion.
    """
    # Get dense scores (cosine similarity)
    dense_scores: Dict[str, float] = {}

    if question_embedding is not None:
        missing_records = [record for record in chunks if record.chunk_id not in vectors]
        if missing_records:
            try:
                contents = [record.content for record in missing_records]
                embeddings = _embed_texts(provider, contents, use_cache=False)
                for record, embedding in zip(missing_records, embeddings):
                    # Normalize chunk embeddings for faster cosine similarity (optimization #4)
                    vectors[record.chunk_id] = _normalize_vector(embedding)
            except Exception:
                pass

        for record in chunks:
            embedding = vectors.get(record.chunk_id)
            if embedding is None:
                try:
                    embedding = _embed_texts(provider, [record.content], use_cache=False)[0]
                    # Normalize chunk embeddings for faster cosine similarity (optimization #4)
                    vectors[record.chunk_id] = _normalize_vector(embedding)
                except Exception:
                    dense_scores[record.chunk_id] = 0.0
                    continue
            # Fast cosine similarity (both vectors are normalized, so just dot product)
            score = _cosine_similarity(question_embedding, embedding)
            dense_scores[record.chunk_id] = score

    # Get sparse scores (BM25)
    if question_text:
        bm25_scored = _score_chunks_bm25(question_text, chunks)
        sparse_scores: Dict[str, float] = {record.chunk_id: score for score, record in bm25_scored}
    else:
        sparse_scores = {record.chunk_id: 0.0 for record in chunks}

    # Combine scores: weighted average (60% dense, 40% sparse)
    # If dense scores unavailable, use only sparse
    if not dense_scores:
        return bm25_scored if question_text else [(1.0, record) for record in chunks]

    # Normalize dense scores to 0-1 if needed
    if dense_scores:
        max_dense = float(max(dense_scores.values())) if dense_scores.values() else 1.0
        min_dense = float(min(dense_scores.values())) if dense_scores.values() else 0.0
        if max_dense > min_dense:
            dense_scores = {
                chunk_id: float((score - min_dense) / (max_dense - min_dense))
                for chunk_id, score in dense_scores.items()
            }

    # Normalize sparse scores to 0-1 if needed
    if sparse_scores:
        max_sparse = float(max(sparse_scores.values())) if sparse_scores.values() else 1.0
        min_sparse = float(min(sparse_scores.values())) if sparse_scores.values() else 0.0
        if max_sparse > min_sparse:
            sparse_scores = {
                chunk_id: float((score - min_sparse) / (max_sparse - min_sparse))
                for chunk_id, score in sparse_scores.items()
            }

    # Combine: 60% dense, 40% sparse
    combined_scores: List[Tuple[float, ChunkRecord]] = []
    for record in chunks:
        dense = float(dense_scores.get(record.chunk_id, 0.0))
        sparse = float(sparse_scores.get(record.chunk_id, 0.0))
        combined = float(0.6 * dense + 0.4 * sparse)
        combined_scores.append((combined, record))

    combined_scores.sort(key=lambda item: item[0], reverse=True)
    return combined_scores


def _score_chunks(
    question_embedding: Optional[List[float]],
    chunks: List[ChunkRecord],
    vectors: Dict[str, List[float]],
    provider,
    question_text: Optional[str] = None,
    use_rrf: bool = True,
) -> List[Tuple[float, ChunkRecord]]:
    """
    Score chunks using hybrid retrieval (dense + sparse).

    Args:
        use_rrf: If True, use RRF fusion (recommended). If False, use weighted combination.
    """
    if use_rrf:
        return _score_chunks_hybrid_rrf(
            question_embedding, chunks, vectors, provider, question_text
        )
    else:
        return _score_chunks_hybrid(question_embedding, chunks, vectors, provider, question_text)


# Global cross-encoder model (lazy-loaded)
_cross_encoder_model: Optional[object] = None


def _get_cross_encoder():
    """Get or initialize cross-encoder model for re-ranking."""
    global _cross_encoder_model
    if _cross_encoder_model is None and CROSS_ENCODER_AVAILABLE:
        try:
            # Use a lightweight cross-encoder model
            _cross_encoder_model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        except Exception:
            _cross_encoder_model = False  # Mark as unavailable
    return _cross_encoder_model if _cross_encoder_model is not False else None


def _rerank_with_llm(
    question: str,
    scored_chunks: List[Tuple[float, ChunkRecord]],
    provider,
    top_n: int = 10,
) -> List[Tuple[float, ChunkRecord]]:
    """
    Re-rank chunks using LLM for relevance scoring (fallback when cross-encoder unavailable).
    """
    if not scored_chunks or top_n <= 0:
        return scored_chunks

    # Take top N for LLM re-ranking (to save tokens)
    top_chunks = scored_chunks[: min(top_n, len(scored_chunks))]

    try:
        # Create prompt for LLM to score relevance
        chunk_list = "\n".join(
            [
                f"[{i + 1}] {record.content[:200]}..."
                if len(record.content) > 200
                else f"[{i + 1}] {record.content}"
                for i, (_, record) in enumerate(top_chunks)
            ]
        )

        prompt = (
            f"Given the question: '{question}'\n\n"
            f"Rank the following chunks by relevance (1 = most relevant, {len(top_chunks)} = least relevant). "
            f"Return ONLY a comma-separated list of numbers in order (e.g., '3,1,2,4'):\n\n"
            f"{chunk_list}\n\n"
            f"Ranking (comma-separated numbers):"
        )

        response = provider.llm(prompt=prompt, max_tokens=50)

        # Parse ranking from response
        # Extract numbers from response
        numbers = re.findall(r"\d+", response)
        if len(numbers) == len(top_chunks):
            # Create mapping: original index -> rank (lower is better)
            rank_map = {int(num) - 1: idx for idx, num in enumerate(numbers)}

            # Convert ranks to scores (inverse: rank 1 = score 1.0, rank N = score 0.1)
            reranked: List[Tuple[float, ChunkRecord]] = []
            for orig_idx, (orig_score, record) in enumerate(top_chunks):
                rank = rank_map.get(orig_idx, len(top_chunks))
                # Convert rank to score (1.0 for rank 0, decreasing)
                llm_score = max(0.1, 1.0 - (rank * 0.1))
                # Combine: 40% original, 60% LLM
                combined_score = 0.4 * orig_score + 0.6 * llm_score
                reranked.append((combined_score, record))

            reranked.sort(key=lambda item: item[0], reverse=True)
            remaining = scored_chunks[len(top_chunks) :]
            return reranked + remaining
    except Exception:
        pass

    # If LLM re-ranking fails, return original
    return scored_chunks


def _rerank_with_cross_encoder(
    question: str,
    scored_chunks: List[Tuple[float, ChunkRecord]],
    provider=None,
    top_n: int = 12,  # Reduced from 20 for faster reranking (optimization #6)
    skip_if_high_score: float = 0.85,  # Early exit if top score is high enough (optimization #3)
) -> List[Tuple[float, ChunkRecord]]:
    """
    Re-rank top chunks using cross-encoder for more accurate relevance scoring.
    Falls back to LLM re-ranking if cross-encoder unavailable, then to original scores.

    Optimization: Skips reranking if top similarity score is already high enough.
    """
    if not scored_chunks:
        return scored_chunks

    # Early exit: Skip reranking if top score is already very high (optimization #3)
    if scored_chunks and scored_chunks[0][0] >= skip_if_high_score:
        return scored_chunks

    # Early exit: Skip reranking if we have very few candidates
    if len(scored_chunks) <= 3:
        return scored_chunks

    # Take top N for re-ranking (to save computation)
    top_chunks = scored_chunks[: min(top_n, len(scored_chunks))]

    cross_encoder = _get_cross_encoder()
    if not cross_encoder:
        # Fallback to LLM re-ranking if cross-encoder unavailable
        if provider:
            return _rerank_with_llm(
                question, scored_chunks, provider, top_n=min(10, len(top_chunks))
            )
        return scored_chunks  # Return original if both unavailable

    try:
        # Prepare pairs for cross-encoder
        pairs = [(question, record.content) for _, record in top_chunks]

        # Get cross-encoder scores
        rerank_scores = cross_encoder.predict(pairs)

        # Normalize scores to 0-1
        if rerank_scores:
            min_score = float(min(rerank_scores))
            max_score = float(max(rerank_scores))
            if max_score > min_score:
                rerank_scores = [(s - min_score) / (max_score - min_score) for s in rerank_scores]
            else:
                rerank_scores = [1.0] * len(rerank_scores)

        # Combine original hybrid score (30%) with cross-encoder score (70%)
        reranked: List[Tuple[float, ChunkRecord]] = []
        for (orig_score, record), rerank_score in zip(top_chunks, rerank_scores):
            combined_score = 0.3 * orig_score + 0.7 * rerank_score
            reranked.append((combined_score, record))

        # Sort by combined score
        reranked.sort(key=lambda item: item[0], reverse=True)

        # Combine with remaining chunks (not re-ranked)
        remaining = scored_chunks[len(top_chunks) :]
        return reranked + remaining
    except Exception:
        # If cross-encoder fails, try LLM fallback
        if provider:
            return _rerank_with_llm(
                question, scored_chunks, provider, top_n=min(10, len(top_chunks))
            )
        return scored_chunks


def _extract_evidence_spans(
    question: str,
    chunk_content: str,
    max_spans: int = 3,
) -> List[Dict[str, object]]:
    """
    Extract evidence spans (relevant sentences/phrases) from chunk content.
    Returns list of spans with their positions and relevance indicators.
    """
    spans: List[Dict[str, object]] = []

    # Split into sentences
    sentences = re.split(r"[.!?]\s+", chunk_content)
    question_lower = question.lower()
    question_words = set(_tokenize(question))

    sentence_scores: List[Tuple[float, str, int]] = []
    for idx, sentence in enumerate(sentences):
        if not sentence.strip():
            continue

        sentence_lower = sentence.lower()
        sentence_words = set(_tokenize(sentence))

        # Score based on word overlap
        if question_words:
            overlap = len(question_words & sentence_words) / len(question_words)
        else:
            overlap = 0.0

        # Bonus for exact phrase matches
        if question_lower in sentence_lower:
            overlap += 0.3

        # Bonus for key terms
        key_terms = [
            "tank",
            "skill",
            "damage",
            "hp",
            "speed",
            "artifact",
            "garage",
            "map",
            "outpost",
        ]
        for term in key_terms:
            if term in sentence_lower:
                overlap += 0.1

        sentence_scores.append((overlap, sentence, idx))

    # Sort by score and take top spans
    sentence_scores.sort(key=lambda x: x[0], reverse=True)

    for score, sentence, idx in sentence_scores[:max_spans]:
        if score > 0.1:  # Only include relevant spans
            # Find position in original content
            start_pos = chunk_content.find(sentence)
            end_pos = start_pos + len(sentence) if start_pos >= 0 else -1

            spans.append(
                {
                    "text": sentence.strip(),
                    "score": float(score),
                    "start_pos": start_pos if start_pos >= 0 else 0,
                    "end_pos": end_pos if end_pos >= 0 else len(sentence),
                    "sentence_index": idx,
                }
            )

    return spans


def _filter_chunks_by_evidence(
    question: str,
    scored_chunks: List[Tuple[float, ChunkRecord]],
    min_evidence_score: float = 0.15,
    keep_top_n: int = 5,
) -> List[Tuple[float, ChunkRecord]]:
    """
    Filter chunks that have at least one relevant evidence span.
    Chunks without sufficient evidence are demoted or removed.

    Args:
        question: The question being asked
        scored_chunks: List of (score, ChunkRecord) tuples
        min_evidence_score: Minimum evidence score to keep a chunk (0-1)
        keep_top_n: Always keep this many top chunks regardless of evidence

    Returns:
        Filtered list of (score, ChunkRecord) tuples
    """
    if not scored_chunks:
        return scored_chunks

    filtered: List[Tuple[float, ChunkRecord]] = []

    for idx, (score, record) in enumerate(scored_chunks):
        # Always keep top N chunks
        if idx < keep_top_n:
            filtered.append((score, record))
            continue

        # Check if chunk has relevant evidence
        evidence_spans = _extract_evidence_spans(question, record.content, max_spans=3)

        if evidence_spans:
            # Check if any span meets the minimum score
            max_evidence_score = max(span["score"] for span in evidence_spans)
            if max_evidence_score >= min_evidence_score:
                filtered.append((score, record))
            # If evidence is weak, demote the chunk
            elif max_evidence_score >= min_evidence_score * 0.5:
                # Reduce score by 50% for weak evidence
                filtered.append((score * 0.5, record))

    # Sort by (potentially adjusted) scores
    filtered.sort(key=lambda item: item[0], reverse=True)
    return filtered


def _select_top_chunks(
    scored: List[Tuple[float, ChunkRecord]],
    *,
    top_k: int,
    per_doc_limit: Optional[int] = None,
) -> List[Tuple[float, ChunkRecord]]:
    selected: List[Tuple[float, ChunkRecord]] = []
    counts: Dict[str, int] = {}
    if per_doc_limit and per_doc_limit > 0:
        for score, record in scored:
            if counts.get(record.doc_id, 0) >= per_doc_limit:
                continue
            selected.append((score, record))
            counts[record.doc_id] = counts.get(record.doc_id, 0) + 1
            if len(selected) >= top_k:
                break
    if len(selected) < top_k:
        for score, record in scored:
            if (score, record) in selected:
                continue
            selected.append((score, record))
            if len(selected) >= top_k:
                break
    return selected


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_top_chunks(
    doc_ids: Sequence[str],
    question: str,
    *,
    provider,
    top_k: int = 8,
    per_doc_limit: Optional[int] = None,
    use_rrf: bool = True,
    filter_by_evidence: bool = True,
) -> List[Dict[str, object]]:
    if not doc_ids:
        raise ValueError("At least one doc_id is required.")

    unique_ids = list(dict.fromkeys(doc_ids))
    all_chunks: List[ChunkRecord] = []
    for doc_id in unique_ids:
        all_chunks.extend(load_doc_chunks(doc_id))
    if not all_chunks:
        raise ValueError("No chunks found for the selected documents. Verify they were indexed.")

    # Try to embed the question, but handle failures gracefully
    question_embedding = None
    try:
        question_embedding = _embed_texts(provider, [question], use_cache=True)[0]
        # Normalize question embedding for faster cosine similarity (optimization #4)
        question_embedding = _normalize_vector(question_embedding)
    except Exception:
        # Embedding failed - will use text-based scoring
        pass

    vectors = _load_chunk_vectors(
        unique_ids, normalize=True
    )  # Pre-normalize vectors (optimization #4)
    scored = _score_chunks(
        question_embedding, all_chunks, vectors, provider, question_text=question, use_rrf=use_rrf
    )

    # Apply evidence filtering (after RRF fusion, before re-ranking)
    if filter_by_evidence:
        scored = _filter_chunks_by_evidence(
            question, scored, min_evidence_score=0.15, keep_top_n=10
        )

    # Re-rank with cross-encoder (take top 50 for re-ranking, with LLM fallback)
    reranked = _rerank_with_cross_encoder(
        question, scored, provider=provider, top_n=min(12, len(scored))
    )

    selected = _select_top_chunks(
        reranked,
        top_k=top_k,
        per_doc_limit=per_doc_limit or (2 if len(unique_ids) > 1 else None),
    )

    # Add evidence spans to results
    results = []
    for score, record in selected:
        evidence_spans = _extract_evidence_spans(question, record.content, max_spans=3)
        results.append(
            {
                "doc_id": record.doc_id,
                "chunk_id": record.chunk_id,
                "content": record.content,
                "score": score,
                "evidence_spans": evidence_spans,
            }
        )

    return results


def _contains_vietnamese(text: str) -> bool:
    """Check if text contains Vietnamese characters."""
    vietnamese_chars = re.compile(
        r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", re.IGNORECASE
    )
    return bool(vietnamese_chars.search(text))


def _try_translate_chunk(provider, content: str, max_length: int = 500) -> str:
    """Try to translate Vietnamese content to English using LLM."""
    if not _contains_vietnamese(content):
        return content  # No Vietnamese, return as-is

    try:
        # Truncate if too long
        content_to_translate = (
            content[:max_length] + "..." if len(content) > max_length else content
        )

        translation_prompt = (
            f"Translate the following Vietnamese text to English. "
            f"Keep the structure and formatting. If there's English text, keep it as-is.\n\n"
            f"Text to translate:\n{content_to_translate}\n\n"
            f"English translation:"
        )

        translated = provider.llm(prompt=translation_prompt)
        return translated.strip()
    except Exception:
        # Translation failed, return original with note
        return f"{content}\n\n*[Note: Vietnamese content - translation unavailable without valid API key]*"


def _build_prompt(doc_title: str, context_blocks: List[str], question: str) -> str:
    context = "\n\n".join(f"[Chunk {idx + 1}]\n{block}" for idx, block in enumerate(context_blocks))
    return (
        "You are an expert assistant answering questions about a Game Design Document. "
        "Use ONLY the provided context. If the answer is missing, say you don't know.\n\n"
        "IMPORTANT: Use two-step reasoning:\n\n"
        "**STEP A: EXTRACT EVIDENCE**\n"
        "First, identify the most relevant sentences or phrases from the context that directly answer the question. "
        "Cite the chunk numbers where you found this evidence.\n"
        "Format: 'From Chunk X: [relevant sentence]'\n\n"
        "**STEP B: PROVIDE ANSWER**\n"
        "Based on the evidence extracted in Step A, provide a clear, concise answer.\n\n"
        "LANGUAGE REQUIREMENTS:\n"
        "1. The context may contain Vietnamese text - you MUST translate all Vietnamese content to English in your English answer.\n"
        "2. You MUST provide your answer in BOTH English and Vietnamese.\n"
        "3. Format your response EXACTLY as follows:\n\n"
        "**English:**\n"
        "Evidence:\n[Evidence from chunks with citations]\n\n"
        "Answer:\n[Your answer in English - translate any Vietnamese text from context]\n\n"
        "**Vietnamese (Tiếng Việt):**\n"
        "Bằng chứng:\n[Bằng chứng từ các đoạn với trích dẫn]\n\n"
        "Trả lời:\n[Your answer in Vietnamese]\n\n"
        f"Document: {doc_title}\n\n"
        f"Context:\n{context}\n\n"
        f"Question: {question}\n\n"
        "Response (follow the two-step format with evidence extraction first, then answer in both English and Vietnamese):"
    )


def ask_with_chunks(
    doc_id: str,
    question: str,
    *,
    provider,
    top_k: int = 8,
    use_rrf: bool = True,
    filter_by_evidence: bool = True,
) -> Dict[str, object]:
    metadata = get_doc_metadata(doc_id)
    if metadata is None:
        raise ValueError(f"Document '{doc_id}' not found. Please index it before asking questions.")

    chunks = load_doc_chunks(doc_id)
    if not chunks:
        raise ValueError(f"No chunks found for '{doc_id}'. Try re-indexing the document first.")

    # Try to embed the question, but handle failures gracefully
    question_embedding = None
    try:
        question_embedding = _embed_texts(provider, [question], use_cache=True)[0]
        # Normalize question embedding for faster cosine similarity (optimization #4)
        question_embedding = _normalize_vector(question_embedding)
    except Exception:
        # Embedding failed - will use text-based scoring
        pass

    vectors = _load_chunk_vectors(
        [doc_id], normalize=True
    )  # Pre-normalize vectors (optimization #4)
    scored = _score_chunks(
        question_embedding, chunks, vectors, provider, question_text=question, use_rrf=use_rrf
    )

    # Apply evidence filtering
    if filter_by_evidence:
        scored = _filter_chunks_by_evidence(
            question, scored, min_evidence_score=0.15, keep_top_n=10
        )

    # Re-rank with cross-encoder (take top 50 for re-ranking)
    reranked = _rerank_with_cross_encoder(
        question, scored, provider=provider, top_n=min(12, len(scored))
    )
    top_records = [record for _, record in reranked[:top_k]]
    prompt = _build_prompt(
        metadata.get("file_path", doc_id), [r.content for r in top_records], question
    )

    try:
        answer_text = provider.llm(prompt=prompt)
        answer = answer_text.strip()

        # Ensure answer has both English and Vietnamese sections
        if "**English:**" not in answer and "**Vietnamese" not in answer:
            # If LLM didn't follow format, wrap the answer
            answer = f"**English:**\n{answer}\n\n**Vietnamese (Tiếng Việt):**\n[Translation pending - please configure API key for full bilingual support]"
    except Exception as e:
        # Fallback to chunks if LLM fails
        answer = f"**English:**\n\nError generating answer: {str(e)}\n\n**Vietnamese (Tiếng Việt):**\n\nLỗi khi tạo câu trả lời: {str(e)}"

    context_payload = []
    for score, record in reranked[:top_k]:
        evidence_spans = _extract_evidence_spans(question, record.content, max_spans=3)
        context_payload.append(
            {
                "chunk_id": record.chunk_id,
                "doc_id": record.doc_id,
                "content": record.content,
                "score": score,
                "evidence_spans": evidence_spans,
            }
        )

    return {
        "answer": answer,
        "doc_id": doc_id,
        "file_path": metadata.get("file_path"),
        "context": context_payload,
    }


def ask_across_docs(
    doc_ids: Sequence[str],
    question: str,
    *,
    provider,
    top_k: int = 8,
    per_doc_limit: Optional[int] = 2,
    use_rrf: bool = True,
    filter_by_evidence: bool = True,
) -> Dict[str, object]:
    if not doc_ids:
        raise ValueError("At least one doc_id is required.")

    unique_ids = list(dict.fromkeys(doc_ids))
    metadata_map = {doc_id: get_doc_metadata(doc_id) or {} for doc_id in unique_ids}

    all_chunks: List[ChunkRecord] = []
    for doc_id in unique_ids:
        all_chunks.extend(load_doc_chunks(doc_id))
    if not all_chunks:
        raise ValueError("No chunks found for the selected documents. Verify they were indexed.")

    # Try to embed the question, but handle failures gracefully
    question_embedding = None
    try:
        question_embedding = _embed_texts(provider, [question], use_cache=True)[0]
        # Normalize question embedding for faster cosine similarity (optimization #4)
        question_embedding = _normalize_vector(question_embedding)
    except Exception:
        # Embedding failed - will use text-based scoring
        pass

    vectors = _load_chunk_vectors(
        unique_ids, normalize=True
    )  # Pre-normalize vectors (optimization #4)
    scored = _score_chunks(
        question_embedding, all_chunks, vectors, provider, question_text=question, use_rrf=use_rrf
    )

    # Apply evidence filtering (after RRF fusion, before re-ranking)
    if filter_by_evidence:
        scored = _filter_chunks_by_evidence(
            question, scored, min_evidence_score=0.15, keep_top_n=10
        )

    # Re-rank with cross-encoder (take top 50 for re-ranking, with LLM fallback)
    reranked = _rerank_with_cross_encoder(
        question, scored, provider=provider, top_n=min(12, len(scored))
    )

    selected = _select_top_chunks(
        reranked,
        top_k=top_k,
        per_doc_limit=per_doc_limit or (2 if len(unique_ids) > 1 else None),
    )

    prompt_docs = ", ".join(
        metadata_map.get(doc_id, {}).get("file_path", doc_id) or doc_id for doc_id in unique_ids
    )
    prompt = _build_prompt(prompt_docs, [record.content for _, record in selected], question)

    # Add evidence spans to context payload
    context_payload = []
    for score, record in selected:
        evidence_spans = _extract_evidence_spans(question, record.content, max_spans=3)
        context_payload.append(
            {
                "doc_id": record.doc_id,
                "chunk_id": record.chunk_id,
                "content": record.content,
                "score": score,
                "evidence_spans": evidence_spans,
            }
        )

    # Try to get LLM answer, but provide chunks as fallback
    try:
        answer_text = provider.llm(prompt=prompt)
        answer = answer_text.strip()

        # Ensure answer has both English and Vietnamese sections
        if "**English:**" not in answer and "**Vietnamese" not in answer:
            # If LLM didn't follow format, wrap the answer
            answer = f"**English:**\n{answer}\n\n**Vietnamese (Tiếng Việt):**\n[Translation pending - please configure API key for full bilingual support]"
    except Exception as e:
        # Log the actual error for debugging
        error_type = type(e).__name__
        error_details = str(e)

        # Check if it's an API key issue
        is_api_key_error = (
            "401" in error_details
            or "API key" in error_details.lower()
            or "authentication" in error_details.lower()
            or "invalid_api_key" in error_details.lower()
            or "api_key" in error_type.lower()
        )
        # If LLM fails, create a summary from chunks
        error_msg = str(e)

        # Provide helpful error message about API key
        api_key_note = ""
        if is_api_key_error:
            api_key_note = (
                "\n\n**API Key Configuration Required:**\n"
                "The LLM generation failed because the API key is missing or invalid.\n"
                "Please check your .env file and ensure you have set either:\n"
                "- DASHSCOPE_API_KEY=your_key_here\n"
                "- OR QWEN_API_KEY=your_key_here\n\n"
                "**Cấu hình API Key cần thiết:**\n"
                "Không thể tạo tóm tắt bằng AI vì API key bị thiếu hoặc không hợp lệ.\n"
                "Vui lòng kiểm tra file .env và đảm bảo bạn đã thiết lập:\n"
                "- DASHSCOPE_API_KEY=your_key_here\n"
                "- HOẶC QWEN_API_KEY=your_key_here\n"
            )

        if selected:
            # Filter out chunks that are just analysis metadata
            useful_chunks = []
            for score, record in selected:
                content = record.content.strip()
                # Skip chunks that are primarily analysis metadata
                is_analysis = (
                    content.startswith("Table Analysis:")
                    or content.startswith("Image Content Analysis:")
                    or content.startswith("Image Path:")
                    or ("Image Path:" in content and len(content.split("\n")) < 5)
                    or (
                        content.count("Image Path:") > 0
                        and len(
                            [
                                line
                                for line in content.split("\n")
                                if line.strip()
                                and not line.startswith("Image")
                                and not line.startswith("Caption")
                            ]
                        )
                        < 3
                    )
                )

                # Prefer actual text content
                if not is_analysis and len(content) > 50:
                    useful_chunks.append((score, record))
                elif not is_analysis and len(content) > 30:  # Keep short but real text
                    useful_chunks.append((score, record))

            # If no useful chunks found, use all chunks but mark them
            if not useful_chunks:
                useful_chunks = selected[:5]

            if useful_chunks:
                chunk_summaries = []
                chunk_summaries_en = []  # English translations

                for score, record in useful_chunks[:5]:  # Top 5 useful chunks
                    content = record.content.strip()
                    # Show more content for text chunks
                    if len(content) > 300:
                        content_preview = content[:300] + "..."
                    else:
                        content_preview = content

                    doc_name = Path(record.doc_id).name if "/" in record.doc_id else record.doc_id
                    chunk_summaries.append(f"**From {doc_name}:**\n{content_preview}")

                    # Try to translate for English section if contains Vietnamese
                    if _contains_vietnamese(content_preview) and not is_api_key_error:
                        try:
                            translated = _try_translate_chunk(
                                provider, content_preview, max_length=300
                            )
                            chunk_summaries_en.append(f"**From {doc_name}:**\n{translated}")
                        except Exception:
                            chunk_summaries_en.append(
                                f"**From {doc_name}:**\n{content_preview}\n\n*[Vietnamese content - translation requires valid API key]*"
                            )
                    else:
                        chunk_summaries_en.append(f"**From {doc_name}:**\n{content_preview}")

                # Format in bilingual structure
                # Use translated versions for English section if available
                english_chunks = chunk_summaries_en if chunk_summaries_en else chunk_summaries
                english_section = (
                    f"**English:**\n\n"
                    f"**Retrieved relevant information from {len(useful_chunks)} chunks:**\n\n"
                    + "\n\n".join(english_chunks)
                )
                if len(useful_chunks) > 5:
                    english_section += f"\n\n... and {len(useful_chunks) - 5} more relevant chunks."

                if is_api_key_error:
                    english_section += (
                        "\n\n*Note: The content above may contain Vietnamese text. "
                        "To get English translations and AI-generated summaries, please configure your API key in .env file.*"
                    )

                vietnamese_section = (
                    f"**Vietnamese (Tiếng Việt):**\n\n"
                    f"**Đã tìm thấy {len(useful_chunks)} đoạn thông tin liên quan:**\n\n"
                    + "\n\n".join(chunk_summaries)
                )
                if len(useful_chunks) > 5:
                    vietnamese_section += (
                        f"\n\n... và {len(useful_chunks) - 5} đoạn thông tin liên quan khác."
                    )

                answer = english_section + "\n\n" + vietnamese_section
                if api_key_note:
                    answer += "\n\n" + api_key_note
            else:
                # Fallback: show any chunks we have
                chunk_summaries = []
                for score, record in selected[:3]:
                    content_preview = (
                        record.content[:200] + "..."
                        if len(record.content) > 200
                        else record.content
                    )
                    chunk_summaries.append(
                        f"**From {Path(record.doc_id).name if '/' in record.doc_id else record.doc_id}:**\n{content_preview}"
                    )

                english_section = (
                    f"**English:**\n\n"
                    f"**Retrieved {len(selected)} chunks:**\n\n"
                    + "\n\n".join(chunk_summaries)
                    + "\n\n*Note: The content above may contain Vietnamese text. "
                    "To get English translations and AI-generated summaries, please configure your API key in .env file.*"
                )
                vietnamese_section = (
                    f"**Vietnamese (Tiếng Việt):**\n\n"
                    f"**Đã tìm thấy {len(selected)} đoạn thông tin:**\n\n"
                    + "\n\n".join(chunk_summaries)
                )
                answer = english_section + "\n\n" + vietnamese_section
                if api_key_note:
                    answer += "\n\n" + api_key_note

            answer += (
                "\n\n*Note: LLM generation unavailable. Showing retrieved chunks. "
                "To get AI-generated summaries with English translations, please configure your API key in .env file.*\n"
            )
            answer += (
                "*Lưu ý: Không thể tạo tóm tắt bằng AI. Đang hiển thị các đoạn thông tin đã tìm thấy. "
                "Để có tóm tắt tự động với bản dịch tiếng Anh, vui lòng cấu hình API key trong file .env.*"
            )
        else:
            answer = f"**English:**\n\nError: Could not retrieve relevant chunks. {error_msg}\n\n"
            answer += f"**Vietnamese (Tiếng Việt):**\n\nLỗi: Không thể tìm thấy các đoạn thông tin liên quan. {error_msg}"

    return {
        "answer": answer,
        "doc_ids": unique_ids,
        "context": context_payload,
    }
