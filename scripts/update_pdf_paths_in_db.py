"""
Update gdd_documents table with pdf_storage_path for all uploaded PDFs.

This script:
1. Lists all PDFs in the gdd_pdfs Supabase Storage bucket
2. Matches them to documents in gdd_documents table by doc_id
3. Updates the pdf_storage_path column
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


def update_pdf_paths():
    """Update gdd_documents with pdf_storage_path from uploaded files."""
    
    try:
        client = get_supabase_client()
    except Exception as e:
        logger.error(f"Failed to get Supabase client: {e}")
        return
    
    # 1. List all PDFs in storage bucket
    logger.info("📦 Fetching files from gdd_pdfs bucket...")
    try:
        files_in_storage = client.storage.from_('gdd_pdfs').list()
        logger.info(f"✓ Found {len(files_in_storage)} files in storage")
    except Exception as e:
        logger.error(f"❌ Error listing files from storage: {e}")
        return
    
    if not files_in_storage:
        logger.warning("No files found in gdd_pdfs bucket")
        return
    
    # 2. Get all documents from database
    logger.info("\n📊 Fetching documents from database...")
    try:
        docs_result = client.table('gdd_documents').select('doc_id, name, pdf_storage_path').execute()
        documents = docs_result.data or []
        logger.info(f"✓ Found {len(documents)} documents in database")
    except Exception as e:
        logger.error(f"❌ Error fetching documents: {e}")
        return
    
    # 3. Match and update
    logger.info("\n🔗 Matching PDFs to documents...")
    logger.info("="*80)
    
    updated_count = 0
    already_set_count = 0
    no_match_count = 0
    
    for file_obj in files_in_storage:
        pdf_filename = file_obj['name']
        
        # Extract doc_id from filename (remove .pdf extension)
        if not pdf_filename.endswith('.pdf'):
            logger.info(f"⚠️  Skipping non-PDF file: {pdf_filename}")
            continue
        
        doc_id = pdf_filename[:-4]  # Remove .pdf
        
        # Find matching document
        matching_doc = None
        for doc in documents:
            if doc['doc_id'] == doc_id:
                matching_doc = doc
                break
        
        if not matching_doc:
            logger.info(f"❌ No matching document for: {pdf_filename}")
            logger.info(f"   Doc ID: {doc_id}")
            no_match_count += 1
            continue
        
        # Check if already set
        current_pdf_path = matching_doc.get('pdf_storage_path')
        if current_pdf_path == pdf_filename:
            logger.info(f"✓ Already set: {doc_id}")
            already_set_count += 1
            continue
        
        # Update the record
        logger.info(f"\n📝 Updating: {doc_id}")
        logger.info(f"   PDF: {pdf_filename}")
        
        try:
            client.table('gdd_documents').update({
                'pdf_storage_path': pdf_filename
            }).eq('doc_id', doc_id).execute()
            
            logger.info(f"   ✅ Updated successfully")
            updated_count += 1
        except Exception as e:
            logger.error(f"   ❌ Error updating: {e}")
    
    # 4. Summary
    logger.info("\n" + "="*80)
    logger.info("UPDATE SUMMARY")
    logger.info("="*80)
    logger.info(f"PDFs in storage:      {len(files_in_storage)}")
    logger.info(f"Docs in database:     {len(documents)}")
    logger.info(f"Newly updated:        {updated_count}")
    logger.info(f"Already set:          {already_set_count}")
    logger.info(f"No match found:       {no_match_count}")
    logger.info("="*80)
    
    # 5. Verify final state
    logger.info("\n🔍 Verifying final state...")
    try:
        result = client.table('gdd_documents').select('doc_id, pdf_storage_path').execute()
        docs_with_pdf = [d for d in result.data if d.get('pdf_storage_path')]
        docs_without_pdf = [d for d in result.data if not d.get('pdf_storage_path')]
        
        logger.info(f"✓ Documents WITH PDF path: {len(docs_with_pdf)}")
        logger.info(f"⚠️  Documents WITHOUT PDF path: {len(docs_without_pdf)}")
        
        if docs_without_pdf:
            logger.info("\nDocuments missing PDF path:")
            for doc in docs_without_pdf[:5]:  # Show first 5
                logger.info(f"  - {doc['doc_id']}")
            if len(docs_without_pdf) > 5:
                logger.info(f"  ... and {len(docs_without_pdf) - 5} more")
    except Exception as e:
        logger.error(f"Error verifying: {e}")


if __name__ == "__main__":
    logger.info("Starting PDF path update...")
    logger.info(f"Project root: {PROJECT_ROOT}")
    update_pdf_paths()
    logger.info("\n✅ Done!")
