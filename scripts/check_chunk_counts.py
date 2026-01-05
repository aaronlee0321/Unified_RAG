"""
Check chunk counts for all documents in Supabase.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from collections import defaultdict

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

load_dotenv(project_root / '.env')

from backend.storage.supabase_client import get_supabase_client

def check_chunk_counts():
    """Check chunk counts for all documents."""
    print("=" * 80)
    print("CHECKING CHUNK COUNTS FOR ALL DOCUMENTS")
    print("=" * 80)
    
    try:
        client = get_supabase_client(use_service_key=True)
        
        # Get all chunks grouped by doc_id
        print("\n[INFO] Fetching all chunks from gdd_chunks table...")
        result = client.table('gdd_chunks').select('doc_id').execute()
        
        chunk_counts = defaultdict(int)
        for row in (result.data or []):
            doc_id = row.get('doc_id')
            if doc_id:
                chunk_counts[doc_id] += 1
        
        print(f"[OK] Found chunks for {len(chunk_counts)} unique doc_ids")
        
        # Get documents from gdd_documents table
        print("\n[INFO] Fetching documents from gdd_documents table...")
        docs_result = client.table('gdd_documents').select('doc_id, name, chunks_count').execute()
        all_docs = {row.get('doc_id'): row for row in (docs_result.data or [])}
        
        print(f"[OK] Found {len(all_docs)} documents in gdd_documents table")
        
        # Analyze chunk counts
        print("\n" + "=" * 80)
        print("CHUNK COUNT ANALYSIS")
        print("=" * 80)
        
        # Documents with 0 chunks
        docs_with_0_chunks = []
        # Documents with 1 chunk
        docs_with_1_chunk = []
        # Documents with 2-5 chunks (suspiciously low)
        docs_with_few_chunks = []
        # Documents with normal chunk counts (>5)
        docs_with_normal_chunks = []
        
        for doc_id, actual_chunk_count in sorted(chunk_counts.items()):
            doc_info = all_docs.get(doc_id, {})
            db_chunks_count = doc_info.get('chunks_count', 0)
            name = doc_info.get('name', 'N/A')
            
            if actual_chunk_count == 0:
                docs_with_0_chunks.append((doc_id, name, db_chunks_count))
            elif actual_chunk_count == 1:
                docs_with_1_chunk.append((doc_id, name, db_chunks_count, actual_chunk_count))
            elif actual_chunk_count <= 5:
                docs_with_few_chunks.append((doc_id, name, db_chunks_count, actual_chunk_count))
            else:
                docs_with_normal_chunks.append((doc_id, name, db_chunks_count, actual_chunk_count))
        
        # Also check documents in gdd_documents that have no chunks
        for doc_id, doc_info in all_docs.items():
            if doc_id not in chunk_counts:
                name = doc_info.get('name', 'N/A')
                db_chunks_count = doc_info.get('chunks_count', 0)
                docs_with_0_chunks.append((doc_id, name, db_chunks_count))
        
        # Print results
        print(f"\n[WARN] Documents with 0 chunks in gdd_chunks: {len(docs_with_0_chunks)}")
        if docs_with_0_chunks:
            print("   (These documents are not indexed or chunks were deleted)")
            for doc_id, name, db_count in docs_with_0_chunks[:10]:
                print(f"      - {doc_id}")
                print(f"        Name: {name}")
                print(f"        DB chunks_count: {db_count}")
                print()
        
        print(f"\n[ERROR] Documents with 1 chunk (SUSPICIOUS - should have many chunks): {len(docs_with_1_chunk)}")
        if docs_with_1_chunk:
            for doc_id, name, db_count, actual_count in docs_with_1_chunk:
                print(f"      - {doc_id}")
                print(f"        Name: {name}")
                print(f"        DB chunks_count: {db_count}")
                print(f"        Actual chunks in gdd_chunks: {actual_count}")
                print()
        
        print(f"\n[WARN] Documents with 2-5 chunks (LOW - might be incomplete): {len(docs_with_few_chunks)}")
        if docs_with_few_chunks:
            for doc_id, name, db_count, actual_count in docs_with_few_chunks[:10]:
                print(f"      - {doc_id}")
                print(f"        Name: {name}")
                print(f"        DB chunks_count: {db_count}")
                print(f"        Actual chunks in gdd_chunks: {actual_count}")
                print()
        
        print(f"\n[OK] Documents with >5 chunks (NORMAL): {len(docs_with_normal_chunks)}")
        if docs_with_normal_chunks:
            print("   Sample (first 5):")
            for doc_id, name, db_count, actual_count in docs_with_normal_chunks[:5]:
                print(f"      - {doc_id}: {actual_count} chunks (DB says: {db_count})")
        
        # Summary statistics
        print("\n" + "=" * 80)
        print("SUMMARY STATISTICS")
        print("=" * 80)
        print(f"Total documents in gdd_documents: {len(all_docs)}")
        print(f"Total doc_ids with chunks: {len(chunk_counts)}")
        print(f"Documents with 0 chunks: {len(docs_with_0_chunks)}")
        print(f"Documents with 1 chunk: {len(docs_with_1_chunk)}")
        print(f"Documents with 2-5 chunks: {len(docs_with_few_chunks)}")
        print(f"Documents with >5 chunks: {len(docs_with_normal_chunks)}")
        
        if chunk_counts:
            max_chunks = max(chunk_counts.values())
            min_chunks = min(chunk_counts.values())
            avg_chunks = sum(chunk_counts.values()) / len(chunk_counts)
            print(f"\nChunk count statistics:")
            print(f"   Min: {min_chunks}")
            print(f"   Max: {max_chunks}")
            print(f"   Average: {avg_chunks:.1f}")
        
        # Check for mismatches between DB chunks_count and actual chunks
        print("\n" + "=" * 80)
        print("MISMATCHES: DB chunks_count vs Actual chunks")
        print("=" * 80)
        mismatches = []
        for doc_id, actual_count in chunk_counts.items():
            doc_info = all_docs.get(doc_id, {})
            db_count = doc_info.get('chunks_count', 0)
            if db_count != actual_count:
                mismatches.append((doc_id, doc_info.get('name', 'N/A'), db_count, actual_count))
        
        if mismatches:
            print(f"[WARN] Found {len(mismatches)} documents with mismatched chunk counts:")
            for doc_id, name, db_count, actual_count in mismatches[:10]:
                print(f"   - {doc_id}")
                print(f"     Name: {name}")
                print(f"     DB chunks_count: {db_count}")
                print(f"     Actual chunks: {actual_count}")
                print()
        else:
            print("[OK] No mismatches found")
        
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_chunk_counts()


