"""
Migration script to move aliases from local JSON file to Supabase.
Run this once to migrate existing aliases to the new Supabase storage.
"""
import sys
import json
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.keyword_storage import insert_alias
from backend.storage.supabase_client import get_supabase_client

def migrate_aliases():
    """Migrate aliases from JSON file to Supabase"""
    
    # Path to the old alias dictionary file
    alias_file = PROJECT_ROOT / 'data' / 'alias_dictionary.json'
    
    if not alias_file.exists():
        print(f"❌ Alias file not found at {alias_file}")
        print("   No migration needed - starting fresh with Supabase.")
        return
    
    print(f"📖 Reading aliases from {alias_file}...")
    
    try:
        with open(alias_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Error reading alias file: {e}")
        return
    
    keywords = data.get('keywords', [])
    if not keywords:
        print("ℹ️  No keywords found in file. Nothing to migrate.")
        return
    
    print(f"📊 Found {len(keywords)} keywords to migrate...")
    
    # Check if Supabase table exists
    try:
        client = get_supabase_client()
        # Try to query the table
        test_result = client.table('keyword_aliases').select('id').limit(1).execute()
        print("✅ Supabase keyword_aliases table is accessible")
    except Exception as e:
        print(f"❌ Error accessing Supabase table: {e}")
        print("   Please run the SQL migration first: deploy/setup_keyword_aliases.sql")
        return
    
    migrated_count = 0
    error_count = 0
    
    for kw in keywords:
        keyword_name = kw.get('name', '').strip()
        language = kw.get('language', 'EN').upper()
        aliases = kw.get('aliases', [])
        
        if not keyword_name:
            print(f"⚠️  Skipping keyword with no name: {kw}")
            continue
        
        # Normalize language
        lang_normalized = 'en' if language in ['EN', 'en'] else 'vi' if language in ['VN', 'vi'] else 'en'
        
        print(f"  📝 Migrating keyword: '{keyword_name}' ({lang_normalized}) with {len(aliases)} aliases...")
        
        for alias_obj in aliases:
            alias_name = alias_obj.get('name', '').strip()
            if not alias_name:
                continue
            
            try:
                insert_alias(keyword_name, alias_name, lang_normalized)
                migrated_count += 1
                print(f"    ✅ '{alias_name}' -> '{keyword_name}'")
            except Exception as e:
                error_count += 1
                # Check if it's a duplicate error (which is fine)
                if 'duplicate' in str(e).lower() or 'unique' in str(e).lower():
                    print(f"    ⚠️  '{alias_name}' already exists (skipping)")
                else:
                    print(f"    ❌ Error migrating '{alias_name}': {e}")
    
    print("\n" + "="*60)
    print(f"✅ Migration complete!")
    print(f"   Migrated: {migrated_count} aliases")
    if error_count > 0:
        print(f"   Errors: {error_count} (may include duplicates)")
    print("="*60)
    
    # Optionally backup the old file
    backup_file = alias_file.with_suffix('.json.backup')
    if not backup_file.exists():
        try:
            import shutil
            shutil.copy2(alias_file, backup_file)
            print(f"💾 Original file backed up to: {backup_file}")
        except Exception as e:
            print(f"⚠️  Could not create backup: {e}")
    
    print("\n💡 You can now delete or rename the old file if migration was successful.")
    print(f"   Old file location: {alias_file}")

if __name__ == '__main__':
    print("🚀 Starting alias migration from file to Supabase...\n")
    migrate_aliases()

