"""
Debug Router - Development/troubleshooting endpoints
"""
from fastapi import APIRouter
from typing import Dict, Any
import os
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/debug/env-check")
async def check_environment_variables() -> Dict[str, Any]:
    """
    Check if critical environment variables are loaded
    
    Returns:
        Status of environment variables (masked for security)
    """
    openai_key = os.getenv('OPENAI_API_KEY')
    supabase_url = os.getenv('SUPABASE_URL')
    supabase_key = os.getenv('SUPABASE_KEY')
    
    return {
        'openai_api_key_loaded': bool(openai_key),
        'openai_api_key_length': len(openai_key) if openai_key else 0,
        'openai_api_key_prefix': openai_key[:15] + '...' if openai_key else None,
        'supabase_url_loaded': bool(supabase_url),
        'supabase_key_loaded': bool(supabase_key),
        'all_env_vars': list(os.environ.keys())[:10]  # First 10 env var names only
    }


@router.get("/debug/openai-test")
async def test_openai_connection() -> Dict[str, Any]:
    """
    Test OpenAI API connection and embedding generation
    
    Returns:
        Test results
    """
    openai_key = os.getenv('OPENAI_API_KEY')
    
    if not openai_key:
        return {
            'success': False,
            'error': 'OPENAI_API_KEY not found in environment',
            'env_vars_count': len(os.environ),
            'sample_env_vars': list(os.environ.keys())[:20]
        }
    
    try:
        from openai import OpenAI
        
        client = OpenAI(api_key=openai_key)
        
        # Try to generate a simple embedding
        response = client.embeddings.create(
            model="text-embedding-ada-002",
            input="Test embedding for The Waite maternity products"
        )
        
        embedding = response.data[0].embedding
        
        return {
            'success': True,
            'openai_client_initialized': True,
            'embedding_length': len(embedding),
            'embedding_sample': embedding[:5],  # First 5 values
            'model_used': 'text-embedding-ada-002'
        }
        
    except Exception as e:
        logger.error(f"OpenAI test failed: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'error_type': type(e).__name__,
            'openai_key_prefix': openai_key[:20] + '...' if openai_key else None
        }
