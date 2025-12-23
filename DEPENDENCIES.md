# Dependencies Included in unified_rag_app

This document lists all dependencies that have been copied into `unified_rag_app` to make it self-contained for deployment.

## Included Dependencies

### 1. `gdd_rag_backbone/`
**Source:** `../gdd_rag_backbone/`  
**Location:** `unified_rag_app/gdd_rag_backbone/`  
**Purpose:** Core RAG functionality including:
- LLM providers (Qwen, Gemini, Vertex AI)
- RAG backend (chunking, querying, reranking)
- Markdown chunking utilities
- Document indexing scripts

**Used by:**
- `backend/gdd_service.py` - For GDD document queries and indexing
- `backend/code_service.py` - For LLM providers (embeddings, chat)
- `backend/storage/gdd_supabase_storage.py` - For reranking and chunk QA
- `backend/storage/code_supabase_storage.py` - For embeddings

### 2. `backend/code_qa_prompts.py`
**Source:** `../codebase_RAG/code_qa/prompts.py`  
**Location:** `unified_rag_app/backend/code_qa_prompts.py`  
**Purpose:** System prompts for Code Q&A:
- `HYDE_SYSTEM_PROMPT` - Query rewriting
- `HYDE_V2_SYSTEM_PROMPT` - Enhanced query refinement
- `CHAT_SYSTEM_PROMPT` - Code-aware assistant prompts

**Used by:**
- `backend/code_service.py` - For Code Q&A queries

## External Dependencies (Not Included)

### PDFtoMarkdown
**Status:** Not included  
**Reason:** PDF upload functionality is currently disabled in the unified app  
**Note:** If PDF upload is needed, either:
1. Include `PDFtoMarkdown/` directory
2. Or use pre-converted markdown files

### Local Data Directories
**Status:** Not needed for deployment  
**Reason:** All data is stored in Supabase:
- GDD documents → `gdd_documents` and `gdd_chunks` tables
- Code files → `code_files` and `code_chunks` tables

**Local directories (for development only):**
- `rag_storage_md/` - Markdown chunks (local fallback)
- `rag_storage_md_indexed/` - Indexed chunks (local fallback)
- `codebase_RAG/code_qa/database/` - LanceDB (migrated to Supabase)

## Path Updates

All imports have been updated to use local paths instead of `PARENT_ROOT`:

### Before:
```python
PARENT_ROOT = PROJECT_ROOT.parent
from gdd_rag_backbone.llm_providers import ...
```

### After:
```python
# gdd_rag_backbone is now in unified_rag_app/gdd_rag_backbone/
from gdd_rag_backbone.llm_providers import ...
```

## Deployment Checklist

✅ `gdd_rag_backbone/` copied to `unified_rag_app/`  
✅ `code_qa_prompts.py` copied to `backend/`  
✅ All imports updated to use local paths  
✅ `PARENT_ROOT` references removed from main app files  
✅ Scripts still use `PARENT_ROOT` (for migration purposes only)

## Notes

- Migration scripts (`scripts/migrate_*.py`) still reference `PARENT_ROOT` to access original data locations
- These scripts are for one-time migration and don't need to be deployed
- The main app (`app.py`, `backend/*.py`) is now fully self-contained

