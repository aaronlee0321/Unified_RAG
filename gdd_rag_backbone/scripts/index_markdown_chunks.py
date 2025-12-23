"""
Script to index markdown chunks with embeddings and store in separate location.

This script:
1. Loads chunks from rag_storage_md/
2. Embeds each chunk using the embedding function
3. Stores chunks and vectors in rag_storage_md_indexed/
4. Updates document status
"""

import argparse
import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional

from gdd_rag_backbone.llm_providers import QwenProvider, make_embedding_func
from gdd_rag_backbone.config import PROJECT_ROOT


# Separate working directory for markdown chunks
MARKDOWN_WORKING_DIR = PROJECT_ROOT / "rag_storage_md_indexed"
MARKDOWN_CHUNKS_DIR = PROJECT_ROOT / "rag_storage_md"

# Storage file paths (separate from main rag_storage)
CHUNKS_PATH = MARKDOWN_WORKING_DIR / "kv_store_text_chunks.json"
VDB_CHUNKS_PATH = MARKDOWN_WORKING_DIR / "vdb_chunks.json"
STATUS_PATH = MARKDOWN_WORKING_DIR / "kv_store_doc_status.json"


def load_markdown_chunks(doc_id: str) -> List[Dict]:
    """
    Load chunks from markdown chunking output.
    
    Args:
        doc_id: Document ID
    
    Returns:
        List of chunk dictionaries
    """
    chunks_file = MARKDOWN_CHUNKS_DIR / doc_id / f"{doc_id}_chunks.json"
    
    if not chunks_file.exists():
        return []
    
    try:
        with open(chunks_file, 'r', encoding='utf-8') as f:
            chunks = json.load(f)
        return chunks
    except Exception as e:
        print(f"  ✗ ERROR loading chunks from {chunks_file}: {e}")
        return []


def load_existing_chunks() -> Dict:
    """Load existing chunks from storage."""
    if not CHUNKS_PATH.exists():
        return {}
    
    try:
        with open(CHUNKS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def load_existing_vectors() -> Dict:
    """Load existing vectors from storage."""
    if not VDB_CHUNKS_PATH.exists():
        return {"data": []}
    
    try:
        with open(VDB_CHUNKS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if "data" not in data:
                return {"data": []}
            return data
    except Exception:
        return {"data": []}


def load_existing_status() -> Dict:
    """Load existing document status."""
    if not STATUS_PATH.exists():
        return {}
    
    try:
        with open(STATUS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_chunks(chunks_data: Dict) -> None:
    """Save chunks to storage."""
    MARKDOWN_WORKING_DIR.mkdir(parents=True, exist_ok=True)
    with open(CHUNKS_PATH, 'w', encoding='utf-8') as f:
        json.dump(chunks_data, f, ensure_ascii=False, indent=2)


def save_vectors(vectors_data: Dict) -> None:
    """Save vectors to storage."""
    MARKDOWN_WORKING_DIR.mkdir(parents=True, exist_ok=True)
    with open(VDB_CHUNKS_PATH, 'w', encoding='utf-8') as f:
        json.dump(vectors_data, f, ensure_ascii=False, indent=2)


def save_status(status_data: Dict) -> None:
    """Save document status."""
    MARKDOWN_WORKING_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATUS_PATH, 'w', encoding='utf-8') as f:
        json.dump(status_data, f, ensure_ascii=False, indent=2)


async def index_chunks_for_doc(
    doc_id: str,
    embedding_func,
    dry_run: bool = False
) -> tuple[bool, str]:
    """
    Index chunks for a single document.
    
    Args:
        doc_id: Document ID
        embedding_func: Embedding function
        dry_run: If True, don't actually index
    
    Returns:
        (success, message) tuple
    """
    # Load markdown chunks
    chunks = load_markdown_chunks(doc_id)
    
    if not chunks:
        return False, f"No chunks found for {doc_id}"
    
    if dry_run:
        return True, f"[DRY RUN] Would index {len(chunks)} chunks for {doc_id}"
    
    print(f"  Processing {len(chunks)} chunks...")
    
    # Load existing storage
    existing_chunks = load_existing_chunks()
    existing_vectors = load_existing_vectors()
    existing_status = load_existing_status()
    
    # Remove existing chunks for this doc_id (to allow re-indexing)
    chunks_to_remove = [
        chunk_id for chunk_id, data in existing_chunks.items()
        if isinstance(data, dict) and data.get("full_doc_id") == doc_id
    ]
    for chunk_id in chunks_to_remove:
        del existing_chunks[chunk_id]
    
    # Remove existing vectors for this doc_id
    existing_vectors["data"] = [
        entry for entry in existing_vectors["data"]
        if entry.get("full_doc_id") != doc_id
    ]
    
    # Process each chunk
    chunk_count = 0
    vector_count = 0
    
    # Batch embeddings for efficiency
    chunk_contents = [chunk["content"] for chunk in chunks]
    
    try:
        # Generate embeddings
        print(f"  Generating embeddings for {len(chunk_contents)} chunks...")
        # EmbeddingFunc from LightRAG is async, so we need to await it
        # It wraps the provider.embed() call internally
        if hasattr(embedding_func, '__call__'):
            # Try async call first (EmbeddingFunc)
            try:
                embeddings = await embedding_func(chunk_contents)
            except TypeError:
                # Fallback to sync call
                embeddings = embedding_func(chunk_contents)
        else:
            # Direct provider call (should be sync)
            embeddings = embedding_func(chunk_contents)
        
        if len(embeddings) != len(chunks):
            raise ValueError(f"Expected {len(chunks)} embeddings, got {len(embeddings)}")
        
        # Store chunks and vectors
        for chunk, embedding in zip(chunks, embeddings):
            chunk_id = chunk["chunk_id"]
            full_chunk_id = f"{doc_id}_{chunk_id}"
            
            # Store chunk content
            existing_chunks[full_chunk_id] = {
                "full_doc_id": doc_id,
                "content": chunk["content"],
                "metadata": chunk.get("metadata", {}),
                "parent_header": chunk.get("parent_header"),
                "part_number": chunk.get("part_number"),
                "token_count": chunk.get("token_count", 0)
            }
            
            # Store vector
            existing_vectors["data"].append({
                "__id__": full_chunk_id,
                "full_doc_id": doc_id,
                "vector": embedding,
                "chunk_id": chunk_id
            })
            
            chunk_count += 1
            vector_count += 1
        
        # Save all data
        save_chunks(existing_chunks)
        save_vectors(existing_vectors)
        
        # Update document status
        now = datetime.now(timezone.utc).isoformat()
        existing_status[doc_id] = {
            "doc_id": doc_id,
            "file_path": str(MARKDOWN_CHUNKS_DIR / doc_id / f"{doc_id}_chunks.json"),
            "file_name": f"{doc_id}_chunks.json",
            "status": "indexed",
            "doc_type": "markdown",
            "created_at": existing_status.get(doc_id, {}).get("created_at", now),
            "updated_at": now,
            "chunks_count": chunk_count,
            "chunks_list": [chunk["chunk_id"] for chunk in chunks]
        }
        save_status(existing_status)
        
        return True, f"✓ Indexed {chunk_count} chunks for {doc_id}"
    
    except Exception as e:
        return False, f"✗ Failed to index {doc_id}: {e}"


def find_indexed_doc_ids() -> List[str]:
    """Find all document IDs that have been chunked."""
    if not MARKDOWN_CHUNKS_DIR.exists():
        return []
    
    doc_ids = []
    for doc_dir in MARKDOWN_CHUNKS_DIR.iterdir():
        if doc_dir.is_dir():
            chunks_file = doc_dir / f"{doc_dir.name}_chunks.json"
            if chunks_file.exists():
                doc_ids.append(doc_dir.name)
    
    return sorted(doc_ids)


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Index markdown chunks with embeddings"
    )
    parser.add_argument(
        "--doc-id",
        type=str,
        help="Document ID to index (if not provided, indexes all found documents)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually doing it"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip documents that are already indexed"
    )
    args = parser.parse_args()
    
    print("=" * 70)
    print("MARKDOWN CHUNKS INDEXING")
    print("=" * 70)
    print(f"Chunks directory: {MARKDOWN_CHUNKS_DIR}")
    print(f"Index storage: {MARKDOWN_WORKING_DIR}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 70)
    print()
    
    # Find documents to index
    if args.doc_id:
        doc_ids = [args.doc_id]
    else:
        doc_ids = find_indexed_doc_ids()
    
    if not doc_ids:
        print("No documents found to index!")
        return 1
    
    print(f"Found {len(doc_ids)} document(s) to index")
    print()
    
    # Check existing status
    existing_status = load_existing_status()
    existing_doc_ids = set(existing_status.keys())
    
    if args.skip_existing:
        doc_ids = [doc_id for doc_id in doc_ids if doc_id not in existing_doc_ids]
        if not doc_ids:
            print("All documents are already indexed. Use --skip-existing=false to re-index anyway.")
            return 0
        print(f"After filtering, {len(doc_ids)} document(s) need indexing")
        print()
    
    # Initialize embedding function
    print("Initializing embedding provider...")
    provider = QwenProvider()
    embedding_func = make_embedding_func(provider)
    print("✓ Embedding provider ready")
    print()
    
    # Process each document
    print("STARTING INDEXING")
    print("=" * 70)
    
    success_count = 0
    fail_count = 0
    
    for i, doc_id in enumerate(doc_ids, 1):
        print(f"[{i}/{len(doc_ids)}] {doc_id}")
        
        success, message = await index_chunks_for_doc(
            doc_id=doc_id,
            embedding_func=embedding_func,
            dry_run=args.dry_run
        )
        
        print(f"  {message}")
        
        if success:
            success_count += 1
        else:
            fail_count += 1
        
        print()
    
    print("=" * 70)
    print(f"COMPLETE: {success_count} succeeded, {fail_count} failed")
    print("=" * 70)
    
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

