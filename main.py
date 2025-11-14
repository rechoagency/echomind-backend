from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from dotenv import load_dotenv
import os
from contextlib import asynccontextmanager
from datetime import datetime

# Load environment variables from .env file
load_dotenv()

# Import routers
from routers.client_onboarding_router import router as onboarding_router
from routers.metrics_router import router as metrics_router

# Lazy-loaded Supabase client
_supabase_client = None

def get_supabase() -> Client:
    """Lazy-load Supabase client to avoid initialization issues"""
    global _supabase_client
    if _supabase_client is None:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            raise ValueError("Missing Supabase credentials in environment variables")
        
        _supabase_client = create_client(supabase_url, supabase_key)
    
    return _supabase_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events"""
    # Startup
    print("🚀 EchoMind Backend Starting...")
    print(f"✅ Environment loaded: {os.getenv('SUPABASE_URL')[:20]}...")
    
    # Initialize Supabase connection
    try:
        supabase = get_supabase()
        print("✅ Supabase connection established")
    except Exception as e:
        print(f"⚠️ Supabase initialization warning: {e}")
    
    yield
    
    # Shutdown
    print("👋 EchoMind Backend Shutting Down...")

# Initialize FastAPI app
app = FastAPI(
    title="EchoMind API",
    description="Reddit Marketing Automation with Intelligence",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(onboarding_router, prefix="/api/onboarding", tags=["Client Onboarding"])
app.include_router(metrics_router, prefix="/api/metrics", tags=["Metrics & Analytics"])

# Health check endpoint
@app.get("/")
async def root():
    """Root endpoint - health check"""
    return {
        "status": "online",
        "service": "EchoMind Backend",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/health")
async def health_check():
    """Detailed health check with system status"""
    try:
        supabase = get_supabase()
        
        # Test database connection
        response = supabase.table("clients").select("client_id").limit(1).execute()
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {
        "status": "healthy",
        "database": db_status,
        "timestamp": datetime.utcnow().isoformat(),
        "environment": {
            "supabase_configured": bool(os.getenv("SUPABASE_URL")),
            "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
            "reddit_configured": bool(os.getenv("REDDIT_CLIENT_ID"))
        }
    }

@app.get("/api/system/status")
async def system_status(supabase: Client = Depends(get_supabase)):
    """Get comprehensive system status including table counts"""
    try:
        # Get counts from key tables
        clients_response = supabase.table("clients").select("client_id", count="exact").execute()
        opportunities_response = supabase.table("opportunities").select("opportunity_id", count="exact").execute()
        content_response = supabase.table("generated_content").select("content_id", count="exact").execute()
        
        # Get document-related counts
        uploads_response = supabase.table("document_uploads").select("upload_id", count="exact").execute()
        chunks_response = supabase.table("document_chunks").select("chunk_id", count="exact").execute()
        
        return {
            "status": "operational",
            "timestamp": datetime.utcnow().isoformat(),
            "database": {
                "clients": clients_response.count,
                "opportunities": opportunities_response.count,
                "generated_content": content_response.count,
                "document_uploads": uploads_response.count,
                "document_chunks": chunks_response.count
            },
            "services": {
                "document_ingestion": "active",
                "opportunity_scoring": "active",
                "product_matchback": "active",
                "content_generation": "active"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"System status check failed: {str(e)}")

# Worker Management Endpoints

@app.post("/api/workers/score-opportunities")
async def trigger_opportunity_scoring(supabase: Client = Depends(get_supabase)):
    """Trigger opportunity scoring worker"""
    try:
        from workers.opportunity_scoring_worker import OpportunityScoringWorker
        
        worker = OpportunityScoringWorker(supabase)
        results = worker.process_opportunities()
        
        return {
            "status": "completed",
            "worker": "opportunity_scoring",
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Opportunity scoring failed: {str(e)}")

@app.post("/api/workers/product-matchback")
async def trigger_product_matchback(supabase: Client = Depends(get_supabase)):
    """Trigger product matchback worker"""
    try:
        from workers.product_matchback_worker import ProductMatchbackWorker
        
        worker = ProductMatchbackWorker(supabase)
        results = worker.process_matchback()
        
        return {
            "status": "completed",
            "worker": "product_matchback",
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Product matchback failed: {str(e)}")

@app.post("/api/workers/generate-content")
async def trigger_content_generation(supabase: Client = Depends(get_supabase)):
    """Trigger content generation worker"""
    try:
        from workers.content_generation_worker import ContentGenerationWorker
        
        worker = ContentGenerationWorker(supabase)
        results = worker.generate_content()
        
        return {
            "status": "completed",
            "worker": "content_generation",
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Content generation failed: {str(e)}")

@app.post("/api/workers/apply-voice")
async def trigger_voice_application(supabase: Client = Depends(get_supabase)):
    """Trigger voice application worker"""
    try:
        from workers.voice_application_worker import VoiceApplicationWorker
        
        worker = VoiceApplicationWorker(supabase)
        results = worker.apply_voice_profiles()
        
        return {
            "status": "completed",
            "worker": "voice_application",
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Voice application failed: {str(e)}")

@app.post("/api/workers/run-all")
async def trigger_all_workers(supabase: Client = Depends(get_supabase)):
    """Trigger complete worker pipeline"""
    try:
        from workers.scheduler import WorkerScheduler
        
        scheduler = WorkerScheduler(supabase)
        results = scheduler.run_full_pipeline()
        
        return {
            "status": "completed",
            "pipeline": "full",
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline execution failed: {str(e)}")

@app.get("/api/workers/status")
async def worker_status(supabase: Client = Depends(get_supabase)):
    """Get current worker processing status"""
    try:
        # Get opportunities with scoring status
        opportunities_query = supabase.table("opportunities").select(
            "opportunity_id, subreddit_score, thread_score, user_score, combined_score, product_matches"
        ).execute()
        
        opportunities = opportunities_query.data
        total_opportunities = len(opportunities)
        
        # Count scored opportunities (those with combined_score)
        scored_opportunities = sum(1 for opp in opportunities if opp.get('combined_score') is not None)
        
        # Count opportunities with product matches
        matched_opportunities = sum(1 for opp in opportunities if opp.get('product_matches') is not None)
        
        # Get generated content count
        content_query = supabase.table("generated_content").select("content_id", count="exact").execute()
        generated_content = content_query.count
        
        # Get voice profiles count
        voice_query = supabase.table("voice_profiles").select("profile_id", count="exact").execute()
        voice_profiles = voice_query.count
        
        # Get document chunks count
        chunks_query = supabase.table("document_chunks").select("chunk_id", count="exact").execute()
        document_chunks = chunks_query.count
        
        return {
            "status": "active",
            "timestamp": datetime.utcnow().isoformat(),
            "opportunities": {
                "total": total_opportunities,
                "scored": scored_opportunities,
                "with_product_matches": matched_opportunities,
                "scoring_completion_rate": f"{(scored_opportunities/total_opportunities*100):.1f}%" if total_opportunities > 0 else "0%"
            },
            "content": {
                "generated_pieces": generated_content
            },
            "voice": {
                "profiles_analyzed": voice_profiles
            },
            "documents": {
                "chunks_indexed": document_chunks
            },
            "workers": {
                "opportunity_scoring": "ready",
                "product_matchback": "ready" if document_chunks > 0 else "waiting_for_documents",
                "content_generation": "ready",
                "voice_application": "ready" if voice_profiles > 0 else "ready"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Worker status check failed: {str(e)}")

# Document Management Endpoint
@app.get("/api/documents/status")
async def document_status(supabase: Client = Depends(get_supabase)):
    """Get document processing status"""
    try:
        # Get document uploads
        uploads_response = supabase.table("document_uploads").select(
            "upload_id, client_id, file_name, file_type, processing_status, created_at"
        ).execute()
        
        # Get chunks count
        chunks_response = supabase.table("document_chunks").select("chunk_id", count="exact").execute()
        
        # Get embeddings count
        embeddings_response = supabase.table("vector_embeddings").select("embedding_id", count="exact").execute()
        
        return {
            "status": "operational",
            "timestamp": datetime.utcnow().isoformat(),
            "uploads": {
                "total": len(uploads_response.data),
                "files": uploads_response.data
            },
            "processing": {
                "chunks_created": chunks_response.count,
                "embeddings_generated": embeddings_response.count
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document status check failed: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
