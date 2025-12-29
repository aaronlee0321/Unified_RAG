-- Add markdown_content column to gdd_documents table
-- This allows storing full markdown content in Supabase (no local file dependency)

ALTER TABLE gdd_documents
ADD COLUMN IF NOT EXISTS markdown_content TEXT;

-- Add index for full-text search if needed (optional)
-- CREATE INDEX IF NOT EXISTS gdd_documents_markdown_content_idx ON gdd_documents USING gin(to_tsvector('english', markdown_content));

COMMENT ON COLUMN gdd_documents.markdown_content IS 'Full markdown content of the document, stored in Supabase to eliminate local file dependencies';
