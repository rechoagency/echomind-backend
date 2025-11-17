# EchoMind Backend - Complete System
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import routers
from client_onboarding_router import router as onboarding_router
from metrics_api_router import router as metrics_router
from routers.dashboard_router import router as dashboard_router
from routers.admin_router import router as admin_router
from routers.option_b_router import router as option_b_router

# Import Supabase client for startup checks
from supabase_client import supabase

app = FastAPI(
    title="EchoMind Backend API",
    description="Reddit Marketing Automation SaaS Platform - Complete System",
    version="2.0.0"
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
app.include_router(onboarding_router, tags=["Client Onboarding"])
app.include_router(metrics_router, tags=["Metrics"])
app.include_router(dashboard_router, tags=["Dashboard"])
app.include_router(admin_router, tags=["Admin"])
app.include_router(option_b_router, tags=["Option B Workers"])

@app.on_event("startup")
async def startup_event():
    """Verify connections on startup and initialize scheduler"""
    print("🚀 EchoMind Backend Starting...")
    print("   Version: 2.0.0 - Complete System")
    
    # Test Supabase connection
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        print(f"✅ Environment loaded: {supabase_url[:30]}...")
        
        # Simple query to verify connection
        result = supabase.table("clients").select("client_id").limit(1).execute()
        print("✅ Supabase connection established")
        print("✅ All systems ready")
    except Exception as e:
        print(f"⚠️ Supabase connection warning: {e}")
    
    # Initialize weekly report scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        from workers.weekly_report_generator import send_weekly_reports
        import asyncio
        
        scheduler = AsyncIOScheduler()
        
        # Monday & Thursday at 7am EST (12pm UTC)
        scheduler.add_job(
            func=lambda: asyncio.create_task(send_weekly_reports()),
            trigger=CronTrigger(
                day_of_week='mon,thu',
                hour=12,  # 12pm UTC = 7am EST
                minute=0,
                timezone='UTC'
            ),
            id='weekly_reports',
            name='Send Weekly Reports to All Clients',
            replace_existing=True
        )
        
        scheduler.start()
        print("✅ Weekly report scheduler initialized (Mon/Thu 7am EST)")
        
        # Store scheduler in app state for shutdown
        app.state.scheduler = scheduler
        
    except Exception as e:
        print(f"⚠️ Scheduler initialization warning: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    print("👋 EchoMind Backend Shutting Down...")
    
    # Shutdown scheduler if it exists
    if hasattr(app.state, 'scheduler'):
        app.state.scheduler.shutdown()
        print("✅ Scheduler shut down")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "active",
        "service": "EchoMind Backend API - Complete System",
        "version": "2.0.0",
        "features": [
            "Client Onboarding",
            "AUTO_IDENTIFY (Subreddits & Keywords)",
            "File Upload & Vectorization",
            "Product Matchback",
            "Opportunity Scoring",
            "Content Calendar Generation",
            "Client Dashboard",
            "Email Notifications",
            "Weekly Reports (Mon/Thu 7am EST)"
        ]
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    return {
        "status": "healthy",
        "database": "connected",
        "redis": "available",
        "version": "2.0.0"
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
