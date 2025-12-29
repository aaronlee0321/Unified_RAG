-- ============================================================
-- SQL Queries to Check GDD Documents Setup in Supabase
-- ============================================================

-- 1. Check if pdf_storage_path column exists in gdd_documents table
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'gdd_documents'
ORDER BY ordinal_position;

-- 2. Check what documents exist and their pdf_storage_path values
SELECT 
    doc_id,
    name,
    file_path,
    pdf_storage_path,
    markdown_content IS NOT NULL as has_markdown,
    created_at
FROM gdd_documents
ORDER BY created_at DESC;

-- 3. Count documents with/without PDF storage path
SELECT 
    COUNT(*) as total_documents,
    COUNT(pdf_storage_path) as documents_with_pdf_path,
    COUNT(*) - COUNT(pdf_storage_path) as documents_without_pdf_path
FROM gdd_documents;

-- 4. Check specific document mentioned in error
SELECT 
    doc_id,
    name,
    file_path,
    pdf_storage_path,
    CASE 
        WHEN markdown_content IS NOT NULL THEN 'Has markdown'
        ELSE 'No markdown'
    END as markdown_status
FROM gdd_documents
WHERE doc_id = 'Asset_UI_Tank_War_Main_Screen_Design';

-- 5. List all storage buckets (requires storage schema access)
-- Note: This may not work depending on your permissions
-- Run this in Supabase SQL Editor or check Storage section in UI
SELECT *
FROM storage.buckets
ORDER BY created_at DESC;

-- 6. Check if gdd-pdfs bucket exists
SELECT 
    id,
    name,
    public,
    created_at
FROM storage.buckets
WHERE name = 'gdd-pdfs';

-- 7. If bucket exists, check what files are in it
SELECT 
    name,
    bucket_id,
    created_at
FROM storage.objects
WHERE bucket_id = 'gdd-pdfs'
ORDER BY created_at DESC;
