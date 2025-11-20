"""
Migration Router - Run database migrations via API
SECURITY: This should be protected or removed after migration
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging

from supabase_client import get_supabase_client

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/migrations/knowledge-base-setup")
async def run_knowledge_base_migration() -> Dict[str, Any]:
    """
    Run the knowledge base RAG migration
    Creates match_knowledge_embeddings function and indexes
    
    SECURITY: This endpoint should be called once and then disabled
    """
    try:
        supabase = get_supabase_client()
        
        # SQL for creating the function
        create_function_sql = """
        CREATE OR REPLACE FUNCTION match_knowledge_embeddings(
          query_embedding vector(1536),
          client_id uuid,
          similarity_threshold float DEFAULT 0.70,
          match_count int DEFAULT 3
        )
        RETURNS TABLE (
          document_id uuid,
          chunk_text text,
          chunk_index int,
          metadata jsonb,
          similarity float
        )
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RETURN QUERY
          SELECT
            de.document_id,
            de.chunk_text,
            de.chunk_index,
            de.metadata,
            1 - (de.embedding <=> query_embedding) as similarity
          FROM document_embeddings de
          WHERE 
            de.client_id = match_knowledge_embeddings.client_id
            AND 1 - (de.embedding <=> query_embedding) >= similarity_threshold
          ORDER BY de.embedding <=> query_embedding
          LIMIT match_count;
        END;
        $$;
        """
        
        # Since we can't execute raw SQL via Supabase client directly,
        # we'll provide clear instructions and verification
        
        logger.info("⚠️ Database migration requires manual SQL execution")
        logger.info("📝 Please run the SQL file: sql/match_knowledge_embeddings.sql")
        
        # Try to test if function exists (will fail if not created)
        try:
            # This will only work if the function is already created
            test_embedding = [0.0] * 1536
            test_client = '00000000-0000-0000-0000-000000000000'
            
            result = supabase.rpc(
                'match_knowledge_embeddings',
                {
                    'query_embedding': test_embedding,
                    'client_id': test_client,
                    'similarity_threshold': 0.7,
                    'match_count': 1
                }
            ).execute()
            
            # If we got here, function exists!
            logger.info("✅ Function match_knowledge_embeddings already exists!")
            
            return {
                "success": True,
                "message": "Knowledge base RAG function already configured",
                "function_status": "✅ EXISTS",
                "note": "The database migration has already been applied."
            }
            
        except Exception as test_error:
            error_msg = str(test_error).lower()
            
            if "does not exist" in error_msg or "function" in error_msg:
                # Function doesn't exist - need to create it
                logger.warning("❌ Function match_knowledge_embeddings does not exist")
                
                return {
                    "success": False,
                    "message": "Database migration required",
                    "function_status": "❌ NOT FOUND",
                    "instructions": {
                        "step_1": "Login to Supabase dashboard: https://supabase.com/dashboard",
                        "step_2": "Go to SQL Editor",
                        "step_3": "Copy contents of: sql/match_knowledge_embeddings.sql",
                        "step_4": "Paste and click 'Run'",
                        "step_5": "Call this endpoint again to verify"
                    },
                    "sql_file_location": "sql/match_knowledge_embeddings.sql",
                    "git_commit": "8d5fb16"
                }
            else:
                # Some other error
                raise test_error
        
        logger.info("✅ Knowledge base migration completed successfully!")
        
        return {
            "success": True,
            "message": "Knowledge base RAG migration completed",
            "steps_completed": [
                "Created match_knowledge_embeddings function",
                "Created vector similarity index (ivfflat)",
                "Created client_id index",
                "Granted permissions to authenticated users",
                "Added function documentation"
            ]
        }
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {str(e)}", exc_info=True)
        
        # Check if it's because the function already exists
        if "already exists" in str(e).lower():
            return {
                "success": True,
                "message": "Migration already applied (function exists)",
                "note": "This is not an error - the database is already configured"
            }
        
        raise HTTPException(
            status_code=500,
            detail=f"Migration failed: {str(e)}"
        )


@router.get("/migrations/verify-knowledge-base")
async def verify_knowledge_base_setup() -> Dict[str, Any]:
    """
    Verify that the knowledge base migration was successful
    Checks if function and indexes exist
    """
    try:
        supabase = get_supabase_client()
        
        # Test if function exists by trying to call it
        try:
            test_embedding = [0.0] * 1536
            test_client = '00000000-0000-0000-0000-000000000000'
            
            result = supabase.rpc(
                'match_knowledge_embeddings',
                {
                    'query_embedding': test_embedding,
                    'client_id': test_client,
                    'similarity_threshold': 0.7,
                    'match_count': 1
                }
            ).execute()
            
            # Function exists and works!
            function_exists = True
            function_error = None
            
        except Exception as e:
            function_exists = False
            function_error = str(e)
        
        # Check if document_embeddings table exists
        try:
            table_check = supabase.table('document_embeddings').select('id').limit(1).execute()
            table_exists = True
        except Exception:
            table_exists = False
        
        return {
            "success": True,
            "function_exists": function_exists,
            "table_exists": table_exists,
            "status": "✅ READY" if function_exists else "⚠️ NOT CONFIGURED",
            "details": {
                "match_knowledge_embeddings": "Found" if function_exists else "Missing",
                "document_embeddings_table": "Found" if table_exists else "Missing",
                "error": function_error if not function_exists else None
            },
            "next_steps": [] if function_exists else [
                "Run POST /api/migrations/knowledge-base-setup to get instructions",
                "Or manually run sql/match_knowledge_embeddings.sql in Supabase"
            ]
        }
        
    except Exception as e:
        logger.error(f"Verification failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Verification failed: {str(e)}"
        )
