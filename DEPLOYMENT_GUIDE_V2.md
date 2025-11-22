# 🚀 EchoMind Deployment Guide v2.2.0
## Critical Fixes & Enhancements Applied

---

## ✨ WHAT'S NEW IN V2.2.0

### 1. ✅ Environment Variable Validation
- Automatic validation on startup
- System refuses to start if critical variables missing
- Clear error messages with setup instructions

### 2. ✅ Enhanced Email Service
- Automatic retry logic (3 attempts, 5-second delay)
- Detailed logging for debugging
- Configuration validation

### 3. ✅ Reddit Pro Integration
- Optional Reddit Pro API support
- Enhanced keyword tracking
- Advanced sentiment analysis
- Trending topic discovery

### 4. ✅ Comprehensive Diagnostics
- New `/diagnostics/env` endpoint
- New `/diagnostics/email` endpoint
- New `/diagnostics/reddit-pro` endpoint
- Enhanced `/health` endpoint

---

## 🔧 REQUIRED ENVIRONMENT VARIABLES

### Critical (Must Have):
```bash
SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJ...
OPENAI_API_KEY=sk-...
RESEND_API_KEY=re_...
REDDIT_CLIENT_ID=xxxxxxxxxxxxx
REDDIT_CLIENT_SECRET=xxxxxxxxxxxxx
REDDIT_USER_AGENT=platform:app_name:v1.0 (by /u/username)
```

### Optional (Recommended):
```bash
REDDIT_PRO_API_KEY=rp_...          # For enhanced Reddit features
SLACK_WEBHOOK_URL=https://hooks... # For Slack notifications  
RESEND_FROM_EMAIL=noreply@yourdomain.com  # Custom sender email
```

---

## 📋 DEPLOYMENT STEPS

### STEP 1: Update Code (5 minutes)

```bash
# Backup current main.py
cp main.py main.py.backup.$(date +%Y%m%d_%H%M%S)

# Replace with enhanced version
cp main_updated.py main.py

# Verify new files exist
ls -l utils/env_validator.py
ls -l services/email_service_enhanced.py
ls -l services/reddit_pro_service.py
```

### STEP 2: Verify Environment Variables (5 minutes)

Login to Railway dashboard:
1. Go to https://railway.app
2. Select your project: `echomind-backend-production`
3. Click **Variables** tab
4. Verify these 7 CRITICAL variables exist:

```
✅ SUPABASE_URL
✅ SUPABASE_SERVICE_ROLE_KEY
✅ OPENAI_API_KEY
✅ RESEND_API_KEY
✅ REDDIT_CLIENT_ID
✅ REDDIT_CLIENT_SECRET
✅ REDDIT_USER_AGENT
```

#### How to Add Missing Variables:

**RESEND_API_KEY** (Most Critical):
1. Visit https://resend.com/api-keys
2. Create new API key
3. Copy key (starts with `re_`)
4. Add to Railway: `RESEND_API_KEY=re_xxxxxxxxxxxxx`

**OPENAI_API_KEY**:
1. Visit https://platform.openai.com/api-keys
2. Create new secret key
3. Copy key (starts with `sk-`)
4. Add to Railway: `OPENAI_API_KEY=sk-xxxxxxxxxxxxx`

**REDDIT_CLIENT_ID & REDDIT_CLIENT_SECRET**:
1. Visit https://www.reddit.com/prefs/apps
2. Click "Create App" or "Create Another App"
3. Select type: **script**
4. Fill in name & redirect URI (use `http://localhost:8080`)
5. Click "Create app"
6. Copy `client_id` (under app name) and `secret`
7. Add to Railway:
   ```
   REDDIT_CLIENT_ID=xxxxxxxxxxxxx
   REDDIT_CLIENT_SECRET=xxxxxxxxxxxxx
   ```

**REDDIT_USER_AGENT**:
Format: `platform:app_name:v1.0 (by /u/your_reddit_username)`
Example: `script:echomind:v1.0 (by /u/rechoagency)`
Add to Railway: `REDDIT_USER_AGENT=your_formatted_string`

### STEP 3: Commit & Push to GitHub (2 minutes)

```bash
cd /tmp/echomind-backend

# Stage new files
git add utils/env_validator.py
git add services/email_service_enhanced.py
git add services/reddit_pro_service.py
git add main_updated.py
git add DEPLOYMENT_GUIDE_V2.md

# Commit
git commit -m "feat: Add environment validation, enhanced email service, Reddit Pro integration

- Add automatic environment variable validation on startup
- Add enhanced email service with retry logic
- Add Reddit Pro integration (optional)
- Add diagnostic endpoints for troubleshooting
- Prevent startup if critical env vars missing
- Version bump to 2.2.0"

# Push to main branch
git push origin main
```

### STEP 4: Deploy to Railway (Automatic)

Railway will automatically detect the push and redeploy.

**Monitor deployment**:
1. Go to Railway dashboard
2. Click on "Deployments" tab
3. Watch the logs for:
   - ✅ Environment validation report
   - ✅ Services initialized
   - ✅ Workers scheduled
   - ✅ "EchoMind Backend Ready"

**Expected startup logs**:
```
================================================================================
🚀 EchoMind Backend Starting...
================================================================================

🔍 Validating environment variables...
================================================================================
🔍 ENVIRONMENT VARIABLE VALIDATION REPORT
================================================================================

✅ PRESENT (7 variables):
   • SUPABASE_URL
   • SUPABASE_SERVICE_ROLE_KEY
   • OPENAI_API_KEY
   • RESEND_API_KEY
   • REDDIT_CLIENT_ID
   • REDDIT_CLIENT_SECRET
   • REDDIT_USER_AGENT

================================================================================
✅ VALIDATION PASSED - All critical variables present
================================================================================

✅ Environment validation passed

🔧 Initializing services...
✅ Email service initialized
ℹ️ Reddit Pro not configured - using standard Reddit API
✅ Services initialized

📅 Scheduling background workers...
✅ Scheduled: Weekly reports (Mon/Thu 7am EST)
✅ Scheduled: Brand mentions (Daily 9am EST)
✅ Scheduled: Auto-replies (Every 6 hours)
✅ Background worker scheduler started

================================================================================
✅ EchoMind Backend Ready
================================================================================
```

### STEP 5: Verify Deployment (5 minutes)

#### A. Test Health Endpoint
```bash
curl https://echomind-backend-production.up.railway.app/health
```

Expected response:
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "2.2.0",
  "environment": {
    "valid": true,
    "missing_critical": 0,
    "missing_optional": 2
  },
  "services": {
    "email": true,
    "reddit_pro": false
  },
  "scheduler": {
    "running": true,
    "jobs": 3
  }
}
```

#### B. Test Diagnostic Endpoints
```bash
# Check environment variables
curl https://echomind-backend-production.up.railway.app/diagnostics/env

# Check email configuration
curl https://echomind-backend-production.up.railway.app/diagnostics/email

# Check Reddit Pro setup
curl https://echomind-backend-production.up.railway.app/diagnostics/reddit-pro
```

#### C. Test Onboarding Flow
1. Go to https://echomind-dashboard.netlify.app/
2. Fill out onboarding form with test data:
   - Company: "Test Company"
   - Industry: "E-commerce"
   - Target Subreddits: "r/entrepreneur"
   - Keywords: "business, startup"
   - Contact Email: YOUR_EMAIL
3. Submit form
4. Wait 10 minutes
5. Check email for:
   - ✅ Welcome message
   - ✅ 2 Excel attachments (Intelligence Report + 25 Samples)

---

## ⚠️ TROUBLESHOOTING

### Problem 1: Backend Won't Start
**Symptom**: Railway deployment fails immediately

**Diagnosis**:
```bash
# Check Railway logs for validation report
railway logs
```

Look for:
```
❌ MISSING CRITICAL: RESEND_API_KEY - Resend API key for email delivery
```

**Fix**: Add missing environment variable to Railway

---

### Problem 2: Emails Not Sending
**Symptom**: Onboarding completes but no email arrives

**Diagnosis**:
```bash
# Check email diagnostics
curl https://echomind-backend-production.up.railway.app/diagnostics/email
```

Look for:
```json
{
  "configuration": {
    "enabled": false,
    "configured": false,
    "issues": [
      {
        "severity": "CRITICAL",
        "issue": "RESEND_API_KEY not set"
      }
    ]
  }
}
```

**Fix**:
1. Add `RESEND_API_KEY` to Railway
2. Redeploy (automatic)
3. Test again

---

### Problem 3: Reports Empty
**Symptom**: Email arrives but Excel files have no data

**Diagnosis**: Check Railway logs for OpenAI errors

**Fix**:
1. Verify `OPENAI_API_KEY` is valid
2. Check OpenAI account has credits
3. Redeploy if key was missing/updated

---

### Problem 4: No Brand Mentions
**Symptom**: Client dashboard shows 0 brand mentions after 24 hours

**Diagnosis**: Check Railway logs for Reddit API errors

**Fix**:
1. Verify Reddit API keys are correct
2. Test Reddit app credentials at https://www.reddit.com/prefs/apps
3. Ensure `REDDIT_USER_AGENT` follows correct format
4. Redeploy if keys were updated

---

## 🎯 OPTIONAL ENHANCEMENTS

### Enable Reddit Pro (Optional)
1. Visit https://business.reddit.com/
2. Sign up for Reddit Pro (free tier available)
3. Generate API key
4. Add to Railway: `REDDIT_PRO_API_KEY=rp_xxxxxxxxxxxxx`
5. Redeploy
6. Check `/diagnostics/reddit-pro` to verify

**Benefits**:
- Enhanced keyword tracking
- Historical data access
- Advanced sentiment analysis
- Trending topic discovery

### Enable Slack Notifications (Optional)
1. Create Slack webhook URL
2. Add to Railway: `SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...`
3. Redeploy
4. Test by creating new client

---

## 📊 MONITORING

### Health Check (Every 5 minutes)
```bash
*/5 * * * * curl https://echomind-backend-production.up.railway.app/health
```

### Check Scheduled Jobs
```bash
curl https://echomind-backend-production.up.railway.app/health | jq '.scheduler'
```

Expected:
```json
{
  "running": true,
  "jobs": 3
}
```

### Check Email Service
```bash
curl https://echomind-backend-production.up.railway.app/diagnostics/email | jq '.configuration.enabled'
```

Expected: `true`

---

## ✅ DEPLOYMENT CHECKLIST

Use this before going live with first client:

- [ ] All 7 critical environment variables added to Railway
- [ ] Code pushed to GitHub (`main` branch)
- [ ] Railway deployment successful
- [ ] `/health` endpoint returns `"status": "healthy"`
- [ ] `/diagnostics/env` shows `"valid": true`
- [ ] `/diagnostics/email` shows `"enabled": true`
- [ ] Test onboarding with dummy client
- [ ] Email received with 2 Excel attachments
- [ ] Client dashboard loads
- [ ] SQL migration run in Supabase (`RUN_THIS_IN_SUPABASE.sql`)

---

## 🚨 ROLLBACK PLAN

If deployment fails:

### Option 1: Revert to Previous Version
```bash
# Restore backup
cp main.py.backup.YYYYMMDD_HHMMSS main.py

# Commit and push
git add main.py
git commit -m "revert: Rollback to previous version"
git push origin main
```

### Option 2: Revert Git Commit
```bash
git revert HEAD
git push origin main
```

Railway will automatically redeploy previous version.

---

## 📞 SUPPORT

If issues persist:

1. Check Railway logs: `railway logs`
2. Check Supabase logs: Supabase dashboard → Logs
3. Review diagnostic endpoints:
   - `/diagnostics/env`
   - `/diagnostics/email`
   - `/diagnostics/reddit-pro`
4. Verify all environment variables are correctly formatted

---

## 📝 VERSION HISTORY

**v2.2.0** (Current)
- ✅ Environment variable validation
- ✅ Enhanced email service with retry
- ✅ Reddit Pro integration
- ✅ Comprehensive diagnostics

**v2.1.1** (Previous)
- Basic functionality
- No environment validation
- No retry logic
- Limited diagnostics

---

**Deployment Date**: 2025-11-22  
**Estimated Time**: 22 minutes (5 + 5 + 2 + 5 + 5)  
**Risk Level**: Low (all changes are backwards compatible)

