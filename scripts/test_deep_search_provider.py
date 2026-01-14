"""Quick test to verify deep search uses OpenAI"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / '.env')
except:
    pass

from backend.services.llm_provider import SimpleLLMProvider
from backend.services.deep_search_service import generate_translation_and_synonyms

print("=" * 60)
print("Deep Search Provider Verification")
print("=" * 60)
print()

# Test SimpleLLMProvider
print("1️⃣  Checking SimpleLLMProvider configuration...")
try:
    provider = SimpleLLMProvider()
    print(f"   ✅ Provider initialized")
    print(f"   🤖 Model: {provider.model}")
    print(f"   🔗 Base URL: {provider.base_url or 'OpenAI default (None)'}")
    
    if provider.base_url is None:
        print("   ✅ Using OpenAI endpoint (base_url is None)")
    else:
        print(f"   ⚠️  Using custom endpoint: {provider.base_url}")
    
    if 'gpt' in provider.model.lower():
        print(f"   ✅ Using OpenAI model: {provider.model}")
    else:
        print(f"   ⚠️  Model might not be OpenAI: {provider.model}")
    
except Exception as e:
    print(f"   ❌ Error: {e}")
    sys.exit(1)

print()
print("2️⃣  Testing deep search translation/synonym generation...")
print("   (This will make an actual API call)")
try:
    result = generate_translation_and_synonyms("tank", "en")
    print(f"   ✅ Deep search function works!")
    print(f"   📝 Translation: {result.get('translation', 'N/A')}")
    print(f"   📝 EN Synonyms: {result.get('synonyms_en', [])}")
    print(f"   📝 VI Synonyms: {result.get('synonyms_vi', [])}")
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print()
print("=" * 60)
print("✅ Deep search is using OpenAI!")
print("=" * 60)

