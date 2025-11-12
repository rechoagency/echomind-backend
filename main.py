from dotenv import load_dotenv
load_dotenv()

"""
EchoMind Backend - Main Application
Reddit Marketing Intelligence Platform
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import os
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="EchoMind API",
    description="Reddit Marketing Intelligence & Automation Platform",
    version="1.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
try:
    from client_onboarding_router import router as onboarding_router
    app.include_router(onboarding_router)
    logger.info("✅ Client onboarding router loaded")
except Exception as e:
    logger.error(f"❌ Failed to load onboarding router: {e}")

try:
    from metrics_router import router as metrics_router
    app.include_router(metrics_router)
    logger.info("✅ Metrics router loaded")
except Exception as e:
    logger.error(f"❌ Failed to load metrics router: {e}")


@app.get("/")
async def root():
    """Root endpoint - API health check"""
    return {
        "service": "EchoMind API",
        "status": "operational",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/system/status")
async def system_status():
    """System status endpoint"""
    env_check = {
        "SUPABASE_URL": bool(os.getenv("SUPABASE_URL")),
        "SUPABASE_KEY": bool(os.getenv("SUPABASE_KEY")),
        "OPENAI_API_KEY": bool(os.getenv("OPENAI_API_KEY")),
        "REDDIT_CLIENT_ID": bool(os.getenv("REDDIT_CLIENT_ID")),
        "REDDIT_CLIENT_SECRET": bool(os.getenv("REDDIT_CLIENT_SECRET"))
    }
    
    return {
        "status": "operational",
        "timestamp": datetime.utcnow().isoformat(),
        "environment_variables": env_check,
        "all_critical_configured": all([
            env_check["SUPABASE_URL"],
            env_check["SUPABASE_KEY"],
            env_check["OPENAI_API_KEY"]
        ])
    }
@app.get("/api/system/env-check")
async def env_check():
    """Check what environment variables are actually loaded"""
    import os
    all_env = dict(os.environ)
    
    # Filter to show only our keys
    relevant = {k: v[:20] + "..." if len(v) > 20 else v 
                for k, v in all_env.items() 
                if any(keyword in k for keyword in ['SUPABASE', 'OPENAI', 'REDDIT', 'GOOGLE'])}
    
    return {
        "found_variables": relevant,
        "total_env_vars": len(all_env)
    }

@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info("🚀 EchoMind Backend Starting...")
    logger.info("=" * 60)
    
    # Check critical environment variables
    required = ["SUPABASE_URL", "SUPABASE_KEY", "OPENAI_API_KEY"]
    for var in required:
        if os.getenv(var):
            logger.info(f"✅ {var}: Configured")
        else:
            logger.warning(f"⚠️  {var}: NOT CONFIGURED")
    
    logger.info("=" * 60)
    logger.info("✅ EchoMind Backend Ready")
    logger.info("=" * 60)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
