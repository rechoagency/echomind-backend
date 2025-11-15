"""
Client Onboarding Router - COMPLETE SYSTEM
Handles ALL 20+ fields with full orchestration:
- File uploads with automatic processing
- Triggers document ingestion → vectorization → matchback
- AUTO_IDENTIFY subreddit/keyword discovery
- Content calendar generation
- Email notifications
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import os
import json
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/client-onboarding", tags=["Client Onboarding"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

supabase = None
document_service = None
onboarding_orchestrator = None

def get_supabase():
    global supabase
    if supabase is None:
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
    return supabase

def get_document_service():
    global document_service
    if document_service is None:
        from services.document_ingestion_service import create_document_service
        document_service = create_document_service(SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY)
    return document_service

def get_orchestrator():
    global onboarding_orchestrator
    if onboarding_orchestrator is None:
        from services.onboarding_orchestrator import OnboardingOrchestrator
        onboarding_orchestrator = OnboardingOrchestrator(get_supabase(), OPENAI_API_KEY)
    return onboarding_orchestrator


@router.post("/onboard")
async def onboard_client(request: dict, background_tasks: BackgroundTasks):
    """
    Complete client onboarding with background processing
    Saves all data, then triggers orchestration in background
    """
    try:
        logger.info(f"🚀 Onboarding new client: {request.get('company_name')}")
        supabase = get_supabase()
        
        # Build complete client record with ALL fields
        client_data = {
            # Company basics
            "company_name": request.get("company_name"),
            "industry": request.get("industry"),
            "website_url": request.get("website_url"),
            "products": request.get("products", []),
            
            # Target configuration
            "target_subreddits": request.get("target_subreddits", []),
            "target_keywords": request.get("target_keywords", []),
            "excluded_keywords": request.get("excluded_keywords", []),
            
            # Brand ownership
            "brand_owns_subreddit": request.get("brand_owns_subreddit", False),
            "brand_owned_subreddits": request.get("brand_owned_subreddits", []),
            
            # Content strategy
            "posting_frequency": request.get("posting_frequency"),
            "monthly_opportunity_budget": request.get("monthly_opportunity_budget"),
            "content_tone": request.get("content_tone"),
            "brand_voice_guidelines": request.get("brand_voice_guidelines"),
            
            # Contact information
            "notification_email": request.get("notification_email"),
            "contact_email": request.get("notification_email"),
            "primary_contact_email": request.get("primary_contact_email") or request.get("notification_email"),
            "primary_contact_name": request.get("primary_contact_name"),
            "slack_webhook_url": request.get("slack_webhook_url"),
            
            # Subscription & billing
            "subscription_tier": request.get("subscription_tier", "professional"),
            "subscription_status": request.get("subscription_status", "active"),
            "monthly_price_usd": request.get("monthly_price_usd", 2000),
            
            # Status tracking
            "onboarding_status": "processing",  # Will be updated by orchestrator
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"📝 Inserting client with {len(client_data)} fields")
        client_result = supabase.table("clients").insert(client_data).execute()
        
        if not client_result.data:
            raise HTTPException(status_code=500, detail="Failed to create client record")
        
        client_id = client_result.data[0]["client_id"]
        logger.info(f"✅ Client created: {client_id}")
        
        # Configure subreddit monitoring (if not AUTO_IDENTIFY)
        target_subreddits = request.get("target_subreddits", [])
        if target_subreddits and target_subreddits != ["AUTO_IDENTIFY"]:
            subreddit_configs = [
                {
                    "client_id": client_id, 
                    "subreddit_name": s.lower().replace("r/", ""), 
                    "is_active": True,
                    "created_at": datetime.utcnow().isoformat()
                } 
                for s in target_subreddits if s != "AUTO_IDENTIFY"
            ]
            if subreddit_configs:
                supabase.table("client_subreddit_config").insert(subreddit_configs).execute()
                logger.info(f"✅ Configured {len(subreddit_configs)} subreddits")
        
        # Configure keyword monitoring (if not AUTO_IDENTIFY)
        target_keywords = request.get("target_keywords", [])
        if target_keywords and target_keywords != ["AUTO_IDENTIFY"]:
            keyword_configs = [
                {
                    "client_id": client_id, 
                    "keyword": k, 
                    "is_active": True,
                    "created_at": datetime.utcnow().isoformat()
                } 
                for k in target_keywords if k != "AUTO_IDENTIFY"
            ]
            if keyword_configs:
                supabase.table("client_keyword_config").insert(keyword_configs).execute()
                logger.info(f"✅ Configured {len(keyword_configs)} keywords")
        
        # Store Reddit profiles
        reddit_profiles = request.get("reddit_user_profiles", [])
        if reddit_profiles:
            profile_records = [
                {
                    "client_id": client_id, 
                    "username": p["username"], 
                    "profile_type": p["profile_type"], 
                    "target_subreddits": p.get("target_subreddits", []),
                    "is_active": True,
                    "created_at": datetime.utcnow().isoformat()
                } 
                for p in reddit_profiles if p.get("username")
            ]
            if profile_records:
                supabase.table("client_reddit_profiles").insert(profile_records).execute()
                logger.info(f"✅ Stored {len(profile_records)} Reddit profiles")
        
        # Schedule background orchestration (AUTO_IDENTIFY, scoring, calendar, etc.)
        background_tasks.add_task(run_onboarding_orchestration, client_id)
        
        logger.info(f"🎉 Onboarding complete for {request.get('company_name')}, orchestration scheduled")
        
        return JSONResponse(content={
            "success": True,
            "client_id": client_id,
            "message": f"Client {request.get('company_name')} onboarded successfully",
            "redirect_url": f"/dashboard?client_id={client_id}",
            "configuration": {
                "subreddits": len(target_subreddits) if target_subreddits != ["AUTO_IDENTIFY"] else "AUTO_IDENTIFY",
                "keywords": len(target_keywords) if target_keywords != ["AUTO_IDENTIFY"] else "AUTO_IDENTIFY",
                "reddit_profiles": len(reddit_profiles),
                "monitoring_status": "processing"
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Onboarding error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-files")
async def upload_files(files: List[UploadFile] = File(...), client_id: str = Form(...)):
    """
    Upload files and trigger processing pipeline
    Called by frontend after onboarding completes
    """
    try:
        document_service = get_document_service()
        supabase = get_supabase()
        
        logger.info(f"📄 Processing {len(files)} files for client {client_id}")
        
        # Verify client exists
        client_check = supabase.table("clients").select("client_id").eq("client_id", client_id).execute()
        if not client_check.data:
            raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
        
        results = []
        
        for file in files:
            logger.info(f"📄 Processing file: {file.filename}")
            
            # Read file content
            file_content = await file.read()
            
            # Process document: Upload → Chunk → Vectorize
            result = document_service.process_document(
                client_id=client_id,
                file_content=file_content,
                filename=file.filename,
                file_type=file.content_type or "application/octet-stream",
                document_type="product_feed"
            )
            
            results.append(result)
            
            if result.get("success"):
                logger.info(f"✅ File processed: {file.filename}")
                logger.info(f"   - Chunks: {result.get('chunks_created', 0)}")
                logger.info(f"   - Vectors: {result.get('vectors_created', 0)}")
        
        successful = sum(1 for r in results if r.get("success"))
        failed = len(results) - successful
        
        # Trigger product matchback if files were successful
        if successful > 0:
            logger.info(f"🔄 Triggering product matchback...")
            try:
                from workers.product_matchback_worker import matchback_all_opportunities
                matchback_result = matchback_all_opportunities(client_id=client_id)
                logger.info(f"✅ Matchback complete: {matchback_result.get('matched', 0)} opportunities matched")
            except Exception as e:
                logger.error(f"Matchback error: {str(e)}")
        
        return JSONResponse(content={
            "success": True,
            "client_id": client_id,
            "total_files": len(files),
            "successful": successful,
            "failed": failed,
            "results": results
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error uploading files: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/client/{client_id}/configuration")
async def get_client_configuration(client_id: str):
    """Get complete client configuration"""
    try:
        supabase = get_supabase()
        
        client = supabase.table("clients").select("*").eq("client_id", client_id).execute()
        if not client.data:
            raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
        
        subreddits = supabase.table("client_subreddit_config").select("*").eq("client_id", client_id).execute()
        keywords = supabase.table("client_keyword_config").select("*").eq("client_id", client_id).execute()
        profiles = supabase.table("client_reddit_profiles").select("*").eq("client_id", client_id).execute()
        documents = supabase.table("document_uploads").select("*").eq("client_id", client_id).execute()
        
        return {
            "success": True,
            "client": client.data[0],
            "subreddits": subreddits.data,
            "keywords": keywords.data,
            "reddit_profiles": profiles.data,
            "documents": documents.data,
            "document_count": len(documents.data) if documents.data else 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


async def run_onboarding_orchestration(client_id: str):
    """Background task: Run complete onboarding orchestration"""
    try:
        logger.info(f"🎯 Starting orchestration for client {client_id}")
        orchestrator = get_orchestrator()
        result = await orchestrator.process_client_onboarding(client_id)
        logger.info(f"✅ Orchestration complete: {result}")
    except Exception as e:
        logger.error(f"❌ Orchestration error: {str(e)}")
