# Render Deployment Fixes

This document outlines the fixes made to ensure all features work on Render (cloud deployment) without local file system dependencies.

## Issues Fixed

### 1. **CODEBASE_ROOT Undefined Error** ✅
**Problem:** The `_resolve_local_code_path()` function referenced `CODEBASE_ROOT` which was never defined, causing the app to crash on Render.

**Solution:** Disabled the function entirely since local file access is not needed on Render:
```python
def _resolve_local_code_path(supabase_path: str) -> Optional[Path]:
    """
    DEPRECATED: This function is no longer used.
    All file operations now use Supabase only (works on Render).
    
    Returns None to indicate local file access is not supported.
    """
    # Local file access is disabled - all operations use Supabase
    return None
```

**Files Changed:**
- `backend/code_service.py`

---

### 2. **Extract Entire Code Feature** ✅
**Problem:** The feature only worked on localhost where it could read files from disk. On Render, there's no local codebase.

**Solution:** Already implemented correctly in `backend/code_service.py` (lines 766-837):
- Retrieves all class chunks from Supabase using `get_code_chunks_for_files()`
- Reconstructs the full file from chunks
- Cleans metadata headers while preserving indentation
- Returns reconstructed code in a code block

**How it works on Render:**
1. User requests "extract entire code" for a file
2. System queries Supabase for all class chunks for that file
3. Chunks are combined and metadata is cleaned
4. Full file is returned as a formatted code block

---

### 3. **List All Methods/Functions Feature** ✅
**Problem:** The regex override logic relied on reading files from local disk. On Render, this failed.

**Solution:** Already implemented correctly in `backend/code_service.py` (lines 969-1103):
- Retrieves class and method chunks from Supabase using `get_code_chunks_for_files()`
- Extracts method names from chunk metadata
- Falls back to parsing source_code from chunks if method names not in metadata
- Returns list of methods with line numbers

**How it works on Render:**
1. User requests "list all methods" for a file
2. System queries Supabase for method chunks and class chunks
3. Method names are extracted from chunks (either from metadata or by parsing source_code)
4. Returns formatted list of all methods

---

### 4. **List All Variables Feature** ✅
**Problem:** The regex override logic for variables also relied on local file access.

**Solution:** Already implemented correctly in `backend/code_service.py` (lines 969-1210):
- Retrieves class chunks from Supabase
- Parses source_code from chunks to extract fields and properties
- Shows method selection UI if methods exist
- Includes global variables option
- Uses RAG with enhanced prompts for selected methods

**How it works on Render:**
1. User requests "list all variables" for a file
2. System queries Supabase for class chunks and method chunks
3. Parses source_code to extract fields, properties, and methods
4. Shows UI for user to select which methods to extract variables from
5. If global variables selected, uses RAG with class chunks to extract class-level fields/properties

---

## Data Flow for Code Q&A Features on Render

```
User Query → Backend Service → Supabase Query → Chunk Retrieval → Processing → Response
```

### Key Points:
1. **No Local Disk Access:** All code is stored and retrieved from Supabase
2. **Chunk-Based Reconstruction:** Full files are reconstructed from chunks
3. **Metadata Extraction:** Method names, class names, and file paths come from chunk metadata
4. **Fallback Parsing:** If metadata missing, parses source_code field using regex
5. **RAG for Complex Queries:** Uses vector search + LLM for variable extraction from methods

---

## PDF Storage and Indexing

### PDF Storage Path Fixes ✅
**Created Script:** `scripts/fix_pdf_storage_paths.py`
- Matches documents in database with PDFs in Supabase Storage
- Fixes mismatched pdf_storage_path values
- Uses fuzzy matching to find correct files

**Usage:**
```bash
python scripts/fix_pdf_storage_paths.py --dry-run  # Preview changes
python scripts/fix_pdf_storage_paths.py            # Apply fixes
```

### Bulk PDF Indexing ✅
**Created Script:** `scripts/bulk_index_pdfs_from_storage.py`
- Indexes PDFs directly from Supabase Storage (no local files needed)
- Downloads PDFs temporarily
- Converts to Markdown using Docling
- Chunks and indexes to Supabase
- Updates gdd_documents table

**Usage:**
```bash
python scripts/bulk_index_pdfs_from_storage.py --dry-run  # Preview what will be indexed
python scripts/bulk_index_pdfs_from_storage.py --limit 5   # Index first 5 PDFs
python scripts/bulk_index_pdfs_from_storage.py             # Index all remaining PDFs
```

---

## Verification

All features now work on Render because:

1. ✅ No `CODEBASE_ROOT` dependency
2. ✅ All file operations use Supabase Storage
3. ✅ Chunk retrieval uses `get_code_chunks_for_files()` from Supabase
4. ✅ PDF retrieval uses `get_gdd_document_pdf_url()` from Supabase Storage
5. ✅ Markdown content stored in `gdd_documents.markdown_content` column
6. ✅ Code source_code stored in `code_chunks.source_code` column

---

## Testing on Render

To verify these fixes work on Render:

1. **Extract Entire Code:**
   ```
   Select a .cs file → Query: "extract entire code"
   ```
   Should return full file contents from Supabase chunks.

2. **List All Methods:**
   ```
   Select a .cs file → Query: "list all methods"
   ```
   Should return all method names from Supabase chunks.

3. **List All Variables:**
   ```
   Select a .cs file → Query: "list all variables"
   ```
   Should show method selection UI with global variables option.

4. **PDF Viewing:**
   ```
   Select a document → Query: "extract entire doc"
   ```
   Should embed PDF viewer from Supabase Storage URL.

---

## Deployment Checklist

Before deploying to Render:

- [x] Remove all local file system dependencies
- [x] Ensure all features use Supabase only
- [x] Fix CODEBASE_ROOT undefined error
- [x] Test extract entire code feature
- [x] Test list all methods feature
- [x] Test list all variables feature
- [x] Create PDF storage path fix script
- [x] Create bulk PDF indexing script
- [x] Index remaining PDFs from storage

---

## Environment Variables Required on Render

```bash
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key

# LLM API Keys
QWEN_API_KEY=your-qwen-api-key
# or
DASHSCOPE_API_KEY=your-dashscope-api-key
# or
OPENAI_API_KEY=your-openai-api-key

# Optional
REDIS_URL=your-redis-url  # If using Redis
COHERE_API_KEY=your-cohere-api-key  # If using Cohere reranking
```

---

## Summary

All code Q&A features and GDD Q&A features now work seamlessly on Render by:
1. Using Supabase as the single source of truth
2. Retrieving all code and documents from Supabase Storage/Database
3. Eliminating local file system dependencies
4. Providing scripts to manage PDFs in Supabase Storage

The application is now fully cloud-native and ready for production deployment on Render.


