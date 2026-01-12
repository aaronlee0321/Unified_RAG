"""
Script to check Supabase Storage bucket configuration and test access.
Run this to verify your gdd_pdfs bucket is properly configured.
"""
import os
from backend.storage.supabase_client import get_supabase_client

def check_bucket_config():
    """Check if gdd_pdfs bucket exists and is accessible."""
    print("=" * 60)
    print("Checking Supabase Storage Bucket Configuration")
    print("=" * 60)
    
    bucket_name = "gdd_pdfs"
    
    try:
        # Try with service key (admin access)
        print(f"\n1. Testing bucket access with service key...")
        service_client = get_supabase_client(use_service_key=True)
        
        try:
            files = service_client.storage.from_(bucket_name).list()
            print(f"   ✅ Bucket '{bucket_name}' exists and is accessible")
            print(f"   📁 Found {len(files)} files in bucket")
            
            if files:
                print(f"\n   Sample files:")
                for i, file in enumerate(files[:5], 1):
                    print(f"   {i}. {file.get('name', 'Unknown')}")
                    print(f"      Size: {file.get('metadata', {}).get('size', 'Unknown')} bytes")
                    print(f"      Updated: {file.get('updated_at', 'Unknown')}")
        except Exception as e:
            print(f"   ❌ Error accessing bucket: {e}")
            print(f"   💡 Make sure the bucket '{bucket_name}' exists in Supabase Storage")
            return False
        
        # Try with anon key (public access)
        print(f"\n2. Testing public access with anon key...")
        anon_client = get_supabase_client(use_service_key=False)
        
        try:
            files = anon_client.storage.from_(bucket_name).list()
            print(f"   ✅ Public access works - bucket is public")
            
            # Try to get a public URL for the first file
            if files:
                test_file = files[0].get('name')
                try:
                    url = anon_client.storage.from_(bucket_name).get_public_url(test_file)
                    print(f"   ✅ Public URL generation works")
                    print(f"   🔗 Sample URL: {url[:80]}...")
                except Exception as e:
                    print(f"   ⚠️  Public URL generation failed: {e}")
                    print(f"   💡 Check RLS policies for the bucket")
        except Exception as e:
            print(f"   ❌ Public access failed: {e}")
            print(f"   💡 The bucket might not be public or RLS policies need to be set")
            print(f"\n   To fix this:")
            print(f"   1. Go to Supabase Dashboard → Storage → Buckets")
            print(f"   2. Click on '{bucket_name}' bucket")
            print(f"   3. Make sure 'Public bucket' toggle is ON")
            print(f"   4. Go to 'Policies' tab and ensure there's a policy allowing SELECT")
            return False
        
        # Check database records
        print(f"\n3. Checking database records...")
        try:
            result = anon_client.table('keyword_documents').select('doc_id, name, file_path').limit(5).execute()
            if result.data:
                print(f"   ✅ Found {len(result.data)} documents in keyword_documents table")
                print(f"\n   Sample documents:")
                for doc in result.data[:3]:
                    doc_id = doc.get('doc_id', 'Unknown')
                    name = doc.get('name', 'Unknown')
                    file_path = doc.get('file_path', 'None')
                    print(f"   - {name}")
                    print(f"     doc_id: {doc_id}")
                    print(f"     file_path: {file_path}")
                    
                    # Check if file exists in bucket
                    if file_path:
                        file_name = file_path.replace('\\', '/').split('/')[-1]
                        file_exists = any(f.get('name') == file_name for f in files)
                        if file_exists:
                            print(f"     ✅ File exists in bucket")
                        else:
                            print(f"     ⚠️  File not found in bucket (might be named differently)")
            else:
                print(f"   ⚠️  No documents found in keyword_documents table")
        except Exception as e:
            print(f"   ❌ Error checking database: {e}")
        
        print(f"\n" + "=" * 60)
        print("✅ Bucket configuration check complete!")
        print("=" * 60)
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    check_bucket_config()


