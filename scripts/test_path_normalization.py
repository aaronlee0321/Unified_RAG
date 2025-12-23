"""
Test path normalization locally
Run this to see how paths are being normalized
"""

import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.code_supabase_storage import normalize_path_consistent

# Test paths from your logs
test_paths = [
    r'c:\users\cpu12391\desktop\gdd_rag_gradio\codebase_rag\tank_online_1-dev\assets\_gameassets\scripts\runtime\amplifyimpostors\plugins\editor\aistartscreen.cs',
    r'c:\users\cpu12391\desktop\gdd_rag_gradio\codebase_rag\tank_online_1-dev\assets\textmesh pro\examples & extras\scripts\benchmark04.cs',
]

print("=" * 80)
print("Path Normalization Test")
print("=" * 80)

for test_path in test_paths:
    normalized = normalize_path_consistent(test_path)
    print(f"\nOriginal:")
    print(f"  {test_path}")
    print(f"\nNormalized:")
    print(f"  {normalized}")
    print(f"\n{'=' * 80}")

