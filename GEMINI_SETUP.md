# 🆓 Gemini Setup Guide

## Step 1: Get Your FREE Gemini API Key

1. **Open the link:** https://aistudio.google.com/app/apikey
   (I've opened it in your browser)

2. **Sign in** with your Google account

3. **Click "Create API Key"**

4. **Copy your API key** (it will look like: `AIza...`)

## Step 2: Configure Your App

Run this command and paste your API key when prompted:

```bash
python3 scripts/configure_gemini.py
```

**OR** manually edit your `.env` file and add:

```bash
GEMINI_API_KEY=your-api-key-here
EMBEDDING_MODEL=text-embedding-004
DEFAULT_LLM_MODEL=gemini-1.5-flash
```

## Step 3: Restart Your App

```bash
python3 app.py
```

## That's It! 🎉

Your app will now use Gemini for:
- ✅ Generating embeddings (for document indexing)
- ✅ LLM queries (for answering questions)

## Verify It's Working

1. Upload a document through the web UI
2. Check the logs - you should see: `✅ Using Gemini embeddings`
3. Try asking a question - it will use Gemini to answer!

## Troubleshooting

**Error: "GEMINI_API_KEY environment variable must be set"**
- Make sure you added the key to `.env` file
- Restart your Flask app after editing `.env`

**Error: "google-genai package is required"**
- Run: `pip install google-genai` (or use your venv: `.venv/bin/pip install google-genai`)

**Error: "Invalid API key"**
- Make sure you copied the full key
- Check that there are no extra spaces
- Try creating a new API key

## Free Tier Limits

Gemini free tier includes:
- Generous rate limits
- No credit card required
- Perfect for development and testing

For production use, check Google's pricing: https://ai.google.dev/pricing
