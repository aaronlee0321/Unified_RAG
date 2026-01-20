#!/bin/bash
# Quick Gemini setup script

echo "🆓 Setting up Google Gemini..."
echo "================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "📝 Creating .env file from env.example..."
    cp env.example .env
    echo "✅ Created .env file"
    echo ""
fi

# Install google-genai package
echo "📦 Installing google-genai package..."
if [ -d ".venv" ]; then
    .venv/bin/pip install google-genai
elif [ -d "venv" ]; then
    venv/bin/pip install google-genai
else
    pip3 install --user google-genai
fi

echo ""
echo "✅ Package installation complete!"
echo ""
echo "📋 Next steps:"
echo "1. Get your FREE Gemini API key:"
echo "   👉 https://aistudio.google.com/app/apikey"
echo ""
echo "2. Sign in with your Google account"
echo ""
echo "3. Click 'Create API Key'"
echo ""
echo "4. Copy your API key and run:"
echo "   python3 scripts/configure_gemini.py"
echo ""
echo "   OR manually edit .env and set:"
echo "   GEMINI_API_KEY=your-key-here"
echo ""
