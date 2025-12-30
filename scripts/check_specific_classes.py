"""Check if specific classes are in Supabase."""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from backend.storage.supabase_client import get_supabase_client

client = get_supabase_client(use_service_key=True)

# Check AmplifyImpostor
print("Checking AmplifyImpostor:")
r = client.table('code_chunks').select('chunk_type, class_name').eq('file_path', 'Assets/_GameAssets/Scripts/Runtime/AmplifyImpostors/Plugins/Scripts/AmplifyImpostor.cs').eq('class_name', 'AmplifyImpostor').execute()
print(f"  Found: {len(r.data)} chunks")
for c in r.data:
    print(f"    {c['chunk_type']}: {c['class_name']}")

# Check NetworkObjectBaker
print("\nChecking NetworkObjectBaker:")
r = client.table('code_chunks').select('chunk_type, class_name').eq('file_path', 'Assets/Photon/Fusion/Runtime/Fusion.Unity.cs').eq('class_name', 'NetworkObjectBaker').execute()
print(f"  Found: {len(r.data)} chunks")
for c in r.data:
    print(f"    {c['chunk_type']}: {c['class_name']}")





