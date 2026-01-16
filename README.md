# Unified RAG Application 🚀

A comprehensive web application that combines **Document Q&A**, **Code Analysis**, and **Keyword Finding** using RAG (Retrieval-Augmented Generation) technology with bilingual support (English/Vietnamese).

---

## **Overview**

The Unified RAG Application is a Flask-based web platform that provides:

1. **GDD RAG (Document Q&A)** - Upload and query technical documents using AI-powered retrieval
2. **Code Q&A** - Index and query C# codebases with intelligent code understanding
3. **Keyword Finder (Document Explainer)** - Bilingual keyword search with AI-powered synonym generation
4. **Document Management** - Manage uploaded documents and keyword aliases

---

## **Features** ✨

### **📄 GDD RAG - Document Q&A**
- Upload PDF documents with automatic text extraction and chunking
- Section-aware document indexing (preserves document structure)
- Contextual Q&A using RAG technology
- Document filtering (query specific documents or all documents)
- Section-specific queries
- HYDE (Hypothetical Document Embeddings) for improved retrieval
- Query history and response tracking

### **💻 Code Q&A**
- Upload and index C# code files (.cs)
- Automatic extraction of:
  - Classes, interfaces, structs, enums
  - Methods with full implementations
  - Fields and properties
- Intelligent code search and retrieval
- File filtering (@filename.cs syntax)
- Method-aware responses
- Code snippet extraction with context

### **🔍 Keyword Finder (Document Explainer)**
- Bilingual keyword search (English ⟷ Vietnamese)
- **Deep Search** feature with AI-powered:
  - Automatic language detection
  - Translation to other language
  - Synonym generation (3 English + 3 Vietnamese)
- Alias dictionary for faster searches
- Document and section selection
- Detailed explanations with source citations
- Save keyword aliases for future use

### **⚙️ Document Management**
- View all uploaded documents (PDFs and code files)
- Document statistics (size, chunks, creation date)
- Delete documents
- Manage keyword aliases
- Filter aliases by language
- Bulk operations support

---

## **Technology Stack** 🛠️

- **Backend Framework:** Flask (Python)
- **Database:** Supabase (PostgreSQL with pgvector)
- **AI/LLM:** OpenAI API, Dashscope (Alibaba Cloud)
- **Embeddings:** OpenAI Embeddings, Dashscope Embeddings
- **Vector Storage:** Supabase (pgvector extension)
- **Full-Text Search:** PostgreSQL FTS (to_tsvector, tsquery)
- **PDF Processing:** Docling, PyPDF2
- **Code Analysis:** Tree-sitter (C# parser)
- **Text Chunking:** LangChain Text Splitters
- **Frontend:** HTML, CSS, JavaScript (Vanilla)

---

## **Quick Start** ⚡

**New to the project?** Follow these steps to get running in 15 minutes:

1. ✅ **Install Python 3.9+** (if not already installed)
2. ✅ **Clone the repository** → `git clone <repo-url> && cd unified_rag_app`
3. ✅ **Create virtual environment** → `python -m venv venv` then activate it
4. ✅ **Install dependencies** → `pip install -r requirements.txt`
5. ✅ **Get API keys** → OpenAI API key + Supabase account
6. ✅ **Create `.env` file** → Copy template and add your keys
7. ✅ **Setup database** → Run SQL scripts in Supabase
8. ✅ **Run the app** → `python app.py`
9. ✅ **Open browser** → `http://localhost:5000`

**Detailed instructions below ↓**

---

## **Prerequisites** 📋

Before you begin, ensure you have the following:

### **Required Software**

| Software | Version | How to Get |
|----------|---------|------------|
| **Python** | 3.9 or higher | [Download from python.org](https://www.python.org/downloads/) |
| **Git** | Latest | [Download from git-scm.com](https://git-scm.com/downloads) |
| **Code Editor** | Any | VS Code, PyCharm, or any text editor |

**Verify Installation:**
```bash
python --version  # Should show 3.9.x or higher
git --version     # Should show git version
```

### **Required Accounts & API Keys**

| Service | Purpose | Free Tier? | How to Get |
|---------|---------|------------|------------|
| **OpenAI** | AI embeddings & LLM | Limited free credits | [platform.openai.com](https://platform.openai.com/) |
| **Supabase** | Database & storage | ✅ Yes | [supabase.com](https://supabase.com/) |
| **Dashscope** | Alternative LLM (optional) | Limited | [dashscope.aliyun.com](https://dashscope.aliyun.com/) |

**Cost Estimate:**
- **Development/Testing**: ~$5-20/month (OpenAI API usage)
- **Production**: Depends on usage volume
- **Supabase**: Free tier is sufficient for most use cases

### **System Requirements**

- **RAM**: Minimum 4GB, Recommended 8GB+
- **Storage**: At least 2GB free space
- **Internet**: Required for API calls and package installation
- **OS**: Windows 10+, macOS 10.14+, or Linux (Ubuntu 18.04+)

**Windows Users:**
- PowerShell 5.1+ or Windows Terminal recommended
- Visual Studio Build Tools may be needed for some packages

---

## **Installation** 🔧

Follow these steps to set up the Unified RAG Application on your local machine.

### **Step 1: Clone the Repository**

First, clone the repository to your local machine:

```bash
git clone <repository-url>
cd unified_rag_app
```

**Note:** Replace `<repository-url>` with the actual repository URL.

---

### **Step 2: Check Python Version**

Ensure you have Python 3.9 or higher installed:

```bash
python --version
# Should show: Python 3.9.x or higher
```

**For Windows users:**
- If you have multiple Python versions, use: `py --version`
- To see all installed versions: `py --list`

**If Python is not installed:**
- Download from [python.org](https://www.python.org/downloads/)
- Make sure to check "Add Python to PATH" during installation

---

### **Step 3: Create Virtual Environment**

A virtual environment isolates your project dependencies. Create one:

**On Windows:**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

**On macOS/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

**What you should see:**
- Your terminal prompt should show `(venv)` at the beginning
- This means the virtual environment is active

**Troubleshooting:**
- **Windows PowerShell:** If you get "execution of scripts is disabled", run:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
- **Alternative activation (Windows):** `venv\Scripts\activate.bat`

---

### **Step 4: Install Dependencies**

Install all required Python packages:

```bash
pip install -r requirements.txt
```

**What happens:**
- This installs all dependencies listed in `requirements.txt`
- May take 2-5 minutes depending on your internet speed
- You'll see progress bars for each package

**Common issues:**
- **"pip is not recognized"**: Make sure Python is in your PATH
- **"Permission denied"**: Make sure your virtual environment is activated
- **Slow download**: This is normal, packages are large

**Verify installation:**
```bash
pip list
# Should show many packages including flask, openai, supabase, etc.
```

---

### **Step 5: Verify Installation**

Test that key packages are installed:

```bash
python -c "import flask; print('Flask:', flask.__version__)"
python -c "import openai; print('OpenAI: OK')"
python -c "from supabase import create_client; print('Supabase: OK')"
```

If all commands succeed, you're ready to configure the application!

---

## **Configuration** ⚙️

Configuration is essential for the application to work. Follow these steps carefully.

### **Step 1: Create Environment File**

Create a `.env` file in the project root directory (same folder as `app.py`).

**On Windows:**
```powershell
# In PowerShell or Command Prompt
cd unified_rag_app
notepad .env
```

**On macOS/Linux:**
```bash
cd unified_rag_app
nano .env
# or
touch .env
```

**Copy this template** and fill in your actual values:

```env
# Flask Configuration
FLASK_SECRET_KEY=your-secret-key-here
FLASK_ENV=development
PORT=5000

# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key

# OpenAI Configuration
OPENAI_API_KEY=your-openai-api-key

# Dashscope (Optional - Alibaba Cloud)
DASHSCOPE_API_KEY=your-dashscope-api-key

# Chunking Configuration (Optional)
CHUNK_SIZE=500
CHUNK_OVERLAP=0.15
```

**Important Notes:**
- ⚠️ **Never commit `.env` to git** - it contains sensitive keys
- ✅ The `.env` file should be in `.gitignore` (already configured)
- ✅ Replace all `your-*-here` placeholders with actual values

---

### **Step 2: Get Your API Keys**

#### **A. OpenAI API Key (Required)**

1. Go to [OpenAI Platform](https://platform.openai.com/)
2. Sign up or log in
3. Navigate to **API Keys** section
4. Click **"Create new secret key"**
5. Copy the key (starts with `sk-...`)
6. Paste it in `.env` as `OPENAI_API_KEY=sk-...`

**Cost Note:** OpenAI charges per API call. Monitor usage in your OpenAI dashboard.

#### **B. Supabase Credentials (Required)**

1. Go to [Supabase](https://supabase.com/)
2. Sign up or log in
3. Create a new project (or use existing)
4. Wait for project to finish setting up (~2 minutes)
5. Go to **Settings** → **API**
6. Copy these values:
   - **Project URL** → `SUPABASE_URL`
   - **anon public key** → `SUPABASE_KEY`
   - **service_role key** → `SUPABASE_SERVICE_KEY` (⚠️ Keep secret!)

**Free Tier:** Supabase free tier is sufficient for development and testing.

#### **C. Dashscope API Key (Optional)**

Only needed if you want to use Alibaba Cloud's LLM as an alternative:
1. Go to [Dashscope](https://dashscope.aliyun.com/)
2. Sign up and get API key
3. Add to `.env` as `DASHSCOPE_API_KEY=...`

---

### **Step 3: Generate Flask Secret Key**

Generate a secure random key for Flask sessions:

**Option 1: Using Python**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Copy the output and use as `FLASK_SECRET_KEY`.

**Option 2: Using Online Generator**
- Visit any secure random string generator
- Generate a 64-character hex string
- Use as `FLASK_SECRET_KEY`

**Example:**
```env
FLASK_SECRET_KEY=a1b2c3d4e5f6... (64 characters)
```

---

### **Step 4: Verify .env File**

Your `.env` file should look like this (with real values):

```env
FLASK_SECRET_KEY=a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef123456
FLASK_ENV=development
PORT=5000

SUPABASE_URL=https://abcdefghijklmnop.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz1234567890
```

**Checklist:**
- ✅ All required keys are present
- ✅ No quotes around values (unless value contains spaces)
- ✅ No trailing spaces
- ✅ File is named exactly `.env` (not `.env.txt`)

**Windows Note:** If you see `.env.txt`, rename it to `.env` (remove `.txt` extension).

### **2. Setup Supabase Database**

Run the following SQL scripts in your Supabase SQL Editor:

#### **a) GDD Documents Tables**

```sql
-- GDD documents table
CREATE TABLE IF NOT EXISTS gdd_documents (
    id SERIAL PRIMARY KEY,
    doc_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    file_path TEXT,
    pdf_storage_path TEXT,
    markdown_storage_path TEXT,
    full_text TEXT,
    status TEXT DEFAULT 'indexed',
    created_at TIMESTAMP DEFAULT NOW()
);

-- GDD chunks table
CREATE TABLE IF NOT EXISTS gdd_chunks (
    id SERIAL PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES gdd_documents(doc_id) ON DELETE CASCADE,
    chunk_id TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    section_heading TEXT,
    chunk_index INTEGER,
    embedding vector(1536),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_gdd_chunks_doc_id ON gdd_chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_gdd_chunks_embedding ON gdd_chunks USING ivfflat (embedding vector_cosine_ops);
```

#### **b) Keyword Documents Tables**

```sql
-- Keyword documents table (for Keyword Finder)
CREATE TABLE IF NOT EXISTS keyword_documents (
    id SERIAL PRIMARY KEY,
    doc_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    file_path TEXT,
    file_size BIGINT,
    full_text TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Keyword chunks table
CREATE TABLE IF NOT EXISTS keyword_chunks (
    id SERIAL PRIMARY KEY,
    doc_id TEXT NOT NULL REFERENCES keyword_documents(doc_id) ON DELETE CASCADE,
    chunk_id TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    section_heading TEXT,
    chunk_index INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Full-text search indexes
CREATE INDEX IF NOT EXISTS idx_keyword_chunks_content_fts 
    ON keyword_chunks USING gin(to_tsvector('english', content));
CREATE INDEX IF NOT EXISTS idx_keyword_documents_fulltext_fts 
    ON keyword_documents USING gin(to_tsvector('english', full_text));
CREATE INDEX IF NOT EXISTS idx_keyword_documents_name_fts 
    ON keyword_documents USING gin(to_tsvector('english', name));
```

#### **c) Keyword Aliases Table**

```sql
-- Keyword aliases table (for bilingual synonym mapping)
CREATE TABLE IF NOT EXISTS keyword_aliases (
    id SERIAL PRIMARY KEY,
    keyword TEXT NOT NULL,
    alias TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'en',
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(keyword, alias)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_keyword_aliases_keyword ON keyword_aliases(keyword);
CREATE INDEX IF NOT EXISTS idx_keyword_aliases_alias ON keyword_aliases(alias);
CREATE INDEX IF NOT EXISTS idx_keyword_aliases_language ON keyword_aliases(language);
```

#### **d) Code Files Tables**

```sql
-- Code files table
CREATE TABLE IF NOT EXISTS code_files (
    id SERIAL PRIMARY KEY,
    file_path TEXT UNIQUE NOT NULL,
    file_name TEXT NOT NULL,
    language TEXT DEFAULT 'csharp',
    indexed_at TIMESTAMP DEFAULT NOW()
);

-- Code chunks table
CREATE TABLE IF NOT EXISTS code_chunks (
    id SERIAL PRIMARY KEY,
    file_path TEXT NOT NULL REFERENCES code_files(file_path) ON DELETE CASCADE,
    chunk_type TEXT NOT NULL,
    name TEXT,
    class_name TEXT,
    code TEXT NOT NULL,
    doc_comment TEXT,
    embedding vector(1536),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_code_chunks_file_path ON code_chunks(file_path);
CREATE INDEX IF NOT EXISTS idx_code_chunks_embedding ON code_chunks USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_code_chunks_type ON code_chunks(chunk_type);
CREATE INDEX IF NOT EXISTS idx_code_chunks_class ON code_chunks(class_name);
```

#### **e) Create Search Function**

```sql
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
```

### **3. Setup Supabase Storage**

Create storage buckets in Supabase Dashboard:

1. Go to **Storage** → **Create new bucket**
2. Create bucket: `gdd_pdfs` (Public or Private based on your needs)
3. Set appropriate policies for file upload/download

---

## **Running the Application** 🚀

### **Before Running: Complete Configuration**

⚠️ **Important:** Make sure you've completed the [Configuration](#configuration-⚙️) section above before running the app. You need:
- ✅ `.env` file created with all required keys
- ✅ Supabase database tables created
- ✅ Supabase storage bucket created

---

### **Development Mode (Recommended for First Time)**

This is the easiest way to run the application locally:

**Step 1: Activate Virtual Environment**

```bash
# Windows
venv\Scripts\Activate.ps1

# macOS/Linux
source venv/bin/activate
```

**Step 2: Run the Application**

```bash
python app.py
```

**What you should see:**
```
 * Serving Flask app 'app'
 * Debug mode: on
 * Running on http://127.0.0.1:5000
 * Press CTRL+C to quit
```

**Step 3: Open in Browser**

Open your web browser and navigate to:
```
http://localhost:5000
```

You should see the Unified RAG Application homepage!

**To Stop the Application:**
- Press `CTRL+C` in the terminal
- The server will shut down gracefully

**Common Issues:**
- **"Port 5000 already in use"**: 
  - Another application is using port 5000
  - Solution: Change `PORT=5001` in `.env` file, or stop the other application
- **"ModuleNotFoundError"**: 
  - Virtual environment not activated or dependencies not installed
  - Solution: Activate venv and run `pip install -r requirements.txt`
- **"Supabase connection failed"**: 
  - Check your `.env` file has correct Supabase credentials
  - Verify Supabase project is active

---

### **Production Mode (Using Gunicorn)**

For production deployment or better performance:

**Step 1: Install Gunicorn**

```bash
pip install gunicorn
```

**Step 2: Run with Gunicorn**

```bash
gunicorn app:app --bind 0.0.0.0:5000 --workers 4 --timeout 120
```

**What this means:**
- `app:app` - Flask app instance (file: `app.py`, variable: `app`)
- `--bind 0.0.0.0:5000` - Listen on all interfaces, port 5000
- `--workers 4` - Use 4 worker processes (adjust based on CPU cores)
- `--timeout 120` - Request timeout in seconds

**When to use:**
- Deploying to production servers
- Need better performance for multiple users
- Running on Linux/macOS (Gunicorn doesn't work on Windows)

**Windows Note:** Gunicorn doesn't work on Windows. Use `python app.py` or deploy to Linux server.

---

### **Running on Different Ports**

To run on a different port (e.g., 5001):

**Option 1: Set in .env file**
```env
PORT=5001
```

**Option 2: Command line (Development)**
```bash
python app.py
# Then access at http://localhost:5001
```

**Option 3: Command line (Gunicorn)**
```bash
gunicorn app:app --bind 0.0.0.0:5001 --workers 4
```

---

### **Verifying Everything Works**

After starting the application, verify:

1. **Homepage loads**: `http://localhost:5000` shows the app interface
2. **Health check**: `http://localhost:5000/health` returns `{"status": "ok"}`
3. **No errors in terminal**: Check terminal for any error messages
4. **Database connection**: Try uploading a document (should connect to Supabase)

**If something doesn't work:**
- Check the terminal for error messages
- Verify `.env` file has all required variables
- Ensure Supabase tables are created
- See [Troubleshooting](#troubleshooting-🔧) section below

---

## **Usage Guide** 📖

### **1. GDD RAG - Document Q&A**

#### **Upload Documents**
1. Navigate to **"Manage Documents"** tab
2. Click **"Upload Document"** in the GDD section
3. Select a PDF file
4. Wait for processing (automatic text extraction and chunking)
5. Document will appear in the documents list

#### **Query Documents**
1. Go to **"GDD RAG"** tab
2. Select document(s) from dropdown:
   - **"All Documents"** - Search across all documents
   - **Specific document** - Search within one document
3. Type your question
4. Click **"Send"** or press Enter
5. View AI-generated answer with source citations

**Query Tips:**
- Be specific in your questions
- Use natural language
- Reference document sections if known
- Use `@section:heading` to filter by section

---

### **2. Code Q&A**

#### **Upload Code Files**
1. Navigate to **"Manage Documents"** tab
2. Click **"Upload Code File"** in the Code section
3. Select a `.cs` file
4. Wait for indexing (automatic method/class extraction)
5. File will appear in indexed files list

#### **Query Codebase**
1. Go to **"Code Q&A"** tab
2. (Optional) Filter files using `@filename.cs` in your query
3. Type your question about the code
4. Click **"Send"** or press Enter
5. View response with code snippets

**Query Examples:**
- "List all methods in UserService.cs"
- "Show me the authentication logic"
- "Find all classes that implement IUserRepository"
- "Extract variables from CalculateTotal method"

---

### **3. Keyword Finder (Document Explainer)**

#### **Search for Keywords**
1. Go to **"Keyword Finder"** tab
2. Enter a keyword in the search box (English or Vietnamese)
3. Click **"Search"** button

#### **If Results Found:**
- You'll see matching documents and sections
- Select items you want explained
- Click **"Generate Explanation"**
- View detailed explanation with sources

#### **If No Results (Use Deep Search):**
1. Click **"Search Deeper"** button next to the search box
2. AI will generate:
   - Translation to other language
   - 3 English synonyms
   - 3 Vietnamese synonyms
3. Select ONE suggested keyword (checkbox)
4. Click **"Search with Selected Keyword"**
5. System asks: **"Save this connection?"**
   - **Yes** → Future searches for your word instantly find this keyword
   - **No** → One-time search only

**Example Flow:**
```
You search: "armor"
→ No results found
→ Click "Search Deeper"
→ AI suggests: tank, xe tăng, armored vehicle, thiết giáp
→ You select: ☑ tank
→ Shows documents about "tank"
→ Popup: "Save 'armor' as alias for 'tank'?"
→ You click: "Yes, Save"
→ Next time "armor" search is instant!
```

---

### **4. Manage Documents & Aliases**

#### **View Documents**
- See all uploaded PDFs and code files
- View statistics: size, chunks, upload date
- Filter by type (PDF/Code)

#### **Delete Documents**
- Click trash icon next to document
- Confirm deletion
- All associated chunks are removed

#### **Manage Aliases**
- View all keyword-alias mappings
- Filter by language (EN/VI)
- Search for specific keywords
- Add new aliases manually
- Delete unwanted aliases

---

## **API Endpoints** 📡

### **GDD RAG Endpoints**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/gdd/query` | Query documents |
| POST | `/api/gdd/upload` | Upload PDF document |
| GET | `/api/gdd/upload/status` | Check upload status |
| GET | `/api/gdd/documents` | List all documents |
| GET | `/api/gdd/sections` | Get document sections |

### **Code Q&A Endpoints**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/code/query` | Query codebase |
| POST | `/api/code/upload` | Upload code file |
| GET | `/api/code/upload/status` | Check upload status |
| GET | `/api/code/files` | List indexed files |

### **Keyword Finder Endpoints**

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/gdd/explainer/search` | Search keyword |
| POST | `/api/gdd/explainer/explain` | Generate explanation |
| POST | `/api/gdd/explainer/deep-search` | AI-powered deep search |
| POST | `/api/gdd/explainer/select-all` | Select all items |
| POST | `/api/gdd/explainer/select-none` | Deselect all items |

### **Management Endpoints**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/manage/aliases` | Get all aliases |
| POST | `/api/manage/aliases` | Add new alias |
| DELETE | `/api/manage/aliases` | Delete alias |
| POST | `/api/manage/aliases/save` | Bulk save aliases |

### **Health Check**

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/healthz` | Health check (k8s compatible) |

---

## **Architecture** 🏗️

```
unified_rag_app/
├── app.py                          # Main Flask application
├── requirements.txt                # Python dependencies
├── runtime.txt                     # Python version for deployment
├── Procfile                        # Deployment configuration
├── .env                            # Environment variables (not in git)
├── env.example                     # Example environment file
│
├── backend/                        # Backend services
│   ├── gdd_service.py             # GDD RAG service
│   ├── gdd_explainer.py           # Keyword finder service
│   ├── gdd_hyde.py                # HYDE query expansion
│   ├── gdd_query_parser.py        # Query parsing utilities
│   ├── code_service.py            # Code Q&A service
│   ├── code_qa_prompts.py         # Code Q&A prompts
│   │
│   ├── services/                  # Shared services
│   │   ├── llm_provider.py        # LLM abstraction layer
│   │   ├── embedding_service.py   # Embedding generation
│   │   ├── search_service.py      # Keyword search
│   │   ├── deep_search_service.py # AI-powered search
│   │   ├── hyde_service.py        # HYDE implementation
│   │   ├── explainer_service.py   # Explanation generation
│   │   └── document_service.py    # Document processing
│   │
│   ├── storage/                   # Storage adapters
│   │   ├── supabase_client.py     # Supabase client
│   │   ├── gdd_supabase_storage.py # GDD storage
│   │   ├── code_supabase_storage.py # Code storage
│   │   └── keyword_storage.py     # Keyword/alias storage
│   │
│   ├── utils/                     # Utility functions
│   │   ├── text_utils.py          # Text processing
│   │   └── token_utils.py         # Token counting
│   │
│   └── shared/                    # Shared configuration
│       └── config.py              # App configuration
│
├── templates/                      # HTML templates
│   ├── base.html                  # Base template
│   ├── index.html                 # Home page
│   ├── gdd_tab.html               # GDD RAG tab
│   ├── code_tab.html              # Code Q&A tab
│   ├── explainer_tab.html         # Keyword Finder tab
│   └── manage_documents.html      # Management tab
│
├── static/                         # Static assets
│   ├── css/
│   │   └── style.css              # Main stylesheet
│   ├── js/
│   │   ├── gdd.js                 # GDD RAG frontend
│   │   ├── code.js                # Code Q&A frontend
│   │   ├── explainer.js           # Keyword Finder frontend
│   │   ├── manage_v3.js           # Management frontend
│   │   └── ...                    # Other JS files
│   └── icons/                     # SVG icons
│
├── docs/                           # Documentation
│   ├── KEYWORD_FINDER_USER_GUIDE.md
│   └── ...
│
├── deploy/                         # Deployment scripts
│   ├── setup_keyword_aliases.sql
│   └── SETUP_KEYWORD_ALIASES.md
│
├── scripts/                        # Utility scripts
│   └── ...
│
└── gdd_rag_backbone/              # RAG core library
    └── ...                        # LightRAG, chunking, etc.
```

---

## **Key Components** 🔑

### **Document Processing Pipeline**
1. **Upload** → PDF received
2. **Extraction** → Text extracted using Docling
3. **Chunking** → Text split with section awareness
4. **Embedding** → Chunks embedded using OpenAI
5. **Storage** → Stored in Supabase with pgvector

### **RAG Query Pipeline**
1. **Query** → User question received
2. **HYDE (Optional)** → Generate hypothetical document
3. **Retrieval** → Search similar chunks using embeddings
4. **Reranking** → Sort by relevance
5. **Generation** → LLM generates answer with context
6. **Citation** → Return answer with source references

### **Deep Search Pipeline**
1. **Detect Language** → English or Vietnamese
2. **LLM Translation** → Generate translation + synonyms
3. **Alias Check** → Check against saved aliases
4. **Database Search** → Full-text search
5. **Verification** → Verify keywords exist in documents
6. **Return Results** → Matched keywords with options

---

## **Environment Variables Reference** 📝

| Variable | Required | Description |
|----------|----------|-------------|
| `FLASK_SECRET_KEY` | Yes | Flask session secret |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_KEY` | Yes | Supabase anon key |
| `SUPABASE_SERVICE_KEY` | Yes | Supabase service role key |
| `OPENAI_API_KEY` | Yes | OpenAI API key |
| `DASHSCOPE_API_KEY` | No | Dashscope API key (optional) |
| `CHUNK_SIZE` | No | Chunk size in tokens (default: 500) |
| `CHUNK_OVERLAP` | No | Chunk overlap ratio (default: 0.15) |
| `PORT` | No | Server port (default: 5000) |
| `FLASK_ENV` | No | Environment (development/production) |

---

## **Deployment** 🌐

### **Deploy to Render**

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Configure:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120`
4. Add environment variables in Render dashboard
5. Deploy!

### **Deploy to Heroku**

```bash
# Login to Heroku
heroku login

# Create app
heroku create your-app-name

# Set environment variables
heroku config:set SUPABASE_URL=your-url
heroku config:set SUPABASE_KEY=your-key
# ... add all other env vars

# Deploy
git push heroku main
```

### **Deploy with Docker**

```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 4 --timeout 120
```

```bash
docker build -t unified-rag-app .
docker run -p 5000:5000 --env-file .env unified-rag-app
```

---

## **Troubleshooting** 🔧

### **Installation Issues**

#### **1. "Python is not recognized" (Windows)**
**Problem:** Python not found in PATH

**Solutions:**
- Reinstall Python and check "Add Python to PATH"
- Use `py` instead of `python`: `py -m venv venv`
- Add Python manually to PATH in System Environment Variables

#### **2. "pip is not recognized"**
**Problem:** pip not installed or not in PATH

**Solutions:**
```bash
# Try python -m pip instead
python -m pip install -r requirements.txt

# Or on Windows
py -m pip install -r requirements.txt
```

#### **3. "Failed building wheel" or compilation errors**
**Problem:** Some packages need C++ compilers

**Solutions:**
- **Windows:** Install [Visual Studio Build Tools](https://visualstudio.microsoft.com/downloads/#build-tools-for-visual-studio-2022)
- **macOS:** Install Xcode Command Line Tools: `xcode-select --install`
- **Linux:** Install build essentials: `sudo apt-get install build-essential`

#### **4. "Permission denied" when installing packages**
**Problem:** Installing to system Python instead of venv

**Solutions:**
- Make sure virtual environment is activated (you should see `(venv)` in prompt)
- Don't use `sudo` with pip when venv is active
- Recreate venv: `rm -rf venv && python -m venv venv`

#### **5. "ModuleNotFoundError" after installation**
**Problem:** Dependencies not installed or wrong Python

**Solutions:**
```bash
# Verify venv is activated
which python  # Should show venv path

# Reinstall dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Verify installation
pip list | grep flask  # Should show flask
```

---

### **Configuration Issues**

#### **6. ".env file not found"**
**Problem:** `.env` file missing or in wrong location

**Solutions:**
- File must be named exactly `.env` (not `.env.txt` or `env`)
- Must be in project root (same folder as `app.py`)
- On Windows: Use `notepad .env` to create (PowerShell may hide it)

#### **7. "Supabase connection failed"**
**Problem:** Invalid credentials or network issue

**Solutions:**
- Verify `.env` has correct `SUPABASE_URL` and `SUPABASE_KEY`
- Check Supabase project is active (not paused)
- Test connection: Visit your Supabase URL in browser
- Verify no extra spaces in `.env` values
- Check firewall/network allows HTTPS connections

#### **8. "OpenAI API error"**
**Problem:** Invalid API key or quota exceeded

**Solutions:**
- Verify `OPENAI_API_KEY` starts with `sk-`
- Check API key in [OpenAI Dashboard](https://platform.openai.com/api-keys)
- Verify billing/quota: [OpenAI Usage](https://platform.openai.com/usage)
- Test key: `curl https://api.openai.com/v1/models -H "Authorization: Bearer YOUR_KEY"`

---

### **Runtime Issues**

#### **9. "No module named 'backend'"**
**Problem:** Running from wrong directory or missing `__init__.py`

**Solutions:**
- Make sure you're in project root: `cd unified_rag_app`
- Verify `backend/` folder exists and has `__init__.py`
- Run: `python app.py` (not `python backend/app.py`)

#### **10. "Port 5000 already in use"**
**Problem:** Another application using port 5000

**Solutions:**
```bash
# Option 1: Change port in .env
PORT=5001

# Option 2: Find and kill process (Windows)
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# Option 2: Find and kill process (macOS/Linux)
lsof -ti:5000 | xargs kill
```

#### **11. "Upload fails / Processing stuck"**
**Problem:** File processing timeout or invalid file

**Solutions:**
- Check PDF file is valid (open it in PDF viewer)
- Verify file size < 50MB (adjust if needed)
- Check Supabase storage bucket exists and has correct permissions
- Increase timeout: `--timeout 300` in gunicorn command
- Check terminal for detailed error messages

#### **12. "Keyword search returns no results"**
**Problem:** No documents indexed or keyword not found

**Solutions:**
- Upload documents first (Manage Documents tab)
- Click "Search Deeper" to use AI suggestions
- Verify `keyword_chunks` table has data in Supabase
- Check documents actually contain the keyword
- Try searching in both English and Vietnamese

#### **13. "Database table does not exist"**
**Problem:** SQL scripts not run in Supabase

**Solutions:**
- Go to Supabase Dashboard → SQL Editor
- Run all SQL scripts from [Configuration section](#2-setup-supabase-database)
- Verify tables exist: Check "Table Editor" in Supabase
- Check for error messages in SQL Editor

---

### **Getting More Help**

If you're still stuck:

1. **Check terminal output** - Error messages usually show the problem
2. **Check Supabase logs** - Dashboard → Logs → API Logs
3. **Verify all prerequisites** - Python version, API keys, etc.
4. **Search GitHub issues** - Someone may have had the same problem
5. **Create a new issue** - Include error messages and steps to reproduce

**Common Error Patterns:**
- `ModuleNotFoundError` → Installation issue
- `Connection refused` → Configuration issue  
- `401 Unauthorized` → API key issue
- `Table does not exist` → Database setup issue

---

## **Development** 👨‍💻

### **Running Tests**

```bash
# Install dev dependencies
pip install pytest pytest-cov

# Run tests
pytest

# With coverage
pytest --cov=backend tests/
```

### **Code Formatting**

```bash
# Install formatters
pip install black flake8

# Format code
black backend/ app.py

# Check style
flake8 backend/ app.py
```

### **Adding New Features**

1. Create feature branch: `git checkout -b feature/your-feature`
2. Implement feature in appropriate module
3. Add tests
4. Update documentation
5. Create pull request

---

## **Performance Optimization** ⚡

### **Tips for Better Performance**

1. **Use smaller chunk sizes** for faster retrieval (adjust `CHUNK_SIZE`)
2. **Enable caching** with Redis for repeated queries
3. **Use Dashscope** for faster Chinese/Vietnamese text processing
4. **Index optimization** - regularly vacuum Postgres tables
5. **Connection pooling** - configure Supabase connection pool
6. **Batch operations** - process multiple files together

---

## **Security** 🔒

### **Best Practices**

1. **Never commit `.env`** file to git
2. **Use service role key** only for admin operations
3. **Enable RLS** (Row Level Security) in Supabase
4. **Validate file uploads** - check file types and sizes
5. **Rate limiting** - implement API rate limits
6. **HTTPS only** in production
7. **Regular updates** - keep dependencies up to date

---

## **Contributing** 🤝

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

---

## **License** 📄

[Your License Here]

---

## **Support** 💬

For issues, questions, or suggestions:
- Open an issue on GitHub
- Contact: [your-email@example.com]
- Documentation: See `docs/` folder

---

## **Acknowledgments** 🙏

- OpenAI for GPT and embeddings
- Supabase for backend infrastructure
- LightRAG for RAG implementation
- Docling for PDF processing
- All open-source contributors

---

**Built with ❤️ using Python, Flask, and AI**

