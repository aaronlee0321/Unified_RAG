"""
Delete incorrect class chunks and reindex multiple files with fixed chunking logic.
"""

import os
import sys
from pathlib import Path
from typing import List, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.storage.supabase_client import get_supabase_client
from backend.storage.code_supabase_storage import index_code_chunks_to_supabase
from backend.code_service import _analyze_csharp_file_symbols
from gdd_rag_backbone.llm_providers import QwenProvider

# Import the fixed chunking functions
from scripts.reindex_complete_codebase import find_type_declarations, build_class_like_chunks

def delete_all_type_chunks_for_file(file_path: str) -> int:
    """Delete all class/struct/interface/enum chunks for a file."""
    client = get_supabase_client(use_service_key=True)
    
    try:
        response = client.table('code_chunks').delete().eq('file_path', file_path).in_('chunk_type', ['class', 'struct', 'interface', 'enum']).execute()
        deleted_count = len(response.data) if response.data else 0
        return deleted_count
    except Exception as e:
        print(f"  Error deleting chunks: {e}")
        return 0

def reindex_file(file_path: str, full_path: str) -> bool:
    """Reindex a single file."""
    print(f"\n{'=' * 80}")
    print(f"Reindexing: {file_path}")
    print(f"{'=' * 80}\n")
    
    if not os.path.exists(full_path):
        print(f"❌ File not found: {full_path}")
        return False
    
    # Read file
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            code_text = f.read()
    except Exception as e:
        print(f"❌ Error reading file: {e}")
        return False
    
    file_name = Path(full_path).name
    
    # Find all type declarations
    print("🔍 Finding type declarations...")
    types = find_type_declarations(code_text)
    print(f"   Found {len(types)} type declaration(s):")
    for type_info in types:
        print(f"   - {type_info['kind']} {type_info['name']}")
    
    if not types:
        print("⚠️  No types found!")
        return False
    
    # Build class chunks
    print("\n📦 Building class chunks...")
    chunks = build_class_like_chunks(code_text, file_path, file_name)
    print(f"   Built {len(chunks)} chunk(s)")
    
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
    # Files to fix
    files_to_check = [
        "Assets/_GameAssets/Scripts/Runtime/AmplifyImpostors/Plugins/Editor/ShaderEditorNode/AmplifyImpostorNode.cs",
        "Assets/_GameAssets/Scripts/Runtime/AmplifyImpostors/Plugins/Scripts/AmplifyImpostor.cs",
        "Assets/_GameModules/MatchMakingFusionModule/Scripts/MatchmakingManager.cs",
        "Assets/_GameModules/TankFusionModule/Scripts/Ability/AbilityBase.cs",
        "Assets/Photon/Fusion/Runtime/Fusion.Unity.cs",
        "Assets/Photon/Fusion/Runtime/Utilities/RunnerVisibility/RunnerAOIGizmos.cs",
        "Assets/Photon/Fusion/Runtime/Utilities/RunnerVisibility/RunnerVisibilityLink.cs",
        "Assets/Plugins/Demigiant/DOTweenPro/DOTweenTextMeshPro.cs",
    ]
    
    print("=" * 80)
    print("Fix Class Chunking for Multiple Files")
    print("=" * 80)
    
    # Try to find files in both workspaces
    workspace_root = PROJECT_ROOT
    gdd_root = Path(r"c:\Users\CPU12391\Desktop\GDD_RAG_Gradio\codebase_RAG\tank_online_1-dev")
    
    results = []
    
    for file_path in files_to_check:
        # Try unified_rag_app first
        workspace_file = workspace_root / file_path
        gdd_file = gdd_root / file_path
        
        full_path = None
        if workspace_file.exists():
            full_path = str(workspace_file)
        elif gdd_file.exists():
            full_path = str(gdd_file)
        
        if not full_path:
            print(f"\n⚠️  Skipping {file_path} - file not found")
            results.append((file_path, False, "File not found"))
            continue
        
        # Step 1: Delete existing chunks
        print(f"\n🗑️  Deleting existing chunks for {file_path}...")
        deleted = delete_all_type_chunks_for_file(file_path)
        print(f"   Deleted {deleted} chunk(s)")
        
        # Step 2: Reindex
        success = reindex_file(file_path, full_path)
        results.append((file_path, success, None))
    
    # Summary
    print(f"\n{'=' * 80}")
    print("Summary")
    print(f"{'=' * 80}\n")
    
    successful = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]
    
    print(f"✅ Successfully reindexed: {len(successful)} file(s)")
    for file_path, _, _ in successful:
        print(f"   - {file_path}")
    
    if failed:
        print(f"\n❌ Failed: {len(failed)} file(s)")
        for file_path, _, reason in failed:
            print(f"   - {file_path}: {reason}")
    
    print(f"\n{'=' * 80}")

if __name__ == "__main__":
    main()





