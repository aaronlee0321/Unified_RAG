"""
Unified RAG Web Application
Combines GDD RAG and Code Q&A into a single Flask app
"""

from flask import Flask, render_template, request, session, jsonify
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import logging
import signal

import uuid
import threading
from time import sleep
# from backend.gdd_service import upload_and_index_document_bytes  # Now using keyword_extractor backend


# --- Simple in-memory progress tracking and job execution ---
import uuid
import threading
from time import sleep

# Global dict: job_id -> progress info
UPLOAD_JOBS = {}  # { job_id: {"status": "running|success|error", "step": "...", "message": "", "doc_id": None } }
JOBS_LOCK = threading.Lock()


def new_job():
    job_id = uuid.uuid4().hex
    with JOBS_LOCK:
        UPLOAD_JOBS[job_id] = {
            "status": "running", "step": "Uploading file", "message": "", "doc_id": None}
    return job_id


def update_job(job_id, step=None, status=None, message=None, doc_id=None):
    with JOBS_LOCK:
        job = UPLOAD_JOBS.get(job_id)
        if not job:
            return
        if step is not None:
            job["step"] = step
        if status is not None:
            job["status"] = status
        if message is not None:
            job["message"] = message
        if doc_id is not None:
            job["doc_id"] = doc_id


def get_job(job_id):
    with JOBS_LOCK:
        return UPLOAD_JOBS.get(job_id, None)


def run_upload_pipeline_async(job_id, pdf_bytes, filename):
    # Progress callback used by document_service (keyword_extractor backend)
    def progress_cb(step_text):
        update_job(job_id, step=step_text)

    try:
        update_job(job_id, step="Starting upload")
        # Use keyword_extractor's document_service.upload_and_index_document
        from backend.services.document_service import upload_and_index_document
        result = upload_and_index_document(
            pdf_bytes, filename, progress_callback=progress_cb)
        # result is dict: {"status": "success|error", "message": "...", "doc_id": "...", "chunks_count": ...}
        if result.get("status") == "success":
            update_job(job_id, status="success", step="Completed",
                       message=result.get("message"), doc_id=result.get("doc_id"))
        else:
            update_job(job_id, status="error", step="Failed",
                       message=result.get("message"))
    except Exception as e:
        import traceback
        error_msg = str(e) + "\n" + traceback.format_exc()
        update_job(job_id, status="error", step="Failed", message=error_msg)


def run_code_upload_pipeline_async(job_id, file_bytes, filename):
    """Process and index a code file asynchronously."""
    def progress_cb(step_text):
        update_job(job_id, step=step_text)

    try:
        update_job(job_id, step="Reading file")

        # Decode file content
        try:
            code_text = file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            code_text = file_bytes.decode('utf-8', errors='ignore')

        # Only process .cs files
        if not filename.lower().endswith('.cs'):
            update_job(job_id, status="error", step="Failed",
                       message="Only .cs files are supported")
            return

        update_job(job_id, step="Extracting methods and classes")

        # Import required functions
        from backend.code_service import _analyze_csharp_file_symbols
        from backend.storage.code_supabase_storage import index_code_chunks_to_supabase
        # COMMENTED OUT: Qwen usage - using OpenAI instead
        # from gdd_rag_backbone.llm_providers import QwenProvider
        from backend.services.llm_provider import SimpleLLMProvider
        import re

        # Use file name as file_path (relative path)
        file_path = filename
        file_name = filename.split(
            '/')[-1] if '/' in filename else filename.split('\\')[-1]

        # Extract methods
        methods, fields, properties = _analyze_csharp_file_symbols(code_text)

        # Helper function to extract method code
        def extract_method_code(code_text, method):
            signature = method.get('signature', '')
            if not signature:
                return ''
            sig_start = code_text.find(signature)
            if sig_start == -1:
                return signature
            brace_start = code_text.find('{', sig_start + len(signature))
            if brace_start == -1:
                arrow_pos = code_text.find('=>', sig_start + len(signature))
                if arrow_pos != -1:
                    end_pos = code_text.find(';', arrow_pos)
                    if end_pos != -1:
                        return code_text[sig_start:end_pos + 1]
                return signature
            brace_count = 1
            pos = brace_start + 1
            while pos < len(code_text) and brace_count > 0:
                char = code_text[pos]
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                elif char in ('"', "'"):
                    quote_char = char
                    pos += 1
                    while pos < len(code_text) and code_text[pos] != quote_char:
                        if code_text[pos] == '\\':
                            pos += 1
                        pos += 1
                pos += 1
            if brace_count == 0:
                return code_text[sig_start:pos]
            return signature

        # Build method chunks
        method_chunks = []
        for method in methods:
            method_code = extract_method_code(code_text, method)
            if not method_code:
                continue

            # Find class name
            class_name = None
            sig_start = code_text.find(method.get('signature', ''))
            if sig_start != -1:
                before_code = code_text[:sig_start]
                class_match = re.search(r'class\s+(\w+)', before_code)
                if class_match:
                    class_name = class_match.group(1)

            method_chunks.append({
                'chunk_type': 'method',
                'name': method.get('name'),
                'class_name': class_name,
                'code': method_code,
                'source_code': method_code,
                'signature': method.get('signature', ''),
                'doc_comment': method.get('doc_comment', ''),
                'metadata': {'line': method.get('line', 1)}
            })

        # Extract class-like types
        class_chunks = []
        TYPE_PATTERN = re.compile(
            r'^[ \t]*(?:\[[^\]]+\]\s*)*'
            r'(?:public|private|protected|internal|abstract|sealed|static|partial)?\s*'
            r'(?P<kind>class|struct|interface|enum)\s+'
            r'(?P<name>\w+)',
            re.MULTILINE | re.IGNORECASE
        )

        for match in TYPE_PATTERN.finditer(code_text):
            kind = match.group("kind").lower()
            name = match.group("name")
            start_pos = match.start()
            brace_pos = code_text.find("{", match.end())
            if brace_pos == -1:
                continue
            brace_count = 1
            pos = brace_pos + 1
            while pos < len(code_text) and brace_count > 0:
                char = code_text[pos]
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                elif char in ('"', "'"):
                    quote_char = char
                    pos += 1
                    while pos < len(code_text) and code_text[pos] != quote_char:
                        if code_text[pos] == '\\':
                            pos += 1
                        pos += 1
                pos += 1
            if brace_count == 0:
                type_code = code_text[start_pos:pos]
                formatted_code = f"File: {file_path}\n\n{type_code}"
                class_chunks.append({
                    'chunk_type': kind,
                    'class_name': name,
                    'source_code': formatted_code,
                    'code': None,
                    'method_declarations': '',
                    'metadata': {'kind': kind}
                })

        update_job(job_id, step="Indexing to Supabase")

        # Initialize provider
        # COMMENTED OUT: Qwen usage - using OpenAI instead
        # provider = QwenProvider()
        provider = SimpleLLMProvider()

        total_chunks = 0

        # Index method chunks
        if method_chunks:
            success = index_code_chunks_to_supabase(
                file_path=file_path,
                file_name=file_name,
                chunks=method_chunks,
                provider=provider
            )
            if success:
                total_chunks += len(method_chunks)

        # Index class chunks
        if class_chunks:
            success = index_code_chunks_to_supabase(
                file_path=file_path,
                file_name=file_name,
                chunks=class_chunks,
                provider=provider
            )
            if success:
                total_chunks += len(class_chunks)

        update_job(job_id, status="success", step="Completed",
                   message=f"Successfully indexed {filename} ({total_chunks} chunks)",
                   doc_id=file_path)

    except Exception as e:
        import traceback
        error_msg = str(e) + "\n" + traceback.format_exc()
        app.logger.error(f"Error in code upload pipeline: {error_msg}")
        update_job(job_id, status="error", step="Failed", message=error_msg)


# Load environment variables
load_dotenv()

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Data Directory
DATA_DIR = PROJECT_ROOT / 'data'
DATA_DIR.mkdir(exist_ok=True)
# Note: ALIAS_DICT_PATH removed - aliases now stored in Supabase keyword_aliases table

# Configuration
CONFIG = {
    'SECRET_KEY': os.getenv('FLASK_SECRET_KEY', os.urandom(24).hex()),
    'LOG_FORMAT': '%(asctime)s - %(message)s',
    'LOG_DATE_FORMAT': '%d-%b-%y %H:%M:%S'
}

# Setup logging


def setup_logging(config):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers if reloaded
    if logger.handlers:
        return logger

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        config['LOG_FORMAT'],
        datefmt=config['LOG_DATE_FORMAT']
    ))
    logger.addHandler(console_handler)

    return logger


# Create Flask app
try:
    app = Flask(__name__)
    app.config.update(CONFIG)
    app.logger = setup_logging(app.config)
    app.logger.info("Flask app object created successfully")
except Exception as e:
    import sys
    import traceback
    print(f"[FATAL] Failed to create Flask app: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    raise

# Log startup configuration
app.logger.info("=" * 60)
app.logger.info("Flask app initializing...")
app.logger.info(f"Project root: {PROJECT_ROOT}")

# Log PORT environment variable (critical for Render)
port_env = os.getenv('PORT')
app.logger.info(
    f"PORT environment variable: {port_env if port_env else 'NOT SET (will use default 5000)'}")
app.logger.info(f"Python version: {sys.version}")

# Initialize service availability flags
gdd_service_available = False
code_service_available = False

# Add health check endpoint early (before other routes)


@app.route('/health', methods=['GET'])
@app.route('/healthz', methods=['GET'])
def health_check():
    """Health check endpoint for Render and monitoring"""
    try:
        return jsonify({
            'status': 'healthy',
            'service': 'unified_rag_app',
            'gdd_service': gdd_service_available,
            'code_service': code_service_available
        }), 200
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500


# Check Supabase configuration
supabase_url = os.getenv('SUPABASE_URL')
supabase_key = os.getenv('SUPABASE_KEY')
supabase_service_key = os.getenv('SUPABASE_SERVICE_KEY')
app.logger.info(f"SUPABASE_URL: {'SET' if supabase_url else 'NOT SET'}")
if supabase_url:
    app.logger.info(f"SUPABASE_URL value: {supabase_url[:30]}...")
app.logger.info(f"SUPABASE_KEY: {'SET' if supabase_key else 'NOT SET'}")
if supabase_key:
    app.logger.info(f"SUPABASE_KEY starts with: {supabase_key[:20]}...")
app.logger.info(
    f"SUPABASE_SERVICE_KEY: {'SET' if supabase_service_key else 'NOT SET'}")
app.logger.info(
    f"DASHSCOPE_API_KEY: {'SET' if os.getenv('DASHSCOPE_API_KEY') else 'NOT SET'}")

# Import services
app.logger.info("Importing GDD service...")
try:
    from backend.gdd_service import (
        upload_and_index_document_bytes,
        list_documents,
        get_document_options,
        query_gdd_documents,
        get_document_sections
    )

    gdd_service_available = True
    app.logger.info("[OK] GDD service imported successfully")

    # Check Supabase availability in GDD service
    try:
        from backend.storage.gdd_supabase_storage import USE_SUPABASE
        app.logger.info(
            f"GDD Supabase storage: {'ENABLED' if USE_SUPABASE else 'DISABLED'}")
    except Exception as e:
        app.logger.warning(f"Could not check GDD Supabase status: {e}")

except ImportError as e:
    app.logger.error(f"[ERROR] Could not import GDD service: {e}")
    import traceback
    app.logger.error(f"Import traceback: {traceback.format_exc()}")
    gdd_service_available = False

app.logger.info("Importing Code service...")
try:
    from backend.code_service import (
        query_codebase,
        list_indexed_files
    )
    code_service_available = True
    app.logger.info("[OK] Code service imported successfully")

    # Check Supabase availability in Code service
    try:
        from backend.storage.code_supabase_storage import USE_SUPABASE as CODE_USE_SUPABASE
        app.logger.info(
            f"Code Supabase storage: {'ENABLED' if CODE_USE_SUPABASE else 'DISABLED'}")
    except Exception as e:
        app.logger.warning(f"Could not check Code Supabase status: {e}")

except ImportError as e:
    app.logger.error(f"[ERROR] Could not import Code service: {e}")
    import traceback
    app.logger.error(f"Import traceback: {traceback.format_exc()}")
    code_service_available = False

# Log all registered routes on startup


def log_registered_routes():
    """Log registered routes for debugging (safe: no recursion)."""
    try:
        with app.app_context():
            app.logger.info("Registered routes:")
            for rule in app.url_map.iter_rules():
                if rule.rule.startswith('/api') or rule.rule in ['/', '/gdd', '/code', '/health']:
                    methods = [m for m in rule.methods if m not in {
                        'HEAD', 'OPTIONS'}]
                    app.logger.info(f"  {rule.rule} [{', '.join(methods)}]")
    except Exception as e:
        app.logger.warning(f"Could not log routes: {e}")


# Log routes after app is fully configured
try:
    log_registered_routes()
    app.logger.info("=" * 60)
    app.logger.info("App is ready to serve requests")
    app.logger.info("=" * 60)

except ImportError as e:
    app.logger.error(f"[ERROR] Could not import Code service: {e}")
    import traceback
    app.logger.error(f"Import traceback: {traceback.format_exc()}")
    code_service_available = False

app.logger.info("=" * 60)


@app.route('/')
def index():
    """Main page with dynamic counts for documents and code files"""
    gdd_count = 0
    code_count = 0

    # Get GDD document count (deduplicated)
    try:
        all_doc_ids = set()

        # Get documents from GDD service (gdd_documents table)
        if gdd_service_available:
            try:
                gdd_docs = list_documents()
                if gdd_docs:
                    for doc in gdd_docs:
                        doc_id = doc.get('doc_id') or doc.get('id')
                        if doc_id:
                            all_doc_ids.add(doc_id)
            except Exception as e:
                app.logger.warning(f"Could not load GDD documents: {e}")

        # Also include keyword documents (deduplicate by doc_id)
        try:
            from backend.storage.keyword_storage import list_keyword_documents
            keyword_docs = list_keyword_documents()
            if keyword_docs:
                for doc in keyword_docs:
                    doc_id = doc.get('doc_id')
                    if doc_id:
                        all_doc_ids.add(doc_id)
        except Exception as e:
            app.logger.warning(f"Could not load keyword documents: {e}")

        gdd_count = len(all_doc_ids)
    except Exception as e:
        app.logger.warning(f"Error counting GDD documents: {e}")

    # Get Code file count
    try:
        if code_service_available:
            code_files = list_indexed_files()
            code_count = len(code_files) if code_files else 0
    except Exception as e:
        app.logger.warning(f"Error counting Code files: {e}")

    return render_template('index.html', gdd_count=gdd_count, code_count=code_count)


@app.route('/gdd')
def gdd_tab():
    """GDD RAG tab"""
    return render_template('gdd_tab.html')


@app.route('/code')
def code_tab():
    """Code Q&A tab"""
    return render_template('code_tab.html')


@app.route('/explainer')
def explainer_tab():
    """Keyword Finder page"""
    return render_template('explainer_tab.html')


@app.route('/manage')
def manage_documents():
    """Manage Documents page"""
    return render_template('manage_documents.html')


@app.route('/api/gdd/query', methods=['POST'])
def gdd_query():
    """Handle GDD RAG queries"""
    try:
        if not gdd_service_available:
            return jsonify({'error': 'GDD service not available'}), 500

        data = request.get_json()
        query = data.get('query', '')
        selected_doc = data.get('selected_doc', None)

        result = query_gdd_documents(query, selected_doc)
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Error in GDD query: {e}")
        return jsonify({'error': str(e), 'status': 'error'}), 500


@app.route('/api/gdd/upload/status', methods=['GET'])
def gdd_upload_status():
    """Poll the current status of an upload job."""
    job_id = request.args.get('job_id')
    if not job_id:
        return jsonify({'status': 'error', 'message': 'job_id required'}), 400

    job = get_job(job_id)
    if not job:
        return jsonify({'status': 'error', 'message': 'Unknown job_id'}), 404

    # Always JSON
    return jsonify({
        'status': job['status'],  # running | success | error
        'step': job['step'],
        'message': job['message'],
        'doc_id': job['doc_id'],
        'job_id': job_id,
    }), 200


@app.route('/api/gdd/upload', methods=['POST'])
def gdd_upload():
    """Start an async upload + index job and return a job_id immediately.
    Uses keyword_extractor backend to store in keyword_documents/keyword_chunks tables."""
    try:
        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'No file provided'}), 400

        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({'status': 'error', 'message': 'No file selected'}), 400

        pdf_bytes = file.read()
        job_id = new_job()
        # Start background thread
        t = threading.Thread(target=run_upload_pipeline_async, args=(
            job_id, pdf_bytes, file.filename), daemon=True)
        t.start()

        # Respond immediately with job_id
        return jsonify({'status': 'accepted', 'job_id': job_id, 'step': 'Uploading file'}), 202

    except Exception as e:
        app.logger.error(f"Error in upload: {e}")
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/gdd/documents', methods=['GET'])
def gdd_documents():
    """List all indexed GDD documents (from both gdd_documents and keyword_documents tables)"""
    app.logger.info("=" * 60)
    app.logger.info("GET /api/gdd/documents - Starting request")

    try:
        all_documents = []
        gdd_docs_count = 0
        keyword_docs_count = 0

        # Get documents from GDD service (gdd_documents table) - may not exist
        if gdd_service_available:
            try:
                app.logger.info(
                    "GDD service is available, calling list_documents()...")
                gdd_docs = list_documents()
                gdd_docs_count = len(gdd_docs) if gdd_docs else 0
                app.logger.info(
                    f"list_documents() returned {gdd_docs_count} documents from gdd_documents table")
                if gdd_docs:
                    all_documents.extend(gdd_docs)
            except Exception as e:
                app.logger.warning(
                    f"Could not load GDD documents (table may not exist): {e}")
                gdd_docs_count = 0

        # Get documents from keyword_extractor backend (keyword_documents table)
        # Store file sizes from storage (used for both GDD and keyword docs)
        file_sizes = {}
        try:
            from backend.storage.keyword_storage import list_keyword_documents
            from backend.storage.supabase_client import get_supabase_client

            keyword_docs = list_keyword_documents()
            keyword_docs_count = len(keyword_docs) if keyword_docs else 0
            app.logger.info(
                f"list_keyword_documents() returned {keyword_docs_count} documents from keyword_documents table")

            # Get chunk counts for all documents in one query (more efficient)
            chunk_counts = {}
            if keyword_docs:
                try:
                    client = get_supabase_client()
                    # Get all doc_ids
                    doc_ids = [doc['doc_id']
                               for doc in keyword_docs if 'doc_id' in doc]
                    if doc_ids:
                        # Query chunk counts grouped by doc_id
                        for doc_id in doc_ids:
                            try:
                                chunks_result = client.table('keyword_chunks').select(
                                    'id', count='exact').eq('doc_id', doc_id).execute()
                                chunk_counts[doc_id] = chunks_result.count if hasattr(
                                    chunks_result, 'count') else 0
                            except:
                                chunk_counts[doc_id] = 0

                except Exception as e:
                    app.logger.warning(f"Could not fetch chunk counts: {e}")

            # Fetch file sizes from Supabase storage bucket (gdd_pdfs) - do this once for all documents
            try:
                if 'client' not in locals():
                    client = get_supabase_client()
                bucket_name = 'gdd_pdfs'
                storage_files = client.storage.from_(bucket_name).list()

                # Create a mapping of filename to size
                for file_info in storage_files:
                    file_name = file_info.get('name', '')
                    # Get size from metadata
                    metadata = file_info.get('metadata', {})
                    file_size_bytes = metadata.get('size', 0)
                    if file_size_bytes:
                        file_sizes[file_name] = file_size_bytes
            except Exception as e:
                app.logger.warning(
                    f"Could not fetch file sizes from storage: {e}")

            # Convert keyword_documents format to match gdd_documents format
            for doc in keyword_docs:
                # Ensure doc has required fields for GDD RAG
                if 'doc_id' not in doc:
                    continue

                doc_id = doc['doc_id']
                # Add chunks_count from our pre-fetched counts
                doc['chunks_count'] = chunk_counts.get(doc_id, 0)

                # Fetch file size from storage if available
                # Try multiple strategies to match the file
                file_path = doc.get('file_path', '')
                pdf_storage_path = doc.get('pdf_storage_path', '')

                # Try to find file size in storage
                file_size = None
                if pdf_storage_path and pdf_storage_path in file_sizes:
                    file_size = file_sizes[pdf_storage_path]
                elif file_path:
                    # Extract filename from file_path
                    import os
                    filename = os.path.basename(file_path)
                    if filename in file_sizes:
                        file_size = file_sizes[filename]
                    # Also try with doc_id as filename (common pattern)
                    elif f"{doc_id}.pdf" in file_sizes:
                        file_size = file_sizes[f"{doc_id}.pdf"]
                    # Try with just the doc_id (no extension)
                    elif doc_id in file_sizes:
                        file_size = file_sizes[doc_id]

                if file_size:
                    doc['size'] = file_size

                # Ensure created_at is preserved (from keyword_documents table)
                # The created_at field should already be in the doc from the database query

                # Ensure status field exists
                if 'status' not in doc:
                    doc['status'] = 'ready' if doc.get(
                        'chunks_count', 0) > 0 else 'indexed'

                all_documents.append(doc)
        except Exception as e:
            app.logger.warning(f"Could not load keyword documents: {e}")
            import traceback
            app.logger.warning(f"Traceback: {traceback.format_exc()}")

        app.logger.info(
            f"Total documents before deduplication: {len(all_documents)} (GDD: {gdd_docs_count}, Keyword: {keyword_docs_count})")

        # Deduplicate documents by doc_id (same document might exist in both tables)
        unique_documents = {}
        for doc in all_documents:
            # Get doc_id from either 'doc_id' or 'id' field
            doc_id = doc.get('doc_id') or doc.get('id')
            if doc_id:
                # Keep the first occurrence, or prefer the one with more complete data
                if doc_id not in unique_documents:
                    unique_documents[doc_id] = doc
                else:
                    # If we already have this doc_id, prefer the one with chunks_count
                    existing = unique_documents[doc_id]
                    if doc.get('chunks_count', 0) > existing.get('chunks_count', 0):
                        unique_documents[doc_id] = doc
                    # Or if existing has no name but new one does, use new one
                    elif not existing.get('name') and doc.get('name'):
                        unique_documents[doc_id] = doc

        # Convert back to list
        all_documents = list(unique_documents.values())

        app.logger.info(
            f"Total documents after deduplication: {len(all_documents)}")

        if all_documents:
            app.logger.info(
                f"Sample document: {all_documents[0].get('name', 'N/A')}")

        # Generate options for dropdown
        options = ["All Documents"]
        for doc in sorted(all_documents, key=lambda x: x.get("doc_id") or x.get("id", "")):
            doc_id = doc.get("doc_id") or doc.get("id", "")
            name = doc.get("name", doc_id)
            options.append(f"{name} ({doc_id})")

        app.logger.info(
            f"Returning response with {len(all_documents)} documents and {len(options)} options")
        app.logger.info("=" * 60)
        return jsonify({
            'documents': all_documents,
            'options': options
        })
    except Exception as e:
        app.logger.error(f"[ERROR] Error listing GDD documents: {e}")
        import traceback
        app.logger.error(f"Traceback: {traceback.format_exc()}")
        app.logger.info("=" * 60)
        return jsonify({'documents': [], 'options': ['All Documents'], 'error': str(e)})


@app.route('/api/gdd/sections', methods=['GET'])
def get_gdd_sections():
    """Get all sections/headers for a specific document"""
    app.logger.info("=" * 60)
    app.logger.info("[GDD Sections API] *** ROUTE HIT ***")
    app.logger.info(f"[GDD Sections API] Request URL: {request.url}")
    app.logger.info(f"[GDD Sections API] Request method: {request.method}")
    app.logger.info(f"[GDD Sections API] Request args: {dict(request.args)}")
    app.logger.info(
        f"[GDD Sections API] doc_id parameter: {request.args.get('doc_id')}")
    app.logger.info("=" * 60)

    try:
        if not gdd_service_available:
            app.logger.warning("[GDD Sections API] GDD service not available")
            return jsonify({'sections': [], 'error': 'GDD service not available'})

        doc_id = request.args.get('doc_id')
        if not doc_id:
            app.logger.warning("[GDD Sections API] Missing doc_id parameter")
            return jsonify({'sections': [], 'error': 'doc_id parameter required'})

        app.logger.info(
            f"[GDD Sections API] Calling get_document_sections for doc_id: {doc_id}")
        # get_document_sections is already imported at module level
        sections = get_document_sections(doc_id)
        app.logger.info(
            f"[GDD Sections API] Returning {len(sections)} sections for doc_id: {doc_id}")

        result = {
            'sections': sections,
            'doc_id': doc_id
        }
        app.logger.info(
            f"[GDD Sections API] Response: {len(sections)} sections")
        return jsonify(result)
    except Exception as e:
        app.logger.error(
            f"[GDD Sections API] Error getting sections for document {request.args.get('doc_id')}: {e}")
        import traceback
        app.logger.error(
            f"[GDD Sections API] Traceback: {traceback.format_exc()}")
        return jsonify({'sections': [], 'error': str(e)})

# Document Explainer routes (Tab 2)


@app.route('/api/gdd/explainer/search', methods=['POST'])
def explainer_search():
    """Search for keyword and return document/section options"""
    app.logger.info("=" * 80)
    app.logger.info("[EXPLAINER SEARCH] Endpoint called")
    app.logger.info(f"[EXPLAINER SEARCH] Request method: {request.method}")
    app.logger.info(f"[EXPLAINER SEARCH] Content-Type: {request.content_type}")
    app.logger.info(f"[EXPLAINER SEARCH] Headers: {dict(request.headers)}")

    try:
        from backend.gdd_explainer import search_for_explainer

        app.logger.info("[EXPLAINER SEARCH] Getting JSON data from request")
        data = request.get_json()
        app.logger.info(f"[EXPLAINER SEARCH] Request data: {data}")

        keyword = data.get('keyword', '') if data else ''
        app.logger.info(
            f"[EXPLAINER SEARCH] Extracted keyword: '{keyword}' (type: {type(keyword)}, length: {len(keyword) if keyword else 0})")

        if not keyword:
            app.logger.warning("[EXPLAINER SEARCH] Empty keyword received")
            return jsonify({
                'choices': [],
                'store_data': [],
                'status_msg': "Please enter a keyword to search.",
                'success': False
            }), 200

        app.logger.info("[EXPLAINER SEARCH] Calling search_for_explainer()")
        result = search_for_explainer(keyword)
        app.logger.info(
            f"[EXPLAINER SEARCH] search_for_explainer() returned: {type(result)}")
        app.logger.info(
            f"[EXPLAINER SEARCH] Result keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
        app.logger.info(
            f"[EXPLAINER SEARCH] Result success: {result.get('success') if isinstance(result, dict) else 'N/A'}")
        app.logger.info(
            f"[EXPLAINER SEARCH] Result choices count: {len(result.get('choices', [])) if isinstance(result, dict) else 'N/A'}")
        app.logger.info(
            f"[EXPLAINER SEARCH] Progress messages: {result.get('progress_messages', []) if isinstance(result, dict) else 'N/A'}")

        app.logger.info("[EXPLAINER SEARCH] Returning JSON response")
        response = jsonify(result)
        app.logger.info(
            f"[EXPLAINER SEARCH] Response status: {response.status_code}")
        app.logger.info("=" * 80)
        return response
    except Exception as e:
        app.logger.error("=" * 80)
        app.logger.error(f"[EXPLAINER SEARCH] ERROR: {str(e)}")
        app.logger.error(f"[EXPLAINER SEARCH] Error type: {type(e).__name__}")
        import traceback
        app.logger.error(
            f"[EXPLAINER SEARCH] Full traceback:\n{traceback.format_exc()}")
        app.logger.error("=" * 80)

        try:
            error_response = jsonify({
                'choices': [],
                'store_data': [],
                'status_msg': f"❌ Error: {str(e)}",
                'success': False
            })
            return error_response, 500
        except Exception as json_error:
            app.logger.error(
                f"[EXPLAINER SEARCH] Failed to create JSON error response: {json_error}")
            return f"Error: {str(e)}", 500


@app.route('/api/gdd/explainer/search/stream', methods=['GET'])
def explainer_search_stream():
    """Stream search progress using Server-Sent Events (SSE)"""
    try:
        from backend.gdd_explainer import search_for_explainer_stream

        keyword = request.args.get('keyword', '')

        return Response(
            stream_with_context(search_for_explainer_stream(keyword)),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',  # IMPORTANT (nginx)
            }
        )
    except Exception as e:
        app.logger.error(f"Error setting up search stream: {e}")
        import traceback
        app.logger.error(traceback.format_exc())
        import json

        def error_stream():
            yield f"data: {json.dumps({'message': f'❌ Error: {str(e)}'})}\n\n"
            yield f"data: {json.dumps({'message': '__DONE__'})}\n\n"
        return Response(
            stream_with_context(error_stream()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
            }
        ), 500


@app.route('/api/gdd/explainer/explain', methods=['POST'])
def explainer_explain():
    """Generate explanation from selected items"""
    try:
        from backend.gdd_explainer import generate_explanation

        data = request.get_json()
        keyword = data.get('keyword', '')
        selected_choices = data.get('selected_choices', [])
        stored_results = data.get('stored_results', [])

        result = generate_explanation(
            keyword, selected_choices, stored_results)
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Error in explainer explain: {e}")
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify({
            'explanation': f"❌ Error: {str(e)}",
            'source_chunks': '',
            'metadata': '',
            'success': False
        }), 500


@app.route('/api/gdd/explainer/select-all', methods=['POST'])
def explainer_select_all():
    """Select all items"""
    try:
        from backend.gdd_explainer import select_all_items

        data = request.get_json()
        stored_results = data.get('stored_results', [])

        result = select_all_items(stored_results)
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Error in explainer select-all: {e}")
        return jsonify({'choices': []}), 500


@app.route('/api/gdd/explainer/select-none', methods=['POST'])
def explainer_select_none():
    """Deselect all items"""
    try:
        from backend.gdd_explainer import select_none_items

        result = select_none_items()
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Error in explainer select-none: {e}")
        return jsonify({'choices': []}), 500


@app.route('/api/gdd/explainer/deep-search', methods=['POST'])
def deep_search():
    """Deep search with LLM translation and synonym generation"""
    try:
        from backend.services.deep_search_service import deep_search_keyword

        data = request.get_json()
        keyword = data.get('keyword', '').strip()

        if not keyword:
            return jsonify({'error': 'Keyword is required'}), 400

        result = deep_search_keyword(keyword)
        return jsonify(result)
    except Exception as e:
        import traceback
        app.logger.error(
            f"Error in deep search: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/code/query', methods=['POST'])
def code_query():
    """Handle Code Q&A queries"""
    try:
        if not code_service_available:
            return jsonify({'error': 'Code service not available', 'status': 'error'}), 500

        data = request.get_json()
        query = data.get('query', '')
        file_filters = data.get('file_filters', [])
        selected_methods = data.get('selected_methods', [])

        app.logger.info(f"[Code Q&A API] Received query: {query[:100]}")
        app.logger.info(f"[Code Q&A API] File filters: {file_filters}")
        app.logger.info(f"[Code Q&A API] Selected methods: {selected_methods}")

        result = query_codebase(
            query, file_filters=file_filters, selected_methods=selected_methods)

        app.logger.info(
            f"[Code Q&A API] Response status: {result.get('status')}")
        app.logger.info(
            f"[Code Q&A API] Response length: {len(result.get('response', ''))}")

        return jsonify(result)
    except Exception as e:
        app.logger.error(f"[Code Q&A API] Error in Code query: {e}")
        import traceback
        app.logger.error(f"[Code Q&A API] Traceback: {traceback.format_exc()}")
        return jsonify({'error': str(e), 'status': 'error'}), 500


@app.route('/api/code/files', methods=['GET'])
def code_files():
    """List all indexed code files"""
    try:
        if not code_service_available:
            return jsonify({'files': []})

        files = list_indexed_files()
        app.logger.info(f"Returning {len(files)} code files")
        return jsonify({'files': files})
    except Exception as e:
        app.logger.error(f"Error listing code files: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'files': []}), 500


@app.route('/api/code/upload', methods=['POST'])
def code_upload():
    """Start an async code file upload + index job and return a job_id immediately."""
    try:
        if not code_service_available:
            return jsonify({'status': 'error', 'message': 'Code service not available'}), 500

        if 'file' not in request.files:
            return jsonify({'status': 'error', 'message': 'No file provided'}), 400

        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({'status': 'error', 'message': 'No file selected'}), 400

        # Only accept .cs files
        if not file.filename.lower().endswith('.cs'):
            return jsonify({'status': 'error', 'message': 'Only .cs files are supported'}), 400

        file_bytes = file.read()
        job_id = new_job()
        # Start background thread
        t = threading.Thread(target=run_code_upload_pipeline_async, args=(
            job_id, file_bytes, file.filename), daemon=True)
        t.start()

        # Respond immediately with job_id
        return jsonify({'status': 'accepted', 'job_id': job_id, 'step': 'Uploading file'}), 202

    except Exception as e:
        app.logger.error(f"Error in code upload: {e}")
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/api/code/upload/status', methods=['GET'])
def code_upload_status():
    """Poll the current status of a code upload job."""
    job_id = request.args.get('job_id')
    if not job_id or job_id == 'undefined':
        return jsonify({'status': 'error', 'message': 'job_id required'}), 400

    job = get_job(job_id)
    if not job:
        return jsonify({'status': 'error', 'message': 'Unknown job_id'}), 404

    # Always JSON
    response = {
        'status': job['status'],  # running | success | error
        'step': job['step'],
        'message': job['message'],
        'job_id': job_id,
    }

    # Add chunks_count if available (for success status)
    if job['status'] == 'success':
        # Try to extract chunks count from message or set default
        message = job.get('message', '')
        import re
        chunks_match = re.search(r'\((\d+)\s+chunks\)', message)
        if chunks_match:
            response['chunks_count'] = int(chunks_match.group(1))
        else:
            response['chunks_count'] = 0

    return jsonify(response), 200


@app.route('/api/debug/code-supabase', methods=['GET'])
def debug_code_supabase():
    """Debug endpoint to check Code Q&A Supabase connection and data"""
    diagnostics = {
        'code_supabase_available': False,
        'code_files_count': 0,
        'code_chunks_count': 0,
        'sample_files': [],
        'errors': []
    }

    try:
        from backend.storage.code_supabase_storage import USE_SUPABASE, list_code_files_supabase
        from backend.storage.supabase_client import get_code_files

        diagnostics['code_supabase_available'] = USE_SUPABASE

        if USE_SUPABASE:
            try:
                files = get_code_files()
                diagnostics['code_files_count'] = len(files) if files else 0
                diagnostics['sample_files'] = [
                    f.get('file_path', 'unknown') for f in (files[:5] if files else [])]

                # Try to get chunk count
                try:
                    from backend.storage.supabase_client import get_supabase_client
                    client = get_supabase_client()
                    result = client.table('code_chunks').select(
                        'id', count='exact').limit(1).execute()
                    diagnostics['code_chunks_count'] = result.count if hasattr(
                        result, 'count') else 'unknown'
                except Exception as e:
                    diagnostics['errors'].append(
                        f"Could not count chunks: {e}")

            except Exception as e:
                diagnostics['errors'].append(f"Error fetching code files: {e}")
        else:
            diagnostics['errors'].append("Code Supabase not configured")

    except Exception as e:
        diagnostics['errors'].append(f"Diagnostic error: {e}")
        import traceback
        diagnostics['traceback'] = traceback.format_exc()

    return jsonify(diagnostics)


@app.route('/api/debug/supabase', methods=['GET'])
def debug_supabase():
    """Diagnostic endpoint to check Supabase connection and configuration"""
    diagnostics = {
        'environment_variables': {},
        'supabase_connection': {},
        'data_access': {},
        'errors': []
    }

    try:
        # Check environment variables (masked for security)
        supabase_url = os.getenv('SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_KEY')
        supabase_service_key = os.getenv('SUPABASE_SERVICE_KEY')

        diagnostics['environment_variables'] = {
            'SUPABASE_URL': supabase_url[:30] + '...' if supabase_url else 'NOT SET',
            'SUPABASE_KEY': supabase_key[:20] + '...' if supabase_key else 'NOT SET',
            'SUPABASE_SERVICE_KEY': 'SET' if supabase_service_key else 'NOT SET',
            'DASHSCOPE_API_KEY': 'SET' if os.getenv('DASHSCOPE_API_KEY') else 'NOT SET'
        }

        # Test Supabase connection
        if supabase_url and supabase_key:
            try:
                from backend.storage.supabase_client import get_supabase_client, get_code_files
                from backend.storage.keyword_storage import list_keyword_documents

                # Test anon key connection
                client = get_supabase_client(use_service_key=False)
                diagnostics['supabase_connection']['anon_key'] = 'SUCCESS'

                # Test data access
                try:
                    # Note: gdd_documents table may not exist, using keyword_documents instead
                    from backend.storage.keyword_storage import list_keyword_documents
                    keyword_docs = list_keyword_documents()
                    diagnostics['data_access']['keyword_documents'] = {
                        'count': len(keyword_docs) if keyword_docs else 0,
                        'status': 'SUCCESS' if keyword_docs and len(keyword_docs) > 0 else 'EMPTY'
                    }
                    if keyword_docs and len(keyword_docs) > 0:
                        diagnostics['data_access']['keyword_sample'] = {
                            'doc_id': keyword_docs[0].get('doc_id'),
                            'name': keyword_docs[0].get('name')
                        }
                except Exception as e:
                    diagnostics['data_access']['keyword_documents'] = {
                        'count': 0,
                        'status': 'ERROR',
                        'error': str(e)
                    }
                    diagnostics['errors'].append(
                        f"GDD documents access error: {e}")

                try:
                    code_files_list = get_code_files()
                    diagnostics['data_access']['code_files'] = {
                        'count': len(code_files_list),
                        'status': 'SUCCESS' if len(code_files_list) > 0 else 'EMPTY'
                    }
                except Exception as e:
                    diagnostics['data_access']['code_files'] = {
                        'count': 0,
                        'status': 'ERROR',
                        'error': str(e)
                    }
                    diagnostics['errors'].append(
                        f"Code files access error: {e}")

            except Exception as e:
                diagnostics['supabase_connection']['anon_key'] = 'FAILED'
                diagnostics['supabase_connection']['error'] = str(e)
                diagnostics['errors'].append(f"Supabase connection error: {e}")
        else:
            diagnostics['supabase_connection']['status'] = 'MISSING_ENV_VARS'
            diagnostics['errors'].append(
                "SUPABASE_URL or SUPABASE_KEY not set")

        # Check if Supabase is being used
        try:
            from backend.storage.gdd_supabase_storage import USE_SUPABASE
            diagnostics['supabase_usage'] = {
                'USE_SUPABASE': USE_SUPABASE,
                'status': 'ENABLED' if USE_SUPABASE else 'DISABLED'
            }
        except Exception as e:
            diagnostics['supabase_usage'] = {
                'status': 'ERROR',
                'error': str(e)
            }

    except Exception as e:
        diagnostics['errors'].append(f"Diagnostic error: {e}")
        import traceback
        diagnostics['traceback'] = traceback.format_exc()

    return jsonify(diagnostics)


@app.route('/api/manage/aliases', methods=['GET'])
def get_aliases():
    """Get all aliases grouped by keyword (Supabase)"""
    try:
        from backend.storage.keyword_storage import list_aliases_grouped
        from datetime import datetime

        grouped = list_aliases_grouped()

        # Convert to frontend format
        keywords_list = list(grouped.values())

        return jsonify({
            'keywords': keywords_list,
            'lastUpdated': datetime.now().isoformat()
        })
    except Exception as e:
        import traceback
        app.logger.error(
            f"Error getting aliases: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/manage/aliases', methods=['POST'])
def add_alias():
    """Add a new alias for a keyword (Supabase)"""
    try:
        from backend.storage.keyword_storage import insert_alias

        data = request.get_json()
        keyword = data.get('keyword', '').strip()
        alias = data.get('alias', '').strip()
        language = data.get('language', 'en')

        if not keyword or not alias:
            return jsonify({'error': 'Keyword and alias are required'}), 400

        result = insert_alias(keyword, alias, language)
        return jsonify(result)
    except Exception as e:
        import traceback
        app.logger.error(f"Error adding alias: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/manage/aliases', methods=['DELETE'])
def remove_alias():
    """Delete an alias (Supabase)"""
    try:
        from backend.storage.keyword_storage import delete_alias

        data = request.get_json()
        keyword = data.get('keyword', '').strip()
        alias = data.get('alias', '').strip()

        if not keyword or not alias:
            return jsonify({'error': 'Keyword and alias are required'}), 400

        success = delete_alias(keyword, alias)
        return jsonify({'success': success})
    except Exception as e:
        import traceback
        app.logger.error(
            f"Error deleting alias: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/manage/aliases/save', methods=['POST'])
def save_aliases():
    """Save aliases (Supabase) - handles bulk updates from frontend"""
    try:
        from backend.storage.keyword_storage import insert_alias, delete_alias
        from datetime import datetime

        data = request.get_json()
        if not data or 'keywords' not in data:
            return jsonify({'error': 'Invalid data'}), 400

        # The frontend sends the full keyword structure with aliases
        # We need to sync it with Supabase
        keywords = data.get('keywords', [])

        # Get current state from Supabase
        from backend.storage.keyword_storage import list_aliases_grouped
        current_grouped = list_aliases_grouped()

        # For simplicity, we'll just add new aliases and keywords
        # Frontend should handle deletions via DELETE endpoint
        for kw in keywords:
            keyword_name = kw.get('name', '').strip()
            language = kw.get('language', 'en').lower()
            aliases = kw.get('aliases', [])

            if not keyword_name:
                continue

            # Add each alias
            for alias_obj in aliases:
                alias_name = alias_obj.get('name', '').strip()
                if alias_name:
                    try:
                        insert_alias(keyword_name, alias_name, language)
                    except Exception as e:
                        # Ignore duplicate errors (UNIQUE constraint)
                        if 'duplicate' not in str(e).lower() and 'unique' not in str(e).lower():
                            app.logger.warning(
                                f"Could not insert alias {alias_name} for {keyword_name}: {e}")

        return jsonify({
            'status': 'success',
            'lastUpdated': datetime.now().isoformat()
        })
    except Exception as e:
        import traceback
        app.logger.error(
            f"Error saving aliases: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint for Render"""
    return jsonify({'status': 'ok', 'service': 'unified-rag-app'}), 200

# Add 404 error handler for debugging


@app.errorhandler(404)
def not_found_error(error):
    """Handle 404 errors with detailed logging"""
    app.logger.error("=" * 60)
    app.logger.error(f"[404 ERROR] Request to {request.url} not found")
    app.logger.error(f"[404 ERROR] Path: {request.path}")
    app.logger.error(f"[404 ERROR] Method: {request.method}")
    app.logger.error(f"[404 ERROR] Args: {dict(request.args)}")
    app.logger.error("=" * 60)
    return jsonify({'error': 'Not found', 'path': request.path, 'method': request.method}), 404

# Log all registered routes after all routes are defined


def log_all_routes():
    """Log all registered routes for debugging"""
    try:
        with app.app_context():
            app.logger.info("=" * 60)
            app.logger.info("All registered routes:")
            api_routes = []
            other_routes = []
            for rule in app.url_map.iter_rules():
                methods = [m for m in rule.methods if m not in {
                    'HEAD', 'OPTIONS'}]
                route_info = f"  {rule.rule} [{', '.join(methods)}]"
                if rule.rule.startswith('/api'):
                    api_routes.append(route_info)
                else:
                    other_routes.append(route_info)

            for route in sorted(api_routes):
                app.logger.info(route)
            for route in sorted(other_routes):
                app.logger.info(route)
            app.logger.info("=" * 60)
    except Exception as e:
        app.logger.warning(f"Could not log routes: {e}")


# Log routes after all are defined
log_all_routes()

# Preload WordNet for synonym generation (avoids delays during first use)
try:
    app.logger.info("=" * 60)
    app.logger.info("Preloading WordNet for synonym generation...")
    from backend.services.translation_synonym_service import preload_wordnet
    preload_wordnet()
    app.logger.info("=" * 60)
except Exception as e:
    app.logger.warning(
        f"WordNet preload failed (synonym generation may be slower): {e}")

# Final validation - ensure app can start
try:
    app.logger.info("=" * 60)
    app.logger.info("App initialization complete")
    app.logger.info(f"App name: {app.name}")
    app.logger.info(f"App debug mode: {app.debug}")
    app.logger.info(
        f"GDD service available: {gdd_service_available if 'gdd_service_available' in globals() else 'Unknown'}")
    app.logger.info(
        f"Code service available: {code_service_available if 'code_service_available' in globals() else 'Unknown'}")
    app.logger.info("=" * 60)
    app.logger.info("✅ App is ready to serve requests")
    app.logger.info("=" * 60)
except Exception as e:
    import sys
    import traceback
    app.logger.error("=" * 60)
    app.logger.error(f"[FATAL] App validation failed: {e}")
    app.logger.error(f"Traceback:\n{traceback.format_exc()}")
    app.logger.error("=" * 60)
    print(f"[FATAL] App validation failed: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)
    # Don't raise - let gunicorn handle it

if __name__ == '__main__':
    # Signal handler for clean shutdown with Ctrl+C
    def signal_handler(sig, frame):
        print("\n\n🛑 Shutting down gracefully... (Ctrl+C pressed)")
        print("Bye! 👋\n")
        sys.exit(0)

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    app.logger.info(f"Starting Flask development server on port {port}")
    app.logger.info("Press Ctrl+C to stop the server")

    try:
        app.run(host='0.0.0.0', port=port, debug=debug, use_reloader=False)
    except KeyboardInterrupt:
        print("\n\n🛑 Server stopped by Ctrl+C")
        sys.exit(0)
