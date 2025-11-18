"""
Client Settings Router - CORRECTED VERSION
Two separate controls: Brand Mention % + Product Mention %
Handles monthly strategy controls: reply/post ratio, brand %, product %, explicit instructions
"""

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import logging

from database import get_supabase_client

router = APIRouter(prefix="/client-settings", tags=["client_settings"])
logger = logging.getLogger(__name__)


class ClientSettingsUpdate(BaseModel):
    """Request model for updating client settings"""
    reply_percentage: float = Field(default=75.0, ge=0, le=100, description="Percentage of monthly content that should be replies")
    post_percentage: float = Field(default=25.0, ge=0, le=100, description="Percentage of monthly content that should be new posts")
    brand_mention_percentage: float = Field(default=0.0, ge=0, le=100, description="Percentage of content mentioning brand name/company")
    product_mention_percentage: float = Field(default=0.0, ge=0, le=100, description="Percentage of RELEVANT opportunities mentioning specific products")
    product_relevance_threshold: float = Field(default=0.75, ge=0, le=1.0, description="Minimum similarity score for product relevance (0.0-1.0)")
    current_phase: int = Field(default=1, ge=1, le=4, description="Current brand introduction phase (1-4)")
    explicit_instructions: Optional[str] = Field(default=None, description="Special instructions: compliance, seasonal, competitor focus")
    auto_phase_progression: bool = Field(default=False, description="Automatically progress through phases")


class ClientSettingsResponse(BaseModel):
    """Response model for client settings"""
    id: Optional[str] = None
    client_id: str
    reply_percentage: float
    post_percentage: float
    brand_mention_percentage: float
    product_mention_percentage: float
    product_relevance_threshold: float
    current_phase: int
    phase_start_date: Optional[str] = None
    explicit_instructions: Optional[str] = None
    auto_phase_progression: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@router.get("/{client_id}", response_model=ClientSettingsResponse)
async def get_client_settings(
    client_id: str = Path(..., description="Client UUID")
):
    """
    Get current strategy settings for a client
    
    Returns default values if no settings exist yet:
    - Reply: 75%, Post: 25%
    - Brand mentions: 0% (Phase 1: Trust Building)
    - Product mentions: 0% (relevance-gated)
    - Product relevance threshold: 0.75 (75% similarity required)
    - No explicit instructions
    """
    try:
        supabase = get_supabase_client()
        
        result = supabase.table("client_settings")\
            .select("*")\
            .eq("client_id", client_id)\
            .execute()
        
        if not result.data:
            # Return defaults if no settings exist
            logger.info(f"No settings found for client {client_id}, returning defaults")
            return ClientSettingsResponse(
                client_id=client_id,
                reply_percentage=75.0,
                post_percentage=25.0,
                brand_mention_percentage=0.0,
                product_mention_percentage=0.0,
                product_relevance_threshold=0.75,
                current_phase=1,
                explicit_instructions=None,
                auto_phase_progression=False
            )
        
        settings = result.data[0]
        logger.info(f"Retrieved settings for client {client_id}")
        
        return ClientSettingsResponse(**settings)
    
    except Exception as e:
        logger.error(f"Error fetching settings for client {client_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch settings: {str(e)}")


@router.post("/{client_id}", response_model=ClientSettingsResponse)
async def update_client_settings(
    settings: ClientSettingsUpdate,
    client_id: str = Path(..., description="Client UUID")
):
    """
    Update or create strategy settings for a client
    
    This endpoint uses UPSERT logic:
    - If settings exist: Updates them
    - If settings don't exist: Creates new record
    
    Validates:
    - reply_percentage + post_percentage = 100
    - All percentages are 0-100
    - Phase is 1-4
    - Product relevance threshold is 0.0-1.0
    
    CRITICAL: product_mention_percentage ONLY applies when product is SPECIFICALLY RELEVANT
    - Vector similarity must be >= product_relevance_threshold FIRST
    - Then percentage is applied probabilistically to relevant opportunities
    """
    try:
        # Validate percentage totals
        if settings.reply_percentage + settings.post_percentage != 100:
            raise HTTPException(
                status_code=400,
                detail=f"Reply and Post percentages must total 100%. Got {settings.reply_percentage + settings.post_percentage}%"
            )
        
        supabase = get_supabase_client()
        
        # Prepare data for upsert
        data = {
            "client_id": client_id,
            "reply_percentage": settings.reply_percentage,
            "post_percentage": settings.post_percentage,
            "brand_mention_percentage": settings.brand_mention_percentage,
            "product_mention_percentage": settings.product_mention_percentage,
            "product_relevance_threshold": settings.product_relevance_threshold,
            "current_phase": settings.current_phase,
            "explicit_instructions": settings.explicit_instructions,
            "auto_phase_progression": settings.auto_phase_progression,
            "updated_at": datetime.utcnow().isoformat()
        }
        
        # Check if this is a phase change
        existing = supabase.table("client_settings")\
            .select("current_phase")\
            .eq("client_id", client_id)\
            .execute()
        
        if existing.data and existing.data[0]["current_phase"] != settings.current_phase:
            # Phase changed - update phase_start_date
            data["phase_start_date"] = datetime.utcnow().isoformat()
            logger.info(f"Phase change detected for client {client_id}: {existing.data[0]['current_phase']} → {settings.current_phase}")
        
        # Upsert (insert or update)
        result = supabase.table("client_settings")\
            .upsert(data, on_conflict="client_id")\
            .execute()
        
        if not result.data:
            raise HTTPException(status_code=500, detail="Failed to save settings")
        
        logger.info(f"Successfully updated settings for client {client_id}: Brand {settings.brand_mention_percentage}%, Product {settings.product_mention_percentage}%")
        
        return ClientSettingsResponse(**result.data[0])
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating settings for client {client_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update settings: {str(e)}")


@router.delete("/{client_id}", status_code=204)
async def reset_client_settings(
    client_id: str = Path(..., description="Client UUID")
):
    """
    Reset client settings to defaults by deleting the record
    
    Next GET will return default values:
    - Reply: 75%, Post: 25%
    - Brand mentions: 0%
    - Product mentions: 0%
    - Phase: 1
    """
    try:
        supabase = get_supabase_client()
        
        supabase.table("client_settings")\
            .delete()\
            .eq("client_id", client_id)\
            .execute()
        
        logger.info(f"Reset settings for client {client_id}")
        
        return None
    
    except Exception as e:
        logger.error(f"Error resetting settings for client {client_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reset settings: {str(e)}")


@router.get("/{client_id}/phase-recommendations")
async def get_phase_recommendations(
    client_id: str = Path(..., description="Client UUID")
):
    """
    Get recommendations for phase progression based on current phase and time
    
    Returns:
    - Current phase info
    - Time in current phase
    - Recommended next actions
    - Suggested brand mention percentage
    - Suggested product mention percentage
    """
    try:
        supabase = get_supabase_client()
        
        result = supabase.table("client_settings")\
            .select("current_phase, phase_start_date, brand_mention_percentage, product_mention_percentage")\
            .eq("client_id", client_id)\
            .execute()
        
        if not result.data:
            return {
                "current_phase": 1,
                "phase_name": "Trust Building",
                "recommended_brand_percentage": 0,
                "recommended_product_percentage": 0,
                "next_phase_ready": False,
                "recommendation": "Start with Phase 1: Build trust with 0% brand/product mentions"
            }
        
        settings = result.data[0]
        current_phase = settings["current_phase"]
        
        # Calculate time in current phase
        phase_start = settings.get("phase_start_date")
        if phase_start:
            from datetime import datetime
            start_date = datetime.fromisoformat(phase_start.replace('Z', '+00:00'))
            days_in_phase = (datetime.utcnow() - start_date.replace(tzinfo=None)).days
        else:
            days_in_phase = 0
        
        # Phase recommendations
        phase_info = {
            1: {
                "name": "Trust Building",
                "recommended_brand_percentage": 0,
                "recommended_product_percentage": 0,
                "min_days": 30,
                "next_phase_brand": 7.5,
                "next_phase_product": 0,
                "tip": "Focus on pure value. Build authentic presence before mentioning brand/products."
            },
            2: {
                "name": "Soft Introduction",
                "recommended_brand_percentage": 7.5,
                "recommended_product_percentage": 5,
                "min_days": 30,
                "next_phase_brand": 17.5,
                "next_phase_product": 10,
                "tip": "Occasionally mention brand naturally. Introduce products ONLY when specifically relevant."
            },
            3: {
                "name": "Product Integration",
                "recommended_brand_percentage": 17.5,
                "recommended_product_percentage": 15,
                "min_days": 60,
                "next_phase_brand": 22.5,
                "next_phase_product": 20,
                "tip": "Regular but balanced brand/product mentions. You've earned trust for recommendations."
            },
            4: {
                "name": "Sustained Authority",
                "recommended_brand_percentage": 22.5,
                "recommended_product_percentage": 20,
                "min_days": None,
                "next_phase_brand": 22.5,
                "next_phase_product": 20,
                "tip": "Maintain authority status with confident brand advocacy and relevant product recommendations."
            }
        }
        
        current_info = phase_info[current_phase]
        next_phase_ready = False
        
        if current_phase < 4 and current_info["min_days"]:
            next_phase_ready = days_in_phase >= current_info["min_days"]
        
        return {
            "current_phase": current_phase,
            "phase_name": current_info["name"],
            "days_in_phase": days_in_phase,
            "recommended_brand_percentage": current_info["recommended_brand_percentage"],
            "recommended_product_percentage": current_info["recommended_product_percentage"],
            "current_brand_percentage": settings["brand_mention_percentage"],
            "current_product_percentage": settings["product_mention_percentage"],
            "next_phase_ready": next_phase_ready,
            "next_phase_brand_percentage": current_info["next_phase_brand"] if current_phase < 4 else None,
            "next_phase_product_percentage": current_info["next_phase_product"] if current_phase < 4 else None,
            "recommendation": current_info["tip"],
            "product_mention_note": "Product mentions ONLY apply when product is specifically relevant to thread (≥75% vector similarity)"
        }
    
    except Exception as e:
        logger.error(f"Error getting phase recommendations for client {client_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get recommendations: {str(e)}")


@router.get("/{client_id}/knowledge-base-stats")
async def get_knowledge_base_stats(
    client_id: str = Path(..., description="Client UUID")
):
    """
    Get statistics about client's uploaded documents and knowledge base
    
    Returns:
    - Document count
    - Total size (GB)
    - Vector chunk count
    - Last updated date
    """
    try:
        supabase = get_supabase_client()
        
        # Get document stats
        docs = supabase.table("document_uploads")\
            .select("id, file_size, uploaded_at")\
            .eq("client_id", client_id)\
            .eq("processing_status", "completed")\
            .execute()
        
        # Get chunk stats
        chunks = supabase.table("client_knowledge_base")\
            .select("id", count="exact")\
            .eq("client_id", client_id)\
            .execute()
        
        document_count = len(docs.data) if docs.data else 0
        total_size_bytes = sum(doc["file_size"] for doc in docs.data) if docs.data else 0
        total_size_gb = total_size_bytes / (1024 ** 3)
        chunk_count = chunks.count if chunks.count else 0
        
        last_updated = None
        if docs.data:
            dates = [doc["uploaded_at"] for doc in docs.data if doc.get("uploaded_at")]
            if dates:
                last_updated = max(dates)
        
        return {
            "document_count": document_count,
            "total_size_gb": round(total_size_gb, 2),
            "chunk_count": chunk_count,
            "last_updated": last_updated or "Never"
        }
    
    except Exception as e:
        logger.error(f"Error getting knowledge base stats for client {client_id}: {e}")
        return {
            "document_count": 0,
            "total_size_gb": 0.0,
            "chunk_count": 0,
            "last_updated": "Unknown"
        }
