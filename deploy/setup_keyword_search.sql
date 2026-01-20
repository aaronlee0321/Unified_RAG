-- Keyword Search Function for Keyword Finder
-- This RPC function is required for the Keyword Finder feature to work
-- Run this in your Supabase SQL Editor

-- Drop existing function if it exists (to handle return type changes)
DROP FUNCTION IF EXISTS keyword_search_documents(TEXT, INT, TEXT);

-- Keyword search function for full-text search
CREATE OR REPLACE FUNCTION keyword_search_documents(
    search_query TEXT,
    match_count INT DEFAULT 100,
    doc_id_filter TEXT DEFAULT NULL
)
RETURNS TABLE (
    doc_id TEXT,
    doc_name TEXT,
    content TEXT,
    section_heading TEXT,
    relevance REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        kc.doc_id,
        kd.name AS doc_name,
        kc.content,
        kc.section_heading,
        ts_rank(to_tsvector('english', kc.content), plainto_tsquery('english', search_query)) AS relevance
    FROM keyword_chunks kc
    JOIN keyword_documents kd ON kc.doc_id = kd.doc_id
    WHERE 
        to_tsvector('english', kc.content) @@ plainto_tsquery('english', search_query)
        AND (doc_id_filter IS NULL OR kc.doc_id = doc_id_filter)
    ORDER BY relevance DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- Grant execute permission to authenticated users (or anon if needed)
-- Adjust based on your security requirements
GRANT EXECUTE ON FUNCTION keyword_search_documents(TEXT, INT, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION keyword_search_documents(TEXT, INT, TEXT) TO anon;
