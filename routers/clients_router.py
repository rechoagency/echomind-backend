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
    owned_subreddits: Optional[List[str]] = None
    company_name: Optional[str] = None
    industry: Optional[str] = None
    notification_email: Optional[str] = None
    subscription_status: Optional[str] = None
    brand_voice: Optional[str] = None
    posting_guidelines: Optional[str] = None
    special_instructions: Optional[str] = None
    strategy_settings: Optional[dict] = None


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
        
        if update_data.owned_subreddits is not None:
            update_dict['owned_subreddits'] = update_data.owned_subreddits
        
        if update_data.brand_voice is not None:
            update_dict['brand_voice'] = update_data.brand_voice
        
        if update_data.posting_guidelines is not None:
            update_dict['posting_guidelines'] = update_data.posting_guidelines
        
        if update_data.special_instructions is not None:
            update_dict['special_instructions'] = update_data.special_instructions
        
        if update_data.strategy_settings is not None:
            update_dict['strategy_settings'] = update_data.strategy_settings
        
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
# Updated: Wed Nov 19 16:10:58 UTC 2025


@router.patch("/clients/{client_id}/strategy")
async def update_strategy_settings(client_id: str, settings: dict):
    """
    Update client strategy settings (reply %, brand mention %, product mention %)
    These settings affect content generation for Monday/Thursday deliveries
    """
    try:
        # Validate settings
        required_keys = ['reply_percentage', 'brand_mention_percentage', 'product_mention_percentage']
        for key in required_keys:
            if key not in settings:
                raise HTTPException(status_code=400, detail=f"Missing required key: {key}")
            if not 0 <= settings[key] <= 100:
                raise HTTPException(status_code=400, detail=f"{key} must be between 0 and 100")
        
        # Check client exists
        existing = supabase.table('clients').select('*').eq('client_id', client_id).single().execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Update BOTH tables to ensure consistency across frontend and workers
        # 1. Update clients.strategy_settings (for frontend display)
        clients_response = supabase.table('clients').update({
            'strategy_settings': settings
        }).eq('client_id', client_id).execute()
        
        # 2. Update client_settings table (for workers and /api/client-settings endpoint)
        # Calculate post_percentage from reply_percentage
        post_percentage = 100 - settings['reply_percentage']
        
        settings_update = {
            'reply_percentage': settings['reply_percentage'],
            'post_percentage': post_percentage,
            'brand_mention_percentage': settings['brand_mention_percentage'],
            'product_mention_percentage': settings['product_mention_percentage']
        }
        
        # Try to update existing settings or insert new row
        existing_settings = supabase.table('client_settings').select('id').eq('client_id', client_id).execute()
        
        if existing_settings.data:
            # Update existing
            settings_response = supabase.table('client_settings').update(settings_update).eq('client_id', client_id).execute()
        else:
            # Insert new
            settings_update['client_id'] = client_id
            settings_response = supabase.table('client_settings').insert(settings_update).execute()
        
        if clients_response.data and settings_response.data:
            logger.info(f"✅ Strategy settings updated in BOTH tables for client {client_id}")
            logger.info(f"   Reply: {settings['reply_percentage']}%, Post: {post_percentage}%")
            logger.info(f"   Brand: {settings['brand_mention_percentage']}%, Product: {settings['product_mention_percentage']}%")
            return {
                "status": "success",
                "message": "Strategy settings updated successfully",
                "settings": settings
            }
        else:
            raise HTTPException(status_code=500, detail="Update failed")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating strategy: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/clients/{client_id}/subreddits")
async def update_subreddits(client_id: str, data: dict):
    """Update client subreddits and owned subreddits"""
    try:
        subreddits = data.get('subreddits', data.get('target_subreddits', []))
        owned_subreddits = data.get('owned_subreddits', [])
        
        # Validate that owned subreddits are subset of all subreddits
        if owned_subreddits and not set(owned_subreddits).issubset(set(subreddits)):
            raise HTTPException(
                status_code=400,
                detail="Owned subreddits must be a subset of all subreddits"
            )
        
        # Check client exists
        existing = supabase.table('clients').select('*').eq('client_id', client_id).single().execute()
        if not existing.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Update database
        response = supabase.table('clients').update({
            'target_subreddits': subreddits,
            'owned_subreddits': owned_subreddits
        }).eq('client_id', client_id).execute()
        
        if response.data:
            logger.info(f"✅ Subreddits updated for client {client_id}: {len(subreddits)} total, {len(owned_subreddits)} owned")
            return {
                "status": "success",
                "message": "Subreddits updated successfully",
                "subreddits": subreddits,
                "owned_subreddits": owned_subreddits
            }
        else:
            raise HTTPException(status_code=500, detail="Update failed")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating subreddits: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user-profiles")
async def get_user_profiles(client_id: str):
    """Get Reddit user profiles for a client"""
    try:
        response = supabase.table('client_reddit_profiles') \
            .select('*') \
            .eq('client_id', client_id) \
            .eq('is_active', True) \
            .execute()
        
        return response.data or []
    
    except Exception as e:
        logger.error(f"Error fetching user profiles: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clients/{client_id}/documents")
async def get_client_documents(client_id: str):
    """Get all uploaded documents for a client"""
    try:
        response = supabase.table('document_uploads') \
            .select('*') \
            .eq('client_id', client_id) \
            .order('created_at', desc=True) \
            .execute()
        
        documents = response.data or []
        
        # Return formatted document list
        return {
            "success": True,
            "count": len(documents),
            "documents": [{
                "id": doc.get('id'),
                "filename": doc.get('filename'),
                "file_type": doc.get('file_type'),
                "document_type": doc.get('document_type'),
                "file_size_bytes": doc.get('file_size_bytes'),
                "chunks_created": doc.get('chunks_created', 0),
                "vectors_created": doc.get('vectors_created', 0),
                "created_at": doc.get('created_at'),
                "status": doc.get('status', 'processed')
            } for doc in documents]
        }
    
    except Exception as e:
        logger.error(f"Error fetching documents: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clients/{client_id}/special-instructions")
async def get_special_instructions(client_id: str):
    """Get all special instructions for a client as array of blocks"""
    try:
        response = supabase.table('clients').select('special_instructions').eq('client_id', client_id).single().execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        instructions = response.data.get('special_instructions')
        
        # If special_instructions is a string, split by newlines into array
        if isinstance(instructions, str):
            blocks = [line.strip() for line in instructions.split('\n') if line.strip()]
        elif isinstance(instructions, list):
            blocks = instructions
        else:
            blocks = []
        
        return {
            "success": True,
            "instructions": blocks
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching special instructions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clients/{client_id}/special-instructions")
async def add_special_instruction(client_id: str, data: dict):
    """Add a new special instruction block"""
    try:
        new_instruction = data.get('instruction', '').strip()
        if not new_instruction:
            raise HTTPException(status_code=400, detail="Instruction cannot be empty")
        
        # Get current instructions
        response = supabase.table('clients').select('special_instructions').eq('client_id', client_id).single().execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        current = response.data.get('special_instructions')
        
        # Convert to array
        if isinstance(current, str):
            blocks = [line.strip() for line in current.split('\n') if line.strip()]
        elif isinstance(current, list):
            blocks = current
        else:
            blocks = []
        
        # Add new instruction
        blocks.append(new_instruction)
        
        # Save back to database
        supabase.table('clients').update({
            'special_instructions': blocks
        }).eq('client_id', client_id).execute()
        
        return {
            "success": True,
            "message": "Special instruction added",
            "instructions": blocks
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding special instruction: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/clients/{client_id}/special-instructions/{index}")
async def delete_special_instruction(client_id: str, index: int):
    """Delete a special instruction by index"""
    try:
        # Get current instructions
        response = supabase.table('clients').select('special_instructions').eq('client_id', client_id).single().execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        current = response.data.get('special_instructions')
        
        # Convert to array
        if isinstance(current, str):
            blocks = [line.strip() for line in current.split('\n') if line.strip()]
        elif isinstance(current, list):
            blocks = current
        else:
            blocks = []
        
        # Validate index
        if index < 0 or index >= len(blocks):
            raise HTTPException(status_code=400, detail="Invalid instruction index")
        
        # Remove instruction
        blocks.pop(index)
        
        # Save back to database
        supabase.table('clients').update({
            'special_instructions': blocks
        }).eq('client_id', client_id).execute()
        
        return {
            "success": True,
            "message": "Special instruction deleted",
            "instructions": blocks
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting special instruction: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clients/{client_id}/test-welcome-email")
async def test_welcome_email(client_id: str):
    """Test endpoint to manually trigger welcome email for debugging"""
    try:
        import os
        
        # Get client data
        client_response = supabase.table('clients').select('*').eq('client_id', client_id).single().execute()
        if not client_response.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        client = client_response.data
        
        # Get opportunities for client
        opps_response = supabase.table('opportunities') \
            .select('*') \
            .eq('client_id', client_id) \
            .order('combined_score', desc=True) \
            .limit(100) \
            .execute()
        
        opportunities = opps_response.data if opps_response.data else []
        
        # Check if RESEND_API_KEY is set
        resend_key = os.getenv('RESEND_API_KEY')
        if not resend_key:
            logger.error("❌ RESEND_API_KEY not configured in environment!")
            return {
                "success": False,
                "error": "RESEND_API_KEY not configured in environment variables",
                "debug": {
                    "client_id": client_id,
                    "client_name": client.get('company_name'),
                    "notification_email": client.get('notification_email'),
                    "opportunities_count": len(opportunities)
                }
            }
        
        # Send welcome email
        logger.info(f"📧 TEST: Sending welcome email to {client.get('notification_email')}")
        
        from services.email_service_with_excel import WelcomeEmailService
        email_service = WelcomeEmailService()
        result = await email_service.send_welcome_email_with_reports(
            client=client,
            opportunities=opportunities
        )
        
        return {
            "success": result.get('success', False),
            "message": "Welcome email test completed",
            "email_result": result,
            "debug": {
                "client_id": client_id,
                "client_name": client.get('company_name'),
                "notification_email": client.get('notification_email'),
                "opportunities_count": len(opportunities),
                "resend_api_key_configured": bool(resend_key)
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Test email error: {str(e)}")
        import traceback
        return {
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }
