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

# Load environment variables
load_dotenv()

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configuration
CONFIG = {
    'SECRET_KEY': os.getenv('FLASK_SECRET_KEY', os.urandom(24).hex()),
    'LOG_FILE': 'app.log',
    'LOG_FORMAT': '%(asctime)s - %(message)s',
    'LOG_DATE_FORMAT': '%d-%b-%y %H:%M:%S'
}

# Setup logging
def setup_logging(config):
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    
    file_handler = logging.FileHandler(config['LOG_FILE'])
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(config['LOG_FORMAT'], datefmt=config['LOG_DATE_FORMAT']))
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(config['LOG_FORMAT'], datefmt=config['LOG_DATE_FORMAT']))
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# Create Flask app
app = Flask(__name__)
app.config.update(CONFIG)
app.logger = setup_logging(app.config)

# Import services
try:
    from backend.gdd_service import (
        upload_and_index_document,
        list_documents,
        get_document_options,
        query_gdd_documents
    )
    gdd_service_available = True
except ImportError as e:
    app.logger.warning(f"Could not import GDD service: {e}")
    gdd_service_available = False

try:
    from backend.code_service import (
        query_codebase,
        list_indexed_files
    )
    code_service_available = True
except ImportError as e:
    app.logger.warning(f"Could not import Code service: {e}")
    code_service_available = False

@app.route('/')
def index():
    """Main page with tabs for GDD RAG and Code Q&A"""
    return render_template('index.html')

@app.route('/gdd')
def gdd_tab():
    """GDD RAG tab"""
    return render_template('gdd_tab.html')

@app.route('/code')
def code_tab():
    """Code Q&A tab"""
    return render_template('code_tab.html')

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

@app.route('/api/gdd/upload', methods=['POST'])
def gdd_upload():
    """Handle document uploads for GDD RAG"""
    try:
        if not gdd_service_available:
            return jsonify({'error': 'GDD service not available'}), 500
        
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided', 'status': 'error'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected', 'status': 'error'}), 400
        
        # Save uploaded file temporarily
        from werkzeug.utils import secure_filename
        import tempfile
        
        filename = secure_filename(file.filename)
        temp_dir = Path(tempfile.gettempdir())
        temp_file = temp_dir / filename
        file.save(str(temp_file))
        
        # Process the file
        result = upload_and_index_document(temp_file)
        
        # Clean up temp file
        try:
            temp_file.unlink()
        except:
            pass
        
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Error in GDD upload: {e}")
        return jsonify({'error': str(e), 'status': 'error'}), 500

@app.route('/api/gdd/documents', methods=['GET'])
def gdd_documents():
    """List all indexed GDD documents"""
    try:
        if not gdd_service_available:
            return jsonify({'documents': [], 'options': ['All Documents']})
        
        documents = list_documents()
        options = get_document_options()
        
        return jsonify({
            'documents': documents,
            'options': options
        })
    except Exception as e:
        app.logger.error(f"Error listing GDD documents: {e}")
        return jsonify({'documents': [], 'options': ['All Documents'], 'error': str(e)})

@app.route('/api/code/query', methods=['POST'])
def code_query():
    """Handle Code Q&A queries"""
    try:
        if not code_service_available:
            return jsonify({'error': 'Code service not available', 'status': 'error'}), 500
        
        data = request.get_json()
        query = data.get('query', '')
        file_filters = data.get('file_filters', [])
        rerank = data.get('rerank', False)
        
        result = query_codebase(query, file_filters=file_filters, rerank=rerank)
        return jsonify(result)
    except Exception as e:
        app.logger.error(f"Error in Code query: {e}")
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
                from backend.storage.supabase_client import get_supabase_client, get_gdd_documents, get_code_files
                
                # Test anon key connection
                client = get_supabase_client(use_service_key=False)
                diagnostics['supabase_connection']['anon_key'] = 'SUCCESS'
                
                # Test data access
                try:
                    gdd_docs = get_gdd_documents()
                    diagnostics['data_access']['gdd_documents'] = {
                        'count': len(gdd_docs),
                        'status': 'SUCCESS' if len(gdd_docs) > 0 else 'EMPTY'
                    }
                    if len(gdd_docs) > 0:
                        diagnostics['data_access']['gdd_sample'] = {
                            'doc_id': gdd_docs[0].get('doc_id'),
                            'name': gdd_docs[0].get('name')
                        }
                except Exception as e:
                    diagnostics['data_access']['gdd_documents'] = {
                        'count': 0,
                        'status': 'ERROR',
                        'error': str(e)
                    }
                    diagnostics['errors'].append(f"GDD documents access error: {e}")
                
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
                    diagnostics['errors'].append(f"Code files access error: {e}")
                
            except Exception as e:
                diagnostics['supabase_connection']['anon_key'] = 'FAILED'
                diagnostics['supabase_connection']['error'] = str(e)
                diagnostics['errors'].append(f"Supabase connection error: {e}")
        else:
            diagnostics['supabase_connection']['status'] = 'MISSING_ENV_VARS'
            diagnostics['errors'].append("SUPABASE_URL or SUPABASE_KEY not set")
        
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

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=port, debug=debug)

