"""Quick test to verify PDF access works"""
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.storage.supabase_client import get_supabase_client, get_gdd_document_pdf_url
import requests

# Test with service key
storage_client = get_supabase_client(use_service_key=True)
files = storage_client.storage.from_('gdd_pdfs').list()
print(f"Found {len(files)} files in storage:")
for f in files[:5]:
    print(f"  - {f.get('name')}")

# Test getting a URL
client = get_supabase_client()
test_doc = "Asset_UI_Tank_War_Mode_Selection_Design"
url = get_gdd_document_pdf_url(test_doc)
print(f"\nTest doc: {test_doc}")
print(f"URL: {url}")
if url:
    try:
        r = requests.head(url, timeout=5)
        print(f"Status: {r.status_code} - {'✓ Accessible' if r.status_code == 200 else '✗ Not accessible'}")
    except Exception as e:
        print(f"Error accessing URL: {e}")


