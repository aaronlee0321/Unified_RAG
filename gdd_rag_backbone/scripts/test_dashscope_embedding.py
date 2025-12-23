"""
Test script for DashScope/OpenAI-compatible embeddings.

This script:
1. Loads .env via config import
2. Verifies API key is available
3. Tests the embedding API call with the specified model
4. Reports success/failure with details

Usage (from repo root):
    python -m gdd_rag_backbone.scripts.test_dashscope_embedding
    python -m gdd_rag_backbone.scripts.test_dashscope_embedding --model text-embedding-v4
"""

import os
import argparse
import sys

# Import config FIRST to ensure .env is loaded
from gdd_rag_backbone import config  # noqa: F401

from openai import OpenAI


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test DashScope embedding API with specified model"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Embedding model name (default: from DEFAULT_EMBEDDING_MODEL env var or config)",
    )
    args = parser.parse_args()

    # Get API key (config.py already loaded .env)
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_API_KEY")
    if not api_key:
        print("ERROR: No DASHSCOPE_API_KEY or QWEN_API_KEY found in environment.")
        print("       Make sure your .env file exists and contains one of these keys.")
        return 1

    # Determine model to use
    model = args.model or os.getenv("DEFAULT_EMBEDDING_MODEL") or "text-embedding-v4"
    
    print("=" * 70)
    print("DASHSCOPE EMBEDDING API TEST")
    print("=" * 70)
    print(f"API Key: {api_key[:10]}...{api_key[-4:]} (masked)")
    print(f"Model: {model}")
    print(f"Base URL: https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
    print("=" * 70)
    print()

    # Initialize client
    client = OpenAI(
        api_key=api_key,
        base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )

    # Test text
    test_text = (
        "The quality of the clothes is excellent, very beautiful, worth the wait, "
        "I like it and will buy here again"
    )
    
    print(f"Testing embedding with text: {test_text[:50]}...")
    print()

    try:
        resp = client.embeddings.create(
            model=model,
            input=test_text,
        )
    except Exception as exc:
        print("❌ EMBEDDING API CALL FAILED")
        print("=" * 70)
        print(f"Error type: {type(exc).__name__}")
        print(f"Error message: {exc}")
        print()
        print("Possible issues:")
        print("  - Model name is incorrect or not available for your account")
        print("  - API key doesn't have access to embedding services")
        print("  - Network/connectivity issue")
        print("=" * 70)
        return 1

    # Success - extract and display results
    emb = resp.data[0].embedding
    dim = len(emb)
    preview = [round(v, 4) for v in emb[:8]]
    
    print("✅ EMBEDDING API CALL SUCCESSFUL")
    print("=" * 70)
    print(f"Embedding dimensions: {dim}")
    print(f"First 8 values: {preview}")
    print(f"Model used: {resp.model if hasattr(resp, 'model') else model}")
    print("=" * 70)
    print()
    print("✓ Your embedding configuration is working correctly!")
    print(f"✓ You can use '{model}' as DEFAULT_EMBEDDING_MODEL in your .env")
    return 0


if __name__ == "__main__":
    sys.exit(main())

