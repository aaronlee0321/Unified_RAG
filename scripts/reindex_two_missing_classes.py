"""
Reindex just AmplifyImpostor and NetworkObjectBaker to see what happens.
"""

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.storage.supabase_client import get_supabase_client
from backend.storage.code_supabase_storage import index_code_chunks_to_supabase
from gdd_rag_backbone.llm_providers import QwenProvider
from scripts.reindex_complete_codebase import find_type_declarations, build_class_like_chunks

def delete_type_chunks_for_file(file_path: str) -> int:
    """Delete all class/struct/interface/enum chunks for a file."""
    client = get_supabase_client(use_service_key=True)
    try:
        response = client.table('code_chunks').delete().eq('file_path', file_path).in_('chunk_type', ['class', 'struct', 'interface', 'enum']).execute()
        return len(response.data) if response.data else 0
    except Exception as e:
        print(f"  Error deleting: {e}")
        return 0

def reindex_file(file_path: str, full_path: str):
    """Reindex a single file with detailed logging."""
    print(f"\n{'=' * 80}")
    print(f"Reindexing: {file_path}")
    print(f"{'=' * 80}\n")
    
    if not os.path.exists(full_path):
        print(f"❌ File not found: {full_path}")
        return False
    
    # Read file
    with open(full_path, 'r', encoding='utf-8') as f:
        code_text = f.read()
    
    file_name = Path(full_path).name
    
    # Find all type declarations
    print("🔍 Finding type declarations...")
    types = find_type_declarations(code_text)
    print(f"   Found {len(types)} type declaration(s):")
    for type_info in types:
        print(f"   - {type_info['kind']} {type_info['name']} (start: {type_info['start']}, end: {type_info['end']}, size: {type_info['end'] - type_info['start']} chars)")
    
    # Filter for the specific classes we're looking for
    target_classes = ['AmplifyImpostor', 'NetworkObjectBaker']
    found_targets = [t for t in types if t['name'] in target_classes]
    
    if found_targets:
        print(f"\n✅ Found target classes:")
        for t in found_targets:
            print(f"   - {t['kind']} {t['name']}")
    else:
        print(f"\n❌ Target classes NOT found in types list!")
        return False
    
    # Build class chunks
    print("\n📦 Building class chunks...")
    chunks = build_class_like_chunks(code_text, file_path, file_name)
    print(f"   Built {len(chunks)} chunk(s)")
    
    # Check if target classes are in chunks
    target_chunks = [c for c in chunks if c.get('class_name') in target_classes]
    if target_chunks:
        print(f"\n✅ Target classes in chunks:")
        for c in target_chunks:
            print(f"   - {c.get('chunk_type')} {c.get('class_name')} (source_code length: {len(c.get('source_code', ''))})")
    else:
        print(f"\n❌ Target classes NOT in chunks!")
        return False
    
    # Initialize provider
    try:
        provider = QwenProvider()
    except Exception as e:
        print(f"❌ Error initializing QwenProvider: {e}")
        return False
    
    # Index to Supabase
    print(f"\n💾 Indexing to Supabase...")
    try:
        success = index_code_chunks_to_supabase(
            file_path=file_path,
            file_name=file_name,
            chunks=chunks,
            provider=provider
        )
        
        if success:
            print(f"✅ Successfully indexed {len(chunks)} chunk(s)")
            return True
        else:
            print(f"❌ Failed to index chunks")
            return False
    except Exception as e:
        print(f"❌ Error indexing: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    files = [
        ("Assets/_GameAssets/Scripts/Runtime/AmplifyImpostors/Plugins/Scripts/AmplifyImpostor.cs", "AmplifyImpostor"),
        ("Assets/Photon/Fusion/Runtime/Fusion.Unity.cs", "NetworkObjectBaker"),
    ]
    
    workspace_root = PROJECT_ROOT
    gdd_root = Path(r"c:\Users\CPU12391\Desktop\GDD_RAG_Gradio\codebase_RAG\tank_online_1-dev")
    
    for file_path, class_name in files:
        # Find file
        workspace_file = workspace_root / file_path
        gdd_file = gdd_root / file_path
        
        full_path = None
        if workspace_file.exists():
            full_path = str(workspace_file)
        elif gdd_file.exists():
            full_path = str(gdd_file)
        
        if not full_path:
            print(f"❌ File not found: {file_path}")
            continue
        
        # Delete existing chunks
        print(f"\n🗑️  Deleting existing type chunks...")
        deleted = delete_type_chunks_for_file(file_path)
        print(f"   Deleted {deleted} chunk(s)")
        
        # Reindex
        reindex_file(file_path, full_path)

if __name__ == "__main__":
    main()





