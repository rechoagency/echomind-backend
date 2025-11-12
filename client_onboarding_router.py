"""
Client Onboarding Router
Handles client registration, configuration, and document uploads
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging
import os
import json

# Import document service
from services.document_ingestion_service import DocumentIngestionService, create_document_service

# Supabase client
from supabase import create_client, Client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/client-onboarding", tags=["Client Onboarding"])

# Get environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize document service
try:
    document_service = create_document_service(SUPABASE_URL, SUPABASE_KEY, OPENAI_API_KEY)
    logger.info("Document ingestion service initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize document service: {str(e)}")
    document_service = None


# Pydantic models
class ClientOnboardingRequest(BaseModel):
    company_name: str = Field(..., description="Client company name")
    industry: str = Field(..., description="Industry/niche")
    target_subreddits: List[str] = Field(..., description="List of target subreddit names")
    keywords: List[str] = Field(..., description="List of keywords to monitor")
    brand_voice: Optional[str] = Field(None, description="Brand voice description")
    response_guidelines: Optional[str] = Field(None, description="Response guidelines")
    contact_email: Optional[str] = Field(None, description="Contact email")


class ClientOnboardingResponse(BaseModel):
    success: bool
    client_id: str
    message: str
    configuration: Dict[str, Any]


@router.post("/register", response_model=ClientOnboardingResponse)
async def register_client(request: ClientOnboardingRequest):
    """
    Register a new client and configure their monitoring settings
    """
    try:
        logger.info(f"Registering new client: {request.company_name}")
        
        # Create client record
        client_data = {
            "company_name": request.company_name,
            "industry": request.industry,
            "brand_voice": request.brand_voice,
            "response_guidelines": request.response_guidelines,
            "contact_email": request.contact_email,
            "onboarding_status": "active",
            "created_at": datetime.utcnow().isoformat()
        }
        
        client_result = supabase.table("clients").insert(client_data).execute()
        client_id = client_result.data[0]["id"]
        
        logger.info(f"Client created with ID: {client_id}")
        
        # Configure subreddit monitoring
        subreddit_configs = []
        for subreddit_name in request.target_subreddits:
            subreddit_config = {
                "client_id": client_id,
                "subreddit_name": subreddit_name.lower().replace("r/", ""),
                "monitoring_enabled": True,
                "created_at": datetime.utcnow().isoformat()
            }
            subreddit_configs.append(subreddit_config)
        
        if subreddit_configs:
            supabase.table("client_subreddit_config").insert(subreddit_configs).execute()
            logger.info(f"Configured {len(subreddit_configs)} subreddits for client {client_id}")
        
        # Configure keyword monitoring
        keyword_configs = []
        for keyword in request.keywords:
            keyword_config = {
                "client_id": client_id,
                "keyword": keyword.lower(),
                "match_type": "AUTO_IDENTIFY",
                "created_at": datetime.utcnow().isoformat()
            }
            keyword_configs.append(keyword_config)
        
        if keyword_configs:
            supabase.table("client_keyword_config").insert(keyword_configs).execute()
            logger.info(f"Configured {len(keyword_configs)} keywords for client {client_id}")
        
        return ClientOnboardingResponse(
            success=True,
            client_id=client_id,
            message=f"Client {request.company_name} registered successfully",
            configuration={
                "subreddits": len(request.target_subreddits),
                "keywords": len(request.keywords),
                "monitoring_status": "active"
            }
        )
        
    except Exception as e:
        logger.error(f"Error registering client: {str(e)}")
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
    if not document_service:
        raise HTTPException(
            status_code=503,
            detail="Document ingestion service not available. Check OpenAI API key configuration."
        )
    
    try:
        logger.info(f"Processing {len(files)} documents for client {client_id}")
        
        # Verify client exists
        client_check = supabase.table("clients").select("id").eq("id", client_id).execute()
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


@router.get("/client/{client_id}/documents")
async def get_client_documents(client_id: str):
    """
    Get all documents for a client
    """
    try:
        # Get document uploads
        documents = supabase.table("document_uploads")\
            .select("*")\
            .eq("client_id", client_id)\
            .order("uploaded_at", desc=True)\
            .execute()
        
        return {
            "success": True,
            "client_id": client_id,
            "document_count": len(documents.data),
            "documents": documents.data
        }
        
    except Exception as e:
        logger.error(f"Error fetching documents: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/client/{client_id}/configuration")
async def get_client_configuration(client_id: str):
    """
    Get client configuration including subreddits and keywords
    """
    try:
        # Get client info
        client = supabase.table("clients").select("*").eq("id", client_id).execute()
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
        
        # Get document count
        documents = supabase.table("document_uploads")\
            .select("id", count="exact")\
            .eq("client_id", client_id)\
            .execute()
        
        return {
            "success": True,
            "client": client.data[0],
            "subreddits": subreddits.data,
            "keywords": keywords.data,
            "document_count": len(documents.data) if documents.data else 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching configuration: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/client/{client_id}/update")
async def update_client_configuration(
    client_id: str,
    brand_voice: Optional[str] = None,
    response_guidelines: Optional[str] = None,
    contact_email: Optional[str] = None
):
    """
    Update client configuration
    """
    try:
        update_data = {}
        
        if brand_voice is not None:
            update_data["brand_voice"] = brand_voice
        if response_guidelines is not None:
            update_data["response_guidelines"] = response_guidelines
        if contact_email is not None:
            update_data["contact_email"] = contact_email
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No update data provided")
        
        update_data["updated_at"] = datetime.utcnow().isoformat()
        
        result = supabase.table("clients").update(update_data).eq("id", client_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
        
        return {
            "success": True,
            "client_id": client_id,
            "updated_fields": list(update_data.keys()),
            "client": result.data[0]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating client: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
