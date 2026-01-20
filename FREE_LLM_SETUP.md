# Free LLM Setup Guide

Since you don't want to pay for OpenAI, here are free alternatives that work with this app:

## Option 1: Ollama (Recommended - Easiest & Free)

**Ollama** runs models locally on your computer - completely free, no API keys needed!

### Setup Steps:

1. **Install Ollama:**
   ```bash
   # macOS
   brew install ollama
   # OR download from https://ollama.ai/download
   ```

2. **Start Ollama service:**
   ```bash
   ollama serve
   ```

3. **Download embedding model:**
   ```bash
   # Download a good embedding model (recommended: mxbai-embed-large)
   ollama pull mxbai-embed-large
   
   # OR for smaller/faster: nomic-embed-text
   ollama pull nomic-embed-text
   ```

4. **Download LLM model (for queries):**
   ```bash
   # Download a good LLM (recommended: llama3.2 or mistral)
   ollama pull llama3.2
   # OR
   ollama pull mistral
   ```

5. **Update your .env file:**
   ```bash
   # Use Ollama instead of OpenAI
   OPENAI_API_KEY=ollama  # Can be anything, not used
   OPENAI_BASE_URL=http://localhost:11434/v1
   EMBEDDING_MODEL=mxbai-embed-large  # or nomic-embed-text
   DEFAULT_LLM_MODEL=llama3.2  # or mistral
   ```

6. **Restart your app:**
   ```bash
   python3 app.py
   ```

**Pros:**
- ✅ Completely free
- ✅ Runs locally (privacy)
- ✅ No API keys needed
- ✅ OpenAI-compatible API

**Cons:**
- ⚠️ Requires local installation
- ⚠️ Needs decent RAM (8GB+ recommended)
- ⚠️ Slower than cloud APIs

---

## Option 2: Google Gemini (Free Tier)

**Google Gemini** offers a generous free tier - already supported in the codebase!

### Setup Steps:

1. **Get Gemini API Key (Free):**
   - Go to https://aistudio.google.com/app/apikey
   - Sign in with Google account
   - Create a new API key (FREE)

2. **Update your .env file:**
   ```bash
   GEMINI_API_KEY=your-gemini-api-key-here
   DEFAULT_LLM_MODEL=gemini-1.5-flash
   DEFAULT_EMBEDDING_MODEL=text-embedding-004
   ```

3. **Update the code to use Gemini** (I'll help with this)

**Pros:**
- ✅ Free tier available
- ✅ Already supported in codebase
- ✅ Good performance

**Cons:**
- ⚠️ Requires Google account
- ⚠️ Rate limits on free tier

---

## Option 3: Hugging Face Inference API (Free Tier)

**Hugging Face** offers free API access to many models.

### Setup Steps:

1. **Get Hugging Face Token:**
   - Go to https://huggingface.co/settings/tokens
   - Create a free account
   - Generate an access token

2. **Update your .env file:**
   ```bash
   HUGGINGFACE_API_KEY=your-hf-token-here
   OPENAI_BASE_URL=https://api-inference.huggingface.co/v1
   ```

**Pros:**
- ✅ Free tier available
- ✅ Many model options

**Cons:**
- ⚠️ Rate limits
- ⚠️ May need code changes

---

## Option 4: OpenRouter (Free Models)

**OpenRouter** aggregates free models from various providers.

### Setup Steps:

1. **Get API Key:**
   - Go to https://openrouter.ai/keys
   - Sign up (free)
   - Create API key

2. **Update your .env file:**
   ```bash
   OPENAI_API_KEY=your-openrouter-key
   OPENAI_BASE_URL=https://openrouter.ai/api/v1
   EMBEDDING_MODEL=mxbai-embed-large  # Free model
   DEFAULT_LLM_MODEL=meta-llama/llama-3.2-3b-instruct:free
   ```

---

## Quick Start: Automated Setup (Easiest!)

Run the setup script to configure everything automatically:

```bash
python3 scripts/setup_free_llm.py
```

This will guide you through setting up Gemini or Ollama step-by-step!

---

## Quick Start: Manual Setup

### Option A: Gemini (Easiest FREE option)

1. **Get API Key:**
   - Go to https://aistudio.google.com/app/apikey
   - Sign in with Google account
   - Create API key (FREE)

2. **Update .env:**
   ```bash
   GEMINI_API_KEY=your-gemini-key-here
   EMBEDDING_MODEL=text-embedding-004
   DEFAULT_LLM_MODEL=gemini-1.5-flash
   ```

3. **Restart app:**
   ```bash
   python3 app.py
   ```

### Option B: Ollama (Local, FREE)

```bash
# 1. Install Ollama
brew install ollama  # macOS
# OR visit https://ollama.ai/download

# 2. Start Ollama (in a separate terminal)
ollama serve

# 3. Download models
ollama pull mxbai-embed-large  # For embeddings
ollama pull llama3.2           # For LLM

# 4. Update .env
OPENAI_BASE_URL=http://localhost:11434/v1
EMBEDDING_MODEL=mxbai-embed-large
DEFAULT_LLM_MODEL=llama3.2
OPENAI_API_KEY=ollama  # Can be anything
```

Then restart your app - it will use Ollama instead of OpenAI!

---

## Which Should You Choose?

- **Ollama**: Best if you want privacy and don't mind local setup
- **Gemini**: Best if you want cloud-based and already have Google account
- **Hugging Face**: Best if you want variety of models
- **OpenRouter**: Best if you want easy cloud access to free models

Let me know which one you'd like to use, and I'll help you configure it!
