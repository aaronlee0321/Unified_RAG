"""
Remove entire files from Supabase that can't be queried properly.
Deletes all chunks (method, class, struct, interface, enum) and file entries.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.storage.supabase_client import get_supabase_client

def remove_file_from_supabase(file_path: str) -> dict:
    """
    Remove all chunks and file entry for a file from Supabase.
    Returns dict with deletion counts.
    """
    client = get_supabase_client(use_service_key=True)
    
    result = {
        "file_path": file_path,
        "chunks_deleted": 0,
        "file_entry_deleted": 0,
        "errors": []
    }
    
    try:
        # Step 1: Delete all chunks (all types)
        print(f"  🗑️  Deleting all chunks for: {file_path}")
        chunks_response = client.table('code_chunks').delete().eq('file_path', file_path).execute()
        result["chunks_deleted"] = len(chunks_response.data) if chunks_response.data else 0
        print(f"     Deleted {result['chunks_deleted']} chunk(s)")
        
        # Step 2: Delete file entry from code_files
        print(f"  🗑️  Deleting file entry for: {file_path}")
        try:
            file_response = client.table('code_files').delete().eq('file_path', file_path).execute()
            result["file_entry_deleted"] = len(file_response.data) if file_response.data else 0
            print(f"     Deleted {result['file_entry_deleted']} file entry/entries")
        except Exception as e:
            error_msg = f"Error deleting file entry: {e}"
            result["errors"].append(error_msg)
            print(f"     ⚠️  {error_msg}")
        
        return result
        
    except Exception as e:
        error_msg = f"Error removing file: {e}"
        result["errors"].append(error_msg)
        print(f"     ❌ {error_msg}")
        return result

def main():
    # Files that can't be queried properly (missing main class chunks due to embedding failures)
    problematic_files = [
        "Assets/_GameAssets/Scripts/Runtime/AmplifyImpostors/Plugins/Scripts/AmplifyImpostor.cs",
        "Assets/Photon/Fusion/Runtime/Fusion.Unity.cs",
    ]
    
    print("=" * 80)
    print("Remove Problematic Files from Supabase")
    print("=" * 80)
    print(f"\nFiles to remove: {len(problematic_files)}")
    for f in problematic_files:
        print(f"  - {f}")
    
    print("\n⚠️  WARNING: This will delete ALL chunks and file entries for these files!")
    response = input("\nContinue? (yes/no): ")
    
    if response.lower() != 'yes':
        print("❌ Cancelled.")
        return
    
    print("\n" + "=" * 80)
    print("Removing files...")
    print("=" * 80)
    
    results = []
    for file_path in problematic_files:
        print(f"\n📄 Processing: {file_path}")
        result = remove_file_from_supabase(file_path)
        results.append(result)
    
    # Summary
    print(f"\n{'=' * 80}")
    print("Summary")
    print(f"{'=' * 80}\n")
    
    total_chunks = sum(r["chunks_deleted"] for r in results)
    total_files = sum(r["file_entry_deleted"] for r in results)
    total_errors = sum(len(r["errors"]) for r in results)
    
    print(f"✅ Successfully processed: {len(results)} file(s)")
    print(f"   Total chunks deleted: {total_chunks}")
    print(f"   Total file entries deleted: {total_files}")
    
    if total_errors > 0:
        print(f"\n⚠️  Errors encountered: {total_errors}")
        for result in results:
            if result["errors"]:
                print(f"\n   File: {result['file_path']}")
                for error in result["errors"]:
                    print(f"     - {error}")
    
    print(f"\n{'=' * 80}")

if __name__ == "__main__":
    main()





