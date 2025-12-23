#!/usr/bin/env python3
"""
Test script to find which Qwen models are accessible with your API key.

This script tests multiple Qwen models to see which ones your API key supports.
"""
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gdd_rag_backbone.config import QWEN_API_KEY


def test_models():
    """Test multiple Qwen models to see which ones work."""
    print("\n")
    print("=" * 80)
    print("🔍 Testing Alibaba Qwen Models")
    print("Finding which models your API key supports...")
    print("=" * 80)
    print()
    
    if not QWEN_API_KEY:
        print("❌ ERROR: QWEN_API_KEY is not set!")
        print("Please set your API key in .env file or environment variable.")
        sys.exit(1)
    
    # List of common Qwen models to test
    models_to_test = [
        # Chat models
        "qwen-turbo",
        "qwen-plus",
        "qwen-max",
        "qwen-max-longcontext",
        "qwen-max-0428",
        "qwen-max-0613",
        "qwen-max-0403",
        
        # Smaller models
        "qwen-7b-chat",
        "qwen-14b-chat",
        "qwen-72b-chat",
        "qwen-1.8b-chat",
        "qwen-32b-chat",
        
        # Vision models
        "qwen-vl-max",
        "qwen-vl-plus",
        "qwen-vl-chat",
        
        # Other variants
        "qwen-coder-max",
        "qwen-coder-plus",
        "qwen-audio-chat",
    ]
    
    try:
        from dashscope import Generation
        import dashscope
    except ImportError:
        print("❌ ERROR: dashscope package not installed.")
        print("Install it with: pip install dashscope")
        sys.exit(1)
    
    # Set API key and region in dashscope module
    dashscope.api_key = QWEN_API_KEY
    from gdd_rag_backbone.config import DASHSCOPE_REGION
    if DASHSCOPE_REGION:
        dashscope.region = DASHSCOPE_REGION
        print(f"Using region: {DASHSCOPE_REGION}")
    
    print(f"Testing {len(models_to_test)} models...")
    print("This may take a moment...\n")
    
    successful_models = []
    failed_models = []
    
    for i, model in enumerate(models_to_test, 1):
        print(f"[{i}/{len(models_to_test)}] Testing: {model:30}", end=" ... ")
        
        try:
            # Test with a simple API call (dashscope will use global api_key and region)
            response = Generation.call(
                model=model,
                messages=[{"role": "user", "content": "Hi"}],
                result_format='message',
                max_tokens=10,  # Keep it short for testing
            )
            
            if response.status_code == 200:
                print("✅ SUCCESS")
                successful_models.append(model)
            else:
                error_msg = response.message if hasattr(response, 'message') else f"Status {response.status_code}"
                print(f"❌ FAILED ({response.status_code}: {error_msg[:40]})")
                failed_models.append((model, response.status_code, error_msg))
        
        except Exception as e:
            error_msg = str(e)[:60]
            print(f"❌ ERROR ({error_msg})")
            failed_models.append((model, "EXCEPTION", error_msg))
    
    # Print summary
    print("\n" + "=" * 80)
    print("📊 RESULTS SUMMARY")
    print("=" * 80)
    
    if successful_models:
        print(f"\n✅ SUCCESSFUL MODELS ({len(successful_models)}):")
        print("-" * 80)
        for model in successful_models:
            print(f"  ✓ {model}")
        
        print(f"\n💡 RECOMMENDED MODEL:")
        print(f"   → {successful_models[0]}")
        print(f"\n   Update your config.py or .env to use:")
        print(f"   DEFAULT_LLM_MODEL={successful_models[0]}")
    else:
        print("\n❌ NO MODELS WORKED")
        print("   Your API key might be invalid or doesn't have model access.")
    
    if failed_models:
        print(f"\n❌ FAILED MODELS ({len(failed_models)}):")
        print("-" * 80)
        for model, status, error in failed_models[:10]:  # Show first 10
            print(f"  ✗ {model:30} - {status}: {error[:50]}")
        if len(failed_models) > 10:
            print(f"  ... and {len(failed_models) - 10} more")
    
    print("\n" + "=" * 80)
    print()


if __name__ == "__main__":
    test_models()

