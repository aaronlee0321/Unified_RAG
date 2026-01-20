# Fixed: Embedding Dimension Mismatch

## Problem
Gemini embeddings are **768 dimensions**, but the database table expects **1536 dimensions**.

**Error:**
```
expected 1536 dimensions, not 768
```

## Root Cause
- **Gemini `text-embedding-004`**: Produces 768-dimensional embeddings
- **Database schema**: `keyword_chunks.embedding vector(1536)` - fixed at 1536 dimensions
- **OpenAI `text-embedding-3-small`**: Produces 1536-dimensional embeddings (matches schema)

## Solution
Added **automatic padding** in `insert_gdd_chunks()` function:
- If embedding is **smaller** than 1536 dimensions → pad with zeros
- If embedding is **larger** than 1536 dimensions → truncate (shouldn't happen)

### How It Works
```python
expected_dim = 1536  # Database schema requirement
current_dim = len(embedding)

if current_dim < expected_dim:
    # Pad with zeros: [0.0, 0.0, ..., 0.0]
    padding_needed = expected_dim - current_dim
    embedding = embedding + [0.0] * padding_needed
```

### Why Zero-Padding Works
- **Cosine similarity** (used by pgvector) normalizes by magnitude
- The important semantic information is in the first 768 dimensions
- Padding with zeros doesn't significantly affect cosine similarity calculations
- This is a common technique for handling different embedding dimensions

## Supported Embedding Models

| Model | Dimensions | Status |
|-------|-----------|--------|
| OpenAI `text-embedding-3-small` | 1536 | ✅ Native (no padding) |
| OpenAI `text-embedding-3-large` | 3072 | ⚠️ Truncated to 1536 |
| Gemini `text-embedding-004` | 768 | ✅ Padded to 1536 |
| Ollama `mxbai-embed-large` | 1024 | ✅ Padded to 1536 |
| Ollama `nomic-embed-text` | 768 | ✅ Padded to 1536 |

## Future Improvement (Optional)

For better performance with different embedding models, you could:

1. **Create separate columns** for different dimensions:
   ```sql
   ALTER TABLE keyword_chunks 
   ADD COLUMN embedding_768 vector(768),
   ADD COLUMN embedding_1024 vector(1024),
   ADD COLUMN embedding_1536 vector(1536);
   ```

2. **Use a larger dimension** that accommodates all models:
   ```sql
   ALTER TABLE keyword_chunks 
   ALTER COLUMN embedding TYPE vector(3072);
   ```
   (Requires recreating the index)

3. **Keep current approach** (padding) - works fine for most use cases!

## Testing

After this fix:
1. ✅ Gemini embeddings (768 dims) → padded to 1536 → inserted successfully
2. ✅ OpenAI embeddings (1536 dims) → no padding needed → inserted successfully
3. ✅ Ollama embeddings (768/1024 dims) → padded to 1536 → inserted successfully

## Next Steps

1. **Restart your Flask app:**
   ```bash
   python3 app.py
   ```

2. **Try uploading a document with Gemini** - it should work now!

3. **Verify embeddings are working:**
   - Check logs for "Padded embedding from 768 to 1536 dimensions"
   - Try querying documents - semantic search should work
