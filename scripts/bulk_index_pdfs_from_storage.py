"""
Bulk index PDFs from Supabase Storage that haven't been indexed yet.

This script:
1. Lists all PDFs in Supabase Storage (gdd_pdfs bucket)
2. Checks which ones are already indexed (have chunks in gdd_chunks table)
3. Downloads unindexed PDFs temporarily
4. Converts them to Markdown using Docling
5. Chunks the markdown
6. Indexes to Supabase with embeddings
7. Updates gdd_documents table with pdf_storage_path and markdown_content

Usage:
    python scripts/bulk_index_pdfs_from_storage.py [--limit N] [--dry-run]
"""

import sys
import os
import argparse
import tempfile
import requests
from pathlib import Path
from typing import List, Dict, Set

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.storage.supabase_client import get_supabase_client
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_indexed_pdfs() -> Set[str]:
    """Get set of PDF filenames that are already indexed (have chunks)."""
    try:
        client = get_supabase_client()
        
        # Get all documents with chunks
        result = client.table('gdd_documents').select('pdf_storage_path, doc_id').execute()
        
        indexed_pdfs = set()
        for doc in (result.data or []):
            pdf_path = doc.get('pdf_storage_path')
            doc_id = doc.get('doc_id')
            
            if pdf_path:
                # Check if this document has chunks
                chunks_result = client.table('gdd_chunks').select('chunk_id').eq('doc_id', doc_id).limit(1).execute()
                if chunks_result.data:
                    indexed_pdfs.add(pdf_path)
                    logger.debug(f"  ✓ {pdf_path} - already indexed (doc_id: {doc_id})")
        
        logger.info(f"Found {len(indexed_pdfs)} already indexed PDFs")
        return indexed_pdfs
        
    except Exception as e:
        logger.error(f"Error checking indexed PDFs: {e}")
        return set()


def get_storage_pdfs() -> List[str]:
    """Get list of all PDFs in Supabase Storage."""
    try:
        client = get_supabase_client(use_service_key=True)
        
        files = client.storage.from_('gdd_pdfs').list()
        pdf_files = [f.get('name', '') for f in files if f.get('name', '').lower().endswith('.pdf')]
        
        logger.info(f"Found {len(pdf_files)} PDFs in Supabase Storage")
        return pdf_files
        
    except Exception as e:
        logger.error(f"Error listing storage PDFs: {e}")
        return []


def download_pdf_from_storage(filename: str, temp_dir: Path) -> Path:
    """Download a PDF from Supabase Storage to a temporary directory."""
    try:
        client = get_supabase_client()
        
        # Get public URL
        url = client.storage.from_('gdd_pdfs').get_public_url(filename)
        
        # Download file
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        
        # Save to temp file
        temp_file = temp_dir / filename
        temp_file.write_bytes(response.content)
        
        logger.info(f"  ✓ Downloaded {filename} ({len(response.content)} bytes)")
        return temp_file
        
    except Exception as e:
        logger.error(f"  ❌ Error downloading {filename}: {e}")
        raise


def index_pdf_document(pdf_path: Path) -> Dict:
    """Index a single PDF document using the complete pipeline."""
    try:
        from backend.gdd_service import upload_and_index_document
        
        result = upload_and_index_document(pdf_path)
        return result
        
    except Exception as e:
        logger.error(f"Error indexing {pdf_path.name}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            'status': 'error',
            'message': str(e)
        }


def bulk_index_pdfs(limit: int = None, dry_run: bool = False):
    """
    Bulk index PDFs from Supabase Storage.
    
    Args:
        limit: Maximum number of PDFs to process (None = all)
        dry_run: If True, only show what would be done without actually indexing
    """
    logger.info("="*80)
    logger.info("BULK PDF INDEXING FROM SUPABASE STORAGE")
    logger.info("="*80)
    
    if dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
        logger.info("")
    
    # Step 1: Get all PDFs from storage
    logger.info("\n📦 Step 1: Listing PDFs in Supabase Storage...")
    storage_pdfs = get_storage_pdfs()
    
    if not storage_pdfs:
        logger.warning("No PDFs found in storage")
        return
    
    logger.info(f"Found {len(storage_pdfs)} PDFs in storage:")
    for i, pdf in enumerate(storage_pdfs[:10], 1):
        logger.info(f"  {i}. {pdf}")
    if len(storage_pdfs) > 10:
        logger.info(f"  ... and {len(storage_pdfs) - 10} more")
    
    # Step 2: Get already indexed PDFs
    logger.info("\n🔍 Step 2: Checking which PDFs are already indexed...")
    indexed_pdfs = get_indexed_pdfs()
    
    # Step 3: Find PDFs that need indexing
    unindexed_pdfs = [pdf for pdf in storage_pdfs if pdf not in indexed_pdfs]
    
    logger.info(f"\n📊 Status:")
    logger.info(f"  Total PDFs in storage:  {len(storage_pdfs)}")
    logger.info(f"  Already indexed:        {len(indexed_pdfs)}")
    logger.info(f"  Need indexing:          {len(unindexed_pdfs)}")
    
    if not unindexed_pdfs:
        logger.info("\n✅ All PDFs are already indexed!")
        return
    
    # Apply limit if specified
    if limit:
        unindexed_pdfs = unindexed_pdfs[:limit]
        logger.info(f"\n⚠️  Limiting to first {limit} PDFs")
    
    logger.info(f"\n📝 PDFs to be indexed ({len(unindexed_pdfs)}):")
    for i, pdf in enumerate(unindexed_pdfs, 1):
        logger.info(f"  {i}. {pdf}")
    
    if dry_run:
        logger.info("\n✅ Dry run complete - no changes made")
        return
    
    # Step 4: Process each unindexed PDF
    logger.info("\n🚀 Step 3: Starting bulk indexing...")
    logger.info("="*80)
    
    success_count = 0
    error_count = 0
    skipped_count = 0
    
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        
        for i, pdf_filename in enumerate(unindexed_pdfs, 1):
            logger.info(f"\n[{i}/{len(unindexed_pdfs)}] Processing: {pdf_filename}")
            logger.info("-" * 60)
            
            try:
                # Download PDF from storage
                logger.info(f"  📥 Downloading from Supabase Storage...")
                pdf_path = download_pdf_from_storage(pdf_filename, temp_path)
                
                # Index the PDF
                logger.info(f"  🔄 Converting, chunking, and indexing...")
                result = index_pdf_document(pdf_path)
                
                if result.get('status') == 'success':
                    logger.info(f"  ✅ Successfully indexed: {pdf_filename}")
                    logger.info(f"     Doc ID: {result.get('doc_id')}")
                    success_count += 1
                elif result.get('status') == 'error':
                    logger.error(f"  ❌ Failed to index: {pdf_filename}")
                    logger.error(f"     Error: {result.get('message')}")
                    error_count += 1
                else:
                    logger.warning(f"  ⚠️  Skipped: {pdf_filename}")
                    skipped_count += 1
                
                # Clean up temp file
                if pdf_path.exists():
                    pdf_path.unlink()
                
            except Exception as e:
                logger.error(f"  ❌ Error processing {pdf_filename}: {e}")
                import traceback
                logger.error(traceback.format_exc())
                error_count += 1
                continue
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info("BULK INDEXING SUMMARY")
    logger.info("="*80)
    logger.info(f"Total PDFs processed:     {len(unindexed_pdfs)}")
    logger.info(f"Successfully indexed:     {success_count}")
    logger.info(f"Errors:                   {error_count}")
    logger.info(f"Skipped:                  {skipped_count}")
    logger.info("="*80)
    
    if success_count > 0:
        logger.info(f"\n✅ Successfully indexed {success_count} PDF(s)")
    if error_count > 0:
        logger.warning(f"\n⚠️  {error_count} PDF(s) failed to index")


def main():
    parser = argparse.ArgumentParser(
        description="Bulk index PDFs from Supabase Storage that haven't been indexed yet"
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=None,
        help='Maximum number of PDFs to process (default: all)'
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
    
    bulk_index_pdfs(limit=args.limit, dry_run=args.dry_run)
    
    logger.info("\n✅ Done!")


if __name__ == "__main__":
    main()


