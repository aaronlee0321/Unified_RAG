"""
Upload PDF files to Supabase Storage and update gdd_documents table.

This script:
1. Finds all PDF files in gdd_data/source/
2. Uploads them to Supabase Storage bucket 'gdd_pdfs'
3. Updates the corresponding gdd_documents records with pdf_storage_path
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


def upload_pdfs_to_supabase():
    """Upload all PDFs from gdd_data/source/ to Supabase Storage."""
    
    # Find all PDFs
    source_dir = PROJECT_ROOT / "gdd_data" / "source"
    if not source_dir.exists():
        logger.error(f"Source directory not found: {source_dir}")
        return
    
    pdf_files = list(source_dir.glob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDF files in {source_dir}")
    
    if not pdf_files:
        logger.warning("No PDF files found to upload")
        return
    
    # Get Supabase client
    try:
        client = get_supabase_client()
    except Exception as e:
        logger.error(f"Failed to get Supabase client: {e}")
        return
    
    uploaded_count = 0
    skipped_count = 0
    error_count = 0
    
    for pdf_file in pdf_files:
        pdf_name = pdf_file.name
        doc_id = pdf_file.stem  # Filename without .pdf extension
        
        logger.info(f"\nProcessing: {pdf_name}")
        logger.info(f"  Doc ID: {doc_id}")
        
        try:
            # Check if document exists in gdd_documents
            doc_result = client.table('gdd_documents').select('doc_id, name, pdf_storage_path').eq('doc_id', doc_id).execute()
            
            if not doc_result.data:
                logger.warning(f"  ⚠️  Document '{doc_id}' not found in gdd_documents table. Skipping.")
                skipped_count += 1
                continue
            
            doc = doc_result.data[0]
            existing_pdf_path = doc.get('pdf_storage_path')
            
            # Check if already uploaded
            if existing_pdf_path == pdf_name:
                logger.info(f"  ✓ Already uploaded: {pdf_name}")
                skipped_count += 1
                continue
            
            # Read PDF file
            with open(pdf_file, 'rb') as f:
                pdf_bytes = f.read()
            
            # Upload to Supabase Storage
            logger.info(f"  📤 Uploading to Supabase Storage...")
            storage_path = pdf_name
            
            try:
                # Try to upload (will fail if file already exists)
                client.storage.from_('gdd_pdfs').upload(
                    path=storage_path,
                    file=pdf_bytes,
                    file_options={
                        "content-type": "application/pdf",
                        "cache-control": "3600",
                        "upsert": "false"  # Don't overwrite existing files
                    }
                )
                logger.info(f"  ✓ Uploaded successfully")
            except Exception as upload_error:
                error_str = str(upload_error)
                if "already exists" in error_str or "Duplicate" in error_str:
                    logger.info(f"  ✓ File already exists in storage")
                else:
                    raise  # Re-raise if it's a different error
            
            # Update gdd_documents table
            logger.info(f"  💾 Updating gdd_documents record...")
            client.table('gdd_documents').update({
                'pdf_storage_path': pdf_name
            }).eq('doc_id', doc_id).execute()
            
            logger.info(f"  ✅ Successfully processed: {pdf_name}")
            uploaded_count += 1
            
        except Exception as e:
            logger.error(f"  ❌ Error processing {pdf_name}: {e}")
            error_count += 1
    
    # Summary
    logger.info("\n" + "="*60)
    logger.info("UPLOAD SUMMARY")
    logger.info("="*60)
    logger.info(f"Total PDFs found:     {len(pdf_files)}")
    logger.info(f"Successfully uploaded: {uploaded_count}")
    logger.info(f"Skipped:              {skipped_count}")
    logger.info(f"Errors:               {error_count}")
    logger.info("="*60)
    
    # Verify uploads
    logger.info("\nVerifying uploads in Supabase Storage...")
    try:
        files_result = client.storage.from_('gdd_pdfs').list()
        logger.info(f"✓ Found {len(files_result)} files in gdd_pdfs bucket")
        for file in files_result[:5]:  # Show first 5
            logger.info(f"  - {file['name']}")
        if len(files_result) > 5:
            logger.info(f"  ... and {len(files_result) - 5} more")
    except Exception as e:
        logger.error(f"Error listing files: {e}")


if __name__ == "__main__":
    logger.info("Starting PDF upload to Supabase Storage...")
    logger.info(f"Project root: {PROJECT_ROOT}")
    upload_pdfs_to_supabase()
    logger.info("\nDone!")
