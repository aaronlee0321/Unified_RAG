"""
Fix pdf_storage_path in database to match actual PDF filenames in Supabase Storage.

This script:
1. Lists all PDFs in storage
2. For each document with a mismatched pdf_storage_path, finds the actual PDF file
3. Updates pdf_storage_path in the database to match the actual filename
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.supabase_client import get_supabase_client
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def normalize_filename(filename: str) -> str:
    """Normalize filename for comparison (remove spaces, underscores, dashes, case-insensitive)"""
    if not filename:
        return ""
    normalized = filename.lower().replace('_', '').replace('-', '').replace(' ', '').replace('.pdf', '')
    # Remove special characters
    normalized = normalized.replace('(', '').replace(')', '').replace('&', '').replace(',', '')
    # Normalize Vietnamese characters to ASCII equivalents for matching
    # This handles cases where storage has "He_Thong" but database has "Hệ_Thống"
    vietnamese_to_ascii = {
        'ệ': 'e', 'ế': 'e', 'ề': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
        'ư': 'u', 'ứ': 'u', 'ừ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
        'ơ': 'o', 'ớ': 'o', 'ờ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
        'ă': 'a', 'ắ': 'a', 'ằ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
        'â': 'a', 'ấ': 'a', 'ầ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
        'ô': 'o', 'ố': 'o', 'ồ': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
        'ê': 'e', 'ế': 'e', 'ề': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
        'đ': 'd', 'Đ': 'd',
        'á': 'a', 'à': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
        'í': 'i', 'ì': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
        'ý': 'y', 'ỳ': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
        'ú': 'u', 'ù': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
        'ó': 'o', 'ò': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
    }
    for viet, ascii_char in vietnamese_to_ascii.items():
        normalized = normalized.replace(viet, ascii_char)
    return normalized


def find_matching_pdf(doc_id: str, stored_path: str, storage_files: list) -> str:
    """Find matching PDF file in storage for a document."""
    # Normalize doc_id for matching
    doc_id_normalized = normalize_filename(doc_id)
    stored_normalized = normalize_filename(stored_path) if stored_path else ""
    
    # Strategy 1: Exact match with stored path
    if stored_path and stored_path in storage_files:
        return stored_path
    
    # Strategy 2: Try doc_id.pdf
    doc_id_filename = f"{doc_id}.pdf"
    if doc_id_filename in storage_files:
        return doc_id_filename
    
    # Strategy 3: Fuzzy matching - normalize and compare
    for file_name in storage_files:
        file_normalized = normalize_filename(file_name)
        
        # Check if stored filename matches
        if stored_normalized and stored_normalized == file_normalized:
            return file_name
        
        # Check if doc_id matches file name
        if doc_id_normalized and (doc_id_normalized in file_normalized or file_normalized in doc_id_normalized):
            # Prefer closer matches (longer common substring)
            return file_name
    
    return None


def fix_pdf_storage_paths(dry_run: bool = False):
    """Fix pdf_storage_path for all documents."""
    try:
        client = get_supabase_client()
        storage_client = get_supabase_client(use_service_key=True)
    except Exception as e:
        logger.error(f"Failed to get Supabase client: {e}")
        return
    
    logger.info("=" * 80)
    logger.info("FIX PDF STORAGE PATHS")
    logger.info("=" * 80)
    
    # 1. Get all PDFs in storage
    logger.info("\n📦 Fetching PDFs from storage...")
    try:
        files = storage_client.storage.from_('gdd_pdfs').list()
        storage_files = [f.get('name', '') for f in files] if files else []
        logger.info(f"✓ Found {len(storage_files)} PDF file(s) in storage")
    except Exception as e:
        logger.error(f"❌ Error listing storage files: {e}")
        return
    
    # 2. Get all documents with pdf_storage_path
    logger.info("\n📄 Fetching documents from database...")
    try:
        docs_result = client.table('gdd_documents').select('doc_id, name, pdf_storage_path').execute()
        documents = docs_result.data if docs_result.data else []
        logger.info(f"✓ Found {len(documents)} document(s)")
    except Exception as e:
        logger.error(f"❌ Error fetching documents: {e}")
        return
    
    # 3. Find and fix mismatches
    logger.info("\n🔍 Finding mismatches and fixing...")
    logger.info("=" * 80)
    
    fixed_count = 0
    not_found_count = 0
    already_correct_count = 0
    
    for doc in documents:
        doc_id = doc.get('doc_id', '')
        stored_path = doc.get('pdf_storage_path', '')
        doc_name = doc.get('name', '')
        
        if not stored_path:
            continue
        
        # Check if stored path matches actual file
        if stored_path in storage_files:
            already_correct_count += 1
            continue
        
        # Try to find matching PDF
        matched_file = find_matching_pdf(doc_id, stored_path, storage_files)
        
        if matched_file:
            logger.info(f"\n📝 {doc_id}")
            logger.info(f"   Current: {stored_path}")
            logger.info(f"   Found:   {matched_file}")
            
            if not dry_run:
                try:
                    client.table('gdd_documents').update({
                        'pdf_storage_path': matched_file
                    }).eq('doc_id', doc_id).execute()
                    logger.info(f"   ✅ Updated")
                    fixed_count += 1
                except Exception as e:
                    logger.error(f"   ❌ Error updating: {e}")
            else:
                logger.info(f"   [DRY RUN] Would update")
                fixed_count += 1
        else:
            logger.warning(f"\n⚠️  {doc_id}")
            logger.warning(f"   Current: {stored_path}")
            logger.warning(f"   ❌ No matching PDF found in storage")
            not_found_count += 1
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Already correct:  {already_correct_count}")
    logger.info(f"Fixed:            {fixed_count}")
    logger.info(f"Not found:        {not_found_count}")
    logger.info("=" * 80)
    
    if dry_run:
        logger.info("\n💡 This was a dry run. Run without --dry-run to apply changes.")
    else:
        logger.info("\n✅ Done!")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Fix pdf_storage_path in database')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be changed without applying')
    args = parser.parse_args()
    
    fix_pdf_storage_paths(dry_run=args.dry_run)
