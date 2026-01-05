"""
Test the updated Qwen embedding API call with dimensions and encoding_format.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()

from gdd_rag_backbone.llm_providers import QwenProvider

print("Testing Qwen Embedding API...")
print("=" * 80)

try:
    provider = QwenProvider()
    print(f"✓ Provider initialized")
    print(f"  Base URL: {provider.base_url}")
    print(f"  Embedding Model: {provider.embedding_model}")
    print(f"  Embedding Dimension: {provider.embedding_dim}")
    
    # Test with a small text
    test_texts = [
        "This is a test sentence for embedding.",
        "Another test sentence to verify the API works."
    ]
    
    print(f"\nTesting embedding with {len(test_texts)} text(s)...")
    embeddings = provider.embed(test_texts)
    
    print(f"✓ Success! Generated {len(embeddings)} embedding(s)")
    print(f"  First embedding dimension: {len(embeddings[0])}")
    print(f"  Second embedding dimension: {len(embeddings[1])}")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()









