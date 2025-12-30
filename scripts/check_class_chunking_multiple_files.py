"""
Check class chunking for multiple files.
Compares what's in Supabase vs what should be chunked.
"""

import sys
import re
from pathlib import Path
from typing import List, Dict, Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.storage.supabase_client import get_supabase_client

# Pattern to find type declarations (same as in reindex_complete_codebase.py)
TYPE_DECL_PATTERN = re.compile(
    r'^[ \t]*(?:\[[^\]]+\]\s*)*'  # Optional whitespace and attributes at line start
    r'(?:public|private|protected|internal|abstract|sealed|static|partial)?\s*'
    r'(?P<kind>class|struct|interface|enum)\s+'
    r'(?P<name>\w+)',
    re.MULTILINE | re.IGNORECASE
)

def find_classes_in_file(file_path: str) -> List[Dict[str, str]]:
    """Find all class/struct/interface/enum declarations in a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            code_text = f.read()
    except Exception as e:
        return []
    
    classes = []
    for match in TYPE_DECL_PATTERN.finditer(code_text):
        kind = match.group("kind").lower()
        name = match.group("name")
        classes.append({"kind": kind, "name": name})
    
    return classes

def get_chunks_from_supabase(file_path: str) -> List[Dict[str, Any]]:
    """Get all class/struct/interface/enum chunks from Supabase for a file."""
    client = get_supabase_client(use_service_key=True)
    
    try:
        response = client.table('code_chunks').select(
            'chunk_type, class_name, source_code'
        ).eq('file_path', file_path).in_('chunk_type', ['class', 'struct', 'interface', 'enum']).execute()
        
        return response.data if response.data else []
    except Exception as e:
        print(f"  Error querying Supabase: {e}")
        return []

def check_file(file_path: str, full_path: str = None):
    """Check chunking for a single file."""
    if full_path is None:
        # Try to find the file in the workspace
        # Check if it's in unified_rag_app
        workspace_path = PROJECT_ROOT / file_path
        if workspace_path.exists():
            full_path = str(workspace_path)
        else:
            # Try GDD_RAG_Gradio path
            gdd_path = Path(r"c:\Users\CPU12391\Desktop\GDD_RAG_Gradio\codebase_RAG\tank_online_1-dev") / file_path
            if gdd_path.exists():
                full_path = str(gdd_path)
            else:
                print(f"  ❌ File not found: {file_path}")
                return
    
    print(f"\n{'=' * 80}")
    print(f"File: {file_path}")
    print(f"{'=' * 80}")
    
    # Find classes in actual file
    print("\n📄 Classes in actual file:")
    actual_classes = find_classes_in_file(full_path)
    if actual_classes:
        for cls in actual_classes:
            print(f"   - {cls['kind']} {cls['name']}")
    else:
        print("   (none found)")
    
    # Get chunks from Supabase
    print("\n💾 Chunks in Supabase:")
    supabase_chunks = get_chunks_from_supabase(file_path)
    if supabase_chunks:
        for chunk in supabase_chunks:
            chunk_type = chunk.get('chunk_type', 'N/A')
            class_name = chunk.get('class_name', 'N/A')
            source_len = len(chunk.get('source_code', ''))
            print(f"   - {chunk_type} '{class_name}' ({source_len} chars)")
    else:
        print("   (none found)")
    
    # Compare
    print("\n🔍 Comparison:")
    actual_names = {(c['kind'], c['name']) for c in actual_classes}
    supabase_names = {(c.get('chunk_type', ''), c.get('class_name', '')) for c in supabase_chunks}
    
    missing_in_supabase = actual_names - supabase_names
    extra_in_supabase = supabase_names - actual_names
    
    if missing_in_supabase:
        print(f"   ❌ Missing in Supabase ({len(missing_in_supabase)}):")
        for kind, name in missing_in_supabase:
            print(f"      - {kind} {name}")
    
    if extra_in_supabase:
        print(f"   ⚠️  Extra in Supabase (incorrect chunks) ({len(extra_in_supabase)}):")
        for kind, name in extra_in_supabase:
            print(f"      - {kind} '{name}'")
    
    if not missing_in_supabase and not extra_in_supabase:
        print("   ✅ All classes correctly chunked!")

def main():
    # Files to check (from the image)
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
    print("Checking Class Chunking for Multiple Files")
    print("=" * 80)
    
    # Try to find files in both workspaces
    workspace_root = PROJECT_ROOT
    gdd_root = Path(r"c:\Users\CPU12391\Desktop\GDD_RAG_Gradio\codebase_RAG\tank_online_1-dev")
    
    for file_path in files_to_check:
        # Try unified_rag_app first
        workspace_file = workspace_root / file_path
        gdd_file = gdd_root / file_path
        
        if workspace_file.exists():
            check_file(file_path, str(workspace_file))
        elif gdd_file.exists():
            check_file(file_path, str(gdd_file))
        else:
            # Just check Supabase
            check_file(file_path)
    
    print(f"\n{'=' * 80}")
    print("✅ Check complete!")
    print(f"{'=' * 80}")

if __name__ == "__main__":
    main()





