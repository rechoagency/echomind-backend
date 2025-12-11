"""
EchoMind Backend - Enhanced with Environment Validation
"""
import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

# Import environment validator FIRST
from utils.env_validator import EnvironmentValidator

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global scheduler
scheduler = AsyncIOScheduler(timezone=pytz.timezone('US/Eastern'))

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    
    # ========================================
    # STEP 1: VALIDATE ENVIRONMENT VARIABLES
    # ========================================
    logger.info("=" * 80)
    logger.info("🚀 EchoMind Backend Starting...")
    logger.info("=" * 80)
    
    try:
        # Validate environment - will exit if critical vars missing
        logger.info("\n🔍 Validating environment variables...")
        validation_report = EnvironmentValidator.get_validation_report()
        print(validation_report)
        
        is_valid, results = EnvironmentValidator.validate_all()
        
        if not is_valid:
            logger.critical("❌ CANNOT START: Missing critical environment variables")
            logger.critical("👉 Add missing variables to Railway and redeploy")
            raise SystemExit(1)
        
        logger.info("✅ Environment validation passed")
        
    except Exception as e:
        logger.critical(f"❌ Environment validation failed: {str(e)}")
        raise
    
    # ========================================
    # STEP 2: INITIALIZE SERVICES
    # ========================================
    logger.info("\n🔧 Initializing services...")
    
    try:
        # Test enhanced services
        from services.email_service_enhanced import email_service
        from services.reddit_pro_service import reddit_pro_service
        
        # Validate email service
        email_config = email_service.validate_configuration()
        if not email_config["enabled"]:
            logger.warning("⚠️ Email service not configured - emails will NOT be sent")
            for issue in email_config["issues"]:
                logger.warning(f"   {issue['severity']}: {issue['issue']}")
        
        # Check Reddit Pro
        if not reddit_pro_service.enabled:
            logger.info("ℹ️ Reddit Pro not configured - using standard Reddit API")
        
        logger.info("✅ Services initialized")
        
    except Exception as e:
        logger.error(f"⚠️ Service initialization warning: {str(e)}")
        # Continue startup even if optional services fail
    
    # ========================================
    # STEP 3: SCHEDULE WORKERS
    # ========================================
    logger.info("\n📅 Scheduling background workers...")
    
    try:
        # Import workers
        from workers import (
            weekly_report_generator,
            brand_mention_monitor,
            auto_reply_generator
        )
        
        # Schedule weekly reports (Monday & Thursday, 7am EST)
        if weekly_report_generator:
            scheduler.add_job(
                weekly_report_generator.generate_all_weekly_reports,
                trigger=CronTrigger(
                    day_of_week='mon,thu',
                    hour=7,
                    minute=0,
                    timezone=pytz.timezone('US/Eastern')
                ),
                id='weekly_reports',
                name='Weekly Reports: Monday & Thursday at 7am EST',
                replace_existing=True
            )
            logger.info("✅ Scheduled: Weekly reports (Mon/Thu 7am EST)")
        
        # Schedule brand mention monitoring (Daily, 9am EST)
        if brand_mention_monitor:
            scheduler.add_job(
                brand_mention_monitor.monitor_all_clients,
                trigger=CronTrigger(
                    hour=9,
                    minute=0,
                    timezone=pytz.timezone('US/Eastern')
                ),
                id='brand_mentions',
                name='Brand Mention Monitor: Daily at 9am EST',
                replace_existing=True
            )
            logger.info("✅ Scheduled: Brand mentions (Daily 9am EST)")
        
        # Schedule auto-reply generation (Every 6 hours)
        if auto_reply_generator:
            scheduler.add_job(
                auto_reply_generator.generate_all_auto_replies,
                trigger=CronTrigger(
                    hour='*/6',
                    timezone=pytz.timezone('UTC')
                ),
                id='auto_replies',
                name='Auto-Reply Generator: Every 6 hours',
                replace_existing=True
            )
            logger.info("✅ Scheduled: Auto-replies (Every 6 hours)")

        # Schedule opportunity scoring (Daily, 10am EST - after Reddit scan at 9am)
        from workers.opportunity_scoring_worker import score_all_opportunities
        scheduler.add_job(
            score_all_opportunities,
            trigger=CronTrigger(
                hour=10,
                minute=0,
                timezone=pytz.timezone('US/Eastern')
            ),
            id='opportunity_scoring',
            name='Opportunity Scoring: Daily at 10am EST',
            replace_existing=True
        )
        logger.info("✅ Scheduled: Opportunity scoring (Daily 10am EST)")

        # Schedule monthly voice database refresh (1st of month at midnight UTC)
        async def refresh_all_voice_profiles():
            """Refresh voice profiles for all active clients"""
            try:
                from workers.voice_database_worker import build_client_voice_database
                from supabase_client import get_supabase_client

                supabase = get_supabase_client()
                clients = supabase.table("clients")\
                    .select("client_id, company_name")\
                    .eq("subscription_status", "active")\
                    .execute()

                logger.info(f"🎤 Monthly voice refresh: Processing {len(clients.data or [])} clients")

                for client in (clients.data or []):
                    try:
                        logger.info(f"  Building voice DB for {client['company_name']}")
                        await build_client_voice_database(client['client_id'])
                    except Exception as e:
                        logger.error(f"  Voice refresh failed for {client['client_id']}: {e}")

                logger.info("✅ Monthly voice refresh complete")
            except Exception as e:
                logger.error(f"Monthly voice refresh failed: {e}")

        scheduler.add_job(
            refresh_all_voice_profiles,
            trigger=CronTrigger(
                day='1',
                hour=0,
                minute=0,
                timezone=pytz.timezone('UTC')
            ),
            id='monthly_voice_refresh',
            name='Monthly Voice Database Refresh: 1st of month at midnight UTC',
            replace_existing=True
        )
        logger.info("✅ Scheduled: Monthly voice refresh (1st of month)")

        # Start scheduler
        scheduler.start()
        logger.info("✅ Background worker scheduler started")

    except Exception as e:
        logger.error(f"❌ Worker scheduling failed: {str(e)}")
        logger.error("   Workers will not run automatically")
        # Continue startup - workers are important but not critical
    
    logger.info("\n" + "=" * 80)
    logger.info("✅ EchoMind Backend Ready")
    logger.info("=" * 80)
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down scheduler...")
    scheduler.shutdown()
    logger.info("✅ Shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="EchoMind Backend",
    description="Social listening and content generation for Reddit",
    version="2.3.1",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================================
# HEALTH CHECK ENDPOINT
# ========================================
@app.get("/health")
async def health_check():
    """Enhanced health check with environment validation"""
    try:
        from supabase_client import supabase
        
        # Check database
        db_status = "disconnected"
        try:
            response = supabase.table("clients").select("client_id").limit(1).execute()
            db_status = "connected"
        except Exception as e:
            logger.error(f"Database health check failed: {str(e)}")
        
        # Check environment variables
        is_valid, env_results = EnvironmentValidator.validate_all()
        
        # Check services (safely)
        email_enabled = False
        reddit_pro_enabled = False
        try:
            from services.email_service_enhanced import email_service
            email_enabled = email_service.enabled
        except Exception as e:
            logger.error(f"Email service check failed: {str(e)}")
        
        try:
            from services.reddit_pro_service import reddit_pro_service
            reddit_pro_enabled = reddit_pro_service.enabled
        except Exception as e:
            logger.error(f"Reddit Pro service check failed: {str(e)}")
        
        return {
            "status": "healthy" if db_status == "connected" and is_valid else "degraded",
            "database": db_status,
            "version": "2.3.0",
            "environment": {
                "valid": is_valid,
                "missing_critical": len(env_results["missing"]),
                "missing_optional": len(env_results["optional_missing"])
            },
            "services": {
                "email": email_enabled,
                "reddit_pro": reddit_pro_enabled
            },
            "scheduler": {
                "running": scheduler.running,
                "jobs": len(scheduler.get_jobs())
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "version": "2.3.0"
        }

# ========================================
# DIAGNOSTIC ENDPOINTS
# ========================================
@app.get("/diagnostics/env")
async def get_env_diagnostics():
    """Get environment variable diagnostics"""
    is_valid, results = EnvironmentValidator.validate_all()
    
    return {
        "valid": is_valid,
        "present": results["present"],
        "missing": results["missing"],
        "optional_missing": results["optional_missing"],
        "warnings": results["warnings"]
    }

@app.get("/diagnostics/email")
async def get_email_diagnostics():
    """Get email service diagnostics"""
    try:
        from services.email_service_enhanced import email_service
        
        config = email_service.validate_configuration()
        setup = email_service.get_setup_instructions()
        
        return {
            "configuration": config,
            "setup_instructions": setup
        }
    except Exception as e:
        logger.error(f"Email diagnostics failed: {str(e)}")
        return {
            "error": str(e),
            "fix": "Check RESEND_API_KEY is set in Railway environment variables",
            "url": "https://resend.com/api-keys"
        }

@app.get("/diagnostics/reddit-pro")
async def get_reddit_pro_diagnostics():
    """Get Reddit Pro diagnostics"""
    from services.reddit_pro_service import reddit_pro_service
    
    return reddit_pro_service.get_setup_instructions()

# ========================================
# IMPORT ROUTERS
# ========================================
logger.info("📦 Loading routers...")

try:
    from client_onboarding_router import router as onboarding_router
    # Router already has /api/client-onboarding prefix, don't add it again
    app.include_router(onboarding_router, tags=["onboarding"])
    logger.info("✅ Loaded: Client Onboarding Router")
except Exception as e:
    logger.error(f"❌ Failed to load onboarding router: {str(e)}")

try:
    from routers.clients_router import router as clients_router
    app.include_router(clients_router, prefix="/api", tags=["clients"])
    logger.info("✅ Loaded: Clients Router")
except Exception as e:
    logger.error(f"❌ Failed to load clients router: {str(e)}")

try:
    from routers.reports_router import router as reports_router
    app.include_router(reports_router, prefix="/api", tags=["reports"])
    logger.info("✅ Loaded: Reports Router")
except Exception as e:
    logger.error(f"❌ Failed to load reports router: {str(e)}")

try:
    from metrics_api_router import router as metrics_router
    # Router already has /api/metrics prefix
    app.include_router(metrics_router, tags=["metrics"])
    logger.info("✅ Loaded: Metrics Router")
except Exception as e:
    logger.error(f"❌ Failed to load metrics router: {str(e)}")

try:
    from routers.dashboard_router import router as dashboard_router
    app.include_router(dashboard_router, prefix="/api", tags=["dashboard"])
    logger.info("✅ Loaded: Dashboard Router")
except Exception as e:
    logger.error(f"❌ Failed to load dashboard router: {str(e)}")

try:
    from routers.admin_router import router as admin_router
    # Router already has /api/admin prefix
    app.include_router(admin_router, tags=["admin"])
    logger.info("✅ Loaded: Admin Router")
except Exception as e:
    logger.error(f"❌ Failed to load admin router: {str(e)}")

try:
    from routers.documents_router import router as documents_router
    app.include_router(documents_router, prefix="/api", tags=["documents"])
    logger.info("✅ Loaded: Documents Router")
except Exception as e:
    logger.error(f"❌ Failed to load documents router: {str(e)}")

try:
    from routers.migration_router import router as migration_router
    app.include_router(migration_router, prefix="/api", tags=["migrations"])
    logger.info("✅ Loaded: Migration Router")
except Exception as e:
    logger.error(f"❌ Failed to load migration router: {str(e)}")

# Option B Router (Brand Monitoring, Workers)
try:
    from routers.option_b_router import router as option_b_router
    app.include_router(option_b_router, tags=["Option B Workers"])
    logger.info("✅ Loaded: Option B Router (Brand Monitoring)")
except Exception as e:
    logger.error(f"❌ Failed to load option_b router: {str(e)}")

# Client Settings Router (Strategy Controls: Reply%, Brand%, Product%)
try:
    from app.routers.client_settings_router_CORRECTED import router as client_settings_router
    app.include_router(client_settings_router, prefix="/api", tags=["client_settings"])
    logger.info("✅ Loaded: Client Settings Router (/api/client-settings)")
except Exception as e:
    logger.error(f"❌ Failed to load client_settings router: {str(e)}")

logger.info("✅ All routers loaded")

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "EchoMind Backend API",
        "version": "2.2.2",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "diagnostics": {
            "environment": "/diagnostics/env",
            "email": "/diagnostics/email",
            "reddit_pro": "/diagnostics/reddit-pro"
        },
        "main_endpoints": {
            "onboard_client": "POST /api/client-onboarding/onboard",
            "list_clients": "GET /api/clients",
            "client_reports": "GET /api/reports/{client_id}/weekly-content"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
