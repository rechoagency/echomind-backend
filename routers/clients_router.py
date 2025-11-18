from fastapi import APIRouter, HTTPException
from supabase import create_client
import os

router = APIRouter()

# Supabase client
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
supabase = create_client(supabase_url, supabase_key)

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
