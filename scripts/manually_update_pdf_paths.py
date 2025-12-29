"""
Manually update pdf_storage_path for specific documents.

Since the Python SDK can't list the storage bucket (permissions issue),
we'll manually update the database with the known PDF filenames.
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


# Manually list all PDF filenames from your storage
PDF_FILES = [
    "Asset_UI_Tank_War_Garage_Design_-_UI_UX.pdf",
    "Asset_UI_Tank_War_In-game_GUI_Design.pdf",
    "Asset_UI_Tank_War_Main_Screen_Design.pdf",
    "Asset_UI_Tank_War_Mode_Selection_Design.pdf",
    "Asset_UI_Tank_War_Result_Screen_Design.pdf",
    "Asset_UI_Tank_War_Reward_Screen_Design.pdf",
    "Asset_UI_Tank_War_Tank_Selection_Screen_Design.pdf",
    "Character_Module_Tank_War_Elemental_Class.pdf",
    "Character_Module_Tank_War_Garage_Design_-_Functions.pdf",
    "Character_Module_Tank_War_Garage_Design_-_Main.pdf",
    "Character_Module_Tank_War_Tank_System_Detail.pdf",
    "Combat_Module_Tank_War_He_Thong_Auto_Focus.pdf",
    "Combat_Module_Tank_War_He_Thong_Nang_Cap_Tank_In-Match.pdf",
    "Combat_Module_Tank_War_Mobile_Skill_Control_System.pdf",
    "Combat_Module_Tank_War_Outpost_Design_-_Base_Capture_Mode.pdf",
    "Combat_Module_Tank_War_Skill_Design_Document.pdf",
    "Demo_Map_Design_file.pdf",
    "Design_DB_schema.pdf",
    "Game_Mode_Module_Tank_War_Deathmatch.pdf",
    "Game_Mode_Module_Tank_War_Gold_in_Match.pdf",
    "Game_Mode_Module_Tank_War_Outpost_Breaker.pdf",
    "Monetization_Module_Tank_War_Economy_&_Monetization_System.pdf",
    "Monetization_Module_Tank_War_Garage_System.pdf",
    "Monetization_Module_Tank_War_Monetization_Localization_(LATAM).pdf",
    "Multiplayer_Module_Tank_War_Match_Profile_Design.pdf",
    "Multiplayer_Module_Tank_War_Matchmaking_System_Design.pdf",
    "Multiplayer_Module_Tank_War_Post-Match_Profile.pdf",
    "Progression_Module_Tank_War_ELO_&_RANK_System_-_OLD_(not_use).pdf",
    "Progression_Module_Tank_War_Leaderboard_System.pdf",
    "Progression_Module_Tank_War_Onboarding_Design_(Chua_xong).pdf",
    "Progression_Module_Tank_War_Onboarding_Tutorial_Mode_Design.pdf",
    "Progression_Module_Tank_Wars_Achievement_Design.pdf",
    "Progression_Module_Tank_Wars_Artifact_Enhancement.pdf",
    "Progression_Module_Tank_Wars_Fusion_Artifact.pdf",
    "Progression_Module_Tank_Wars_Tổng_Quan_Artifact_System.pdf",
    "string.pdf",
    "Tank_War_User_Profile_Design.pdf",
    "Weighted_Index_Formular.pdf",
    "World_Tank_War_Camera_Logic_System.pdf",
    "World_Tank_War_Grass_Logic_Design.pdf",
    "World_Tank_War_Map_Design_-_Outpost_Breaker.pdf",
    "World_Tank_War_Map_Document.pdf",
]


def update_pdf_paths_manually():
    """Manually update pdf_storage_path for documents."""
    
    try:
        client = get_supabase_client()
    except Exception as e:
        logger.error(f"Failed to get Supabase client: {e}")
        return
    
    logger.info("="*80)
    logger.info("MANUAL PDF PATH UPDATE")
    logger.info("="*80)
    
    # First, check if column exists
    logger.info("\n📋 Checking if pdf_storage_path column exists...")
    try:
        result = client.table('gdd_documents').select('doc_id, pdf_storage_path').limit(1).execute()
        logger.info("✓ Column exists!")
    except Exception as e:
        if "does not exist" in str(e):
            logger.error("❌ Column 'pdf_storage_path' does not exist!")
            logger.error("\nPlease run this SQL in your Supabase SQL Editor first:")
            logger.error("-" * 80)
            logger.error("ALTER TABLE gdd_documents ADD COLUMN IF NOT EXISTS pdf_storage_path TEXT;")
            logger.error("-" * 80)
            return
        else:
            logger.error(f"Error checking column: {e}")
            return
    
    # Get all documents
    logger.info("\n📊 Fetching all documents...")
    try:
        result = client.table('gdd_documents').select('doc_id, name').execute()
        documents = result.data or []
        logger.info(f"✓ Found {len(documents)} documents in database")
    except Exception as e:
        logger.error(f"❌ Error fetching documents: {e}")
        return
    
    # Update each document
    logger.info("\n🔗 Matching PDFs to documents...")
    logger.info("="*80)
    
    updated_count = 0
    not_found_count = 0
    
    for pdf_filename in PDF_FILES:
        # Extract doc_id from filename (remove .pdf)
        doc_id = pdf_filename[:-4]
        
        logger.info(f"\n📝 Processing: {pdf_filename}")
        logger.info(f"   Doc ID: {doc_id}")
        
        # Check if document exists
        matching_doc = None
        for doc in documents:
            if doc['doc_id'] == doc_id:
                matching_doc = doc
                break
        
        if not matching_doc:
            logger.warning(f"   ⚠️  Document '{doc_id}' not found in database")
            not_found_count += 1
            continue
        
        # Update the record
        try:
            client.table('gdd_documents').update({
                'pdf_storage_path': pdf_filename
            }).eq('doc_id', doc_id).execute()
            
            logger.info(f"   ✅ Updated successfully")
            updated_count += 1
        except Exception as e:
            logger.error(f"   ❌ Error updating: {e}")
    
    # Summary
    logger.info("\n" + "="*80)
    logger.info("UPDATE SUMMARY")
    logger.info("="*80)
    logger.info(f"PDFs to process:      {len(PDF_FILES)}")
    logger.info(f"Successfully updated: {updated_count}")
    logger.info(f"Not found in DB:      {not_found_count}")
    logger.info("="*80)
    
    # Verify
    logger.info("\n🔍 Verifying updates...")
    try:
        result = client.table('gdd_documents').select('doc_id, pdf_storage_path').execute()
        docs_with_pdf = [d for d in result.data if d.get('pdf_storage_path')]
        
        logger.info(f"✓ Documents with PDF path: {len(docs_with_pdf)}")
        
        if docs_with_pdf:
            logger.info("\nUpdated documents:")
            for doc in docs_with_pdf:
                logger.info(f"  - {doc['doc_id']}: {doc['pdf_storage_path']}")
    except Exception as e:
        logger.error(f"Error verifying: {e}")


if __name__ == "__main__":
    logger.info("Starting manual PDF path update...")
    logger.info(f"Project root: {PROJECT_ROOT}")
    update_pdf_paths_manually()
    logger.info("\n✅ Done!")
