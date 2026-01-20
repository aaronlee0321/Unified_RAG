"""
Global configuration for the GDD RAG Backbone system.
"""
import os
from pathlib import Path
from typing import Optional

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    # Load .env file from project root
    PROJECT_ROOT = Path(__file__).parent.parent
    env_path = PROJECT_ROOT / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # python-dotenv not installed, skip .env loading
    pass

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent

# Default paths
DEFAULT_WORKING_DIR = PROJECT_ROOT / "rag_storage"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "output"
DEFAULT_DOCS_DIR = PROJECT_ROOT / "docs"

# RAG-Anything configuration defaults
# Using "docling" as default to avoid PyTorch compatibility issues with MinerU
DEFAULT_PARSER = "docling"  # Options: "mineru" or "docling"
DEFAULT_PARSE_METHOD = "auto"
DEFAULT_ENABLE_IMAGE_PROCESSING = True
DEFAULT_ENABLE_TABLE_PROCESSING = True
DEFAULT_ENABLE_EQUATION_PROCESSING = True

# LLM Provider configuration (from environment variables)
# Check both DASHSCOPE_API_KEY (DashScope library standard) and QWEN_API_KEY (custom)
# DASHSCOPE_API_KEY takes priority as it's what the dashscope library expects
QWEN_API_KEY: Optional[str] = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
DASHSCOPE_REGION: Optional[str] = os.getenv("REGION", "intl")  # Region for DashScope (e.g., "intl", "cn")

# Set base URL based on region (INTL vs CN)
# INTL region uses dashscope-intl.aliyuncs.com
# CN region uses dashscope.aliyuncs.com
if DASHSCOPE_REGION and DASHSCOPE_REGION.lower() == "intl":
    DEFAULT_QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
elif DASHSCOPE_REGION and DASHSCOPE_REGION.lower() == "cn":
    DEFAULT_QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
else:
    DEFAULT_QWEN_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"  # Default to INTL

QWEN_BASE_URL: Optional[str] = os.getenv("QWEN_BASE_URL", DEFAULT_QWEN_BASE_URL)

VERTEX_PROJECT_ID: Optional[str] = os.getenv("VERTEX_PROJECT_ID")
VERTEX_LOCATION: Optional[str] = os.getenv("VERTEX_LOCATION", "us-central1")

OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL: Optional[str] = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# Google Gemini API configuration
GEMINI_API_KEY: Optional[str] = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

# Model defaults - Using Google Gemini by default
DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "gemini-1.5-flash")
# Gemini embedding model default
DEFAULT_EMBEDDING_MODEL = os.getenv("DEFAULT_EMBEDDING_MODEL", "text-embedding-004")

# Ensure directories exist
DEFAULT_WORKING_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_DOCS_DIR.mkdir(parents=True, exist_ok=True)

