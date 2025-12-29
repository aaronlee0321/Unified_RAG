-- Add pdf_storage_path column to gdd_documents table
-- This column stores the filename of the PDF in Supabase Storage (gdd_pdfs bucket)

ALTER TABLE gdd_documents 
ADD COLUMN IF NOT EXISTS pdf_storage_path TEXT;

-- Add comment to explain the column
COMMENT ON COLUMN gdd_documents.pdf_storage_path IS 
'Filename of the PDF file stored in the gdd_pdfs Supabase Storage bucket. Example: Asset_UI_Tank_War_Main_Screen_Design.pdf';

-- Create an index for faster queries
CREATE INDEX IF NOT EXISTS idx_gdd_documents_pdf_storage_path 
ON gdd_documents(pdf_storage_path);
