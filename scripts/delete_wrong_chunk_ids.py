"""
Delete all chunks with wrong chunk_id format (those without doc_id prefix).

Wrong format: chunk_001, chunk_002 (not globally unique)
Correct format: {doc_id}_chunk_001, {doc_id}_chunk_002

This script identifies and deletes chunks that don't have the doc_id prefix.
"""

import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / '.env')

from backend.storage.supabase_client import get_supabase_client
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def delete_wrong_chunk_ids():
    """Delete chunks with wrong chunk_id format."""
    logger.info("=" * 80)
    logger.info("DELETING CHUNKS WITH WRONG CHUNK_ID FORMAT")
    logger.info("=" * 80)
    
    try:
        client = get_supabase_client(use_service_key=True)
        
        # Get all chunks
        logger.info("Fetching all chunks from gdd_chunks table...")
        result = client.table('gdd_chunks').select('chunk_id, doc_id').execute()
        
        all_chunks = result.data or []
        logger.info(f"Found {len(all_chunks)} total chunks")
        
        # Identify chunks with wrong format
        # Wrong format: chunk_id starts with "chunk_" and doesn't contain "_" before it
        # Correct format: chunk_id is "{doc_id}_chunk_XXX"
        wrong_chunks = []
        correct_chunks = []
        
        for chunk in all_chunks:
            chunk_id = chunk.get('chunk_id', '')
            doc_id = chunk.get('doc_id', '')
            
            # Check if chunk_id is in wrong format
            # Wrong: "chunk_001" (no doc_id prefix)
            # Correct: "Doc_ID_chunk_001" (has doc_id prefix)
            if chunk_id.startswith('chunk_') and '_' not in chunk_id[:chunk_id.index('chunk_')]:
                # This is wrong format - chunk_id doesn't have doc_id prefix
                wrong_chunks.append({
                    'chunk_id': chunk_id,
                    'doc_id': doc_id
                })
            else:
                correct_chunks.append({
                    'chunk_id': chunk_id,
                    'doc_id': doc_id
                })
        
        logger.info(f"\n[ANALYSIS]")
        logger.info(f"  Total chunks: {len(all_chunks)}")
        logger.info(f"  Wrong format (will be deleted): {len(wrong_chunks)}")
        logger.info(f"  Correct format (will be kept): {len(correct_chunks)}")
        
        if wrong_chunks:
            logger.info(f"\n[INFO] Sample wrong format chunks (first 10):")
            for i, chunk in enumerate(wrong_chunks[:10], 1):
                logger.info(f"  {i}. chunk_id: {chunk['chunk_id']}, doc_id: {chunk['doc_id']}")
        
        if not wrong_chunks:
            logger.info("\n[SUCCESS] No chunks with wrong format found!")
            return
        
        # Group wrong chunks by doc_id for reporting
        wrong_by_doc = {}
        for chunk in wrong_chunks:
            doc_id = chunk['doc_id']
            if doc_id not in wrong_by_doc:
                wrong_by_doc[doc_id] = []
            wrong_by_doc[doc_id].append(chunk['chunk_id'])
        
        logger.info(f"\n[INFO] Wrong chunks by document:")
        for doc_id, chunk_ids in sorted(wrong_by_doc.items()):
            logger.info(f"  {doc_id}: {len(chunk_ids)} chunks")
        
        # Delete chunks with wrong format
        logger.info(f"\n[ACTION] Deleting {len(wrong_chunks)} chunks with wrong format...")
        
        deleted_count = 0
        batch_size = 100
        
        for i in range(0, len(wrong_chunks), batch_size):
            batch = wrong_chunks[i:i + batch_size]
            chunk_ids_to_delete = [chunk['chunk_id'] for chunk in batch]
            
            try:
                # Delete by chunk_id
                result = client.table('gdd_chunks').delete().in_('chunk_id', chunk_ids_to_delete).execute()
                batch_deleted = len(result.data) if result.data else 0
                deleted_count += batch_deleted
                logger.info(f"  Deleted batch {i//batch_size + 1}: {batch_deleted} chunks")
            except Exception as e:
                logger.error(f"  Error deleting batch {i//batch_size + 1}: {e}")
        
        logger.info(f"\n[RESULT] Deleted {deleted_count} chunks with wrong format")
        
        # Verify deletion
        logger.info(f"\n[VERIFICATION] Verifying deletion...")
        verify_result = client.table('gdd_chunks').select('chunk_id').execute()
        remaining_chunks = verify_result.data or []
        
        # Check if any wrong format chunks remain
        remaining_wrong = []
        for chunk in remaining_chunks:
            chunk_id = chunk.get('chunk_id', '')
            if chunk_id.startswith('chunk_') and '_' not in chunk_id[:chunk_id.index('chunk_')]:
                remaining_wrong.append(chunk_id)
        
        if remaining_wrong:
            logger.warning(f"  [WARN] {len(remaining_wrong)} wrong format chunks still remain")
            logger.warning(f"  Sample: {remaining_wrong[:5]}")
        else:
            logger.info(f"  [OK] All wrong format chunks deleted successfully")
        
        logger.info(f"\n[SUMMARY]")
        logger.info(f"  Total chunks before: {len(all_chunks)}")
        logger.info(f"  Wrong format chunks: {len(wrong_chunks)}")
        logger.info(f"  Deleted: {deleted_count}")
        logger.info(f"  Remaining chunks: {len(remaining_chunks)}")
        logger.info(f"  Remaining wrong format: {len(remaining_wrong)}")
        
    except Exception as e:
        logger.error(f"\n[ERROR] Error deleting wrong chunk IDs: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    delete_wrong_chunk_ids()
