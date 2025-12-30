"""
List all documents in the database to see their actual doc_ids.
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


def list_all_documents():
    """List all documents in the database."""
    
    try:
        client = get_supabase_client()
    except Exception as e:
        logger.error(f"Failed to get Supabase client: {e}")
        return
    
    logger.info("="*80)
    logger.info("ALL DOCUMENTS IN DATABASE")
    logger.info("="*80)
    
    try:
        result = client.table('gdd_documents').select('doc_id, name, file_path, pdf_storage_path').execute()
        documents = result.data or []
        
        logger.info(f"\n✓ Found {len(documents)} documents:\n")
        
        for i, doc in enumerate(documents, 1):
            logger.info(f"{i}. doc_id: {doc.get('doc_id', 'N/A')}")
            logger.info(f"   name: {doc.get('name', 'N/A')}")
            logger.info(f"   file_path: {doc.get('file_path', 'N/A')}")
            logger.info(f"   pdf_storage_path: {doc.get('pdf_storage_path', 'N/A')}")
            logger.info("")
        
    except Exception as e:
        logger.error(f"❌ Error fetching documents: {e}")


if __name__ == "__main__":
    list_all_documents()

