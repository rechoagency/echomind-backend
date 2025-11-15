"""
Client Onboarding Router - COMPLETE REWRITE
Handles ALL 20+ fields from frontend with NO data loss
Maps to complete Supabase schema including client_reddit_profiles table
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import os
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/client-onboarding", tags=["Client Onboarding"])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

supabase = None
document_service = None

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


@router.post("/onboard")
async def onboard_client(request: dict):
    """
    Complete client onboarding - Maps ALL 20+ fields
    Frontend sends: company info, products, subreddits, keywords, profiles, pricing, contacts
    Database receives: ALL fields properly mapped to correct columns
    """
    try:
        logger.info(f"🚀 Onboarding new client: {request.get('company_name')}")
        supabase = get_supabase()
        
        # Build complete client record with ALL fields from frontend
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
            "onboarding_status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        
        logger.info(f"📝 Inserting client with {len(client_data)} fields")
        client_result = supabase.table("clients").insert(client_data).execute()
        
        if not client_result.data:
            raise HTTPException(status_code=500, detail="Failed to create client record")
        
        client_id = client_result.data[0]["client_id"]
        logger.info(f"✅ Client created: {client_id}")
        
        # Configure subreddit monitoring (separate table)
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
        
        # Configure keyword monitoring (separate table)
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
        
        # Store Reddit profiles (separate table: client_reddit_profiles)
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
        
        logger.info(f"🎉 Onboarding complete for {request.get('company_name')}")
        
        return JSONResponse(content={
            "success": True,
            "client_id": client_id,
            "message": f"Client {request.get('company_name')} onboarded successfully",
            "configuration": {
                "subreddits": len(target_subreddits) if target_subreddits != ["AUTO_IDENTIFY"] else "AUTO_IDENTIFY",
                "keywords": len(target_keywords) if target_keywords != ["AUTO_IDENTIFY"] else "AUTO_IDENTIFY",
                "reddit_profiles": len(reddit_profiles),
                "monitoring_status": "active"
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Onboarding error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/upload-documents/{client_id}")
async def upload_documents(
    client_id: str,
    files: List[UploadFile] = File(...),
    document_type: str = Form("brand_document")
):
    """
    Upload and process documents for a client
    Supports: PDF, Word, Excel, CSV, JSON, TXT
    """
    try:
        document_service = get_document_service()
        supabase = get_supabase()
        
        logger.info(f"📄 Processing {len(files)} documents for client {client_id}")
        
        # Verify client exists
        client_check = supabase.table("clients").select("client_id").eq("client_id", client_id).execute()
        if not client_check.data:
            raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
        
        results = []
        
        for file in files:
            logger.info(f"Processing file: {file.filename}")
            
            # Read file content
            file_content = await file.read()
            
            # Process document
            result = document_service.process_document(
                client_id=client_id,
                file_content=file_content,
                filename=file.filename,
                file_type=file.content_type or "application/octet-stream",
                document_type=document_type
            )
            
            results.append(result)
        
        # Count successes and failures
        successful = sum(1 for r in results if r.get("success"))
        failed = len(results) - successful
        
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
        logger.error(f"Error uploading documents: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/client/{client_id}/configuration")
async def get_client_configuration(client_id: str):
    """
    Get complete client configuration including subreddits, keywords, and Reddit profiles
    """
    try:
        supabase = get_supabase()
        
        # Get client info
        client = supabase.table("clients").select("*").eq("client_id", client_id).execute()
        if not client.data:
            raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
        
        # Get subreddit config
        subreddits = supabase.table("client_subreddit_config")\
            .select("*")\
            .eq("client_id", client_id)\
            .execute()
        
        # Get keyword config
        keywords = supabase.table("client_keyword_config")\
            .select("*")\
            .eq("client_id", client_id)\
            .execute()
        
        # Get Reddit profiles
        profiles = supabase.table("client_reddit_profiles")\
            .select("*")\
            .eq("client_id", client_id)\
            .execute()
        
        # Get document count
        documents = supabase.table("document_uploads")\
            .select("upload_id", count="exact")\
            .eq("client_id", client_id)\
            .execute()
        
        return {
            "success": True,
            "client": client.data[0],
            "subreddits": subreddits.data,
            "keywords": keywords.data,
            "reddit_profiles": profiles.data,
            "document_count": len(documents.data) if documents.data else 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
