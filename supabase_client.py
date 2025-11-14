import os
from supabase import create_client, Client

# Get Supabase credentials from environment
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Also check for alternate variable name (SUPABASE_KEY) as fallback
if not SUPABASE_SERVICE_ROLE_KEY:
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_KEY")

# Validate credentials exist
if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print(f"WARNING: Missing Supabase credentials!")
    print(f"SUPABASE_URL present: {bool(SUPABASE_URL)}")
    print(f"SUPABASE_SERVICE_ROLE_KEY present: {bool(SUPABASE_SERVICE_ROLE_KEY)}")

# Create global Supabase client
supabase: Client = None

def get_supabase_client() -> Client:
    """
    Get or create Supabase client instance.
    This function is called by all routers and workers.
    """
    global supabase
    
    if supabase is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            raise ValueError("Missing Supabase credentials in environment variables")
        
        supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    
    return supabase

# Also export the client directly for backward compatibility
supabase = get_supabase_client()
