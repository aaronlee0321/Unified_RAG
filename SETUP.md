# Unified RAG – Setup Guide

This guide walks you through setting up and running the Unified RAG app from scratch.

---

## Prerequisites

- **Python 3.11 only** (other versions are not supported). Check with `python3 --version` or `python --version`; you should see `3.11.x`. If needed, install Python 3.11 from [python.org](https://www.python.org/downloads/) or your package manager (e.g. `pyenv install 3.11`).
- **Supabase account** (free tier is fine)
- **LLM API key** – at least one of:
  - OpenAI API key, or
  - Qwen/DashScope API key, or
  - An OpenAI-compatible endpoint (e.g. Ollama) with base URL + key

---

## 1. Clone and enter the project

```bash
git clone <your-repo-url>
cd Unified_RAG
```

---

## 2. Create a virtual environment and install dependencies

Use Python 3.11 to create the venv:

```bash
python3.11 -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

If `python3.11` is not in your PATH, use the full path to your Python 3.11 binary or ensure Python 3.11 is the default `python3`.

---

## 3. Set up Supabase

### 3.1 Create a Supabase project

1. Go to [supabase.com](https://supabase.com) and sign in.
2. Create a new project (choose org, name, database password, region).
3. Wait for the project to be ready.

### 3.2 Run the schema script

1. In the Supabase Dashboard, open **SQL Editor**.
2. Create a **New query**.
3. Copy the contents of `**supabase_deploy.sql**` from this repo and paste into the editor.
4. Click **Run** (or press Cmd/Ctrl+Enter).
   This creates all tables and indexes (keyword_documents, keyword_chunks, keyword_aliases, code_files, code_chunks).

### 3.3 Create the storage bucket for PDFs and images

1. In the Dashboard, go to **Storage**.
2. Click **New bucket**.
3. Name: `**gdd_pdfs**` (exactly).
4. Set **Public bucket** to **ON** (so image URLs work).
5. Create the bucket.

### 3.4 Get your API keys

1. Go to **Project Settings** → **API**.
2. Copy:

- **Project URL** → use for `SUPABASE_URL`
- **anon public** key → use for `SUPABASE_KEY`
- **service_role** key → use for `SUPABASE_SERVICE_KEY` (keep this secret; used for uploads and admin operations)

---

## 4. Configure environment variables

1. Copy the example env file:

```bash
 cp .env.example .env
```

2. Edit `**.env**` and set:

| Variable                                | Where to get it                                                               | Required |
| --------------------------------------- | ----------------------------------------------------------------------------- | -------- |
| `SUPABASE_URL`                          | Supabase → Project Settings → API → Project URL                               | Yes      |
| `SUPABASE_KEY`                          | Supabase → Project Settings → API → anon public                               | Yes      |
| `SUPABASE_SERVICE_KEY`                  | Supabase → Project Settings → API → service_role                              | Yes      |
| `OPENAI_API_KEY`                        | [platform.openai.com](https://platform.openai.com/api-keys) (if using OpenAI) | Yes      |
| or `DASHSCOPE_API_KEY` / `QWEN_API_KEY` | DashScope / Qwen console (if using Qwen)                                      | Yes      |
| `FLASK_SECRET_KEY`                      | Any long random string (or leave default for dev)                             | Optional |
| `PORT`                                  | Port to run the app (default 5000)                                            | Optional |

    You need **at least one** LLM/embedding provider (OpenAI, Qwen, or an OpenAI-compatible endpoint like Ollama).

3. For **Ollama** (local, no API key): set `OPENAI_BASE_URL=http://localhost:11434/v1` and `OPENAI_API_KEY=ollama`, and run Ollama locally.
4. Save the file. **Do not commit `.env**`(it is in`.gitignore`).

---

## 5. Run the app

```bash
python app.py
```

Or with Flask:

```bash
flask run --host=0.0.0.0 --port=5000
```

Then open a browser to **[http://localhost:5000](http://localhost:5000)** (or the port you set in `PORT`).

---

## 6. Verify setup

- **Home** – Shows document and code file counts (may be 0 at first).
- **GDD RAG** – Upload a PDF; it should process and index (requires LLM key for embeddings).
- **Code Q&A** – Upload a `.cs` file; it should index (requires LLM key for embeddings).
- **Keyword Finder** – Search and explain (translation/synonyms work without extra keys; explanations need LLM).
- **Manage Documents** – List/delete GDD docs and code files.

If you see “Supabase not configured” or “No API key found”, double-check `.env` and that you ran `supabase_deploy.sql` and created the `gdd_pdfs` bucket.

---

## Troubleshooting

| Issue                                  | What to check                                                                                                                     |
| -------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Import errors                          | Ensure you’re in the project root and the virtualenv is activated; run `pip install -r requirements.txt` again.                   |
| “SUPABASE_URL or SUPABASE_KEY not set” | `.env` exists in the project root, variable names match `.env.example`, no typos.                                                 |
| “match_keyword_chunks RPC not found”   | Supabase vector search RPCs may need to be created; see project docs or `supabase_deploy.sql` for any RPC definitions.            |
| PDF upload fails                       | Supabase project is ready, `gdd_pdfs` bucket exists and is public, `SUPABASE_SERVICE_KEY` is set.                                 |
| No embeddings / “No API key found”     | At least one of `OPENAI_API_KEY`, `DASHSCOPE_API_KEY`, or `QWEN_API_KEY` is set (or OpenAI-compatible base URL + key for Ollama). |

---

## Optional

- **Chunking:** Adjust `CHUNK_SIZE` and `CHUNK_OVERLAP` in `.env` (see `backend/shared/config.py`).
- **Models:** Set `DEFAULT_LLM_MODEL` and `DEFAULT_EMBEDDING_MODEL` in `.env` to use different models.
