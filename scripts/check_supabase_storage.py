"""
Diagnostic script to check what's in Supabase Storage.
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.supabase_client import get_supabase_client
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_storage():
    """Check Supabase Storage buckets and contents."""
    
    try:
        client = get_supabase_client()
    except Exception as e:
        logger.error(f"Failed to get Supabase client: {e}")
        return
    
    logger.info("="*80)
    logger.info("SUPABASE STORAGE DIAGNOSTIC")
    logger.info("="*80)
    
    # 1. List all buckets
    logger.info("\n📦 Listing all storage buckets...")
    try:
        buckets = client.storage.list_buckets()
        logger.info(f"✓ Found {len(buckets)} bucket(s):")
        for bucket in buckets:
            logger.info(f"\n  Bucket: {bucket.name}")
            logger.info(f"    ID: {bucket.id}")
            logger.info(f"    Public: {bucket.public}")
            logger.info(f"    Created: {bucket.created_at}")
    except Exception as e:
        logger.error(f"❌ Error listing buckets: {e}")
        return
    
    # 2. Check gdd_pdfs bucket specifically
    logger.info("\n" + "="*80)
    logger.info("📁 Checking 'gdd_pdfs' bucket...")
    try:
        files = client.storage.from_('gdd_pdfs').list()
        logger.info(f"✓ Found {len(files)} file(s) in gdd_pdfs bucket:")
        
        if files:
            for file in files:
                logger.info(f"\n  File: {file['name']}")
                logger.info(f"    ID: {file.get('id', 'N/A')}")
                logger.info(f"    Size: {file.get('metadata', {}).get('size', 'N/A')} bytes")
                logger.info(f"    Created: {file.get('created_at', 'N/A')}")
                logger.info(f"    Updated: {file.get('updated_at', 'N/A')}")
        else:
            logger.warning("  ⚠️  Bucket is empty!")
            
    except Exception as e:
        logger.error(f"❌ Error accessing gdd_pdfs bucket: {e}")
    
    # 3. Try to list with different path patterns
    logger.info("\n" + "="*80)
    logger.info("🔍 Trying different list patterns...")
    
    patterns_to_try = [
        ('/', 'root directory'),
        ('', 'empty string'),
        (None, 'None/default'),
    ]
    
    for pattern, description in patterns_to_try:
        try:
            logger.info(f"\n  Trying pattern: {pattern} ({description})")
            if pattern is None:
                files = client.storage.from_('gdd_pdfs').list()
            else:
                files = client.storage.from_('gdd_pdfs').list(path=pattern)
            logger.info(f"    Result: {len(files)} files")
            if files and len(files) > 0:
                logger.info(f"    First file: {files[0]['name']}")
        except Exception as e:
            logger.info(f"    Error: {e}")
    
    # 4. Check database for pdf_storage_path values
    logger.info("\n" + "="*80)
    logger.info("🗄️  Checking gdd_documents table for pdf_storage_path...")
    try:
        result = client.table('gdd_documents').select('doc_id, pdf_storage_path').execute()
        docs_with_pdf = [d for d in result.data if d.get('pdf_storage_path')]
        docs_without_pdf = [d for d in result.data if not d.get('pdf_storage_path')]
        
        logger.info(f"✓ Total documents: {len(result.data)}")
        logger.info(f"  With PDF path: {len(docs_with_pdf)}")
        logger.info(f"  Without PDF path: {len(docs_without_pdf)}")
        
        if docs_with_pdf:
            logger.info("\n  Documents with PDF path (first 5):")
            for doc in docs_with_pdf[:5]:
                logger.info(f"    - {doc['doc_id']}: {doc['pdf_storage_path']}")
        
    except Exception as e:
        logger.error(f"❌ Error checking database: {e}")
    
    logger.info("\n" + "="*80)
    logger.info("✅ Diagnostic complete!")
    logger.info("="*80)


if __name__ == "__main__":
    check_storage()
