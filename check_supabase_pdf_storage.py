"""
Check what's actually stored in Supabase for PDFs
"""

import os
import sys

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from backend.storage.supabase_client import get_supabase_client

# Get Supabase client
client = get_supabase_client()

print("="*80)
print("Checking gdd_documents table for PDF info")
print("="*80)

# Check gdd_documents table
result = client.table('gdd_documents').select('doc_id, name, file_path').limit(5).execute()

print(f"\nFound {len(result.data)} documents (showing first 5):")
for doc in result.data:
    print(f"\ndoc_id: {doc.get('doc_id')}")
    print(f"  name: {doc.get('name')}")
    print(f"  file_path: {doc.get('file_path')}")

print("\n" + "="*80)
print("Checking Supabase Storage buckets")
print("="*80)

# Check storage buckets
try:
    buckets = client.storage.list_buckets()
    print(f"\nFound {len(buckets)} storage buckets:")
    for bucket in buckets:
        print(f"  - {bucket['name']} (public: {bucket.get('public', False)})")
        
        # If gdd_pdfs bucket exists, list files
        if bucket['name'] == 'gdd_pdfs':
            print(f"\n    Files in {bucket['name']}:")
            files = client.storage.from_(bucket['name']).list()
            if files:
                for file in files[:10]:
                    print(f"      - {file['name']}")
            else:
                print("      (empty)")
except Exception as e:
    print(f"\nError checking storage: {e}")

print("\n" + "="*80)
