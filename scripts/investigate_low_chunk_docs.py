"""
Investigate documents with suspiciously low chunk counts.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / '.env')

from backend.storage.supabase_client import get_supabase_client

# Documents with suspiciously low chunk counts
problem_doc_ids = [
    "Combat_Module_Tank_War_Hệ_Thống_Auto_Focus",  # 1 chunk
    "Progression_Module_Tank_Wars_Tổng_Quan_Artifact_System",  # 1 chunk
    "Combat_Module_Tank_War_Hệ_Thống_Nâng_Cấp_Tank_In_Match",  # 2 chunks
]

def investigate_low_chunk_docs():
    """Investigate why these documents have so few chunks."""
    print("=" * 80)
    print("INVESTIGATING DOCUMENTS WITH LOW CHUNK COUNTS")
    print("=" * 80)
    
    try:
        client = get_supabase_client(use_service_key=True)
        
        for doc_id in problem_doc_ids:
            print(f"\n{'='*80}")
            print(f"DOCUMENT: {doc_id}")
            print(f"{'='*80}")
            
            # Get document info
            doc_result = client.table('gdd_documents').select('*').eq('doc_id', doc_id).execute()
            doc_info = doc_result.data[0] if doc_result.data else None
            
            if doc_info:
                print(f"\n[INFO] Document Info:")
                print(f"   Name: {doc_info.get('name', 'N/A')}")
                print(f"   File path: {doc_info.get('file_path', 'N/A')}")
                print(f"   DB chunks_count: {doc_info.get('chunks_count', 0)}")
                markdown_content = doc_info.get('markdown_content', '')
                if markdown_content:
                    print(f"   Markdown length: {len(markdown_content)} characters")
                    print(f"   Markdown preview (first 500 chars):")
                    print(f"   {markdown_content[:500]}...")
                else:
                    print(f"   Markdown content: (empty)")
            
            # Get all chunks
            chunks_result = client.table('gdd_chunks').select('*').eq('doc_id', doc_id).execute()
            chunks = chunks_result.data or []
            
            print(f"\n[INFO] Found {len(chunks)} chunks")
            
            for i, chunk in enumerate(chunks, 1):
                print(f"\n   Chunk {i}:")
                print(f"      ID: {chunk.get('id')}")
                print(f"      Content length: {len(chunk.get('content', ''))} characters")
                print(f"      section_path: {chunk.get('section_path') or '(empty)'}")
                print(f"      section_title: {chunk.get('section_title') or '(empty)'}")
                print(f"      metadata: {chunk.get('metadata', {})}")
                content = chunk.get('content', '')
                if content:
                    print(f"      Content preview (first 300 chars):")
                    print(f"      {content[:300]}...")
                else:
                    print(f"      Content: (empty)")
            
            # Check if markdown exists and estimate expected chunks
            if doc_info and markdown_content:
                # Rough estimate: chunks are typically 500-2000 chars
                estimated_chunks = len(markdown_content) // 1000
                print(f"\n[INFO] Estimated chunks (based on markdown length): ~{estimated_chunks}")
                print(f"[WARN] Actual chunks: {len(chunks)}")
                if len(chunks) < estimated_chunks:
                    print(f"[ERROR] Document appears to be under-chunked!")
        
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    investigate_low_chunk_docs()


