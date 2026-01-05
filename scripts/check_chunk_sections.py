"""
Check if chunks have section information.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / '.env')

from backend.storage.supabase_client import get_supabase_client

# Documents that are returning 0 sections
problem_doc_ids = [
    "Combat_Module_Tank_War_Hệ_Thống_Auto_Focus",
    "Combat_Module_Tank_War_Hệ_Thống_Nâng_Cấp_Tank_In_Match",
]

def check_chunk_sections():
    """Check if chunks have section information."""
    print("=" * 80)
    print("CHECKING CHUNK SECTIONS")
    print("=" * 80)
    
    try:
        client = get_supabase_client(use_service_key=True)
        
        for doc_id in problem_doc_ids:
            print(f"\n[CHECK] Checking: {doc_id}")
            
            result = client.table('gdd_chunks').select(
                'id, doc_id, section_path, section_title, metadata'
            ).eq('doc_id', doc_id).limit(10).execute()
            
            chunks = result.data or []
            print(f"   [INFO] Found {len(chunks)} chunks")
            
            for i, chunk in enumerate(chunks, 1):
                print(f"\n   Chunk {i}:")
                print(f"      ID: {chunk.get('id')}")
                print(f"      section_path: {chunk.get('section_path') or '(empty)'}")
                print(f"      section_title: {chunk.get('section_title') or '(empty)'}")
                metadata = chunk.get('metadata', {})
                if isinstance(metadata, dict):
                    numbered_header = metadata.get('numbered_header', '')
                    section_index = metadata.get('section_index', '')
                    print(f"      numbered_header: {numbered_header or '(empty)'}")
                    print(f"      section_index: {section_index or '(empty)'}")
                else:
                    print(f"      metadata: {metadata}")
        
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_chunk_sections()


