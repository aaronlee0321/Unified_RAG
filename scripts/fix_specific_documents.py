"""
Fix specific problematic documents that can't be selected or queried.

This script updates document names in Supabase to match markdown filenames exactly.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.storage.supabase_client import get_supabase_client
from gdd_rag_backbone.scripts.chunk_markdown_files import generate_doc_id
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def fix_document_names():
    """Fix document names to match markdown filenames."""
    client = get_supabase_client(use_service_key=True)  # Use service key for updates
    markdown_dir = PROJECT_ROOT / "gdd_data" / "markdown"
    
    # Map of problematic doc_ids to their correct markdown filenames
    fixes = {
        "Monetization_Module_Tank_War_Monetization_Localization_(LATAM)": "[Monetization Module] [Tank War] Monetization Localization (LATAM).md",
        "Progression_Module_Tank_Wars_Tổng_Quan_Artifact_System": "[Progression Module] [Tank Wars] Tổng Quan Artifact System.md",
        "Progression_Module_Tank_War_Onboarding_Design_(Chưa_xong)": "[Progression Module] [Tank War] Onboarding Design (Chưa xong).md",
        "Progression_Module_Tank_War_ELO_&_RANK_System_OLD_(not_use)": "[Progression Module] [Tank War] ELO & RANK System - OLD (not use).md",
        "Progression_Module_Tank_War_Leaderboard_System": "[Progression Module] [Tank War] Leaderboard System.md",
        "Character_Module_Tank_War_Elemental_Class": "[Character Module] [Tank War] [Elemental Class].md",
        "string": "string.md",
    }
    
    logger.info("="*80)
    logger.info("FIXING SPECIFIC DOCUMENT NAMES")
    logger.info("="*80)
    
    for doc_id, expected_name in fixes.items():
        # Get the full file path
        md_file = markdown_dir / expected_name
        if not md_file.exists():
            logger.warning(f"  ⚠️  Markdown file not found: {expected_name}")
            continue
        
        # Update the document
        try:
            result = client.table('gdd_documents').update({
                'name': expected_name,
                'file_path': str(md_file)
            }).eq('doc_id', doc_id).execute()
            
            # Check if update worked by querying the document
            check = client.table('gdd_documents').select('name').eq('doc_id', doc_id).execute()
            if check.data:
                current_name = check.data[0].get('name', '')
                logger.info(f"  ✅ Updated {doc_id}")
                logger.info(f"     Name: {current_name}")
                logger.info(f"     File path: {md_file}")
            else:
                logger.warning(f"  ⚠️  Document not found: {doc_id}")
        except Exception as e:
            logger.error(f"  ❌ Error updating {doc_id}: {e}")
    
    logger.info("\n✅ Done!")


if __name__ == "__main__":
    fix_document_names()

