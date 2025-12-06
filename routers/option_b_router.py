"""
Option B Worker Control Router
API endpoints to manually trigger Option B workers
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional
import asyncio
from datetime import datetime

router = APIRouter(prefix="/api/option-b", tags=["Option B Workers"])


class WorkerResponse(BaseModel):
    """Response model for worker execution"""
    status: str
    message: str
    started_at: str
    worker_name: str


@router.post("/brand-mentions/run", response_model=WorkerResponse)
async def trigger_brand_mention_monitor(background_tasks: BackgroundTasks):
    """
    Manually trigger brand mention monitoring
    Scans all monitored subreddits for brand mentions with GPT-4 sentiment analysis
    """
    from workers.brand_mention_monitor import run_opportunity_monitor
    
    started_at = datetime.utcnow().isoformat()
    
    # Run in background so API returns immediately
    background_tasks.add_task(run_opportunity_monitor)
    
    return WorkerResponse(
        status="started",
        message="Brand mention monitor started in background",
        started_at=started_at,
        worker_name="brand_mention_monitor"
    )


@router.post("/auto-replies/run", response_model=WorkerResponse)
async def trigger_auto_reply_generator(background_tasks: BackgroundTasks):
    """
    Manually trigger auto-reply generation
    Detects replies to client posts and generates contextual responses
    """
    from workers.auto_reply_generator import run_auto_reply_generator
    
    started_at = datetime.utcnow().isoformat()
    
    # Run in background
    background_tasks.add_task(run_auto_reply_generator)
    
    return WorkerResponse(
        status="started",
        message="Auto-reply generator started in background",
        started_at=started_at,
        worker_name="auto_reply_generator"
    )


@router.post("/voice-database/run", response_model=WorkerResponse)
async def trigger_voice_database_worker(
    background_tasks: BackgroundTasks,
    client_id: Optional[str] = None
):
    """
    Manually trigger voice database worker
    Crawls Reddit to analyze voice patterns of top Redditors

    Args:
        client_id: Optional client filter (if not provided, processes all clients)

    Returns immediately and runs crawler in background.
    """
    started_at = datetime.utcnow().isoformat()

    # Capture client_id in closure for background task
    target_client_id = client_id

    def run_voice_worker_sync():
        """Sync wrapper that runs async voice worker in new event loop"""
        import logging
        logger = logging.getLogger(__name__)

        try:
            from workers.voice_database_worker import build_client_voice_database
            from supabase_client import get_supabase_client

            # Create new event loop for background thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                if target_client_id:
                    logger.info(f"🎤 Voice crawler starting for client {target_client_id}")
                    loop.run_until_complete(build_client_voice_database(target_client_id))
                    logger.info(f"✅ Voice crawler completed for client {target_client_id}")
                else:
                    logger.info("🎤 Voice crawler starting for ALL clients")
                    supabase = get_supabase_client()
                    clients_response = supabase.table("clients").select("client_id").execute()
                    for client in clients_response.data:
                        try:
                            loop.run_until_complete(build_client_voice_database(client['client_id']))
                            logger.info(f"✅ Voice crawler completed for client {client['client_id']}")
                        except Exception as e:
                            logger.error(f"❌ Error building voice DB for {client['client_id']}: {e}")
                    logger.info("✅ Voice crawler completed for ALL clients")
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"❌ Voice worker failed: {e}")
            import traceback
            traceback.print_exc()

    # Add sync wrapper to background tasks - returns immediately
    background_tasks.add_task(run_voice_worker_sync)

    return WorkerResponse(
        status="started",
        message=f"Voice database worker started for {'client ' + target_client_id if target_client_id else 'all clients'}",
        started_at=started_at,
        worker_name="voice_database_worker"
    )


@router.post("/run-all", response_model=WorkerResponse)
async def trigger_all_option_b_workers(background_tasks: BackgroundTasks):
    """
    Run all Option B workers in sequence:
    1. Voice Database (creates voice profiles)
    2. Brand Mention Monitor (scans for mentions)
    3. Auto Reply Generator (generates replies)
    """
    from workers.brand_mention_monitor import run_brand_mention_monitor
    from workers.auto_reply_generator import run_auto_reply_generator
    
    started_at = datetime.utcnow().isoformat()
    
    def run_all_workers():
        print("=" * 70)
        print("RUNNING ALL OPTION B WORKERS")
        print("=" * 70)
        
        # Step 1: Brand Mentions
        print("\n[1/2] Brand Mention Monitor...")
        run_brand_mention_monitor()
        
        # Step 2: Auto Replies
        print("\n[2/2] Auto Reply Generator...")
        run_auto_reply_generator()
        
        print("\nNote: Voice Database Worker is async and should be run separately via /voice-database/run endpoint")
        
        print("\n✅ ALL OPTION B WORKERS COMPLETE")
    
    # Run in background
    background_tasks.add_task(run_all_workers)
    
    return WorkerResponse(
        status="started",
        message="Brand Mentions and Auto Replies workers started. Run /voice-database/run separately for voice profiles.",
        started_at=started_at,
        worker_name="all_option_b_workers"
    )


@router.get("/status")
async def get_option_b_status():
    """
    Get status of Option B features and recent activity
    """
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from supabase_client import supabase
    
    try:
        # Count voice profiles
        voice_count = supabase.table("voice_profiles").select("id", count="exact").execute()
        
        # Count brand mentions (last 7 days)
        mentions_count = supabase.table("brand_mentions").select("id", count="exact").execute()
        
        # Count auto replies (pending)
        replies_pending = supabase.table("auto_replies")\
            .select("id", count="exact")\
            .eq("status", "pending")\
            .execute()
        
        # Count products with embeddings
        products_count = supabase.table("products")\
            .select("id", count="exact")\
            .not_.is_("embedding", "null")\
            .execute()
        
        return {
            "status": "active",
            "voice_profiles": voice_count.count,
            "brand_mentions_total": mentions_count.count,
            "auto_replies_pending": replies_pending.count,
            "products_with_embeddings": products_count.count,
            "features": {
                "voice_database": voice_count.count > 0,
                "brand_monitoring": True,
                "auto_replies": True,
                "product_matching": products_count.count > 0
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching status: {str(e)}")
