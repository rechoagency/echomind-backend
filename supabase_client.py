import os
import logging
from functools import lru_cache
from supabase import create_client, Client
from typing import Optional

logger = logging.getLogger(__name__)

# Get Supabase credentials from environment
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Also check for alternate variable name (SUPABASE_KEY) as fallback
if not SUPABASE_SERVICE_ROLE_KEY:
    SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_KEY")

# Create global Supabase client with singleton pattern
_supabase_client: Optional[Client] = None


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Get or create Supabase client instance with proper error handling.
    Uses connection pooling via singleton pattern + LRU cache.
    
    This function is called by all routers and workers.
    
    Returns:
        Client: Supabase client instance
        
    Raises:
        ValueError: If credentials are missing
        ConnectionError: If connection to Supabase fails
    """
    global _supabase_client
    
    if _supabase_client is not None:
        return _supabase_client
    
    try:
        # Validate credentials
        if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
            logger.error("Missing Supabase credentials in environment variables")
            logger.error(f"SUPABASE_URL present: {bool(SUPABASE_URL)}")
            logger.error(f"SUPABASE_SERVICE_ROLE_KEY present: {bool(SUPABASE_SERVICE_ROLE_KEY)}")
            raise ValueError(
                "Missing Supabase credentials. "
                "Ensure SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are set."
            )
        
        # Create client with error handling
        logger.info("Creating Supabase client connection...")
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        logger.info("✅ Supabase client connected successfully")
        
        return _supabase_client
        
    except ValueError as e:
        logger.error(f"❌ Configuration error: {e}")
        raise
    except Exception as e:
        logger.error(f"❌ Failed to create Supabase client: {e}")
        raise ConnectionError(f"Failed to connect to Supabase: {e}") from e


def health_check() -> bool:
    """
    Check if Supabase connection is healthy.
    
    Returns:
        bool: True if connection is healthy, False otherwise
    """
    try:
        client = get_supabase_client()
        # Simple query to test connection
        client.table('clients').select('id').limit(1).execute()
        return True
    except Exception as e:
        logger.error(f"Supabase health check failed: {e}")
        return False


# Initialize client on module import with error handling
try:
    supabase = get_supabase_client()
except Exception as e:
    logger.warning(f"Could not initialize Supabase client on import: {e}")
    logger.warning("Client will be initialized on first use")
    supabase = None
