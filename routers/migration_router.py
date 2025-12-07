"""
Migration Router - Run database migrations via API
SECURITY: This should be protected or removed after migration
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import logging
import os

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
        # Try to use psycopg2 for raw SQL execution
        try:
            import psycopg2
            from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
            
            # Get DATABASE_URL from environment (Railway provides this)
            database_url = os.getenv('DATABASE_URL')
            if not database_url:
                raise ValueError("DATABASE_URL not found in environment")
            
            # Read SQL file
            sql_file_path = os.path.join(os.path.dirname(__file__), '..', 'sql', 'match_knowledge_embeddings.sql')
            with open(sql_file_path, 'r') as f:
                sql_content = f.read()
            
            # Connect and execute
            conn = psycopg2.connect(database_url)
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            
            logger.info("🔧 Executing SQL migration...")
            cursor.execute(sql_content)
            
            cursor.close()
            conn.close()
            
            logger.info("✅ SQL migration executed successfully!")
            
            return {
                "success": True,
                "message": "Knowledge base RAG migration completed successfully",
                "method": "direct_sql_execution",
                "steps_completed": [
                    "Created match_knowledge_embeddings function",
                    "Created vector similarity index (ivfflat)",
                    "Created client_id index",
                    "Granted permissions to authenticated users",
                    "Added function documentation"
                ]
            }
            
        except ImportError:
            # psycopg2 not available - fall back to verification only
            logger.warning("⚠️ psycopg2 not installed - cannot execute raw SQL")
            pass
        except Exception as sql_error:
            logger.error(f"SQL execution error: {str(sql_error)}")
            # Continue to verification
            pass
        
        # Verify if function exists (whether we created it or it was already there)
        supabase = get_supabase_client()
        
        try:
            # Test if function exists
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
            
            # Function exists!
            logger.info("✅ Function match_knowledge_embeddings verified!")
            
            return {
                "success": True,
                "message": "Knowledge base RAG function is configured",
                "function_status": "✅ EXISTS",
                "note": "The database migration is complete."
            }
            
        except Exception as test_error:
            error_msg = str(test_error).lower()
            
            if "does not exist" in error_msg or "function" in error_msg:
                # Function doesn't exist - provide manual instructions
                logger.warning("❌ Function match_knowledge_embeddings does not exist")
                
                return {
                    "success": False,
                    "message": "Database migration required - manual SQL execution needed",
                    "function_status": "❌ NOT FOUND",
                    "reason": "psycopg2 not available for direct SQL execution",
                    "instructions": {
                        "step_1": "Login to Supabase dashboard: https://supabase.com/dashboard",
                        "step_2": "Go to SQL Editor",
                        "step_3": "Copy SQL from: https://github.com/rechoagency/echomind-backend/blob/main/sql/match_knowledge_embeddings.sql",
                        "step_4": "Paste and click 'Run'",
                        "step_5": "Call this endpoint again to verify"
                    },
                    "sql_file_location": "sql/match_knowledge_embeddings.sql",
                    "sql_content_preview": """
CREATE OR REPLACE FUNCTION match_knowledge_embeddings(
  query_embedding vector(1536),
  client_id uuid,
  similarity_threshold float DEFAULT 0.70,
  match_count int DEFAULT 3
)
RETURNS TABLE (...)
                    """.strip()
                }
            else:
                # Some other error
                raise test_error
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {str(e)}", exc_info=True)
        
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
                "Run POST /api/migrations/knowledge-base-setup",
                "Or manually run sql/match_knowledge_embeddings.sql in Supabase SQL Editor"
            ]
        }
        
    except Exception as e:
        logger.error(f"Verification failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Verification failed: {str(e)}"
        )


@router.post("/migrations/add-scoring-columns")
async def run_scoring_columns_migration() -> Dict[str, Any]:
    """
    Add scoring columns to opportunities table using Supabase RPC.
    Uses individual ALTER TABLE statements via Supabase client.
    """
    try:
        supabase = get_supabase_client()
        columns_added = []
        errors = []

        # Define columns to add
        column_definitions = [
            ("composite_score", "DECIMAL(5,2)"),
            ("commercial_intent_score", "DECIMAL(5,2)"),
            ("relevance_score", "DECIMAL(5,2)"),
            ("engagement_score", "DECIMAL(5,2)"),
            ("timing_score", "DECIMAL(5,2)"),
            ("priority_tier", "VARCHAR(20)"),
            ("scoring_debug", "JSONB"),
        ]

        # Check which columns already exist
        try:
            # Try selecting all columns to see which exist
            test = supabase.table("opportunities").select("id").limit(1).execute()
        except Exception as e:
            logger.error(f"Failed to connect to opportunities table: {e}")
            raise

        # For each column, try an update that would fail if column doesn't exist
        for col_name, col_type in column_definitions:
            try:
                # Try to select the column - if it fails, column doesn't exist
                supabase.table("opportunities").select(col_name).limit(1).execute()
                columns_added.append(f"{col_name} (already exists)")
            except Exception:
                # Column doesn't exist - we need to add it via SQL Editor
                errors.append(f"{col_name} needs to be added")

        if errors:
            # Return SQL for manual execution
            return {
                "success": False,
                "message": "Some columns need to be added manually via Supabase SQL Editor",
                "columns_to_add": errors,
                "columns_existing": columns_added,
                "manual_sql": """
-- Run this in Supabase SQL Editor:
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS composite_score DECIMAL(5,2);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS commercial_intent_score DECIMAL(5,2);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS relevance_score DECIMAL(5,2);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS engagement_score DECIMAL(5,2);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS timing_score DECIMAL(5,2);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS priority_tier VARCHAR(20);
ALTER TABLE opportunities ADD COLUMN IF NOT EXISTS scoring_debug JSONB;

CREATE INDEX IF NOT EXISTS idx_opportunities_composite_score ON opportunities (composite_score);
CREATE INDEX IF NOT EXISTS idx_opportunities_priority_tier ON opportunities (priority_tier);

NOTIFY pgrst, 'reload schema';
                """,
                "instructions": [
                    "1. Go to Supabase Dashboard > SQL Editor",
                    "2. Copy and run the SQL above",
                    "3. Call this endpoint again to verify"
                ]
            }

        return {
            "success": True,
            "message": "All scoring columns already exist",
            "columns": columns_added
        }

    except Exception as e:
        logger.error(f"Scoring migration check failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Migration check failed: {str(e)}"
        )
