#!/usr/bin/env python3
"""
List available embedding models from DashScope API.
"""
import os
from dotenv import load_dotenv

load_dotenv('.env')

api_key = os.getenv("DASHSCOPE_API_KEY")

print("\n" + "=" * 80)
print("🔍 Checking Available Embedding Models")
print("=" * 80)
print()

# Check OpenAI-compatible endpoint
print("1. Checking OpenAI-compatible endpoint...")
try:
    from openai import OpenAI
    client = OpenAI(
        api_key=api_key,
        base_url='https://dashscope-intl.aliyuncs.com/compatible-mode/v1',
    )
    
    try:
        models = client.models.list()
        embedding_models = [m.id for m in models if 'embedding' in m.id.lower()]
        if embedding_models:
            print("   ✅ Found embedding models:")
            for m in embedding_models:
                print(f"      - {m}")
        else:
            print("   ⚠️  No embedding models found in list")
    except Exception as e:
        print(f"   ❌ Error listing models: {e}")
except ImportError:
    print("   ❌ openai package not installed")
except Exception as e:
    print(f"   ❌ Error: {e}")

print()

# Check DashScope native API
print("2. Testing known embedding model names...")
try:
    from dashscope import embeddings
    import dashscope
    
    dashscope.api_key = api_key
    dashscope.region = 'intl'
    
    models_to_test = [
        'text-embedding-v1',
        'text-embedding-v2',
        'text-embedding-v3',
        'text-embedding-async-v1',
        'text-embedding-async-v2',
        'text-embedding-async-v3',
    ]
    
    working_models = []
    for model in models_to_test:
        try:
            response = embeddings.TextEmbedding.call(
                model=model,
                input=['test'],
            )
            if response.status_code == 200:
                print(f"   ✅ {model}: WORKING")
                working_models.append(model)
            else:
                print(f"   ❌ {model}: {response.status_code} - {getattr(response, 'message', 'Unknown')}")
        except Exception as e:
            print(f"   ❌ {model}: {str(e)[:60]}")
    
    if working_models:
        print(f"\n   ✅ Working models: {', '.join(working_models)}")
    else:
        print("\n   ❌ No working embedding models found")
        print("   This suggests your API key doesn't have embedding access.")
        
except ImportError:
    print("   ❌ dashscope package not installed")
except Exception as e:
    print(f"   ❌ Error: {e}")

print("\n" + "=" * 80)
print("\n💡 If no embedding models work, your API key may not have embedding access.")
print("   Check the Model Studio console for embedding service availability.")
print("=" * 80)

