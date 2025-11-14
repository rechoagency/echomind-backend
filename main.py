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
from typing import Optional

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


# ============================================================================
# WORKER ENDPOINTS
# ============================================================================

@app.post("/api/workers/run-full-pipeline")
async def run_full_pipeline(client_id: Optional[str] = None, force_regenerate: bool = False):
    """
    Run complete intelligence pipeline:
    1. Score opportunities (commercial intent)
    2. Match products (vector search)
    3. Generate content (GPT with products)
    4. Apply voice profiles
    
    Query params:
    - client_id: Optional UUID to filter specific client
    - force_regenerate: Force regeneration even if already processed
    """
    try:
        from workers.scheduler import WorkerScheduler
        
        scheduler = WorkerScheduler()
        result = scheduler.run_full_pipeline(client_id, force_regenerate)
        
        return {
            "success": True,
            "pipeline_result": result
        }
    except Exception as e:
        logger.error(f"Error running full pipeline: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/workers/run-incremental")
async def run_incremental_update(client_id: Optional[str] = None):
    """
    Process only new opportunities (incremental update)
    More efficient than full pipeline when adding new data
    """
    try:
        from workers.scheduler import WorkerScheduler
        
        scheduler = WorkerScheduler()
        result = scheduler.process_new_opportunities_incremental(client_id)
        
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        logger.error(f"Error running incremental update: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/workers/score-opportunities")
async def score_opportunities(client_id: Optional[str] = None):
    """
    Run only opportunity scoring worker
    Calculates commercial intent scores
    """
    try:
        from workers.opportunity_scoring_worker import OpportunityScoringWorker
        
        worker = OpportunityScoringWorker()
        result = worker.process_all_opportunities(client_id)
        
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        logger.error(f"Error scoring opportunities: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/workers/matchback-products")
async def matchback_products(client_id: Optional[str] = None, force_rematch: bool = False):
    """
    Run only product matchback worker
    Performs vector similarity search
    """
    try:
        from workers.product_matchback_worker import ProductMatchbackWorker
        
        worker = ProductMatchbackWorker()
        result = worker.process_all_opportunities(client_id, force_rematch)
        
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        logger.error(f"Error matching products: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/workers/generate-content")
async def generate_content(
    client_id: Optional[str] = None,
    regenerate: bool = False,
    only_with_products: bool = True
):
    """
    Run only content generation worker
    Creates Reddit responses with GPT-4
    """
    try:
        from workers.content_generation_worker import ContentGenerationWorker
        
        worker = ContentGenerationWorker()
        result = worker.process_all_opportunities(client_id, regenerate, only_with_products)
        
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        logger.error(f"Error generating content: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/workers/apply-voice")
async def apply_voice(client_id: Optional[str] = None, reapply: bool = False):
    """
    Run only voice application worker
    Applies subreddit voice formatting to content
    """
    try:
        from workers.voice_application_worker import VoiceApplicationWorker
        
        worker = VoiceApplicationWorker()
        result = worker.process_all_content(client_id, reapply)
        
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        logger.error(f"Error applying voice: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/workers/regenerate-client/{client_id}")
async def regenerate_client_content(client_id: str):
    """
    Regenerate all content for a specific client
    Useful after updating documents or voice profiles
    """
    try:
        from workers.scheduler import WorkerScheduler
        
        scheduler = WorkerScheduler()
        result = scheduler.regenerate_content_for_client(client_id)
        
        return {
            "success": True,
            "result": result
        }
    except Exception as e:
        logger.error(f"Error regenerating client content: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/workers/status")
async def worker_status():
    """
    Check status of worker system and recent pipeline runs
    """
    try:
        from supabase import create_client
        
        supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
        
        # Count opportunities by status
        total_opps = supabase.table("opportunities").select("id", count="exact").execute()
        scored_opps = supabase.table("opportunities").select("id", count="exact").not_.is_("opportunity_score", "null").execute()
        matched_opps = supabase.table("opportunities").select("id", count="exact").not_.is_("product_matches", "null").execute()
        
        # Count generated content
        total_content = supabase.table("generated_content").select("id", count="exact").execute()
        with_products = supabase.table("generated_content").select("id", count="exact").eq("has_product_mention", True).execute()
        voice_applied = supabase.table("generated_content").select("id", count="exact").eq("voice_applied", True).execute()
        
        return {
            "status": "operational",
            "timestamp": datetime.utcnow().isoformat(),
            "opportunities": {
                "total": len(total_opps.data) if total_opps.data else 0,
                "scored": len(scored_opps.data) if scored_opps.data else 0,
                "with_product_matches": len(matched_opps.data) if matched_opps.data else 0,
                "pending_scoring": len(total_opps.data) - len(scored_opps.data) if total_opps.data and scored_opps.data else 0
            },
            "content": {
                "total_generated": len(total_content.data) if total_content.data else 0,
                "with_product_mentions": len(with_products.data) if with_products.data else 0,
                "voice_applied": len(voice_applied.data) if voice_applied.data else 0
            },
            "workers_available": {
                "opportunity_scoring": True,
                "product_matchback": True,
                "content_generation": True,
                "voice_application": True,
                "scheduler": True
            }
        }
    except Exception as e:
        logger.error(f"Error checking worker status: {str(e)}")
        return {
            "status": "error",
            "error": str(e)
        }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
