-- Fix keyword_search_documents function to use language-agnostic text search
-- This allows matching both English and Vietnamese keywords

-- STEP 1: Check current function definition (run this first to see what needs to be changed)
-- Uncomment the line below to see the current function:
-- SELECT pg_get_functiondef(oid) FROM pg_proc WHERE proname = 'keyword_search_documents';

-- STEP 2: Drop the existing function if it exists
-- Note: Adjust the parameter types if your function has different signature
DROP FUNCTION IF EXISTS keyword_search_documents(text, integer, text);

-- Recreate the function with 'simple' text search configuration (language-agnostic)
-- This will match both English and Vietnamese text
CREATE OR REPLACE FUNCTION keyword_search_documents(
    search_query TEXT,
    match_count INTEGER DEFAULT 100,
    doc_id_filter TEXT DEFAULT NULL
)
RETURNS TABLE (
    chunk_id TEXT,
    doc_id TEXT,
    doc_name TEXT,
    content TEXT,
    section_heading TEXT,
    relevance REAL
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        kc.chunk_id::TEXT,
        kc.doc_id::TEXT,
        kd.name::TEXT as doc_name,
        kc.content::TEXT,
        kc.section_heading::TEXT,
        -- Use 'simple' configuration for language-agnostic matching
        -- This works for both English and Vietnamese
        ts_rank(
            to_tsvector('simple', COALESCE(kc.content, '')),
            plainto_tsquery('simple', search_query)
        )::REAL as relevance
    FROM keyword_chunks kc
    JOIN keyword_documents kd ON kc.doc_id = kd.doc_id
    WHERE 
        -- Use 'simple' configuration for matching
        to_tsvector('simple', COALESCE(kc.content, '')) @@ plainto_tsquery('simple', search_query)
        AND (doc_id_filter IS NULL OR kc.doc_id = doc_id_filter)
    ORDER BY relevance DESC
    LIMIT match_count;
END;
$$;

-- Grant execute permission (adjust role as needed)
GRANT EXECUTE ON FUNCTION keyword_search_documents(TEXT, INTEGER, TEXT) TO authenticated;
GRANT EXECUTE ON FUNCTION keyword_search_documents(TEXT, INTEGER, TEXT) TO anon;

-- Add comment explaining the change
COMMENT ON FUNCTION keyword_search_documents IS 
'Search keyword documents using language-agnostic full-text search. 
Uses ''simple'' text search configuration to match both English and Vietnamese keywords.';
