# Fix: Keyword Finder Not Loading Database

## Problem
The Keyword Finder feature doesn't load/search the database because the required SQL function is missing.

## Root Cause
The Keyword Finder uses a Supabase RPC (Remote Procedure Call) function called `keyword_search_documents` to search through your documents. This function needs to be created in your Supabase database.

## Solution

### Step 1: Create the Search Function

1. **Open Supabase Dashboard:**
   - Go to your Supabase project: https://supabase.com/dashboard
   - Select your project

2. **Open SQL Editor:**
   - Click on **SQL Editor** in the left sidebar
   - Click **New Query**

3. **Run the SQL Script:**
   - Copy the contents of `deploy/setup_keyword_search.sql`
   - Paste into the SQL Editor
   - Click **Run** (or press `Ctrl+Enter` / `Cmd+Enter`)

   **OR** run this SQL directly:

   ```sql
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

   -- Grant execute permission
   GRANT EXECUTE ON FUNCTION keyword_search_documents(TEXT, INT, TEXT) TO authenticated;
   GRANT EXECUTE ON FUNCTION keyword_search_documents(TEXT, INT, TEXT) TO anon;
   ```

4. **Verify it worked:**
   - You should see "Success. No rows returned" (this is normal - the function was created)
   - Check the Functions list in Supabase to confirm `keyword_search_documents` exists

### Step 2: Verify Your Data

Make sure you have documents indexed:

1. **Check if documents exist:**
   ```sql
   SELECT COUNT(*) FROM keyword_documents;
   ```

2. **Check if chunks exist:**
   ```sql
   SELECT COUNT(*) FROM keyword_chunks;
   ```

   If both return 0, you need to upload/index documents first!

### Step 3: Test the Keyword Finder

1. **Restart your Flask app** (if it's running):
   ```bash
   # Stop with Ctrl+C, then restart
   python3 app.py
   ```

2. **Open Keyword Finder:**
   - Go to http://localhost:13699/explainer
   - Enter a keyword (e.g., "tank", "combat", "system")
   - Click Search

3. **Expected Result:**
   - You should see document/section results appear
   - If you see "No results found", try a different keyword that exists in your documents

## Troubleshooting

### Error: "function keyword_search_documents does not exist"
- **Solution:** The function wasn't created. Go back to Step 1 and make sure you ran the SQL script successfully.

### Error: "permission denied for function keyword_search_documents"
- **Solution:** The GRANT statements didn't run. Run them again:
  ```sql
  GRANT EXECUTE ON FUNCTION keyword_search_documents(TEXT, INT, TEXT) TO authenticated;
  GRANT EXECUTE ON FUNCTION keyword_search_documents(TEXT, INT, TEXT) TO anon;
  ```

### "No results found" even with documents indexed
- **Possible causes:**
  1. **No chunks indexed:** Check `SELECT COUNT(*) FROM keyword_chunks;` - should be > 0
  2. **Keyword doesn't exist:** Try searching for words you know are in your documents
  3. **Full-text search not working:** Check if chunks have `content` field populated:
     ```sql
     SELECT doc_id, section_heading, LEFT(content, 50) as content_preview 
     FROM keyword_chunks 
     LIMIT 5;
     ```

### Still not working?
1. **Check Flask logs** for errors when searching
2. **Check Supabase logs** (Dashboard → Logs → Postgres Logs)
3. **Verify your `.env` file** has correct Supabase credentials

## What This Function Does

The `keyword_search_documents` function:
- Searches through `keyword_chunks` table using PostgreSQL full-text search
- Joins with `keyword_documents` to get document names
- Returns results ranked by relevance (how well they match the search query)
- Supports filtering by specific document ID (optional)

This is the core search functionality that powers the Keyword Finder feature!
