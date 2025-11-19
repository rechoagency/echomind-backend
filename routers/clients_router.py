from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from supabase_client import supabase
import logging

logger = logging.getLogger(__name__)
router = APIRouter()


class ClientUpdateRequest(BaseModel):
    """Model for updating client data"""
    target_keywords: Optional[List[str]] = None
    target_subreddits: Optional[List[str]] = None
    company_name: Optional[str] = None
    industry: Optional[str] = None
    notification_email: Optional[str] = None
    subscription_status: Optional[str] = None


@router.get("/clients/{client_id}")
async def get_client(client_id: str):
    """Get client data by ID"""
    try:
        response = supabase.table('clients') \
            .select('*') \
            .eq('client_id', client_id) \
            .single() \
            .execute()
        
        if response.data:
            return response.data
        else:
            raise HTTPException(status_code=404, detail="Client not found")
    
    except Exception as e:
        print(f"Error fetching client: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clients")
async def list_clients():
    """List all clients"""
    try:
        response = supabase.table('clients') \
            .select('*') \
            .order('created_at', desc=True) \
            .execute()
        
        return response.data or []
    
    except Exception as e:
        print(f"Error listing clients: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/clients/{client_id}")
async def update_client(client_id: str, update_data: ClientUpdateRequest):
    """
    Update client data (keywords, subreddits, or other fields)
    
    Supports partial updates - only send fields you want to change
    """
    try:
        # Check client exists
        existing = supabase.table('clients') \
            .select('*') \
            .eq('client_id', client_id) \
            .single() \
            .execute()
        
        if not existing.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Build update dict with only provided fields
        update_dict = {}
        
        if update_data.target_keywords is not None:
            update_dict['target_keywords'] = update_data.target_keywords
            logger.info(f"Updating keywords for {client_id}: {update_data.target_keywords}")
        
        if update_data.target_subreddits is not None:
            update_dict['target_subreddits'] = update_data.target_subreddits
            logger.info(f"Updating subreddits for {client_id}: {update_data.target_subreddits}")
        
        if update_data.company_name is not None:
            update_dict['company_name'] = update_data.company_name
        
        if update_data.industry is not None:
            update_dict['industry'] = update_data.industry
        
        if update_data.notification_email is not None:
            update_dict['notification_email'] = update_data.notification_email
        
        if update_data.subscription_status is not None:
            update_dict['subscription_status'] = update_data.subscription_status
        
        if not update_dict:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        # Update in database
        response = supabase.table('clients') \
            .update(update_dict) \
            .eq('client_id', client_id) \
            .execute()
        
        if response.data:
            logger.info(f"Successfully updated client {client_id}")
            return {
                "success": True,
                "message": "Client updated successfully",
                "client": response.data[0]
            }
        else:
            raise HTTPException(status_code=500, detail="Update failed")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating client: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
