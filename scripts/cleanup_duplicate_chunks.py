"""
Clean up duplicate and incorrect chunks for a specific file.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.storage.supabase_client import get_supabase_client

def cleanup_file(file_path: str):
    """Delete duplicate and incorrect chunks for a file."""
    client = get_supabase_client(use_service_key=True)
    
    print(f"Cleaning up chunks for: {file_path}\n")
    
    # Get all chunks
    response = client.table('code_chunks').select(
        'id, chunk_type, class_name, created_at'
    ).eq('file_path', file_path).execute()
    
    print(f"Found {len(response.data)} total chunks\n")
    
    # Group by chunk_type and class_name
    chunks_by_type = {}
    for chunk in response.data:
        key = (chunk['chunk_type'], chunk.get('class_name'))
        if key not in chunks_by_type:
            chunks_by_type[key] = []
        chunks_by_type[key].append(chunk)
    
    # Find duplicates and incorrect chunks
    to_delete = []
    
    for (chunk_type, class_name), chunks in chunks_by_type.items():
        if len(chunks) > 1:
            # Keep the most recent, delete others
            chunks_sorted = sorted(chunks, key=lambda x: x.get('created_at', ''), reverse=True)
            print(f"  {chunk_type} '{class_name}': {len(chunks)} chunks - keeping newest, deleting {len(chunks)-1} duplicates")
            to_delete.extend([c['id'] for c in chunks_sorted[1:]])
        elif class_name in ['name', 'names']:
            # Delete incorrect chunks
            print(f"  {chunk_type} '{class_name}': INCORRECT - deleting")
            to_delete.append(chunks[0]['id'])
    
    # Delete chunks
    if to_delete:
        print(f"\nDeleting {len(to_delete)} chunk(s)...")
        for chunk_id in to_delete:
            try:
                client.table('code_chunks').delete().eq('id', chunk_id).execute()
            except Exception as e:
                print(f"  Error deleting {chunk_id}: {e}")
        print(f"✅ Deleted {len(to_delete)} chunk(s)")
    else:
        print("\n✅ No duplicates or incorrect chunks found")

if __name__ == "__main__":
    file_path = "Assets/_GameModules/Editor/NamingConventionScanner.cs"
    cleanup_file(file_path)









