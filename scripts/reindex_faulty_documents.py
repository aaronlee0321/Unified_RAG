"""
Re-chunk, re-embed, and re-index only the faulty documents (those with 1-2 chunks).

This script:
1. Identifies documents with suspiciously low chunk counts (1-2 chunks)
2. Finds their markdown files in gdd_data/markdown
3. Deletes existing chunks from Supabase
4. Re-chunks the markdown
5. Re-generates embeddings
6. Re-indexes to Supabase
"""

import sys
import os
from pathlib import Path
from typing import List, Dict, Set, Optional
from collections import defaultdict

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.storage.supabase_client import get_supabase_client
from backend.storage.gdd_supabase_storage import index_gdd_chunks_to_supabase
from gdd_rag_backbone.llm_providers import QwenProvider
from gdd_rag_backbone.markdown_chunking import MarkdownChunker
from gdd_rag_backbone.scripts.chunk_markdown_files import generate_doc_id
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def normalize_for_matching(text: str) -> str:
    """Normalize text for fuzzy matching."""
    if not text:
        return ""
    return text.lower().replace("_", "").replace("-", "").replace(" ", "").replace("(", "").replace(")", "").replace("[", "").replace("]", "").replace(",", "")


def find_faulty_documents(max_chunks: int = 2) -> List[Dict]:
    """
    Find documents with suspiciously low chunk counts.
    
    Args:
        max_chunks: Maximum chunk count to consider as faulty (default: 2)
    
    Returns:
        List of document info dicts with doc_id, name, actual_chunks, db_chunks_count
    """
    logger.info("=" * 80)
    logger.info("IDENTIFYING FAULTY DOCUMENTS")
    logger.info("=" * 80)
    
    try:
        client = get_supabase_client(use_service_key=True)
        
        # Get all chunks grouped by doc_id
        logger.info("Fetching chunk counts from gdd_chunks table...")
        result = client.table('gdd_chunks').select('doc_id').execute()
        
        chunk_counts = defaultdict(int)
        for row in (result.data or []):
            doc_id = row.get('doc_id')
            if doc_id:
                chunk_counts[doc_id] += 1
        
        logger.info(f"Found chunks for {len(chunk_counts)} unique doc_ids")
        
        # Get documents from gdd_documents table
        logger.info("Fetching documents from gdd_documents table...")
        docs_result = client.table('gdd_documents').select('doc_id, name, chunks_count').execute()
        all_docs = {row.get('doc_id'): row for row in (docs_result.data or [])}
        
        logger.info(f"Found {len(all_docs)} documents in gdd_documents table")
        
        # Find faulty documents
        faulty_docs = []
        for doc_id, actual_chunks in chunk_counts.items():
            if actual_chunks <= max_chunks:
                doc_info = all_docs.get(doc_id, {})
                faulty_docs.append({
                    'doc_id': doc_id,
                    'name': doc_info.get('name', 'N/A'),
                    'actual_chunks': actual_chunks,
                    'db_chunks_count': doc_info.get('chunks_count', 0)
                })
        
        # Also check documents with 0 chunks but have markdown_content
        for doc_id, doc_info in all_docs.items():
            if doc_id not in chunk_counts:
                # Check if document has markdown_content (should be indexed)
                markdown_result = client.table('gdd_documents').select('markdown_content').eq('doc_id', doc_id).execute()
                if markdown_result.data and markdown_result.data[0].get('markdown_content'):
                    faulty_docs.append({
                        'doc_id': doc_id,
                        'name': doc_info.get('name', 'N/A'),
                        'actual_chunks': 0,
                        'db_chunks_count': doc_info.get('chunks_count', 0)
                    })
        
        logger.info(f"\n[RESULT] Found {len(faulty_docs)} faulty documents:")
        for doc in faulty_docs:
            logger.info(f"  - {doc['doc_id']}: {doc['actual_chunks']} chunks (DB says: {doc['db_chunks_count']})")
        
        return faulty_docs
        
    except Exception as e:
        logger.error(f"Error finding faulty documents: {e}")
        import traceback
        traceback.print_exc()
        return []


def find_markdown_file(doc_id: str, markdown_dir: Path) -> Optional[Path]:
    """
    Find markdown file for a given doc_id.
    
    Uses fuzzy matching to handle variations in naming.
    """
    if not markdown_dir.exists():
        logger.error(f"Markdown directory does not exist: {markdown_dir}")
        return None
    
    md_files = list(markdown_dir.glob("*.md"))
    doc_id_normalized = normalize_for_matching(doc_id)
    
    # Try exact match first (generate doc_id from filename and compare)
    for md_file in md_files:
        generated_doc_id = generate_doc_id(md_file)
        if generated_doc_id == doc_id:
            return md_file
    
    # Try fuzzy matching
    best_match = None
    best_score = 0
    
    for md_file in md_files:
        generated_doc_id = generate_doc_id(md_file)
        generated_normalized = normalize_for_matching(generated_doc_id)
        filename_normalized = normalize_for_matching(md_file.stem)
        
        # Calculate match score
        if doc_id_normalized == generated_normalized:
            return md_file  # Perfect match
        
        # Check if doc_id is contained in filename or vice versa
        if doc_id_normalized in generated_normalized or generated_normalized in doc_id_normalized:
            score = min(len(doc_id_normalized), len(generated_normalized)) / max(len(doc_id_normalized), len(generated_normalized))
            if score > best_score:
                best_score = score
                best_match = md_file
    
    if best_match and best_score > 0.7:  # 70% similarity threshold
        logger.info(f"  Fuzzy matched: {doc_id} -> {best_match.name} (score: {best_score:.2f})")
        return best_match
    
    return None


def delete_chunks_for_doc(doc_id: str) -> int:
    """Delete all chunks for a document from Supabase."""
    try:
        client = get_supabase_client(use_service_key=True)
        
        # Delete chunks
        result = client.table('gdd_chunks').delete().eq('doc_id', doc_id).execute()
        deleted_count = len(result.data) if result.data else 0
        
        logger.info(f"  Deleted {deleted_count} chunks for {doc_id}")
        return deleted_count
        
    except Exception as e:
        logger.error(f"  Error deleting chunks for {doc_id}: {e}")
        return 0


def reindex_markdown_file(md_path: Path, doc_id: str) -> Dict:
    """
    Re-chunk, re-embed, and re-index a markdown file.
    
    Args:
        md_path: Path to markdown file
        doc_id: Document ID
    
    Returns:
        Dict with status and message
    """
    try:
        logger.info(f"\n{'='*80}")
        logger.info(f"RE-INDEXING: {md_path.name}")
        logger.info(f"Doc ID: {doc_id}")
        logger.info(f"{'='*80}")
        
        # Read markdown content
        logger.info("Reading markdown file...")
        markdown_content = md_path.read_text(encoding='utf-8')
        logger.info(f"  Read {len(markdown_content)} characters")
        
        # Chunk the markdown
        logger.info("Chunking markdown...")
        chunker = MarkdownChunker()
        chunks = chunker.chunk_document(
            markdown_content=markdown_content,
            doc_id=doc_id,
            filename=md_path.name,
        )
        logger.info(f"  Created {len(chunks)} chunks")
        
        if len(chunks) == 0:
            return {
                'status': 'error',
                'message': 'No chunks created from markdown'
            }
        
        # Convert MarkdownChunk objects to dictionaries
        chunks_dicts = []
        for chunk in chunks:
            # Make chunk_id globally unique by prepending doc_id
            # chunk.chunk_id is like "chunk_001", we need "{doc_id}_chunk_001"
            raw_chunk_id = chunk.chunk_id
            full_chunk_id = f"{doc_id}_{raw_chunk_id}"
            
            chunk_dict = {
                'chunk_id': full_chunk_id,  # Use full format for global uniqueness
                'content': chunk.content,
                'doc_id': chunk.doc_id,
                'metadata': chunk.metadata,
                'section': chunk.metadata.get('section_header', ''),
            }
            chunks_dicts.append(chunk_dict)
        
        # Generate PDF filename (for pdf_storage_path)
        pdf_filename = md_path.stem.replace(' ', '_').replace('[', '').replace(']', '').replace(',', '').replace('(', '').replace(')', '')
        pdf_filename = pdf_filename.replace('__', '_').strip('_') + '.pdf'
        
        # Index to Supabase
        logger.info("Generating embeddings and indexing to Supabase...")
        provider = QwenProvider()
        index_gdd_chunks_to_supabase(
            doc_id=doc_id,
            chunks=chunks_dicts,
            provider=provider,
            markdown_content=markdown_content,
            pdf_storage_path=pdf_filename
        )
        logger.info(f"  ✅ Successfully indexed {len(chunks_dicts)} chunks")
        
        return {
            'status': 'success',
            'message': f'Successfully re-indexed {len(chunks_dicts)} chunks',
            'chunks': len(chunks_dicts)
        }
        
    except Exception as e:
        logger.error(f"  ❌ Error re-indexing {md_path.name}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'status': 'error',
            'message': str(e)
        }


def main():
    """Main function to re-index faulty documents."""
    logger.info("=" * 80)
    logger.info("RE-INDEXING FAULTY DOCUMENTS")
    logger.info("=" * 80)
    
    # Find faulty documents
    faulty_docs = find_faulty_documents(max_chunks=2)
    
    if not faulty_docs:
        logger.info("\n[SUCCESS] No faulty documents found!")
        return
    
    # Find markdown directory
    markdown_dir = PROJECT_ROOT / "gdd_data" / "markdown"
    if not markdown_dir.exists():
        logger.error(f"Markdown directory does not exist: {markdown_dir}")
        return
    
    logger.info(f"\n[INFO] Markdown directory: {markdown_dir}")
    
    # Process each faulty document
    logger.info(f"\n{'='*80}")
    logger.info("PROCESSING FAULTY DOCUMENTS")
    logger.info(f"{'='*80}")
    
    success_count = 0
    error_count = 0
    not_found_count = 0
    
    for doc_info in faulty_docs:
        doc_id = doc_info['doc_id']
        logger.info(f"\n[PROCESSING] {doc_id}")
        logger.info(f"  Current chunks: {doc_info['actual_chunks']}")
        
        # Find markdown file
        md_file = find_markdown_file(doc_id, markdown_dir)
        if not md_file:
            logger.warning(f"  ⚠️  Markdown file not found for {doc_id}")
            not_found_count += 1
            continue
        
        logger.info(f"  Found markdown file: {md_file.name}")
        
        # Delete existing chunks
        logger.info("  Deleting existing chunks...")
        deleted = delete_chunks_for_doc(doc_id)
        logger.info(f"  Deleted {deleted} existing chunks")
        
        # Re-index
        result = reindex_markdown_file(md_file, doc_id)
        
        if result['status'] == 'success':
            success_count += 1
            logger.info(f"  ✅ Success: {result['message']}")
        else:
            error_count += 1
            logger.error(f"  ❌ Error: {result['message']}")
    
    # Summary
    logger.info(f"\n{'='*80}")
    logger.info("SUMMARY")
    logger.info(f"{'='*80}")
    logger.info(f"Total faulty documents: {len(faulty_docs)}")
    logger.info(f"Successfully re-indexed: {success_count}")
    logger.info(f"Errors: {error_count}")
    logger.info(f"Markdown files not found: {not_found_count}")
    logger.info(f"{'='*80}")


if __name__ == "__main__":
    main()


