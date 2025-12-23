-- Update match_code_chunks function to use ILIKE pattern matching for file_path
-- This allows matching paths even if they're in slightly different formats
-- (e.g., Windows paths from frontend vs normalized paths in database)

CREATE OR REPLACE FUNCTION match_code_chunks(
    query_embedding vector(1024),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10,
    file_path_filter TEXT DEFAULT NULL,
    chunk_type_filter TEXT DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    file_path TEXT,
    chunk_type TEXT,
    class_name TEXT,
    method_name TEXT,
    source_code TEXT,
    similarity float,
    metadata JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        cc.id,
        cc.file_path,
        cc.chunk_type,
        cc.class_name,
        cc.method_name,
        cc.source_code,
        1 - (cc.embedding <=> query_embedding) as similarity,
        cc.metadata
    FROM code_chunks cc
    WHERE 
        cc.embedding IS NOT NULL
        AND (file_path_filter IS NULL OR cc.file_path ILIKE '%' || file_path_filter || '%')
        AND (chunk_type_filter IS NULL OR cc.chunk_type = chunk_type_filter)
        AND (1 - (cc.embedding <=> query_embedding)) >= match_threshold
    ORDER BY cc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

