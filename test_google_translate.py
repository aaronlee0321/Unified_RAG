"""
Free Google Translate API Test CLI (No API key required)
Uses deep-translator library (free and unlimited)
Language detection powered by fast-langdetect (80x faster fastText)
Based on: https://github.com/matheuss/google-translate-api
          https://github.com/LlmKira/fast-langdetect
"""
import os
from dotenv import load_dotenv

load_dotenv()


def detect_language_local(text: str) -> str:
    """
    Fast language detection using fast-langdetect (fastText-based).
    Returns ISO 639-1 language code (e.g., 'en', 'vi', 'zh', 'ja')
    """
    try:
        from fast_langdetect import detect

        # Detect language using fast-langdetect (lite model by default)
        result = detect(text, model='lite', k=1)

        if result and len(result) > 0:
            # Extract language code (e.g., 'en', 'vi', 'zh-cn')
            lang_code = result[0]['lang']

            # Handle language codes with subtags (e.g., 'zh-cn' -> 'zh', 'pt-br' -> 'pt')
            # For compatibility with Google Translate API
            base_lang = lang_code.split('-')[0].lower()
            return base_lang

        # Fallback to English if detection fails
        return 'en'

    except ImportError:
        # Fallback to simple regex-based detection if fast-langdetect not installed
        import re
        vietnamese_chars = re.compile(
            r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđĐ]',
            re.IGNORECASE
        )
        return 'vi' if vietnamese_chars.search(text) else 'en'
    except Exception as e:
        # Fallback to English on any error
        print(f"⚠️  Language detection error: {e}")
        return 'en'


def translate_with_google(text: str, target_language: str = None):
    """
    Translate text using free Google Translate API (no API key needed)
    Uses deep-translator library

    Args:
        text: Text to translate
        target_language: Target language code ('en' or 'vi')
                        If None, auto-detects and translates to opposite

    Returns:
        dict with translation results
    """
    try:
        from deep_translator import GoogleTranslator

        # Detect source language locally first
        detected_lang = detect_language_local(text)

        # Determine target language if not specified
        if target_language is None:
            if detected_lang == 'vi':
                target_language = 'en'
            else:
                target_language = 'vi'

        # Translate
        translator = GoogleTranslator(source='auto', target=target_language)
        translated_text = translator.translate(text)

        # Try to get detected language from translator
        # (deep-translator doesn't always return this, so we use our detection)
        try:
            # Some versions return detected language
            detected = translator.detect(text)
            if isinstance(detected, dict):
                detected_lang = detected.get('lang', detected_lang)
        except:
            pass

        return {
            'original_text': text,
            'translated_text': translated_text,
            'detected_language': detected_lang,
            'target_language': target_language,
            'success': True
        }

    except ImportError:
        return {
            'original_text': text,
            'translated_text': None,
            'error': 'deep-translator not installed. Run: pip install deep-translator',
            'success': False
        }
    except Exception as e:
        return {
            'original_text': text,
            'translated_text': None,
            'error': str(e),
            'success': False
        }


def display_translation(result: dict):
    """Display translation results"""
    print("\n" + "=" * 70)

    if not result['success']:
        print("❌ Translation Failed")
        print(f"Error: {result['error']}")
        print("=" * 70 + "\n")
        return

    # Language names
    lang_names = {
        'en': 'English',
        'vi': 'Vietnamese',
        'vie': 'Vietnamese'
    }

    detected = result['detected_language']
    target = result['target_language']

    print(f"📝 Original Text: {result['original_text']}")
    print(f"🌍 Detected Language: {lang_names.get(detected, detected)}")
    print("=" * 70)

    print(f"\n🔄 Translation to {lang_names.get(target, target)}:")
    print(f"   {result['translated_text']}")

    print("\n" + "=" * 70 + "\n")


def batch_translate(texts: list, target_language: str = None):
    """Translate multiple texts"""
    print("\n" + "=" * 70)
    print(f"📚 Batch Translation ({len(texts)} items)")
    print("=" * 70)

    results = []
    for i, text in enumerate(texts, 1):
        print(f"\n[{i}/{len(texts)}] Translating: {text[:50]}...")
        result = translate_with_google(text, target_language)
        results.append(result)

        if result['success']:
            print(f"   ✓ {result['translated_text'][:60]}...")
        else:
            print(f"   ✗ Failed: {result['error']}")

    print("\n" + "=" * 70)
    print(
        f"✅ Completed: {sum(1 for r in results if r['success'])}/{len(texts)} successful")
    print("=" * 70 + "\n")

    return results


def show_examples():
    """Show translation examples"""
    examples = [
        "tank",
        "xe tăng",
        "military vehicle",
        "phương tiện quân sự",
        "The tank has heavy armor",
        "Xe tăng có lớp giáp dày"
    ]

    print("\n" + "=" * 70)
    print("📚 Google Translate Examples")
    print("=" * 70)

    for example in examples:
        print(f"\n{'─'*70}")
        result = translate_with_google(example)
        display_translation(result)
        input("Press Enter for next example...")


def check_dependencies():
    """Check if required libraries are installed"""
    all_installed = True

    # Check deep-translator
    try:
        from deep_translator import GoogleTranslator
        print("✅ deep-translator library is installed")
    except ImportError:
        print("❌ deep-translator library not found")
        print("   Install: pip install deep-translator")
        all_installed = False

    # Check fast-langdetect
    try:
        from fast_langdetect import detect
        print("✅ fast-langdetect library is installed (80x faster language detection)")
    except ImportError:
        print("⚠️  fast-langdetect library not found (optional, fallback to regex)")
        print("   Install for better detection: pip install fast-langdetect")
        # Don't set all_installed = False, as this is optional

    if not all_installed:
        print("\n❌ Missing required dependencies")
        print("\nInstall all at once:")
        print("   pip install deep-translator fast-langdetect")
        print("\nFeatures:")
        print("  • deep-translator: FREE and UNLIMITED Google Translate API")
        print("  • fast-langdetect: Detects 176 languages (80x faster than alternatives)")

    return all_installed


def main():
    """Main CLI loop"""
    print("\n" + "=" * 70)
    print("🌐 Free Google Translate API Test (No API Key Required!)")
    print("=" * 70)
    print("Features:")
    print("  • FREE and UNLIMITED (no API key needed)")
    print("  • Auto-detect language (supports 176+ languages)")
    print("  • 80x faster language detection with fast-langdetect")
    print("  • Translate between any language pair")
    print("  • Batch translation support")
    print("  • Uses same servers as translate.google.com")
    print("\nCommands:")
    print("  • 'examples' - Show translation examples")
    print("  • 'batch' - Test batch translation")
    print("  • 'quit' or 'exit' - Exit")
    print("=" * 70 + "\n")

    # Check dependencies
    if not check_dependencies():
        print("\n❌ Cannot proceed without required library")
        return

    print()

    while True:
        try:
            # Get input
            user_input = input("Enter text to translate: ").strip()

            # Check exit
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye!")
                break

            # Check examples
            if user_input.lower() == 'examples':
                show_examples()
                continue

            # Check batch
            if user_input.lower() == 'batch':
                print("\nBatch mode: Enter texts (one per line), empty line to finish:")
                texts = []
                while True:
                    line = input(f"  [{len(texts)+1}]: ").strip()
                    if not line:
                        break
                    texts.append(line)

                if texts:
                    batch_translate(texts)
                continue

            if not user_input:
                continue

            # Translate
            result = translate_with_google(user_input)
            display_translation(result)

        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()


if __name__ == '__main__':
    main()
