# Instructions for Indexing Tank War Documents

## Overview
This script indexes PDF documents from the `Tank War/` directory into your Supabase database.

## Prerequisites
1. Ensure your `.env` file is configured with:
   - `SUPABASE_URL`
   - `SUPABASE_KEY` 
   - `SUPABASE_SERVICE_KEY`
   - `DASHSCOPE_API_KEY` (for embeddings)

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Running the Script

### Option 1: Run the Python script directly
```bash
cd /Users/madeinheaven/Documents/GitHub/Unified_RAG
python3 scripts/index_tank_war_docs.py
```

### Option 2: Use the Flask app upload interface
1. Start the Flask app:
   ```bash
   python3 app.py
   ```
2. Navigate to the GDD tab in your browser
3. Use the document upload interface to upload PDFs one by one

### Option 3: Modify the script to select different files
Edit `scripts/index_tank_war_docs.py` and modify the `selected_files` list in the `if __name__ == "__main__":` section.

## Files Selected for Indexing
The script is configured to index these 5 files:
1. `[Character Module] [Tank War] Garage Design - Main.pdf`
2. `[Combat Module] [Tank War] Shooting Logic.pdf`
3. `[Progression Module] [Tank War] Leaderboard System.pdf`
4. `[Tank War] User Profile Design.pdf`
5. `[World] [Tank War] Map Design - Outpost Breaker.pdf`

## Troubleshooting

### Segmentation Fault
If you encounter a segmentation fault, it may be due to:
- Native library conflicts (docling dependencies)
- Python version incompatibility
- Missing system dependencies

**Solution**: Try using the Flask app upload interface instead (Option 2 above).

### Import Errors
If you see import errors:
1. Ensure you're in the project root directory
2. Check that all dependencies are installed: `pip install -r requirements.txt`
3. Verify your Python version is 3.9+

### Supabase Connection Errors
1. Verify your `.env` file has correct Supabase credentials
2. Check that your Supabase project is active
3. Ensure the `gdd_pdfs` bucket exists in Supabase Storage

## What the Script Does
1. Reads PDF files from the `Tank War/` directory
2. Converts PDFs to Markdown using Docling
3. Chunks the markdown content
4. Generates embeddings for each chunk
5. Uploads PDFs to Supabase Storage (`gdd_pdfs` bucket)
6. Stores chunks and embeddings in Supabase database (`keyword_chunks` table)
7. Stores document metadata in Supabase (`keyword_documents` table)

## Expected Output
You should see progress messages like:
```
📁 Found X PDF files in Tank War directory
📚 Indexing 5 PDF files:
  1. [Character Module] [Tank War] Garage Design - Main.pdf
  ...

[1/5] Processing: [Character Module] [Tank War] Garage Design - Main.pdf
  → Converting to Markdown
  → Preparing document identifiers
  → Uploading PDF to storage
  → Chunking Markdown
  → Generating embeddings
  → Indexing into Supabase
  → Completed
✅ Successfully indexed: [Character Module] [Tank War] Garage Design - Main.pdf (doc_id: ...)

📊 Summary:
  ✅ Successfully indexed: 5
  ❌ Failed: 0
  📁 Total processed: 5
```
