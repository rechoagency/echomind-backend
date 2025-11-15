"""
Admin Router - Client Management Operations
Includes: Delete clients with confirmation, bulk operations
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])

supabase = None

def get_supabase():
    global supabase
    if supabase is None:
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
    return supabase


class DeleteClientRequest(BaseModel):
    client_id: str
    confirmation: bool = False  # Must be True to actually delete


@router.delete("/clients/{client_id}")
async def delete_client(client_id: str, confirmation: bool = False):
    """
    Delete a client and ALL associated data
    
    Requires confirmation=true to actually delete
    Without confirmation, returns what would be deleted
    """
    try:
        supabase = get_supabase()
        
        # Get client info first
        client = supabase.table("clients").select("*").eq("client_id", client_id).execute()
        
        if not client.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        client_data = client.data[0]
        
        # Count associated data
        opportunities = supabase.table("opportunities").select("opportunity_id", count="exact").eq("client_id", client_id).execute()
        documents = supabase.table("document_uploads").select("id", count="exact").eq("client_id", client_id).execute()
        calendars = supabase.table("content_calendars").select("id", count="exact").eq("client_id", client_id).execute()
        
        summary = {
            "client": client_data.get("company_name"),
            "client_id": client_id,
            "will_delete": {
                "opportunities": len(opportunities.data) if opportunities.data else 0,
                "documents": len(documents.data) if documents.data else 0,
                "calendars": len(calendars.data) if calendars.data else 0
            }
        }
        
        # If not confirmed, return preview
        if not confirmation:
            return {
                "action": "preview",
                "message": "This is a preview. Set confirmation=true to actually delete.",
                **summary,
                "warning": "⚠️ This action cannot be undone!"
            }
        
        # CONFIRMED - Actually delete
        logger.warning(f"🗑️ DELETING CLIENT: {client_data.get('company_name')} ({client_id})")
        
        # Delete associated data (cascade should handle most, but be explicit)
        supabase.table("opportunities").delete().eq("client_id", client_id).execute()
        supabase.table("document_uploads").delete().eq("client_id", client_id).execute()
        supabase.table("content_calendars").delete().eq("client_id", client_id).execute()
        supabase.table("client_subreddit_config").delete().eq("client_id", client_id).execute()
        supabase.table("client_keyword_config").delete().eq("client_id", client_id).execute()
        
        # Delete client
        supabase.table("clients").delete().eq("client_id", client_id).execute()
        
        logger.info(f"✅ Client deleted: {client_data.get('company_name')}")
        
        return {
            "success": True,
            "action": "deleted",
            "message": f"Client '{client_data.get('company_name')}' and all associated data deleted",
            **summary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting client: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clients/bulk-delete")
async def bulk_delete_clients(client_ids: List[str], confirmation: bool = False):
    """
    Delete multiple clients at once
    
    Requires confirmation=true to actually delete
    """
    try:
        results = []
        
        for client_id in client_ids:
            try:
                result = await delete_client(client_id, confirmation)
                results.append({
                    "client_id": client_id,
                    "status": "success",
                    "result": result
                })
            except Exception as e:
                results.append({
                    "client_id": client_id,
                    "status": "failed",
                    "error": str(e)
                })
        
        return {
            "success": True,
            "deleted": len([r for r in results if r["status"] == "success"]),
            "failed": len([r for r in results if r["status"] == "failed"]),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Bulk delete error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resend-notification/{client_id}")
async def resend_notification(client_id: str):
    """
    Manually resend onboarding notification email
    Useful for testing or if initial email failed
    """
    try:
        import os
        from services.onboarding_orchestrator import OnboardingOrchestrator
        
        supabase = get_supabase()
        openai_key = os.getenv("OPENAI_API_KEY")
        
        # Get client
        client = supabase.table("clients").select("*").eq("client_id", client_id).execute()
        if not client.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Send notification
        orchestrator = OnboardingOrchestrator(supabase, openai_key)
        result = await orchestrator._send_welcome_email(client.data[0], {"success": True, "items": 0})
        
        return {
            "success": result.get("success"),
            "client_id": client_id,
            "email": client.data[0].get("notification_email"),
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resending notification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
