# Railway Environment Variables Setup

## Required Environment Variables

Add these to your Railway project at:
**https://railway.app/project/echomind-backend**

Click **Variables** tab, then add each variable listed below.

⚠️ **IMPORTANT:** Get actual values from `/EchoMind_System_Complete_Fix_Nov23_2025/master_credentials.env` in AI Drive

### Core Database (CRITICAL)
```
SUPABASE_URL=[Get from AI Drive: master_credentials.env]
SUPABASE_KEY=[Get from AI Drive: master_credentials.env]
SUPABASE_SERVICE_KEY=[Get from AI Drive: master_credentials.env]
```

### OpenAI API (CRITICAL)
```
OPENAI_API_KEY=[Get from AI Drive: master_credentials.env]
```

### Reddit API (CRITICAL)
```
REDDIT_CLIENT_ID=[Get from AI Drive: master_credentials.env]
REDDIT_CLIENT_SECRET=[Get from AI Drive: master_credentials.env]
```

### Google OAuth (CRITICAL)
```
GOOGLE_CLIENT_ID=[Get from AI Drive: master_credentials.env]
GOOGLE_CLIENT_SECRET=[Get from AI Drive: master_credentials.env]
GOOGLE_REDIRECT_URI=https://echomind-backend-production.up.railway.app/api/google/callback
```

### Application Config
```
PORT=8080
```

### Optional (for full functionality)
```
N8N_API_KEY=[Create at: https://recho-echomind.app.n8n.cloud/settings/api]
RESEND_API_KEY=[Get from: https://resend.com/api-keys]
```

## Where to Get the Values

**All API keys and secrets are stored securely in AI Drive:**
- Location: `/EchoMind_System_Complete_Fix_Nov23_2025/master_credentials.env`
- Download link provided in conversation history
- Contains all values with proper formatting

## After Adding Variables

1. Click **Deploy** button in Railway
2. Wait for deployment to complete (2-3 minutes)
3. Verify at: https://echomind-backend-production.up.railway.app/health
4. Check that `database_connected: true` in the response

## Troubleshooting

If `database_connected: false`:
1. Verify SUPABASE_URL and SUPABASE_KEY are set correctly
2. Check Railway logs for connection errors
3. Ensure no extra spaces or line breaks in values
4. Redeploy after fixing

If deployment fails:
1. Check Railway build logs
2. Verify all CRITICAL variables are set
3. Ensure Python dependencies are installing correctly
4. Contact support if issues persist

## Security Note

🔒 **Never commit real API keys to public repositories**
- This file uses placeholders for security
- Real values are in AI Drive (private storage)
- Use Railway's environment variables (encrypted at rest)
