-- =============================================================================
-- Unified RAG – Supabase schema deploy script
-- Run this in Supabase SQL Editor (New Project → SQL Editor → New query) to
-- create all tables, indexes, and the storage bucket. Use with your own
-- SUPABASE_URL and keys so others can run the project with their own data.
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- =============================================================================
-- 1. keyword_documents (GDD / Keyword Finder documents)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.keyword_documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id text NOT NULL,
    name text NOT NULL,
    file_path text,
    file_size bigint,
    full_text text,
    chunks_count integer DEFAULT 0,
    indexed_at timestamptz DEFAULT now(),
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    gdd_version text,
    gdd_author text,
    gdd_date text,
    images jsonb DEFAULT '[]'::jsonb,
    CONSTRAINT keyword_documents_doc_id_key UNIQUE (doc_id)
);

-- =============================================================================
-- 2. keyword_chunks (chunks with embeddings for GDD RAG / Keyword Finder)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.keyword_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id text NOT NULL,
    doc_id text NOT NULL,
    content text NOT NULL,
    section_heading text,
    chunk_index integer,
    embedding vector(1536),
    created_at timestamptz DEFAULT now(),
    CONSTRAINT keyword_chunks_chunk_id_key UNIQUE (chunk_id)
);

CREATE INDEX IF NOT EXISTS keyword_chunks_doc_id_idx ON public.keyword_chunks USING btree (doc_id);
CREATE INDEX IF NOT EXISTS keyword_chunks_embedding_idx ON public.keyword_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS keyword_chunks_index_idx ON public.keyword_chunks USING btree (doc_id, chunk_index);
CREATE INDEX IF NOT EXISTS keyword_chunks_section_heading_idx ON public.keyword_chunks USING btree (section_heading);
CREATE INDEX IF NOT EXISTS keyword_chunks_content_fts_idx ON public.keyword_chunks USING gin (to_tsvector('english'::regconfig, content));

-- =============================================================================
-- 3. keyword_aliases (keyword ↔ alias mappings for Keyword Finder)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.keyword_aliases (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    keyword text NOT NULL,
    alias text NOT NULL,
    language text DEFAULT 'en'::text,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    CONSTRAINT keyword_aliases_keyword_alias_key UNIQUE (keyword, alias)
);

CREATE INDEX IF NOT EXISTS keyword_aliases_keyword_idx ON public.keyword_aliases USING btree (keyword);
CREATE INDEX IF NOT EXISTS keyword_aliases_alias_idx ON public.keyword_aliases USING btree (alias);
CREATE INDEX IF NOT EXISTS keyword_aliases_language_idx ON public.keyword_aliases USING btree (language);

-- =============================================================================
-- 4. code_files (indexed code files for Code Q&A)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.code_files (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path text NOT NULL,
    file_name text NOT NULL,
    normalized_path text NOT NULL,
    indexed_at timestamptz DEFAULT now(),
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    CONSTRAINT code_files_file_path_key UNIQUE (file_path)
);

CREATE INDEX IF NOT EXISTS code_files_file_path_idx ON public.code_files USING btree (file_path);
CREATE INDEX IF NOT EXISTS code_files_file_name_idx ON public.code_files USING btree (file_name);

-- =============================================================================
-- 5. code_chunks (method/class chunks with embeddings for Code Q&A)
-- =============================================================================
CREATE TABLE IF NOT EXISTS public.code_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    file_path text NOT NULL,
    chunk_type text NOT NULL,
    class_name text,
    method_name text,
    source_code text NOT NULL,
    code text,
    embedding vector(1024),
    doc_comment text,
    constructor_declaration text,
    method_declarations text,
    code_references text,
    metadata jsonb,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS code_chunks_file_path_idx ON public.code_chunks USING btree (file_path);
CREATE INDEX IF NOT EXISTS code_chunks_type_idx ON public.code_chunks USING btree (chunk_type);
CREATE INDEX IF NOT EXISTS code_chunks_file_type_idx ON public.code_chunks USING btree (file_path, chunk_type);
CREATE INDEX IF NOT EXISTS code_chunks_embedding_idx ON public.code_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- =============================================================================
-- 6. Full-text search indexes (keyword_documents)
-- =============================================================================
CREATE INDEX IF NOT EXISTS keyword_documents_fulltext_fts_idx ON public.keyword_documents USING gin (to_tsvector('english'::regconfig, full_text));
CREATE INDEX IF NOT EXISTS keyword_documents_name_fts_idx ON public.keyword_documents USING gin (to_tsvector('english'::regconfig, name));

-- =============================================================================
-- 7. Storage bucket "gdd_pdfs" (for GDD PDFs and images)
-- Supabase recommends creating buckets via Dashboard or API, not raw SQL.
-- After running this script:
--   • Dashboard: Project → Storage → New bucket → name: gdd_pdfs, Public: ON
--   • Or via API: supabase.storage.createBucket('gdd_pdfs', { public: true })
-- =============================================================================

-- =============================================================================
-- 8. Row Level Security (RLS) – enable if you want to restrict access.
-- With RLS disabled, anon + service_role keys can read/write; suitable for
-- single-tenant or trusted backend. Uncomment and adjust policies if needed.
-- =============================================================================
-- ALTER TABLE public.keyword_documents ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.keyword_chunks ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.keyword_aliases ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.code_files ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE public.code_chunks ENABLE ROW LEVEL SECURITY;
-- Then add policies, e.g.:
-- CREATE POLICY "Allow all for service role" ON public.keyword_documents FOR ALL USING (true);

-- =============================================================================
-- Done. Set SUPABASE_URL, SUPABASE_KEY (and SUPABASE_SERVICE_KEY for uploads)
-- in your .env and run the app.
-- =============================================================================
