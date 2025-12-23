"""
Test what paths are actually stored in Supabase
Run this to see what file_path values exist in the database
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

def test_supabase_paths():
    """Check what paths are stored in Supabase"""
    print("=" * 80)
    print("Supabase Path Check")
    print("=" * 80)
    
    try:
        client = get_supabase_client()
        
        # Get sample file paths from code_files
        print("\n1. Sample file_paths from code_files table:")
        result = client.table('code_files').select('file_path, file_name').limit(10).execute()
        if result.data:
            for file in result.data:
                print(f"   - {file.get('file_path', 'N/A')}")
                print(f"     File: {file.get('file_name', 'N/A')}")
        else:
            print("   No files found")
        
        # Get sample file paths from code_chunks
        print("\n2. Sample file_paths from code_chunks table:")
        result = client.table('code_chunks').select('file_path').limit(20).execute()
        if result.data:
            unique_paths = set()
            for chunk in result.data:
                path = chunk.get('file_path', '')
                if path:
                    unique_paths.add(path)
            
            print(f"   Found {len(unique_paths)} unique paths:")
            for path in sorted(list(unique_paths))[:10]:
                print(f"   - {path}")
        else:
            print("   No chunks found")
        
        # Test search with a normalized path
        print("\n3. Testing path matching:")
        from backend.storage.code_supabase_storage import normalize_path_consistent
        
        test_path = r'c:\users\cpu12391\desktop\gdd_rag_gradio\codebase_rag\tank_online_1-dev\assets\_gameassets\scripts\runtime\amplifyimpostors\plugins\editor\aistartscreen.cs'
        normalized = normalize_path_consistent(test_path)
        print(f"   Original: {test_path}")
        print(f"   Normalized: {normalized}")
        
        # Try to find matching chunks with different variations
        if normalized:
            print(f"\n   Testing different matching strategies:")
            
            # Strategy 1: Full normalized path
            result = client.table('code_chunks').select('id, file_path').ilike('file_path', f'%{normalized}%').limit(5).execute()
            print(f"   1. ILIKE '%{normalized}%': {len(result.data) if result.data else 0} chunks")
            
            # Strategy 2: Just the filename
            filename = normalized.split('/')[-1] if '/' in normalized else normalized
            result2 = client.table('code_chunks').select('id, file_path').ilike('file_path', f'%{filename}%').limit(5).execute()
            print(f"   2. ILIKE '%{filename}%': {len(result2.data) if result2.data else 0} chunks")
            if result2.data:
                print(f"      Sample matches:")
                for chunk in result2.data[:3]:
                    print(f"        - {chunk.get('file_path', 'N/A')}")
            
            # Strategy 3: Try with Assets/ instead of assets/
            normalized_assets = normalized.replace('/assets/', '/Assets/').replace('assets/', 'Assets/')
            result3 = client.table('code_chunks').select('id, file_path').ilike('file_path', f'%{normalized_assets}%').limit(5).execute()
            print(f"   3. ILIKE '%{normalized_assets}%': {len(result3.data) if result3.data else 0} chunks")
            
            # Strategy 4: Try with _GameAssets instead of _gameassets
            normalized_gameassets = normalized.replace('_gameassets', '_GameAssets').replace('_gamemodules', '_GameModules')
            result4 = client.table('code_chunks').select('id, file_path').ilike('file_path', f'%{normalized_gameassets}%').limit(5).execute()
            print(f"   4. ILIKE '%{normalized_gameassets}%': {len(result4.data) if result4.data else 0} chunks")
            
            # Show what paths actually exist that contain parts of our search
            print(f"\n   Searching for paths containing 'aistartscreen' (case-insensitive):")
            result5 = client.table('code_chunks').select('file_path').ilike('file_path', '%aistartscreen%').limit(10).execute()
            if result5.data:
                unique_paths = set(chunk.get('file_path', '') for chunk in result5.data)
                print(f"   Found {len(unique_paths)} unique paths:")
                for path in sorted(list(unique_paths)):
                    print(f"     - {path}")
            else:
                print("   No paths found containing 'aistartscreen'")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    test_supabase_paths()

