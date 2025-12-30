"""
Fix document name matching issues between sidebar and Supabase.

This script:
1. Checks all documents in Supabase
2. Verifies doc_ids match what's generated from markdown filenames
3. Updates document names in Supabase to match markdown filenames
4. Fixes PDF storage paths to match actual PDF filenames
5. Ensures "extract all doc" works for all documents

Usage:
    python scripts/fix_document_name_matching.py [--dry-run]
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.storage.supabase_client import get_supabase_client
from gdd_rag_backbone.scripts.chunk_markdown_files import generate_doc_id
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def normalize_for_matching(text: str) -> str:
    """Normalize text for fuzzy matching (removes special chars, lowercases)."""
    if not text:
        return ""
    # Remove special characters and normalize
    normalized = text.lower()
    normalized = normalized.replace("[", "").replace("]", "")
    normalized = normalized.replace(",", "").replace("_", "")
    normalized = normalized.replace("-", "").replace(" ", "")
    normalized = normalized.replace("(", "").replace(")", "")
    # Remove Vietnamese diacritics for better matching
    # This is a simple approach - for production, use unidecode
    return normalized


def get_markdown_files() -> List[Path]:
    """Get all markdown files from gdd_data/markdown."""
    markdown_dir = PROJECT_ROOT / "gdd_data" / "markdown"
    if not markdown_dir.exists():
        logger.error(f"Markdown directory not found: {markdown_dir}")
        return []
    
    md_files = list(markdown_dir.glob("*.md"))
    logger.info(f"Found {len(md_files)} markdown files")
    return sorted(md_files)


def get_supabase_documents() -> List[Dict]:
    """Get all documents from Supabase."""
    try:
        client = get_supabase_client()
        result = client.table('gdd_documents').select('*').execute()
        return result.data or []
    except Exception as e:
        logger.error(f"Error getting documents from Supabase: {e}")
        return []


def get_storage_pdfs() -> List[str]:
    """Get all PDF filenames from Supabase Storage."""
    try:
        client = get_supabase_client()
        # List files in the gdd-pdfs bucket
        storage = client.storage.from_('gdd-pdfs')
        files = storage.list()
        
        pdf_files = []
        if files:
            for file_info in files:
                if isinstance(file_info, dict):
                    name = file_info.get('name', '')
                else:
                    name = str(file_info)
                if name.endswith('.pdf'):
                    pdf_files.append(name)
        
        logger.info(f"Found {len(pdf_files)} PDF files in storage")
        return pdf_files
    except Exception as e:
        logger.error(f"Error getting PDF files from storage: {e}")
        return []


def find_matching_pdf(markdown_filename: str, pdf_files: List[str]) -> Optional[str]:
    """Find matching PDF file for a markdown filename."""
    # Generate expected PDF filename
    pdf_name = markdown_filename.replace('.md', '.pdf')
    pdf_name = pdf_name.replace('[', '').replace(']', '')
    pdf_name = pdf_name.replace('(', '').replace(')', '')
    pdf_name = pdf_name.replace(',', '')
    pdf_name = pdf_name.replace(' ', '_')
    while '__' in pdf_name:
        pdf_name = pdf_name.replace('__', '_')
    pdf_name = pdf_name.strip('_')
    
    # Try exact match first
    if pdf_name in pdf_files:
        return pdf_name
    
    # Try fuzzy matching
    normalized_target = normalize_for_matching(pdf_name)
    for pdf_file in pdf_files:
        normalized_pdf = normalize_for_matching(pdf_file)
        if normalized_target == normalized_pdf:
            return pdf_file
    
    # Try partial matching
    for pdf_file in pdf_files:
        if normalize_for_matching(pdf_name) in normalize_for_matching(pdf_file) or \
           normalize_for_matching(pdf_file) in normalize_for_matching(pdf_name):
            return pdf_file
    
    return None


def fix_document_matching(dry_run: bool = False):
    """Fix document name matching and PDF paths."""
    logger.info("="*80)
    logger.info("FIX DOCUMENT NAME MATCHING")
    logger.info("="*80)
    
    if dry_run:
        logger.info("DRY RUN MODE - No changes will be made")
        logger.info("")
    
    # Step 1: Get all markdown files
    logger.info("📦 Step 1: Getting markdown files...")
    md_files = get_markdown_files()
    logger.info(f"Found {len(md_files)} markdown files")
    
    # Step 2: Get all documents from Supabase
    logger.info("\n📊 Step 2: Getting documents from Supabase...")
    supabase_docs = get_supabase_documents()
    logger.info(f"Found {len(supabase_docs)} documents in Supabase")
    
    # Step 3: Get PDF files from storage
    logger.info("\n📄 Step 3: Getting PDF files from storage...")
    pdf_files = get_storage_pdfs()
    logger.info(f"Found {len(pdf_files)} PDF files in storage")
    
    # Step 4: Build mapping of markdown files to expected doc_ids
    logger.info("\n🔍 Step 4: Building document mappings...")
    md_to_doc_id = {}
    for md_file in md_files:
        doc_id = generate_doc_id(md_file)
        md_to_doc_id[md_file.name] = {
            'doc_id': doc_id,
            'file_path': str(md_file),
            'markdown_filename': md_file.name
        }
    
    # Step 5: Match Supabase documents with markdown files
    logger.info("\n🔗 Step 5: Matching documents...")
    updates_needed = []
    
    for md_file in md_files:
        md_name = md_file.name
        expected_doc_id = generate_doc_id(md_file)
        
        # Find matching document in Supabase
        matching_doc = None
        for doc in supabase_docs:
            doc_id = doc.get('doc_id', '')
            # Try exact match
            if doc_id == expected_doc_id:
                matching_doc = doc
                break
            # Try fuzzy match
            if normalize_for_matching(doc_id) == normalize_for_matching(expected_doc_id):
                matching_doc = doc
                break
        
        if not matching_doc:
            logger.warning(f"  ⚠️  No Supabase document found for: {md_name} (expected doc_id: {expected_doc_id})")
            continue
        
        # Check if updates are needed
        updates = {}
        current_doc_id = matching_doc.get('doc_id', '')
        current_name = matching_doc.get('name', '')
        current_file_path = matching_doc.get('file_path', '')
        current_pdf_path = matching_doc.get('pdf_storage_path', '')
        
        # Check doc_id
        if current_doc_id != expected_doc_id:
            logger.warning(f"  ⚠️  Doc ID mismatch for {md_name}:")
            logger.warning(f"      Current: {current_doc_id}")
            logger.warning(f"      Expected: {expected_doc_id}")
            # Note: We can't change doc_id (it's the primary key), so we'll need to handle this differently
        
        # Check name
        if current_name != md_name:
            logger.info(f"  📝 Name update needed for {md_name}:")
            logger.info(f"      Current: {current_name}")
            logger.info(f"      New: {md_name}")
            updates['name'] = md_name
        
        # Check file_path
        expected_file_path = str(md_file)
        if current_file_path != expected_file_path:
            logger.info(f"  📁 File path update needed for {md_name}:")
            logger.info(f"      Current: {current_file_path}")
            logger.info(f"      New: {expected_file_path}")
            updates['file_path'] = expected_file_path
        
        # Check PDF path
        matching_pdf = find_matching_pdf(md_name, pdf_files)
        if matching_pdf:
            if current_pdf_path != matching_pdf:
                logger.info(f"  📄 PDF path update needed for {md_name}:")
                logger.info(f"      Current: {current_pdf_path}")
                logger.info(f"      New: {matching_pdf}")
                updates['pdf_storage_path'] = matching_pdf
        else:
            logger.warning(f"  ⚠️  No matching PDF found for {md_name}")
        
        if updates:
            updates_needed.append({
                'doc_id': current_doc_id,
                'updates': updates,
                'markdown_file': md_name
            })
    
    # Step 6: Apply updates
    if updates_needed:
        logger.info(f"\n📤 Step 6: Applying {len(updates_needed)} updates...")
        
        if not dry_run:
            client = get_supabase_client()
            
            for item in updates_needed:
                doc_id = item['doc_id']
                updates = item['updates']
                md_file = item['markdown_file']
                
                try:
                    result = client.table('gdd_documents').update(updates).eq('doc_id', doc_id).execute()
                    logger.info(f"  ✅ Updated {md_file} (doc_id: {doc_id})")
                    logger.info(f"     Updates: {', '.join(updates.keys())}")
                except Exception as e:
                    logger.error(f"  ❌ Failed to update {md_file} (doc_id: {doc_id}): {e}")
        else:
            logger.info("\n📋 Updates that would be made:")
            for item in updates_needed:
                logger.info(f"  - {item['markdown_file']} (doc_id: {item['doc_id']})")
                for key, value in item['updates'].items():
                    logger.info(f"    {key}: {value}")
    else:
        logger.info("\n✅ No updates needed - all documents are correctly matched!")
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info("SUMMARY")
    logger.info("="*80)
    logger.info(f"Markdown files:        {len(md_files)}")
    logger.info(f"Supabase documents:    {len(supabase_docs)}")
    logger.info(f"PDF files in storage:  {len(pdf_files)}")
    logger.info(f"Updates needed:        {len(updates_needed)}")
    logger.info("="*80)


def main():
    parser = argparse.ArgumentParser(
        description="Fix document name matching between sidebar and Supabase"
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    
    args = parser.parse_args()
    
    fix_document_matching(dry_run=args.dry_run)
    
    logger.info("\n✅ Done!")


if __name__ == "__main__":
    main()


