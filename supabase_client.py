"""
Centralized Supabase client with error handling and connection pooling
CRITICAL FIX: Added proper error handling to prevent system-wide crashes
"""
import os
import logging
from functools import lru_cache
from supabase import create_client, Client
from typing import Optional

logger = logging.getLogger(__name__)

@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Get or create a singleton Supabase client with error handling
    
    Uses LRU cache to ensure only one client instance exists (connection pooling)
    
    Returns:
        Client: Supabase client instance
        
    Raises:
        ValueError: If credentials are missing
        Exception: If client creation fails
    """
    url: Optional[str] = os.getenv("SUPABASE_URL")
    key: Optional[str] = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        error_msg = "SUPABASE_URL and SUPABASE_KEY must be set in environment"
        logger.critical(error_msg)
        raise ValueError(error_msg)
    
    try:
        client = create_client(url, key)
        logger.info("✅ Supabase client initialized successfully")
        return client
    except Exception as e:
        logger.critical(f"❌ Failed to create Supabase client: {e}")
        raise Exception(f"Supabase client initialization failed: {e}") from e

def get_supabase_client_safe() -> Optional[Client]:
    """
    Safe version that returns None instead of raising on failure
    Use this for non-critical operations
    """
    try:
        return get_supabase_client()
    except Exception as e:
        logger.error(f"Failed to get Supabase client: {e}")
        return None

# Create default client for backward compatibility
# Don't fail at import time - let calling code handle it
supabase = None
try:
    supabase = get_supabase_client()
except Exception as e:
    logger.warning(f"Supabase client not initialized at import time: {e}. Will initialize on first use.")
