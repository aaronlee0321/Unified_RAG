# How to Create the `gdd_pdfs` Storage Bucket in Supabase

The application needs a storage bucket named `gdd_pdfs` to store uploaded PDF files. If you see a "Bucket not found" error, follow these steps:

## Steps to Create the Bucket

1. **Go to your Supabase Dashboard**
   - Visit https://app.supabase.com
   - Log in and select your project

2. **Navigate to Storage**
   - In the left sidebar, click on **"Storage"**

3. **Create New Bucket**
   - Click the **"New bucket"** button (or **"Create bucket"**)
   - Enter the bucket name: `gdd_pdfs`
   - **Important**: Make sure the name is exactly `gdd_pdfs` (lowercase, with underscore)

4. **Configure Bucket Settings**
   - **Public bucket**: 
     - ✅ Check "Public bucket" if you want PDFs to be accessible via public URLs
     - ❌ Uncheck if you want PDFs to be private (requires authentication)
   - For most use cases, **public bucket is recommended** so users can view PDFs directly

5. **Set Bucket Policies (if needed)**
   - If you made it public, you may need to set policies:
     - Go to **"Policies"** tab for the bucket
     - Add a policy to allow public read access:
       ```sql
       -- Allow public read access
       CREATE POLICY "Public Access" ON storage.objects
       FOR SELECT USING (bucket_id = 'gdd_pdfs');
       ```

6. **Save the Bucket**
   - Click **"Create bucket"** or **"Save"**

## Verify the Bucket

After creating the bucket, you should see it listed in your Storage section. The bucket should be named exactly `gdd_pdfs`.

## Alternative: Use SQL to Create Bucket

If you prefer using SQL, you can run this in the Supabase SQL Editor:

```sql
-- Create the bucket
INSERT INTO storage.buckets (id, name, public)
VALUES ('gdd_pdfs', 'gdd_pdfs', true)
ON CONFLICT (id) DO NOTHING;

-- Allow public read access (if bucket is public)
CREATE POLICY IF NOT EXISTS "Public Access" ON storage.objects
FOR SELECT USING (bucket_id = 'gdd_pdfs');
```

## Note

- The application will continue to work even if the bucket doesn't exist - PDFs just won't be stored in Supabase Storage
- Documents will still be indexed and searchable, but the original PDF files won't be available for download/viewing
- Creating the bucket is recommended for full functionality
