from fastapi import APIRouter, HTTPException
from supabase_client import supabase

router = APIRouter()

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
