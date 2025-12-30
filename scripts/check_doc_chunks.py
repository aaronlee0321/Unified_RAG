"""
Diagnostic script to check if documents have chunks in Supabase.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add backend to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / '.env')

from backend.storage.supabase_client import get_supabase_client

# Documents that are returning 0 sections
problem_doc_ids = [
    "Character_Module_Tank_War_Tank_System_Detail",
    "Combat_Module_Tank_War_Hệ_Thống_Auto_Focus",
    "Combat_Module_Tank_War_Hệ_Thống_Nâng_Cấp_Tank_In_Match",
    "Combat_Module_Tank_War_Mobile_Skill_Control_System",
    "Combat_Module_Tank_War_Outpost_Design_Base_Capture_Mode",
    "Combat_Module_Tank_War_Skill_Design_Document",
]

def check_doc_chunks():
    """Check if documents have chunks in Supabase."""
    print("=" * 80)
    print("CHECKING DOCUMENT CHUNKS IN SUPABASE")
    print("=" * 80)
    
    try:
        client = get_supabase_client(use_service_key=True)
        
        # First, get all unique doc_ids from gdd_chunks
        print("\n[INFO] Fetching all doc_ids from gdd_chunks table...")
        result = client.table('gdd_chunks').select('doc_id').execute()
        
        all_doc_ids = set()
        for row in (result.data or []):
            all_doc_ids.add(row.get('doc_id'))
        
        print(f"[OK] Found {len(all_doc_ids)} unique doc_ids with chunks in database")
        print(f"\n[INFO] Sample doc_ids (first 10):")
        for i, doc_id in enumerate(sorted(all_doc_ids)[:10], 1):
            print(f"   {i}. {doc_id}")
        
        # Check each problem doc_id
        print("\n" + "=" * 80)
        print("CHECKING PROBLEM DOC_IDS")
        print("=" * 80)
        
        for doc_id in problem_doc_ids:
            print(f"\n[CHECK] Checking: {doc_id}")
            
            # Check exact match
            result = client.table('gdd_chunks').select('id, doc_id, section_path').eq('doc_id', doc_id).limit(5).execute()
            exact_match_count = len(result.data or [])
            
            if exact_match_count > 0:
                print(f"   [OK] Found {exact_match_count} chunks (exact match)")
                # Get total count
                count_result = client.table('gdd_chunks').select('id', count='exact').eq('doc_id', doc_id).execute()
                total_count = count_result.count if hasattr(count_result, 'count') else exact_match_count
                print(f"   [INFO] Total chunks: {total_count}")
                
                # Show sample sections
                sections = set()
                for row in (result.data or []):
                    section = row.get('section_path', '')
                    if section:
                        sections.add(section)
                if sections:
                    print(f"   [INFO] Sample sections: {list(sections)[:3]}")
            else:
                print(f"   [WARN] No chunks found (exact match)")
                
                # Try case-insensitive search
                all_doc_ids_lower = {d.lower(): d for d in all_doc_ids}
                doc_id_lower = doc_id.lower()
                
                if doc_id_lower in all_doc_ids_lower:
                    actual_doc_id = all_doc_ids_lower[doc_id_lower]
                    print(f"   [WARN] Found case-insensitive match: {actual_doc_id}")
                    result2 = client.table('gdd_chunks').select('id').eq('doc_id', actual_doc_id).limit(1).execute()
                    count = len(result2.data or [])
                    print(f"   [INFO] Chunks for actual doc_id: {count}")
                else:
                    # Try fuzzy matching
                    print(f"   [INFO] Trying fuzzy matching...")
                    similar = []
                    for existing_doc_id in all_doc_ids:
                        # Normalize both for comparison
                        def normalize(text):
                            return text.lower().replace('_', '').replace('-', '').replace(' ', '')
                        
                        if normalize(doc_id) == normalize(existing_doc_id):
                            similar.append(existing_doc_id)
                        elif normalize(doc_id) in normalize(existing_doc_id) or normalize(existing_doc_id) in normalize(doc_id):
                            similar.append(existing_doc_id)
                    
                    if similar:
                        print(f"   [INFO] Similar doc_ids found:")
                        for similar_id in similar[:5]:
                            result3 = client.table('gdd_chunks').select('id').eq('doc_id', similar_id).limit(1).execute()
                            count = len(result3.data or [])
                            print(f"      - {similar_id} ({count} chunks)")
                    else:
                        print(f"   [ERROR] No similar doc_ids found")
        
        # Also check gdd_documents table
        print("\n" + "=" * 80)
        print("CHECKING GDD_DOCUMENTS TABLE")
        print("=" * 80)
        
        docs_result = client.table('gdd_documents').select('doc_id, name, chunks_count').execute()
        all_docs = {row.get('doc_id'): row for row in (docs_result.data or [])}
        
        print(f"✅ Found {len(all_docs)} documents in gdd_documents table")
        
        for doc_id in problem_doc_ids:
            if doc_id in all_docs:
                doc_info = all_docs[doc_id]
                chunks_count = doc_info.get('chunks_count', 0)
                name = doc_info.get('name', 'N/A')
                print(f"\n   ✅ {doc_id}")
                print(f"      Name: {name}")
                print(f"      Chunks count (from DB): {chunks_count}")
            else:
                print(f"\n   ❌ {doc_id} - NOT FOUND in gdd_documents")
        
        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total doc_ids with chunks: {len(all_doc_ids)}")
        print(f"Total documents in gdd_documents: {len(all_docs)}")
        print(f"Problem doc_ids checked: {len(problem_doc_ids)}")
        
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_doc_chunks()
