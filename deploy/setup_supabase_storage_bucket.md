# Setup Supabase Storage Bucket for PDFs

## Problem
The error `"Bucket not found"` means the `gdd-pdfs` storage bucket doesn't exist in your Supabase project yet.

## Solution: Create the Storage Bucket

### Option 1: Via Supabase Dashboard (Recommended)

1. Go to your Supabase Dashboard: https://app.supabase.com
2. Select your project
3. Navigate to **Storage** in the left sidebar
4. Click **"New bucket"**
5. Configure the bucket:
   - **Name**: `gdd-pdfs`
   - **Public bucket**: ✅ **YES** (check this box)
   - **File size limit**: 50 MB (or as needed)
   - **Allowed MIME types**: `application/pdf`
6. Click **"Create bucket"**

### Option 2: Via SQL (Alternative)

Run this SQL in your Supabase SQL Editor:

```sql
-- Create the gdd-pdfs bucket
INSERT INTO storage.buckets (id, name, public)
VALUES ('gdd-pdfs', 'gdd-pdfs', true);

-- Set up RLS policies for public read access
CREATE POLICY "Public Access for PDFs"
ON storage.objects FOR SELECT
USING (bucket_id = 'gdd-pdfs');

CREATE POLICY "Authenticated users can upload PDFs"
ON storage.objects FOR INSERT
WITH CHECK (
  bucket_id = 'gdd-pdfs' 
  AND auth.role() = 'authenticated'
);
```

## After Creating the Bucket

### Upload Your PDF Files

You need to upload your PDF files to the bucket. You can do this via:

1. **Supabase Dashboard**:
   - Go to Storage → gdd-pdfs bucket
   - Click "Upload file"
   - Upload your PDFs from `gdd_data/source/` directory

2. **Using Python script** (recommended for bulk upload):

```python
# Run this script to upload all PDFs
python scripts/upload_pdfs_to_supabase.py
```

### Verify the Setup

After creating the bucket and uploading files, run these SQL queries to verify:

```sql
-- Check bucket exists
SELECT * FROM storage.buckets WHERE name = 'gdd-pdfs';

-- Check uploaded files
SELECT name, created_at 
FROM storage.objects 
WHERE bucket_id = 'gdd-pdfs'
ORDER BY created_at DESC;

-- Get public URL for a test file
SELECT 
    name,
    'https://' || current_setting('app.settings.supabase_url')::text || '/storage/v1/object/public/gdd-pdfs/' || name as public_url
FROM storage.objects 
WHERE bucket_id = 'gdd-pdfs'
LIMIT 5;
```

## Update Document Records

After uploading PDFs, update the `gdd_documents` table to reference them:

```sql
-- Example: Update a document to reference its PDF
UPDATE gdd_documents
SET pdf_storage_path = 'Asset_UI_Tank_War_Main_Screen_Design.pdf'
WHERE doc_id = 'Asset_UI_Tank_War_Main_Screen_Design';
```

Or use the bulk upload script which will update both the storage AND the database records.
