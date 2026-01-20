"""
Shared configuration for unified RAG app
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Flask configuration
FLASK_SECRET_KEY = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')
FLASK_ENV = os.getenv('FLASK_ENV', 'development')
PORT = int(os.getenv('PORT', 5000))

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
SUPABASE_SERVICE_KEY = os.getenv('SUPABASE_SERVICE_KEY')

# Qwen/DashScope API configuration
DASHSCOPE_API_KEY = os.getenv('DASHSCOPE_API_KEY') or os.getenv('QWEN_API_KEY')
QWEN_API_KEY = os.getenv('QWEN_API_KEY') or DASHSCOPE_API_KEY
REGION = os.getenv('REGION', 'intl')

# Model configuration
DEFAULT_LLM_MODEL = os.getenv('DEFAULT_LLM_MODEL', 'gemini-1.5-flash')
DEFAULT_EMBEDDING_MODEL = os.getenv('DEFAULT_EMBEDDING_MODEL', 'text-embedding-004')

# Chunking configuration (for keyword extractor backend)
CHUNK_SIZE = int(os.getenv('CHUNK_SIZE', 500))
CHUNK_OVERLAP = float(os.getenv('CHUNK_OVERLAP', 0.15))

# Redis configuration (optional)
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / 'data'
DATA_DIR.mkdir(exist_ok=True)

def validate_config():
    """Validate that required configuration is present"""
    errors = []
    
    if not SUPABASE_URL:
        errors.append("SUPABASE_URL is required")
    if not SUPABASE_KEY:
        errors.append("SUPABASE_KEY is required")
    # Prefer Gemini; do not require paid providers
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        errors.append("GEMINI_API_KEY (or GOOGLE_API_KEY) is required for LLM/embeddings")
    
    if errors:
        raise ValueError("Configuration errors:\n" + "\n".join(f"  - {e}" for e in errors))
    
    return True

