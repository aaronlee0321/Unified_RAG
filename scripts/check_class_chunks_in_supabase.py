"""
Check what class chunks are stored in Supabase for a specific file.
Compare with actual file to verify chunking correctness.
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.storage.supabase_client import get_supabase_client

def check_class_chunks(file_path: str):
    """
    Check what class chunks are stored in Supabase for the given file.
    """
    client = get_supabase_client(use_service_key=True)
    
    # Try different path formats
    path_variants = [
        file_path,
        file_path.replace('\\', '/'),
        file_path.replace('/', '\\'),
        f"Assets/{file_path.split('Assets/')[-1]}" if 'Assets/' in file_path else None,
    ]
    path_variants = [p for p in path_variants if p]
    
    print("=" * 80)
    print(f"Checking class chunks for: {file_path}")
    print("=" * 80)
    
    all_chunks = []
    
    for path_variant in path_variants:
        print(f"\nTrying path variant: {path_variant}")
        try:
            # Get all class chunks for this file
            response = client.table('code_chunks').select(
                'id, file_path, chunk_type, class_name, source_code, created_at'
            ).eq('file_path', path_variant).eq('chunk_type', 'class').execute()
            
            if response.data:
                print(f"✓ Found {len(response.data)} class chunk(s) with this path")
                all_chunks.extend(response.data)
                break
            else:
                print(f"✗ No chunks found with this path")
        except Exception as e:
            print(f"✗ Error querying with this path: {e}")
    
    # Also try case-insensitive search
    if not all_chunks:
        print("\nTrying case-insensitive search...")
        try:
            # Get all chunks and filter manually
            response = client.table('code_chunks').select(
                'id, file_path, chunk_type, class_name, source_code, created_at'
            ).eq('chunk_type', 'class').execute()
            
            if response.data:
                # Filter by filename
                filename = Path(file_path).name
                matching_chunks = [
                    chunk for chunk in response.data 
                    if Path(chunk['file_path']).name.lower() == filename.lower()
                ]
                
                if matching_chunks:
                    print(f"✓ Found {len(matching_chunks)} class chunk(s) by filename")
                    all_chunks = matching_chunks
        except Exception as e:
            print(f"✗ Error in case-insensitive search: {e}")
    
    if not all_chunks:
        print("\n❌ No class chunks found in Supabase for this file!")
        return
    
    print(f"\n{'=' * 80}")
    print(f"Found {len(all_chunks)} class chunk(s):")
    print(f"{'=' * 80}\n")
    
    for i, chunk in enumerate(all_chunks, 1):
        print(f"Chunk {i}:")
        print(f"  File Path: {chunk['file_path']}")
        print(f"  Class Name: {chunk.get('class_name', 'N/A')}")
        print(f"  Created At: {chunk.get('created_at', 'N/A')}")
        
        source_code = chunk.get('source_code', '')
        if source_code:
            # Show first 500 chars and last 200 chars
            print(f"  Source Code Length: {len(source_code)} characters")
            print(f"  First 500 chars:")
            print(f"  {'-' * 76}")
            print(f"  {source_code[:500]}")
            if len(source_code) > 500:
                print(f"  ... ({len(source_code) - 500} more characters) ...")
                print(f"  Last 200 chars:")
                print(f"  {source_code[-200:]}")
            print(f"  {'-' * 76}")
        else:
            print(f"  ⚠️  No source_code found!")
        
        print()
    
    # Summary
    print(f"{'=' * 80}")
    print("Summary:")
    print(f"  Total chunks: {len(all_chunks)}")
    class_names = [chunk.get('class_name', 'N/A') for chunk in all_chunks]
    print(f"  Class names: {', '.join(class_names)}")
    print(f"{'=' * 80}")

if __name__ == "__main__":
    # File to check
    file_path = "Assets/_GameModules/Editor/NamingConventionScanner.cs"
    
    # Also accept command line argument
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
    
    check_class_chunks(file_path)









