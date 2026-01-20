#!/usr/bin/env python3
"""
Configure Gemini API key in .env file.
"""
import os
import sys
from pathlib import Path

def main():
    print("=" * 60)
    print("🔧 Gemini Configuration")
    print("=" * 60)
    print()
    print("To get your FREE Gemini API key:")
    print("1. Go to: https://aistudio.google.com/app/apikey")
    print("2. Sign in with your Google account")
    print("3. Click 'Create API Key'")
    print("4. Copy your API key")
    print()
    
    api_key = input("Paste your Gemini API key here: ").strip()
    
    if not api_key:
        print("❌ No API key provided. Exiting.")
        sys.exit(1)
    
    # Find .env file
    env_path = Path('.env')
    if not env_path.exists():
        # Try to copy from env.example
        example_path = Path('env.example')
        if example_path.exists():
            print("📝 Creating .env from env.example...")
            env_path.write_text(example_path.read_text())
        else:
            print("❌ .env file not found and env.example doesn't exist.")
            print("   Please create .env manually.")
            sys.exit(1)
    
    # Read current .env
    lines = env_path.read_text().split('\n')
    
    # Update or add Gemini config
    gemini_found = False
    embedding_found = False
    llm_found = False
    
    for i, line in enumerate(lines):
        if line.startswith('GEMINI_API_KEY='):
            lines[i] = f'GEMINI_API_KEY={api_key}'
            gemini_found = True
        elif line.startswith('EMBEDDING_MODEL=') and not embedding_found:
            # Only update if it's not already set to a Gemini model
            if 'text-embedding-004' not in line:
                lines[i] = 'EMBEDDING_MODEL=text-embedding-004  # Gemini embedding model'
            embedding_found = True
        elif line.startswith('DEFAULT_LLM_MODEL=') and not llm_found:
            # Only update if it's not already set to a Gemini model
            if 'gemini' not in line.lower():
                lines[i] = 'DEFAULT_LLM_MODEL=gemini-1.5-flash  # Gemini LLM model'
            llm_found = True
    
    # Add if not found
    if not gemini_found:
        # Find where to insert (after Supabase config or at end)
        insert_idx = len(lines)
        for i, line in enumerate(lines):
            if '# LLM & EMBEDDING' in line or '# 🆓 FREE Option 1' in line:
                insert_idx = i
                break
        
        # Insert Gemini config
        gemini_config = [
            '',
            '# 🆓 FREE Option 1: Google Gemini (Recommended - Easiest FREE option)',
            '# Get free API key: https://aistudio.google.com/app/apikey',
            f'GEMINI_API_KEY={api_key}',
            'EMBEDDING_MODEL=text-embedding-004  # Gemini embedding model',
            'DEFAULT_LLM_MODEL=gemini-1.5-flash  # Gemini LLM model',
        ]
        
        # Insert before any existing LLM config
        lines[insert_idx:insert_idx] = gemini_config
    
    # Ensure embedding and LLM models are set correctly
    if not embedding_found:
        # Add embedding model if not found
        for i, line in enumerate(lines):
            if line.startswith('GEMINI_API_KEY='):
                # Add after GEMINI_API_KEY
                lines.insert(i + 1, 'EMBEDDING_MODEL=text-embedding-004  # Gemini embedding model')
                break
    
    if not llm_found:
        # Add LLM model if not found
        for i, line in enumerate(lines):
            if line.startswith('EMBEDDING_MODEL=') and 'text-embedding-004' in line:
                # Add after EMBEDDING_MODEL
                lines.insert(i + 1, 'DEFAULT_LLM_MODEL=gemini-1.5-flash  # Gemini LLM model')
                break
    
    # Write back
    env_path.write_text('\n'.join(lines))
    
    print()
    print("=" * 60)
    print("✅ Gemini configured successfully!")
    print("=" * 60)
    print()
    print("Configuration added to .env:")
    print(f"  GEMINI_API_KEY={api_key[:10]}...")
    print("  EMBEDDING_MODEL=text-embedding-004")
    print("  DEFAULT_LLM_MODEL=gemini-1.5-flash")
    print()
    print("📋 Next steps:")
    print("1. Make sure google-genai is installed:")
    print("   pip install google-genai")
    print("   (or: python3 scripts/setup_gemini.sh)")
    print()
    print("2. Restart your Flask app:")
    print("   python3 app.py")
    print()
    print("3. Try uploading a document - it will use Gemini!")
    print()

if __name__ == '__main__':
    main()
