"""
Test script to verify OpenAI API key and default model configuration.
This script checks if OpenAI API is properly configured and working.
"""
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    env_path = PROJECT_ROOT / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"📄 Loaded .env file from: {env_path}")
    else:
        print(f"⚠️  .env file not found at: {env_path}")
except ImportError:
    print("⚠️  python-dotenv not installed. Install with: pip install python-dotenv")
except Exception as e:
    print(f"⚠️  Error loading .env file: {e}")

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    print("❌ ERROR: openai package is not installed.")
    print("   Install with: pip install openai")
    sys.exit(1)

def test_openai_setup():
    """Test OpenAI API key and model configuration"""
    
    print("=" * 60)
    print("OpenAI API Configuration Test")
    print("=" * 60)
    print()
    
    # Step 1: Check API key
    print("1️⃣  Checking API Key...")
    api_key = os.getenv('OPENAI_API_KEY')
    
    if not api_key:
        print("   ❌ OPENAI_API_KEY not found in environment variables")
        print("   💡 Set it in your .env file or export it:")
        print("      export OPENAI_API_KEY=your-key-here")
        return False
    else:
        # Mask the key for display
        masked_key = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
        print(f"   ✅ OPENAI_API_KEY found: {masked_key}")
    
    print()
    
    # Step 2: Check default model
    print("2️⃣  Checking Default Model...")
    default_model = os.getenv('DEFAULT_LLM_MODEL') or os.getenv('LLM_MODEL', 'gpt-4o-mini')
    
    # Normalize model name (handle case variations)
    default_model_lower = default_model.lower()
    expected_model = 'gpt-4o-mini'
    
    if default_model_lower == expected_model:
        print(f"   ✅ Default model is correct: {default_model}")
    else:
        print(f"   ⚠️  Default model is: {default_model}")
        print(f"   💡 Expected: {expected_model}")
        print(f"   💡 Update your .env file: DEFAULT_LLM_MODEL={expected_model}")
    
    print()
    
    # Step 3: Test API connection
    print("3️⃣  Testing API Connection...")
    try:
        client = OpenAI(api_key=api_key)
        
        # Make a simple test call
        print("   📡 Making test API call...")
        response = client.chat.completions.create(
            model=default_model_lower,
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Say 'Hello' if you can read this."}
            ],
            max_tokens=10,
            temperature=0
        )
        
        result = response.choices[0].message.content.strip()
        print(f"   ✅ API call successful!")
        print(f"   📝 Response: {result}")
        
        # Verify model used
        model_used = response.model
        print(f"   🤖 Model used: {model_used}")
        
        # OpenAI may return model with date suffix (e.g., gpt-4o-mini-2024-07-18)
        # Check if it starts with the expected model name
        if model_used.lower().startswith(expected_model):
            print(f"   ✅ Model matches expected: {expected_model} (with date suffix: {model_used})")
        elif model_used.lower() == expected_model:
            print(f"   ✅ Model matches expected: {expected_model}")
        else:
            print(f"   ⚠️  Model used ({model_used}) differs from expected ({expected_model})")
        
    except Exception as e:
        print(f"   ❌ API call failed: {str(e)}")
        print()
        print("   Common issues:")
        print("   - Invalid API key")
        print("   - Insufficient API credits")
        print("   - Network connectivity issues")
        print("   - Model name incorrect or not available")
        return False
    
    print()
    
    # Step 4: Test SimpleLLMProvider
    print("4️⃣  Testing SimpleLLMProvider...")
    try:
        from backend.services.llm_provider import SimpleLLMProvider
        
        provider = SimpleLLMProvider()
        print(f"   ✅ SimpleLLMProvider initialized")
        print(f"   🤖 Provider model: {provider.model}")
        print(f"   🔗 Provider base_url: {provider.base_url or 'OpenAI default'}")
        
        # Test a simple call
        print("   📡 Making test call through SimpleLLMProvider...")
        test_response = provider.llm(
            "Say 'Test successful' if you can read this.",
            system_prompt="You are a test assistant.",
            max_tokens=10
        )
        print(f"   ✅ SimpleLLMProvider test successful!")
        print(f"   📝 Response: {test_response}")
        
    except Exception as e:
        print(f"   ❌ SimpleLLMProvider test failed: {str(e)}")
        import traceback
        print(f"   📋 Traceback:")
        print(traceback.format_exc())
        return False
    
    print()
    
    # Step 5: Summary
    print("=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
    print()
    print("Summary:")
    print(f"  • API Key: ✅ Configured")
    print(f"  • Default Model: {default_model}")
    print(f"  • API Connection: ✅ Working")
    print(f"  • SimpleLLMProvider: ✅ Working")
    print()
    print("Your OpenAI setup is ready to use! 🚀")
    
    return True

if __name__ == '__main__':
    success = test_openai_setup()
    sys.exit(0 if success else 1)

