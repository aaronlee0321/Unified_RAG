#!/usr/bin/env python3
"""
Quick setup script to configure free LLM options.
Helps you configure Ollama (local, free).
"""
import os
import sys
from pathlib import Path


def check_env_file():
    """Check if .env file exists."""
    env_path = Path('.env')
    if not env_path.exists():
        print("❌ .env file not found!")
        print("   Creating .env from env.example...")
        example_path = Path('env.example')
        if example_path.exists():
            env_path.write_text(example_path.read_text())
            print("✅ Created .env file")
        else:
            print("❌ env.example not found. Please create .env manually.")
            return None
    return env_path


def setup_ollama():
    """Setup Ollama (local, free)."""
    print("\n🆓 Setting up Ollama (FREE - Local)")
    print("=" * 50)
    print("Ollama runs models locally on your computer.")
    print()
    print("First, make sure Ollama is installed:")
    print("  macOS: brew install ollama")
    print("  OR download from: https://ollama.ai/download")
    print()

    installed = input("Is Ollama installed? (y/n): ").strip().lower()
    if installed != 'y':
        print("⏭️  Please install Ollama first, then run this script again")
        return False

    print("\nNext, start Ollama in a separate terminal:")
    print("  ollama serve")
    print()
    started = input("Is Ollama running? (y/n): ").strip().lower()
    if started != 'y':
        print("⏭️  Please start Ollama first: ollama serve")
        return False

    print("\nDownload required models:")
    print("  ollama pull mxbai-embed-large  # For embeddings")
    print("  ollama pull llama3.2           # For LLM queries")
    print()
    models_ready = input("Are models downloaded? (y/n): ").strip().lower()
    if models_ready != 'y':
        print("⏭️  Please download models first")
        return False

    env_path = check_env_file()
    if not env_path:
        return False

    # Read current .env
    env_content = env_path.read_text()

    # Update or add Ollama config
    lines = env_content.split('\n')
    updated = False

    # Check if Ollama config exists
    ollama_found = False
    for i, line in enumerate(lines):
        if 'localhost:11434' in line or '127.0.0.1:11434' in line:
            ollama_found = True
            break

    if not ollama_found:
        # Add Ollama config
        lines.append('')
        lines.append('# Ollama (FREE - Local, OpenAI-compatible)')
        lines.append('OPENAI_BASE_URL=http://localhost:11434/v1')
        lines.append('OPENAI_API_KEY=ollama  # Can be anything, not used')
        lines.append('EMBEDDING_MODEL=mxbai-embed-large')
        lines.append('DEFAULT_LLM_MODEL=llama3.2')
        updated = True

    if updated:
        env_path.write_text('\n'.join(lines))
        print("✅ Ollama configured!")
        print("   Added to .env:")
        print("   OPENAI_BASE_URL=http://localhost:11434/v1")
        print("   EMBEDDING_MODEL=mxbai-embed-large")
        print("   DEFAULT_LLM_MODEL=llama3.2")
        return True

    return False


def main():
    print("=" * 60)
    print("🆓 FREE LLM Setup Helper")
    print("=" * 60)
    print()
    print("This script helps you configure FREE alternatives to OpenAI.")
    print()
    print("Options:")
    print("  1. Ollama (FREE, runs locally on your computer)")
    print()

    choice = input("Choose option (1): ").strip()

    if choice == '1':
        setup_ollama()
    else:
        print("❌ Invalid choice")
        return

    print()
    print("=" * 60)
    print("✅ Setup complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Restart your Flask app: python3 app.py")
    print("2. Try uploading a document to test")
    print()
    print("The app will automatically use Ollama if configured.")
    print("Priority: Ollama > OpenAI > Qwen/DashScope (if configured)")


if __name__ == '__main__':
    main()
