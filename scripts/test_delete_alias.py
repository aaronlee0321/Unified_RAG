"""
Test script to verify delete alias functionality works with Supabase.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env')
except:
    pass

from backend.storage.keyword_storage import insert_alias, delete_alias, list_all_aliases

print("=" * 60)
print("Delete Alias Test")
print("=" * 60)
print()

# Test 1: Add a test alias
print("1️⃣  Adding test alias...")
try:
    result = insert_alias("test_keyword", "test_alias", "en")
    print(f"   ✅ Added: 'test_alias' -> 'test_keyword'")
except Exception as e:
    if 'duplicate' in str(e).lower() or 'unique' in str(e).lower():
        print("   ⚠️  Alias already exists (this is okay)")
    else:
        print(f"   ❌ Error: {e}")
        sys.exit(1)

print()

# Test 2: Verify it exists
print("2️⃣  Verifying alias exists...")
aliases = list_all_aliases()
test_found = False
for row in aliases:
    if row['keyword'].lower() == 'test_keyword' and row['alias'].lower() == 'test_alias':
        test_found = True
        print(f"   ✅ Found alias: '{row['alias']}' -> '{row['keyword']}'")
        break

if not test_found:
    print("   ⚠️  Alias not found in list (might be case mismatch)")

print()

# Test 3: Delete the alias
print("3️⃣  Deleting alias...")
try:
    success = delete_alias("test_keyword", "test_alias")
    if success:
        print("   ✅ Delete successful!")
    else:
        print("   ❌ Delete returned False (alias might not exist)")
except Exception as e:
    print(f"   ❌ Error: {e}")
    sys.exit(1)

print()

# Test 4: Verify it's deleted
print("4️⃣  Verifying alias is deleted...")
aliases_after = list_all_aliases()
still_exists = False
for row in aliases_after:
    if row['keyword'].lower() == 'test_keyword' and row['alias'].lower() == 'test_alias':
        still_exists = True
        print(f"   ❌ Alias still exists: '{row['alias']}' -> '{row['keyword']}'")
        break

if not still_exists:
    print("   ✅ Alias successfully deleted!")

print()
print("=" * 60)
print("✅ Delete alias test complete!")
print("=" * 60)

