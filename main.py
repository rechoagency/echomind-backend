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

# Import routers
from client_onboarding_router import router as onboarding_router
from metrics_router import router as metrics_router

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
    allow_origins=["*"],  # Configure this properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(onboarding_router)
app.include_router(metrics_router)

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": "Internal server error",
            "detail": str(exc)
        }
    )


@app.get("/")
async def root():
    """
    Root endpoint - API health check
    """
    return {
        "service": "EchoMind API",
        "status": "operational",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint for monitoring
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "echomind-backend"
    }


@app.get("/api/system/status")
async def system_status():
    """
    System status endpoint - Check API credentials and service availability
    """
    status = {
        "timestamp": datetime.utcnow().isoformat(),
        "services": {},
        "api_credentials": {}
    }
    
    # Check environment variables
    env_vars = {
        "SUPABASE_URL": os.getenv("SUPABASE_URL"),
        "SUPABASE_SERVICE_KEY": os.getenv("SUPABASE_SERVICE_KEY"),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "REDDIT_CLIENT_ID": os.getenv("REDDIT_CLIENT_ID"),
        "REDDIT_CLIENT_SECRET": os.getenv("REDDIT_CLIENT_SECRET"),
        "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_CLIENT_ID"),
        "GOOGLE_CLIENT_SECRET": os.getenv("GOOGLE_CLIENT_SECRET"),
        "GOOGLE_REDIRECT_URI": os.getenv("GOOGLE_REDIRECT_URI")
    }
    
    # Check which credentials are configured
    for key, value in env_vars.items():
        status["api_credentials"][key] = {
            "configured": value is not None and len(value) > 0,
            "length": len(value) if value else 0
        }
    
    # Check document service availability
    try:
        from services.document_ingestion_service import DocumentIngestionService
        status["services"]["document_ingestion"] = {
            "available": True,
            "status": "operational"
        }
    except ImportError as e:
        status["services"]["document_ingestion"] = {
            "available": False,
            "error": str(e)
        }
    
    # Overall health
    all_critical_configured = all([
        env_vars["SUPABASE_URL"],
        env_vars["SUPABASE_SERVICE_KEY"],
        env_vars["OPENAI_API_KEY"]
    ])
    
    status["overall_status"] = "healthy" if all_critical_configured else "degraded"
    status["critical_services_ready"] = all_critical_configured
    
    return status


@app.get("/api/system/info")
async def system_info():
    """
    System information endpoint
    """
    return {
        "service": "EchoMind Backend",
        "version": "1.0.0",
        "features": {
            "client_onboarding": True,
            "document_ingestion": True,
            "metrics_tracking": True,
            "reddit_monitoring": True,
            "content_generation": True,
            "voice_analytics": True
        },
        "endpoints": {
            "onboarding": "/api/client-onboarding/*",
            "metrics": "/api/metrics/*",
            "system": "/api/system/*"
        }
    }


# Startup event
@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info("EchoMind Backend Starting...")
    logger.info("=" * 60)
    
    # Log environment check
    required_vars = ["SUPABASE_URL", "SUPABASE_SERVICE_KEY", "OPENAI_API_KEY"]
    for var in required_vars:
        value = os.getenv(var)
        if value:
            logger.info(f"✅ {var}: Configured ({len(value)} chars)")
        else:
            logger.warning(f"⚠️  {var}: NOT CONFIGURED")
    
    logger.info("=" * 60)
    logger.info("🚀 EchoMind Backend Ready")
    logger.info("=" * 60)


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("EchoMind Backend Shutting Down...")


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
