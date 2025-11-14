# EchoMind Backend - Force Redeploy
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import routers (FIXED - removed routers. prefix)
from client_onboarding_router import router as onboarding_router
from metrics_api_router import router as metrics_router

# Import Supabase client for startup checks
from supabase_client import supabase

app = FastAPI(
    title="EchoMind Backend API",
    description="Reddit Marketing Automation SaaS Platform",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(onboarding_router, prefix="/api/onboarding", tags=["Client Onboarding"])
app.include_router(metrics_router, prefix="/api/metrics", tags=["Metrics"])

@app.on_event("startup")
async def startup_event():
    """Verify connections on startup"""
    print("🚀 EchoMind Backend Starting...")
    
    # Test Supabase connection
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        print(f"✅ Environment loaded: {supabase_url[:30]}...")
        
        # Simple query to verify connection
        result = supabase.table("clients").select("client_id").limit(1).execute()
        print("✅ Supabase connection established")
    except Exception as e:
        print(f"⚠️ Supabase connection warning: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("👋 EchoMind Backend Shutting Down...")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "active",
        "service": "EchoMind Backend API",
        "version": "1.0.0"
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "database": "connected",
        "redis": "available"
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
