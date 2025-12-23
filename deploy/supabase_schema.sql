-- Supabase Database Schema for Unified RAG App
-- Run this in your Supabase SQL Editor after enabling pgvector extension

-- Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- GDD RAG Tables
-- ============================================================================

-- GDD Documents table (metadata)
CREATE TABLE IF NOT EXISTS gdd_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    file_path TEXT,
    file_size BIGINT,
    chunks_count INTEGER DEFAULT 0,
    indexed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- GDD Chunks table (with embeddings)
CREATE TABLE IF NOT EXISTS gdd_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id TEXT UNIQUE NOT NULL,
    doc_id TEXT NOT NULL REFERENCES gdd_documents(doc_id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(1024), -- Qwen text-embedding-v4 has 1024 dimensions
    metadata JSONB, -- Store additional metadata like chunk index, section, etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for vector similarity search on GDD chunks
CREATE INDEX IF NOT EXISTS gdd_chunks_embedding_idx ON gdd_chunks 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Index for filtering by doc_id
CREATE INDEX IF NOT EXISTS gdd_chunks_doc_id_idx ON gdd_chunks(doc_id);

-- ============================================================================
-- Code Q&A Tables
-- ============================================================================

-- Code Files table (metadata)
CREATE TABLE IF NOT EXISTS code_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path TEXT UNIQUE NOT NULL,
    file_name TEXT NOT NULL,
    normalized_path TEXT NOT NULL,
    indexed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Code Chunks table (methods and classes with embeddings)
CREATE TABLE IF NOT EXISTS code_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path TEXT NOT NULL REFERENCES code_files(file_path) ON DELETE CASCADE,
    chunk_type TEXT NOT NULL CHECK (chunk_type IN ('method', 'class')),
    class_name TEXT,
    method_name TEXT, -- NULL for class chunks
    source_code TEXT NOT NULL,
    code TEXT, -- For methods: the method code
    embedding vector(1024), -- Qwen text-embedding-v4 has 1024 dimensions
    doc_comment TEXT,
    constructor_declaration TEXT, -- For classes
    method_declarations TEXT, -- For classes
    code_references TEXT, -- Renamed from 'references' (PostgreSQL keyword)
    metadata JSONB, -- Store additional metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for vector similarity search on code chunks
CREATE INDEX IF NOT EXISTS code_chunks_embedding_idx ON code_chunks 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Index for filtering by file_path
CREATE INDEX IF NOT EXISTS code_chunks_file_path_idx ON code_chunks(file_path);

-- Index for filtering by chunk_type
CREATE INDEX IF NOT EXISTS code_chunks_type_idx ON code_chunks(chunk_type);

-- Composite index for common queries
CREATE INDEX IF NOT EXISTS code_chunks_file_type_idx ON code_chunks(file_path, chunk_type);

-- ============================================================================
-- Vector Search Functions
-- ============================================================================

-- Function for GDD chunk similarity search
CREATE OR REPLACE FUNCTION match_gdd_chunks(
    query_embedding vector(1024),
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 10,
    doc_id_filter TEXT DEFAULT NULL
)
RETURNS TABLE (
    chunk_id TEXT,
    doc_id TEXT,
    content TEXT,
    similarity float,
    metadata JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        gc.chunk_id,
        gc.doc_id,
        gc.content,
        1 - (gc.embedding <=> query_embedding) as similarity,
        gc.metadata
    FROM gdd_chunks gc
    WHERE 
        gc.embedding IS NOT NULL
        AND (doc_id_filter IS NULL OR gc.doc_id = doc_id_filter)
        AND (1 - (gc.embedding <=> query_embedding)) >= match_threshold
    ORDER BY gc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function for Code chunk similarity search
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

-- ============================================================================
-- Helper Functions
-- ============================================================================

-- Function to update document chunks count
CREATE OR REPLACE FUNCTION update_gdd_document_chunks_count()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE gdd_documents
    SET chunks_count = (
        SELECT COUNT(*) FROM gdd_chunks WHERE doc_id = NEW.doc_id
    ),
    updated_at = NOW()
    WHERE doc_id = NEW.doc_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update chunks count
CREATE TRIGGER update_gdd_chunks_count
AFTER INSERT OR DELETE ON gdd_chunks
FOR EACH ROW
EXECUTE FUNCTION update_gdd_document_chunks_count();

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Triggers for updated_at
CREATE TRIGGER update_gdd_documents_updated_at
BEFORE UPDATE ON gdd_documents
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_gdd_chunks_updated_at
BEFORE UPDATE ON gdd_chunks
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_code_files_updated_at
BEFORE UPDATE ON code_files
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_code_chunks_updated_at
BEFORE UPDATE ON code_chunks
FOR EACH ROW
EXECUTE FUNCTION update_updated_at_column();

