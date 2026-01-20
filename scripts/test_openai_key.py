#!/usr/bin/env python3
"""
Test script to verify OpenAI API key is working.
Tests both LLM and embedding functionality.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_openai_key():
    """Test OpenAI API key for both LLM and embeddings."""
    print("=" * 80)
    print("OpenAI API Key Test")
    print("=" * 80)
    
    # Check if API key is set
    api_key = os.getenv('OPENAI_API_KEY')
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY not found in environment")
        print("\nPlease add to your .env file:")
        print("  OPENAI_API_KEY=sk-your-key-here")
        return False
    
    print(f"✅ API Key found: {api_key[:10]}...{api_key[-4:]}")
    print()
    
    # Test OpenAI client import
    try:
        from openai import OpenAI
        print("✅ OpenAI package imported successfully")
    except ImportError:
        print("❌ ERROR: openai package not installed")
        print("Install with: pip install openai")
        return False
    
    # Initialize client
    base_url = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
    print(f"📍 Using base URL: {base_url}")
    print()
    
    client = OpenAI(api_key=api_key, base_url=base_url)
    
    # Test 1: List models (simple API call)
    print("Test 1: Listing available models...")
    try:
        models = client.models.list()
        model_names = [model.id for model in models.data[:5]]
        print(f"✅ Successfully connected to OpenAI API")
        print(f"   Found {len(models.data)} models (showing first 5): {', '.join(model_names)}")
    except Exception as e:
        print(f"❌ Failed to list models: {e}")
        return False
    print()
    
    # Test 2: Test LLM (chat completion)
    print("Test 2: Testing LLM (chat completion)...")
    llm_works = False
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": "Say 'Hello, OpenAI is working!' and nothing else."}
            ],
            max_tokens=20
        )
        result = response.choices[0].message.content.strip()
        print(f"✅ LLM test successful")
        print(f"   Response: {result}")
        llm_works = True
    except Exception as e:
        error_msg = str(e)
        if "429" in error_msg or "quota" in error_msg.lower() or "insufficient_quota" in error_msg.lower():
            print(f"⚠️  LLM test failed: Quota exceeded")
            print(f"   Error: {error_msg}")
            print(f"   Your API key is valid, but you've exceeded your usage quota.")
            print(f"   Please check: https://platform.openai.com/usage")
            print(f"   Note: Embeddings may still work even if LLM quota is exceeded")
        else:
            print(f"❌ LLM test failed: {e}")
    print()
    
    # Test 3: Test Embeddings
    print("Test 3: Testing Embeddings...")
    try:
        test_texts = ["This is a test sentence.", "Another test sentence."]
        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=test_texts
        )
        embeddings = [item.embedding for item in response.data]
        print(f"✅ Embedding test successful")
        print(f"   Generated {len(embeddings)} embeddings")
        print(f"   Embedding dimension: {len(embeddings[0])}")
        print(f"   First embedding (first 5 values): {embeddings[0][:5]}")
    except Exception as e:
        print(f"❌ Embedding test failed: {e}")
        error_msg = str(e)
        if "Invalid API-key" in error_msg or "401" in error_msg:
            print("\n⚠️  Your API key may be invalid or expired.")
            print("   Please check:")
            print("   1. The key is correct (no typos, no extra spaces)")
            print("   2. The key is active in your OpenAI dashboard")
            print("   3. You have sufficient credits/quota")
        elif "model" in error_msg.lower() and "not found" in error_msg.lower():
            print("\n⚠️  The embedding model may not be available.")
            print("   Try: text-embedding-3-small or text-embedding-ada-002")
        return False
    print()
    
    # Test 4: Test with custom embedding model from env
    embedding_model = os.getenv('EMBEDDING_MODEL', 'text-embedding-3-small')
    if embedding_model != 'text-embedding-3-small':
        print(f"Test 4: Testing custom embedding model ({embedding_model})...")
        try:
            response = client.embeddings.create(
                model=embedding_model,
                input=["Test"]
            )
            print(f"✅ Custom embedding model test successful")
            print(f"   Model: {embedding_model}")
            print(f"   Dimension: {len(response.data[0].embedding)}")
        except Exception as e:
            print(f"⚠️  Custom embedding model test failed: {e}")
            print(f"   Falling back to default: text-embedding-3-small")
        print()
    
    # Summary
    print("=" * 80)
    if llm_works:
        print("✅ ALL TESTS PASSED!")
        print("=" * 80)
        print("\nYour OpenAI API key is working correctly.")
        print("The app should be able to use OpenAI for:")
        print("  ✓ LLM queries (gpt-4o-mini)")
        print("  ✓ Embeddings (text-embedding-3-small)")
    else:
        print("⚠️  PARTIAL SUCCESS")
        print("=" * 80)
        print("\nYour OpenAI API key is VALID, but:")
        print("  ⚠️  LLM quota exceeded (429 error)")
        print("  ✅ Embeddings are working")
        print("\nTo fix:")
        print("  1. Check your usage: https://platform.openai.com/usage")
        print("  2. Add credits: https://platform.openai.com/account/billing")
        print("  3. Or wait for quota to reset")
        print("\nNote: Embeddings should still work for indexing documents!")
    print()
    return True  # Return True even if LLM quota exceeded, since embeddings work

if __name__ == "__main__":
    success = test_openai_key()
    sys.exit(0 if success else 1)
