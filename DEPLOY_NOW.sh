#!/bin/bash
# ================================================================
# EchoMind v2.2.0 - AUTOMATIC DEPLOYMENT SCRIPT
# ================================================================
# This script will deploy all fixes to GitHub and Railway
# Run this from /tmp/echomind-backend directory
# ================================================================

set -e  # Exit on error

echo "🚀 EchoMind v2.2.0 Deployment Starting..."
echo ""
echo "📦 What will be deployed:"
echo "   ✅ Environment variable validation"
echo "   ✅ Enhanced email service with retry logic"
echo "   ✅ Reddit Pro integration"
echo "   ✅ Comprehensive diagnostics endpoints"
echo ""

# Check if we're in the right directory
if [ ! -f "main.py" ]; then
    echo "❌ ERROR: Not in echomind-backend directory"
    echo "   Run: cd /tmp/echomind-backend"
    exit 1
fi

# Check if changes are committed
if git diff --cached --quiet; then
    echo "❌ ERROR: No changes staged for commit"
    echo "   Changes have already been committed."
    echo "   Just need to push to GitHub."
    echo ""
    echo "   Run: git push origin main"
    exit 1
fi

echo "✅ All checks passed"
echo ""

# Push to GitHub
echo "📤 Pushing to GitHub..."
if git push origin main; then
    echo "✅ Successfully pushed to GitHub!"
    echo ""
    echo "🔄 Railway will automatically detect the push and redeploy"
    echo ""
    echo "📊 Monitor deployment:"
    echo "   1. Go to https://railway.app"
    echo "   2. Select: echomind-backend-production"
    echo "   3. Click: Deployments tab"
    echo "   4. Watch logs for: ✅ EchoMind Backend Ready"
    echo ""
    echo "⏱️  Expected deployment time: 2-3 minutes"
    echo ""
    echo "✅ DEPLOYMENT INITIATED"
else
    echo "❌ Push failed - likely need authentication"
    echo ""
    echo "🔧 To fix:"
    echo "   1. Get GitHub Personal Access Token"
    echo "   2. Run: git remote set-url origin https://USERNAME:TOKEN@github.com/rechoagency/echomind-backend.git"
    echo "   3. Run: git push origin main"
    exit 1
fi
