"""
Index markdown files directly to Supabase (skip PDF conversion).

This script:
1. Reads markdown files from gdd_data/markdown/
2. Chunks the markdown with MarkdownChunker
3. Generates embeddings using QwenProvider
4. Indexes to Supabase with metadata
5. Updates gdd_documents table with markdown_content and pdf_storage_path

Usage:
    python scripts/index_markdown_files_to_supabase.py [--limit N] [--dry-run]
"""

import sys
import os
import argparse
from pathlib import Path
from typing import List, Dict, Set

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


def get_indexed_doc_ids() -> Set[str]:
    """Get set of doc_ids that are already indexed (have chunks)."""
    try:
        client = get_supabase_client()
        
        # Get all documents with chunks
        result = client.table('gdd_documents').select('doc_id').execute()
        
        indexed_docs = set()
        for doc in (result.data or []):
            doc_id = doc.get('doc_id')
            
            if doc_id:
                # Check if this document has chunks
                chunks_result = client.table('gdd_chunks').select('chunk_id').eq('doc_id', doc_id).limit(1).execute()
                if chunks_result.data:
                    indexed_docs.add(doc_id)
                    logger.debug(f"  ✓ {doc_id} - already indexed")
        
        logger.info(f"Found {len(indexed_docs)} already indexed documents")
        return indexed_docs
        
    except Exception as e:
        logger.error(f"Error checking indexed documents: {e}")
        return set()


def get_markdown_files(markdown_dir: Path) -> List[Path]:
    """Get list of all markdown files in directory."""
    md_files = list(markdown_dir.glob("*.md"))
    logger.info(f"Found {len(md_files)} markdown files")
    return sorted(md_files)


def generate_pdf_filename(markdown_filename: str) -> str:
    """
    Generate expected PDF filename from markdown filename.
    
    Examples:
    - "[Asset, UI] [Tank War] Garage Design - UI_UX.md" -> "Asset_UI_Tank_War_Garage_Design_-_UI_UX.pdf"
    - "World Tank War Map Document.md" -> "World_Tank_War_Map_Document.pdf"
    """
    # Remove .md extension
    name = markdown_filename.replace('.md', '')
    
    # Replace brackets and special chars
    name = name.replace('[', '').replace(']', '')
    name = name.replace('(', '').replace(')', '')
    name = name.replace(',', '')
    
    # Replace spaces with underscores
    name = name.replace(' ', '_')
    
    # Remove multiple underscores
    while '__' in name:
        name = name.replace('__', '_')
    
    # Add .pdf extension
    return name.strip('_') + '.pdf'


def index_markdown_file(md_path: Path, provider: QwenProvider) -> Dict:
    """Index a single markdown file to Supabase."""
    try:
        logger.info(f"  📄 Reading markdown file...")
        markdown_content = md_path.read_text(encoding='utf-8')
        
        # Generate doc_id from filename
        doc_id = generate_doc_id(md_path)
        logger.info(f"  Generated doc_id: {doc_id}")
        
        # Generate expected PDF filename
        pdf_filename = generate_pdf_filename(md_path.name)
        logger.info(f"  Expected PDF filename: {pdf_filename}")
        
        # Chunk the markdown
        logger.info(f"  🔪 Chunking markdown...")
        chunker = MarkdownChunker()
        chunks = chunker.chunk_document(
            markdown_content=markdown_content,
            doc_id=doc_id,
            filename=md_path.name,
        )
        logger.info(f"  ✓ Created {len(chunks)} chunks")
        
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
            }
            chunks_dicts.append(chunk_dict)
        
        # Index to Supabase
        logger.info(f"  📤 Indexing to Supabase...")
        index_gdd_chunks_to_supabase(
            doc_id=doc_id,
            chunks=chunks_dicts,
            provider=provider,
            markdown_content=markdown_content,
            pdf_storage_path=pdf_filename
        )
        logger.info(f"  ✅ Successfully indexed")
        
        return {
            'status': 'success',
            'doc_id': doc_id,
            'chunks': len(chunks)
        }
        
    except Exception as e:
        logger.error(f"  ❌ Error indexing {md_path.name}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'status': 'error',
            'message': str(e)
        }


def index_markdown_files(limit: int = None, dry_run: bool = False):
    """
    Index markdown files from gdd_data/markdown/ to Supabase.
    
    Args:
        limit: Maximum number of files to process (None = all)
        dry_run: If True, only show what would be done without actually indexing
    """
    logger.info("="*80)
    logger.info("INDEX MARKDOWN FILES TO SUPABASE")
    logger.info("="*80)
    
    if dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
        logger.info("")
    
    # Get markdown directory
    markdown_dir = PROJECT_ROOT / "gdd_data" / "markdown"
    if not markdown_dir.exists():
        logger.error(f"Markdown directory not found: {markdown_dir}")
        return
    
    logger.info(f"Markdown directory: {markdown_dir}")
    
    # Step 1: Get all markdown files
    logger.info("\n📦 Step 1: Listing markdown files...")
    md_files = get_markdown_files(markdown_dir)
    
    if not md_files:
        logger.warning("No markdown files found")
        return
    
    logger.info(f"Found {len(md_files)} markdown files:")
    for i, md_file in enumerate(md_files[:10], 1):
        logger.info(f"  {i}. {md_file.name}")
    if len(md_files) > 10:
        logger.info(f"  ... and {len(md_files) - 10} more")
    
    # Step 2: Get already indexed documents
    logger.info("\n🔍 Step 2: Checking which documents are already indexed...")
    indexed_docs = get_indexed_doc_ids()
    
    # Step 3: Find files that need indexing
    unindexed_files = []
    for md_file in md_files:
        doc_id = generate_doc_id(md_file)
        if doc_id not in indexed_docs:
            unindexed_files.append(md_file)
    
    logger.info(f"\n📊 Status:")
    logger.info(f"  Total markdown files:   {len(md_files)}")
    logger.info(f"  Already indexed:        {len(indexed_docs)}")
    logger.info(f"  Need indexing:          {len(unindexed_files)}")
    
    if not unindexed_files:
        logger.info("\n✅ All markdown files are already indexed!")
        return
    
    # Apply limit if specified
    if limit:
        unindexed_files = unindexed_files[:limit]
        logger.info(f"\n⚠️  Limiting to first {limit} files")
    
    logger.info(f"\n📝 Files to be indexed ({len(unindexed_files)}):")
    for i, md_file in enumerate(unindexed_files, 1):
        logger.info(f"  {i}. {md_file.name}")
    
    if dry_run:
        logger.info("\n✅ Dry run complete - no changes made")
        return
    
    # Step 4: Process each unindexed file
    logger.info("\n🚀 Step 3: Starting bulk indexing...")
    logger.info("="*80)
    
    # Initialize provider
    logger.info("Initializing QwenProvider for embeddings...")
    try:
        provider = QwenProvider()
        logger.info("✓ Provider initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize provider: {e}")
        return
    
    success_count = 0
    error_count = 0
    
    for i, md_file in enumerate(unindexed_files, 1):
        logger.info(f"\n[{i}/{len(unindexed_files)}] Processing: {md_file.name}")
        logger.info("-" * 60)
        
        try:
            result = index_markdown_file(md_file, provider)
            
            if result.get('status') == 'success':
                logger.info(f"  ✅ Successfully indexed: {md_file.name}")
                logger.info(f"     Doc ID: {result.get('doc_id')}")
                logger.info(f"     Chunks: {result.get('chunks')}")
                success_count += 1
            else:
                logger.error(f"  ❌ Failed to index: {md_file.name}")
                logger.error(f"     Error: {result.get('message')}")
                error_count += 1
                
        except Exception as e:
            logger.error(f"  ❌ Error processing {md_file.name}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            error_count += 1
            continue
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info("INDEXING SUMMARY")
    logger.info("="*80)
    logger.info(f"Total files processed:    {len(unindexed_files)}")
    logger.info(f"Successfully indexed:     {success_count}")
    logger.info(f"Errors:                   {error_count}")
    logger.info("="*80)
    
    if success_count > 0:
        logger.info(f"\n✅ Successfully indexed {success_count} markdown file(s)")
    if error_count > 0:
        logger.warning(f"\n⚠️  {error_count} file(s) failed to index")


def main():
    parser = argparse.ArgumentParser(
        description="Index markdown files from gdd_data/markdown/ to Supabase"
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Maximum number of files to process (default: all)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without actually indexing'
    )
    
    args = parser.parse_args()
    
    logger.info(f"Project root: {PROJECT_ROOT}")
    logger.info(f"Python: {sys.version}")
    
    # Check environment
    if not os.getenv('SUPABASE_URL') or not os.getenv('SUPABASE_KEY'):
        logger.error("❌ SUPABASE_URL and SUPABASE_KEY must be set in .env")
        sys.exit(1)
    
    if not os.getenv('QWEN_API_KEY') and not os.getenv('DASHSCOPE_API_KEY'):
        logger.error("❌ QWEN_API_KEY or DASHSCOPE_API_KEY must be set in .env for embeddings")
        sys.exit(1)
    
    index_markdown_files(limit=args.limit, dry_run=args.dry_run)
    
    logger.info("\n✅ Done!")


if __name__ == "__main__":
    main()

