# How to Fix Embedding API Key Error

## Error Message
```
Invalid API-key provided. Your API key may not have access to embedding services.
```

## Quick Fix

### Step 1: Check Your .env File

Make sure you have one of these API keys configured in your `.env` file:

```bash
# Option 1: DashScope/Qwen (Current default)
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxx
REGION=intl

# OR

QWEN_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxx
REGION=intl
```

### Step 2: Get a Valid API Key

#### For DashScope/Qwen:
1. Go to https://dashscope.console.aliyun.com/
2. Sign in with your Alibaba Cloud account
3. Navigate to **API Keys** section
4. Create a new API key or copy an existing one
5. **Important**: Make sure embedding services are enabled for your account
   - Go to **Services** → **Text Embedding**
   - Ensure the service is activated
   - Check your quota/usage limits

#### For OpenAI (Alternative):
1. Go to https://platform.openai.com/api-keys
2. Sign in and create a new API key
3. Add to `.env`:
   ```bash
   OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxx
   EMBEDDING_MODEL=text-embedding-3-small
   ```

### Step 3: Verify API Key Format

- DashScope keys usually start with `sk-` followed by alphanumeric characters
- OpenAI keys start with `sk-` followed by alphanumeric characters
- Make sure there are no extra spaces or quotes around the key

### Step 4: Enable Embedding Access

**For DashScope:**
1. Log into DashScope Console
2. Go to **Services** → **Text Embedding**
3. Activate the embedding service if not already active
4. Check your quota/credits balance
5. Make sure your API key has permissions for embedding models

**Common Issues:**
- ❌ API key expired or revoked
- ❌ Embedding service not activated in your account
- ❌ Insufficient quota/credits
- ❌ Wrong region setting (should be `intl` for international, `cn` for China)

### Step 5: Test Your API Key

You can test if your API key works by running:

```bash
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv('DASHSCOPE_API_KEY') or os.getenv('QWEN_API_KEY')
if api_key:
    print(f'✅ API key found: {api_key[:10]}...')
    # Try to import and test
    try:
        import dashscope
        dashscope.api_key = api_key
        print('✅ DashScope imported successfully')
    except Exception as e:
        print(f'❌ Error: {e}')
else:
    print('❌ No API key found in .env file')
"
```

### Step 6: Restart the Application

After updating your `.env` file:
```bash
# Stop the current app (Ctrl+C)
# Then restart:
python3 app.py
```

## Alternative: Use OpenAI Embeddings

If DashScope/Qwen continues to have issues, you can switch to OpenAI:

1. Get an OpenAI API key from https://platform.openai.com/api-keys
2. Add to `.env`:
   ```bash
   OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxx
   EMBEDDING_MODEL=text-embedding-3-small
   ```
3. The code will automatically use OpenAI embeddings if available

## Troubleshooting

### Error: "Invalid API-key provided"
- ✅ Check the key is correct (no typos, no extra spaces)
- ✅ Verify the key is active in your DashScope/OpenAI dashboard
- ✅ Make sure embedding services are enabled

### Error: "API key may not have access to embedding services"
- ✅ Enable Text Embedding service in DashScope console
- ✅ Check your account has sufficient quota/credits
- ✅ Verify your API key permissions include embedding access

### Error: "No embedding provider available"
- ✅ Check your `.env` file exists and has the correct variable names
- ✅ Make sure you're using `DASHSCOPE_API_KEY` or `QWEN_API_KEY` (not `QWEN_API_KEY` if you meant DashScope)
- ✅ Restart the application after changing `.env`

## Still Having Issues?

1. Check the application logs for detailed error messages
2. Verify your API key works by testing it directly:
   ```bash
   curl -X POST https://dashscope-intl.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding \
     -H "Authorization: Bearer YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"text-embedding-v2","input":"test"}'
   ```
3. Contact DashScope support if the API key is valid but still not working
