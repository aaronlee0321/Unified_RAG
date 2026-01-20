# Fixed: Table Not Found Error

## Problem
The app was trying to use `gdd_documents` and `gdd_chunks` tables that don't exist in your Supabase database.

**Error:**
```
Could not find the table 'public.gdd_documents' in the schema cache
```

## Solution
Updated the code to use the **shared tables** (`keyword_documents` and `keyword_chunks`) that are used by both Keyword Finder and GDD RAG features.

## Changes Made

### 1. Updated `insert_gdd_document()` function
- **Before:** Used `gdd_documents` table
- **After:** Uses `keyword_documents` table
- **Field mapping:**
  - `markdown_content` → `full_text`
  - `pdf_storage_path` → stored in `file_path`

### 2. Updated `insert_gdd_chunks()` function
- **Before:** Used `gdd_chunks` table
- **After:** Uses `keyword_chunks` table
- **Field mapping:**
  - Maps `section_title`/`subsection_title` → `section_heading`
  - Maps `section_index`/`paragraph_index` → `chunk_index`
  - Removed unsupported fields (`metadata`, `section_path`, etc.)

### 3. Updated other functions
- `get_gdd_documents()` → uses `keyword_documents`
- `get_gdd_document_markdown()` → uses `keyword_documents.full_text`
- `delete_gdd_document()` → uses `keyword_documents`
- PDF storage path lookup → uses `keyword_documents.file_path`

## Database Schema

Your Supabase database should have these tables (from README):

```sql
-- Keyword documents table (used by both Keyword Finder and GDD RAG)
CREATE TABLE IF NOT EXISTS keyword_documents (
    id SERIAL PRIMARY KEY,
    doc_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    file_path TEXT,
    file_size BIGINT,
    full_text TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Keyword chunks table (used by both Keyword Finder and GDD RAG)
CREATE TABLE IF NOT EXISTS keyword_chunks (
    id SERIAL PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES keyword_documents(doc_id) ON DELETE CASCADE,
    chunk_id TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    section_heading TEXT,
    chunk_index INTEGER,
    embedding vector(1536),  -- Vector embeddings for semantic search (GDD RAG)
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Next Steps

1. **Restart your Flask app:**
   ```bash
   python3 app.py
   ```

2. **Try uploading a document again** - it should work now!

3. **Verify it's working:**
   - Check the logs for successful indexing
   - Try querying a document through the web UI

## Notes

- The function names still use `gdd` prefix (e.g., `insert_gdd_document`) for clarity, but they now use the shared `keyword_*` tables
- This is the correct setup according to the README - you don't need separate `gdd_documents` or `gdd_chunks` tables
- Both Keyword Finder and GDD RAG features share the same tables, which simplifies the database schema
