"""
Admin Router - Client Management Operations
Includes: Delete clients with confirmation, bulk operations
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List
import logging
import os
from datetime import datetime
from openai import AsyncOpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Admin"])

supabase = None

def get_supabase():
    global supabase
    if supabase is None:
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
    return supabase


class DeleteClientRequest(BaseModel):
    client_id: str
    confirmation: bool = False  # Must be True to actually delete


@router.delete("/clients/{client_id}")
async def delete_client(client_id: str, confirmation: bool = False):
    """
    Delete a client and ALL associated data
    
    Requires confirmation=true to actually delete
    Without confirmation, returns what would be deleted
    """
    try:
        supabase = get_supabase()
        
        # Get client info first
        client = supabase.table("clients").select("*").eq("client_id", client_id).execute()
        
        if not client.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        client_data = client.data[0]
        
        # Count associated data
        opportunities = supabase.table("opportunities").select("opportunity_id", count="exact").eq("client_id", client_id).execute()
        documents = supabase.table("document_uploads").select("id", count="exact").eq("client_id", client_id).execute()
        calendars = supabase.table("content_calendars").select("id", count="exact").eq("client_id", client_id).execute()
        
        summary = {
            "client": client_data.get("company_name"),
            "client_id": client_id,
            "will_delete": {
                "opportunities": len(opportunities.data) if opportunities.data else 0,
                "documents": len(documents.data) if documents.data else 0,
                "calendars": len(calendars.data) if calendars.data else 0
            }
        }
        
        # If not confirmed, return preview
        if not confirmation:
            return {
                "action": "preview",
                "message": "This is a preview. Set confirmation=true to actually delete.",
                **summary,
                "warning": "⚠️ This action cannot be undone!"
            }
        
        # CONFIRMED - Actually delete
        logger.warning(f"🗑️ DELETING CLIENT: {client_data.get('company_name')} ({client_id})")
        
        # Delete associated data (cascade should handle most, but be explicit)
        supabase.table("opportunities").delete().eq("client_id", client_id).execute()
        supabase.table("document_uploads").delete().eq("client_id", client_id).execute()
        supabase.table("content_calendars").delete().eq("client_id", client_id).execute()
        supabase.table("client_subreddit_config").delete().eq("client_id", client_id).execute()
        supabase.table("client_keyword_config").delete().eq("client_id", client_id).execute()
        
        # Delete client
        supabase.table("clients").delete().eq("client_id", client_id).execute()
        
        logger.info(f"✅ Client deleted: {client_data.get('company_name')}")
        
        return {
            "success": True,
            "action": "deleted",
            "message": f"Client '{client_data.get('company_name')}' and all associated data deleted",
            **summary
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting client: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clients/bulk-delete")
async def bulk_delete_clients(client_ids: List[str], confirmation: bool = False):
    """
    Delete multiple clients at once
    
    Requires confirmation=true to actually delete
    """
    try:
        results = []
        
        for client_id in client_ids:
            try:
                result = await delete_client(client_id, confirmation)
                results.append({
                    "client_id": client_id,
                    "status": "success",
                    "result": result
                })
            except Exception as e:
                results.append({
                    "client_id": client_id,
                    "status": "failed",
                    "error": str(e)
                })
        
        return {
            "success": True,
            "deleted": len([r for r in results if r["status"] == "success"]),
            "failed": len([r for r in results if r["status"] == "failed"]),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Bulk delete error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resend-notification/{client_id}")
async def resend_notification(client_id: str):
    """
    Manually resend onboarding notification email
    Useful for testing or if initial email failed
    """
    try:
        import os
        from services.onboarding_orchestrator import OnboardingOrchestrator
        
        supabase = get_supabase()
        openai_key = os.getenv("OPENAI_API_KEY")
        
        # Get client
        client = supabase.table("clients").select("*").eq("client_id", client_id).execute()
        if not client.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Send notification
        orchestrator = OnboardingOrchestrator(supabase, openai_key)
        result = await orchestrator._send_welcome_email(client.data[0], {"success": True, "items": 0})
        
        return {
            "success": result.get("success"),
            "client_id": client_id,
            "email": client.data[0].get("notification_email"),
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resending notification: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send-weekly-reports")
async def send_weekly_reports_to_all():
    """
    Manually trigger weekly report generation for all clients
    Useful for testing the report system
    """
    try:
        import asyncio
        from workers.weekly_report_generator import WeeklyReportGenerator
        
        logger.info("Manual weekly report generation triggered")
        
        generator = WeeklyReportGenerator()
        result = await generator.send_reports_to_all_clients()
        
        return {
            "success": True,
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Error sending weekly reports: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger-orchestrator/{client_id}")
async def trigger_full_orchestrator(client_id: str, background_tasks: BackgroundTasks):
    """
    Manually trigger full orchestrator for a client
    
    This will:
    1. Run AUTO_IDENTIFY keyword expansion
    2. Scrape Reddit for 50-100 opportunities
    3. Score and prioritize opportunities
    4. Generate Intelligence Report & Sample Content
    5. Send welcome email with reports
    
    Use this when:
    - Initial onboarding failed to collect opportunities
    - Client has 0 opportunities in database
    - Need to re-run full data collection
    
    Returns immediately, processing runs in background (5-10 minutes)
    """
    try:
        from services.onboarding_orchestrator import OnboardingOrchestrator
        from services.delayed_report_workflow import DelayedReportWorkflow
        
        supabase = get_supabase()
        openai_key = os.getenv("OPENAI_API_KEY")
        
        # Fetch client
        client_response = supabase.table("clients").select("*").eq("client_id", client_id).execute()
        
        if not client_response.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        client = client_response.data[0]
        company_name = client.get('company_name', 'Client')
        
        logger.info(f"🚀 Manual orchestrator trigger for: {company_name}")
        
        # Run orchestrator in background
        async def run_full_workflow():
            try:
                # Step 1: Run orchestrator (scraping + scoring)
                orchestrator = OnboardingOrchestrator(supabase, openai_key)
                result = await orchestrator.process_client_onboarding(client_id)
                
                logger.info(f"✅ Orchestrator completed for {company_name}: {result}")
                
                # Step 2: Run delayed report workflow
                openai_client = AsyncOpenAI(api_key=openai_key)
                workflow = DelayedReportWorkflow(supabase, openai_client)
                
                notification_email = client.get('primary_contact_email') or client.get('notification_email')
                slack_webhook = client.get('slack_webhook_url')
                
                await workflow.run_workflow(
                    client_id=client_id,
                    notification_email=notification_email,
                    slack_webhook=slack_webhook,
                    min_opportunities=10,
                    timeout_seconds=600
                )
                
                logger.info(f"✅ Full workflow completed for {company_name}")
                
            except Exception as e:
                logger.error(f"❌ Workflow error for {company_name}: {str(e)}", exc_info=True)
        
        # Add to background tasks
        background_tasks.add_task(run_full_workflow)
        
        return {
            "success": True,
            "message": f"Full orchestrator triggered for {company_name}",
            "client_id": client_id,
            "company_name": company_name,
            "estimated_completion": "5-10 minutes",
            "steps": [
                "1. AUTO_IDENTIFY keywords",
                "2. Scrape Reddit for opportunities",
                "3. Score and prioritize",
                "4. Generate Intelligence Report",
                "5. Generate Sample Content",
                "6. Send welcome email"
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering orchestrator: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send-weekly-report/{client_id}")
async def send_weekly_report_to_client(client_id: str):
    """
    Send weekly report to a specific client
    Useful for testing with individual clients
    """
    try:
        from workers.weekly_report_generator import WeeklyReportGenerator
        
        supabase = get_supabase()
        
        # Fetch client
        client_response = supabase.table("clients").select("*").eq("client_id", client_id).execute()
        
        if not client_response.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        client = client_response.data[0]
        
        logger.info(f"Manual weekly report for: {client.get('company_name')}")
        
        generator = WeeklyReportGenerator()
        result = await generator._generate_and_send_report(client)
        
        return {
            "success": result.get("success"),
            "client_id": client_id,
            "company_name": client.get("company_name"),
            "result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending weekly report: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/regenerate-reports/{client_id}")
async def regenerate_onboarding_reports(client_id: str, background_tasks: BackgroundTasks):
    """
    Regenerate Intelligence Report and Sample Content for a client
    
    Use this when:
    - Initial onboarding workflow failed
    - Client needs updated reports
    - Testing report generation
    
    Returns immediately, reports generated in background
    """
    try:
        from fastapi import BackgroundTasks
        supabase = get_supabase()
        
        # Verify client exists
        client_response = supabase.table("clients").select("*").eq("client_id", client_id).execute()
        
        if not client_response.data:
            raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
        
        client = client_response.data[0]
        company_name = client.get("company_name")
        notification_email = client.get("primary_contact_email") or client.get("notification_email")
        slack_webhook = client.get("slack_webhook_url")
        
        if not notification_email:
            raise HTTPException(status_code=400, detail="Client has no email address for reports")
        
        logger.info(f"🔄 Regenerating reports for: {company_name} ({client_id})")
        
        # Trigger delayed report workflow in background
        from client_onboarding_router import run_onboarding_with_delayed_reports
        
        background_tasks.add_task(
            run_onboarding_with_delayed_reports,
            client_id,
            notification_email,
            slack_webhook
        )
        
        return {
            "success": True,
            "message": f"Report generation started for {company_name}",
            "client_id": client_id,
            "email": notification_email,
            "estimated_time": "5-10 minutes",
            "note": "You will receive Intelligence Report and Sample Content via email"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating reports: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trigger-reddit-scan")
async def trigger_reddit_scan(background_tasks: BackgroundTasks, request: dict = None):
    """
    Manually trigger Reddit opportunity scan for all clients or specific client
    
    Used for:
    - Immediate scanning after onboarding (don't wait for scheduled job)
    - Testing Reddit monitoring
    - Recovering from failed scans
    
    Body (optional):
    {
        "client_id": "uuid"  # If omitted, scans all active clients
    }
    """
    try:
        client_id = request.get("client_id") if request else None
        
        if client_id:
            # Scan specific client
            supabase = get_supabase()
            client = supabase.table("clients").select("*").eq("client_id", client_id).execute()
            
            if not client.data:
                raise HTTPException(status_code=404, detail="Client not found")
            
            client_data = client.data[0]
            company_name = client_data.get("company_name")
            subreddits = client_data.get("target_subreddits", [])
            keywords = client_data.get("target_keywords", [])
            
            if not subreddits or not keywords:
                raise HTTPException(
                    status_code=400,
                    detail=f"Client {company_name} has no subreddits or keywords configured"
                )
            
            logger.info(f"🔍 Triggering Reddit scan for: {company_name}")
            logger.info(f"   Subreddits: {subreddits}")
            logger.info(f"   Keywords: {keywords}")
            
            # Run scan in background
            from workers.brand_mention_monitor import scan_for_opportunities, save_opportunities
            
            def scan_and_save():
                opportunities = scan_for_opportunities(client_id, company_name, subreddits, keywords)
                if opportunities:
                    save_opportunities(opportunities)
                    logger.info(f"✅ Created {len(opportunities)} opportunities for {company_name}")
                else:
                    logger.warning(f"⚠️  No opportunities found for {company_name}")
                return opportunities
            
            background_tasks.add_task(scan_and_save)
            
            return {
                "success": True,
                "message": f"Reddit scan started for {company_name}",
                "client_id": client_id,
                "estimated_time": "2-3 minutes",
                "note": "Check dashboard for opportunities"
            }
        
        else:
            # Scan all active clients
            logger.info("🔍 Triggering Reddit scan for ALL active clients")
            
            from workers.brand_mention_monitor import run_opportunity_monitor
            
            background_tasks.add_task(run_opportunity_monitor)
            
            return {
                "success": True,
                "message": "Reddit scan started for all active clients",
                "estimated_time": "5-10 minutes",
                "note": "Scanning all configured subreddits"
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error triggering Reddit scan: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-worker-pipeline")
async def run_worker_pipeline(background_tasks: BackgroundTasks, request: dict):
    """
    Manually trigger the full worker pipeline for a client
    
    Pipeline stages:
    1. Opportunity Scoring
    2. Product Matchback
    3. Content Generation
    4. Voice Application
    
    Used for:
    - Processing newly discovered opportunities
    - Regenerating content after document updates
    - Testing the full pipeline
    
    Body:
    {
        "client_id": "uuid",
        "force_regenerate": false  # Optional: regenerate existing content
    }
    """
    try:
        client_id = request.get("client_id")
        force_regenerate = request.get("force_regenerate", False)
        
        if not client_id:
            raise HTTPException(status_code=400, detail="client_id is required")
        
        supabase = get_supabase()
        client = supabase.table("clients").select("*").eq("client_id", client_id).execute()
        
        if not client.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        company_name = client.data[0].get("company_name")
        
        logger.info(f"⚙️  Triggering worker pipeline for: {company_name}")
        
        # Run pipeline in background
        from workers.scheduler import run_full_pipeline
        
        background_tasks.add_task(
            run_full_pipeline,
            client_id,
            force_regenerate
        )
        
        return {
            "success": True,
            "message": f"Worker pipeline started for {company_name}",
            "client_id": client_id,
            "force_regenerate": force_regenerate,
            "estimated_time": "5-10 minutes",
            "pipeline_stages": [
                "Opportunity Scoring",
                "Product Matchback",
                "Content Generation",
                "Voice Application"
            ],
            "note": "Check dashboard for content pieces after completion"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running worker pipeline: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


class TestContentRequest(BaseModel):
    client_id: str = None
    count: int = 2
    opportunity_id: str = None  # Optional: Test specific opportunity


@router.post("/test-content-generation")
async def test_content_generation_sync(request: TestContentRequest = None):
    """
    Synchronous test endpoint for content generation.
    Runs content generation directly (not in background) so we can see errors.

    This is for debugging only - returns full result including any errors.

    Body (optional):
    {
        "client_id": "uuid",  # If omitted, uses first active client
        "count": 2            # Number of opportunities to process (default 2)
    }
    """
    import traceback

    try:
        logger.info("🧪 TEST CONTENT GENERATION - Starting synchronous test")

        # Import the worker
        from workers.content_generation_worker import ContentGenerationWorker

        # Create worker instance
        worker = ContentGenerationWorker()

        # Get client_id from request or find first active client
        client_id = request.client_id if request and request.client_id else None
        count = request.count if request and request.count else 2

        if not client_id:
            # Find first active client with opportunities
            clients = worker.supabase.table("clients").select("client_id, company_name").eq("subscription_status", "active").limit(5).execute()
            for c in (clients.data or []):
                opps = worker.supabase.table("opportunities").select("opportunity_id").eq("client_id", c["client_id"]).limit(1).execute()
                if opps.data:
                    client_id = c["client_id"]
                    logger.info(f"🧪 Using client: {c['company_name']} ({client_id})")
                    break

            if not client_id:
                return {"success": False, "error": "No active clients with opportunities found"}

        logger.info(f"🧪 Calling process_all_opportunities for client {client_id}")

        # Check if specific opportunity_id was provided
        specific_opp_id = request.opportunity_id if request and request.opportunity_id else None

        if specific_opp_id:
            # Get specific opportunity
            logger.info(f"🧪 Testing specific opportunity: {specific_opp_id}")
            worker_query = worker.supabase.table("opportunities")\
                .select("opportunity_id, client_id, thread_title, original_post_text, subreddit, thread_url, date_found")\
                .eq("opportunity_id", specific_opp_id)\
                .execute()
            test_opps = worker_query.data if worker_query.data else []
            opps_count = len(test_opps)
            sample_opp = test_opps[0] if test_opps else None
            worker_query_count = len(test_opps)
        else:
            # First, let's check how many opportunities exist using worker's supabase
            opps_check = worker.supabase.table("opportunities").select("opportunity_id, thread_title").eq("client_id", client_id).order("date_found", desc=True).limit(5).execute()
            opps_count = len(opps_check.data) if opps_check.data else 0
            sample_opp = opps_check.data[0] if opps_check.data else None

            # Also check what the worker's query returns
            worker_query = worker.supabase.table("opportunities").select("opportunity_id, client_id, thread_title, original_post_text, subreddit, thread_url, date_found").eq("client_id", client_id).order("date_found", desc=True).limit(10).execute()
            worker_query_count = len(worker_query.data) if worker_query.data else 0

            # Directly call generate_content_for_client with limited opportunities to avoid timeout
            # Take first 'count' opportunities for quick test
            test_opps = worker_query.data[:count] if worker_query.data else []

        if test_opps:
            try:
                result = worker.generate_content_for_client(
                    client_id=client_id,
                    opportunities=test_opps,
                    delivery_batch=f"TEST-{datetime.now().strftime('%Y-%m-%d')}"
                )
            except Exception as gen_error:
                gen_tb = traceback.format_exc()
                result = {
                    "success": False,
                    "error": f"Generation failed: {str(gen_error)}",
                    "traceback": gen_tb
                }
        else:
            result = {"success": False, "error": "No opportunities found"}

        logger.info(f"🧪 Result: {result}")

        # Check actual content in database after generation
        content_check = worker.supabase.table("content_delivered").select("id, client_id, content_type, subreddit_name, delivered_at").eq("client_id", client_id).order("delivered_at", desc=True).limit(5).execute()
        content_count = len(content_check.data) if content_check.data else 0
        sample_content = content_check.data[0] if content_check.data else None

        return {
            "success": True,
            "test_type": "synchronous_content_generation",
            "client_id": client_id,
            "opportunities_check": {
                "count": opps_count,
                "sample": sample_opp,
                "worker_query_count": worker_query_count,
                "test_opportunities": [
                    {
                        "id": o.get("opportunity_id"),
                        "subreddit": o.get("subreddit"),
                        "title": o.get("thread_title", "")[:80]
                    } for o in test_opps
                ]
            },
            "result": result,
            "content_in_database": {
                "count": content_count,
                "sample": sample_content
            }
        }

    except Exception as e:
        error_traceback = traceback.format_exc()
        logger.error(f"🧪 TEST FAILED: {e}")
        logger.error(f"Traceback: {error_traceback}")

        return {
            "success": False,
            "test_type": "synchronous_content_generation",
            "error": str(e),
            "traceback": error_traceback
        }


@router.post("/run-opportunity-scoring")
async def run_opportunity_scoring(client_id: str = None):
    """
    Manually trigger opportunity scoring for all or specific client.
    Scores opportunities by: buying intent, pain points, questions, engagement, urgency.
    """
    try:
        logger.info(f"🎯 Starting opportunity scoring (client_id: {client_id or 'all'})")

        from workers.opportunity_scoring_worker import OpportunityScoringWorker

        worker = OpportunityScoringWorker()
        result = worker.process_all_opportunities(client_id)

        logger.info(f"🎯 Scoring complete: {result}")

        return {
            "success": True,
            "action": "opportunity_scoring",
            "client_id": client_id,
            "result": result
        }

    except Exception as e:
        logger.error(f"🎯 Scoring failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/pipeline-status")
async def get_pipeline_status():
    """
    Get status of all pipeline components.
    """
    try:
        supabase = get_supabase()

        # Check voice profiles
        voice_profiles = supabase.table("voice_profiles").select("id", count="exact").execute()
        voice_count = voice_profiles.count if voice_profiles.count else 0

        # Check scored opportunities
        scored_opps = supabase.table("opportunities").select("opportunity_id", count="exact").not_.is_("opportunity_score", "null").execute()
        scored_count = scored_opps.count if scored_opps.count else 0

        # Check total opportunities
        total_opps = supabase.table("opportunities").select("opportunity_id", count="exact").execute()
        total_count = total_opps.count if total_opps.count else 0

        # Check knowledge base (document_uploads or client_documents)
        try:
            docs = supabase.table("document_uploads").select("id", count="exact").execute()
            docs_count = docs.count if docs.count else 0
        except:
            docs_count = 0

        # Check vector embeddings
        try:
            embeddings = supabase.table("vector_embeddings").select("id", count="exact").execute()
            embeddings_count = embeddings.count if embeddings.count else 0
        except:
            embeddings_count = 0

        # Check content delivered
        content = supabase.table("content_delivered").select("id", count="exact").execute()
        content_count = content.count if content.count else 0

        return {
            "pipeline_components": {
                "voice_database": {
                    "profiles": voice_count,
                    "status": "POPULATED" if voice_count > 0 else "EMPTY"
                },
                "opportunity_scoring": {
                    "scored": scored_count,
                    "total": total_count,
                    "percentage": round(scored_count / total_count * 100, 1) if total_count > 0 else 0,
                    "status": "COMPLETE" if scored_count == total_count and total_count > 0 else "PARTIAL" if scored_count > 0 else "NOT_RUN"
                },
                "knowledge_base": {
                    "documents": docs_count,
                    "embeddings": embeddings_count,
                    "status": "POPULATED" if embeddings_count > 0 else "EMPTY"
                },
                "content_generation": {
                    "pieces": content_count,
                    "status": "ACTIVE" if content_count > 0 else "NO_CONTENT"
                }
            },
            "overall_status": "READY" if voice_count > 0 and scored_count > 0 else "NEEDS_SETUP"
        }

    except Exception as e:
        logger.error(f"Pipeline status check failed: {e}")
        return {"error": str(e)}


@router.post("/configure-subreddits")
async def configure_client_subreddits(request: dict):
    """
    Add subreddits to client_subreddit_config table for an existing client.
    Use this to fix clients that were onboarded without proper subreddit configuration.

    Request body:
    {
        "client_id": "uuid-here",
        "subreddits": ["Menopause", "PCOS", "TryingForABaby"]
    }
    """
    try:
        supabase = get_supabase()
        client_id = request.get("client_id")
        subreddits = request.get("subreddits", [])

        if not client_id:
            return {"success": False, "error": "client_id is required"}
        if not subreddits:
            return {"success": False, "error": "subreddits list is required"}

        # Verify client exists
        client = supabase.table("clients").select("client_id, company_name").eq("client_id", client_id).execute()
        if not client.data:
            return {"success": False, "error": f"Client {client_id} not found"}

        # Check existing subreddit configs
        existing = supabase.table("client_subreddit_config").select("subreddit_name").eq("client_id", client_id).execute()
        existing_names = [s["subreddit_name"].lower() for s in (existing.data or [])]

        # Insert new subreddits (skip duplicates)
        new_configs = []
        skipped = []
        for sub in subreddits:
            sub_clean = sub.lower().replace("r/", "")
            if sub_clean in existing_names:
                skipped.append(sub_clean)
            else:
                new_configs.append({
                    "client_id": client_id,
                    "subreddit_name": sub_clean,
                    "is_active": True,
                    "created_at": datetime.utcnow().isoformat()
                })

        if new_configs:
            supabase.table("client_subreddit_config").insert(new_configs).execute()
            logger.info(f"Added {len(new_configs)} subreddits for client {client_id}")

        return {
            "success": True,
            "client_id": client_id,
            "client_name": client.data[0].get("company_name"),
            "added": [c["subreddit_name"] for c in new_configs],
            "skipped_duplicates": skipped,
            "total_configured": len(existing_names) + len(new_configs)
        }

    except Exception as e:
        logger.error(f"Configure subreddits failed: {e}")
        return {"success": False, "error": str(e)}


@router.get("/client-subreddits/{client_id}")
async def get_client_subreddits(client_id: str):
    """Get all configured subreddits for a client"""
    try:
        supabase = get_supabase()

        # Get subreddit configs
        configs = supabase.table("client_subreddit_config").select("*").eq("client_id", client_id).execute()

        return {
            "client_id": client_id,
            "subreddits": configs.data or [],
            "count": len(configs.data or [])
        }

    except Exception as e:
        logger.error(f"Get subreddits failed: {e}")
        return {"error": str(e)}


@router.post("/reprocess-documents/{client_id}")
async def reprocess_stuck_documents(client_id: str, background_tasks: BackgroundTasks):
    """
    Reprocess documents stuck in 'processing' status

    Use this when documents were uploaded but chunking/embedding failed
    (typically due to timeout)

    Runs in background - returns immediately
    """
    try:
        supabase = get_supabase()

        # Get client info
        client = supabase.table("clients").select("company_name").eq("client_id", client_id).execute()
        if not client.data:
            raise HTTPException(status_code=404, detail="Client not found")

        company_name = client.data[0].get("company_name")

        # Get stuck documents
        stuck_docs = supabase.table("document_uploads")\
            .select("*")\
            .eq("client_id", client_id)\
            .eq("processing_status", "processing")\
            .execute()

        if not stuck_docs.data:
            return {
                "success": True,
                "message": "No stuck documents to reprocess",
                "client_id": client_id
            }

        logger.info(f"🔄 Reprocessing {len(stuck_docs.data)} stuck documents for {company_name}")

        async def reprocess_documents():
            """Background task to reprocess documents"""
            from services.document_ingestion_service import DocumentIngestionService

            service = DocumentIngestionService(supabase, os.getenv("OPENAI_API_KEY"))
            results = []

            for doc in stuck_docs.data:
                doc_id = doc.get("id")
                filename = doc.get("filename")

                try:
                    # Mark as failed first (so we can retry)
                    supabase.table("document_uploads").update({
                        "processing_status": "retrying"
                    }).eq("id", doc_id).execute()

                    # We don't have the original file content, so mark as failed
                    # Future: store files in Supabase Storage for retry
                    supabase.table("document_uploads").update({
                        "processing_status": "failed",
                        "error_message": "Cannot reprocess - original file not stored. Please re-upload."
                    }).eq("id", doc_id).execute()

                    results.append({
                        "document_id": doc_id,
                        "filename": filename,
                        "status": "marked_failed",
                        "message": "Please re-upload this file"
                    })

                except Exception as e:
                    logger.error(f"Error marking document {doc_id}: {e}")
                    results.append({
                        "document_id": doc_id,
                        "filename": filename,
                        "status": "error",
                        "error": str(e)
                    })

            logger.info(f"✅ Reprocessing complete for {company_name}: {len(results)} documents updated")
            return results

        background_tasks.add_task(reprocess_documents)

        return {
            "success": True,
            "message": f"Reprocessing {len(stuck_docs.data)} stuck documents for {company_name}",
            "client_id": client_id,
            "documents": [{"id": d["id"], "filename": d.get("filename")} for d in stuck_docs.data],
            "note": "Documents will be marked as failed - please re-upload them"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reprocess documents failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{client_id}/stuck")
async def delete_stuck_documents(client_id: str):
    """
    Delete all documents stuck in 'processing' status

    Use this to clean up failed uploads so user can try again
    """
    try:
        supabase = get_supabase()

        # Get client info
        client = supabase.table("clients").select("company_name").eq("client_id", client_id).execute()
        if not client.data:
            raise HTTPException(status_code=404, detail="Client not found")

        company_name = client.data[0].get("company_name")

        # Get stuck documents before deleting
        stuck_docs = supabase.table("document_uploads")\
            .select("id, filename")\
            .eq("client_id", client_id)\
            .eq("processing_status", "processing")\
            .execute()

        if not stuck_docs.data:
            return {
                "success": True,
                "message": "No stuck documents to delete",
                "client_id": client_id
            }

        # Delete stuck documents
        deleted_count = len(stuck_docs.data)
        supabase.table("document_uploads")\
            .delete()\
            .eq("client_id", client_id)\
            .eq("processing_status", "processing")\
            .execute()

        logger.info(f"🗑️ Deleted {deleted_count} stuck documents for {company_name}")

        return {
            "success": True,
            "message": f"Deleted {deleted_count} stuck documents for {company_name}",
            "client_id": client_id,
            "deleted": [{"id": d["id"], "filename": d.get("filename")} for d in stuck_docs.data]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete stuck documents failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rag-diagnostic/{client_id}")
async def diagnose_rag_system(client_id: str):
    """
    Diagnostic endpoint to check if RAG (knowledge base) is working for a client.

    Checks:
    1. Document embeddings table has data
    2. RPC function match_knowledge_embeddings exists
    3. Test query returns results
    """
    try:
        supabase = get_supabase()
        results = {
            "client_id": client_id,
            "checks": {}
        }

        # Check 1: Does document_embeddings table have data for this client?
        try:
            embeddings = supabase.table("document_embeddings")\
                .select("id, document_id, chunk_index, created_at")\
                .eq("client_id", client_id)\
                .limit(5)\
                .execute()
            results["checks"]["document_embeddings"] = {
                "status": "found" if embeddings.data else "empty",
                "count": len(embeddings.data) if embeddings.data else 0,
                "sample": embeddings.data[:2] if embeddings.data else []
            }
        except Exception as e:
            results["checks"]["document_embeddings"] = {
                "status": "error",
                "error": str(e)
            }

        # Check 2: Does document_uploads table have completed docs?
        try:
            docs = supabase.table("document_uploads")\
                .select("id, filename, processing_status, chunk_count")\
                .eq("client_id", client_id)\
                .execute()
            results["checks"]["document_uploads"] = {
                "status": "found" if docs.data else "empty",
                "count": len(docs.data) if docs.data else 0,
                "completed": len([d for d in (docs.data or []) if d.get("processing_status") == "completed"]),
                "total_chunks_reported": sum(d.get("chunk_count", 0) or 0 for d in (docs.data or []))
            }
        except Exception as e:
            results["checks"]["document_uploads"] = {
                "status": "error",
                "error": str(e)
            }

        # Check 3: Does the RPC function exist?
        try:
            test_embedding = [0.0] * 1536
            rpc_result = supabase.rpc(
                'match_knowledge_embeddings',
                {
                    'query_embedding': test_embedding,
                    'client_id': client_id,
                    'similarity_threshold': 0.0,  # Very low to get any results
                    'match_count': 3
                }
            ).execute()
            results["checks"]["rpc_function"] = {
                "status": "exists",
                "test_results_count": len(rpc_result.data) if rpc_result.data else 0
            }
        except Exception as e:
            error_msg = str(e).lower()
            if "does not exist" in error_msg or "function" in error_msg:
                results["checks"]["rpc_function"] = {
                    "status": "missing",
                    "error": "Function match_knowledge_embeddings not found",
                    "fix": "Run sql/match_knowledge_embeddings.sql in Supabase SQL Editor"
                }
            else:
                results["checks"]["rpc_function"] = {
                    "status": "error",
                    "error": str(e)
                }

        # Summary
        embeddings_ok = results["checks"].get("document_embeddings", {}).get("status") == "found"
        rpc_ok = results["checks"].get("rpc_function", {}).get("status") == "exists"

        if embeddings_ok and rpc_ok:
            results["rag_status"] = "WORKING"
            results["message"] = "RAG system is configured and has embeddings"
        elif rpc_ok and not embeddings_ok:
            results["rag_status"] = "NO_EMBEDDINGS"
            results["message"] = "RPC function exists but no embeddings found - documents may not have been vectorized"
        elif not rpc_ok:
            results["rag_status"] = "RPC_MISSING"
            results["message"] = "match_knowledge_embeddings function not found - run migration SQL"
        else:
            results["rag_status"] = "NOT_CONFIGURED"
            results["message"] = "RAG system needs setup"

        return results

    except Exception as e:
        logger.error(f"RAG diagnostic failed: {e}")
        return {"error": str(e)}


@router.post("/test-voice-crawl")
async def test_voice_crawl_single_subreddit(request: dict, background_tasks: BackgroundTasks):
    """
    Test voice crawl for a SINGLE subreddit (runs in background).

    Body:
    {
        "client_id": "uuid",
        "subreddit": "HomeImprovement"
    }

    This crawls just one subreddit with reduced limits for testing.
    Returns immediately, crawl runs in background.
    """
    try:
        client_id = request.get("client_id")
        subreddit = request.get("subreddit")

        if not client_id or not subreddit:
            return {"error": "client_id and subreddit are required"}

        # Clean subreddit name
        subreddit = subreddit.replace("r/", "").strip()

        logger.info(f"🎤 Starting background voice crawl for r/{subreddit} (client: {client_id})")

        async def run_voice_crawl():
            try:
                from workers.voice_database_worker import VoiceDatabaseWorker

                worker = VoiceDatabaseWorker()
                worker.TOP_USERS_PER_SUBREDDIT = 10  # Very small for quick test
                worker.COMMENTS_PER_USER = 5

                await worker.analyze_subreddit_voice(subreddit, client_id)
                logger.info(f"✅ Voice crawl complete for r/{subreddit}")
            except Exception as e:
                logger.error(f"Background voice crawl failed: {e}")

        background_tasks.add_task(run_voice_crawl)

        return {
            "success": True,
            "message": f"Voice crawl started in background for r/{subreddit}",
            "client_id": client_id,
            "subreddit": subreddit,
            "note": "Check /api/admin/pipeline-status in ~60 seconds to see if profile was created"
        }

    except Exception as e:
        logger.error(f"Voice crawl test failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/create-voice-profile")
async def create_voice_profile_manual(request: dict):
    """
    Create a voice profile manually (without Reddit crawling).

    This is useful for testing the pipeline when Reddit crawling is slow.

    Body:
    {
        "client_id": "uuid",
        "subreddit": "HomeImprovement"
    }

    v3: Uses delete+insert instead of upsert
    """
    try:
        supabase = get_supabase()

        client_id = request.get("client_id")
        subreddit = request.get("subreddit")

        if not client_id or not subreddit:
            return {"error": "client_id and subreddit are required"}

        subreddit = subreddit.replace("r/", "").strip().lower()

        # Default voice profile values
        profile_values = {
            "dominant_tone": "helpful",
            "formality_score": 0.3,
            "lowercase_start_pct": 25,
            "exclamation_usage_pct": 12
        }

        # Use a synthetic redditor_username for subreddit-wide voice (table requires it)
        synthetic_username = f"__subreddit_voice_{subreddit}__"

        # Try multiple column combinations until one works
        column_attempts = [
            # Attempt 1: Most complete
            {
                "client_id": client_id,
                "redditor_username": synthetic_username,
                "subreddit": subreddit,
                "dominant_tone": profile_values["dominant_tone"],
                "formality_score": profile_values["formality_score"],
                "lowercase_start_pct": profile_values["lowercase_start_pct"],
                "exclamation_usage_pct": profile_values["exclamation_usage_pct"],
                "created_at": datetime.utcnow().isoformat()
            },
            # Attempt 2: Without numeric columns
            {
                "client_id": client_id,
                "redditor_username": synthetic_username,
                "subreddit": subreddit,
                "dominant_tone": profile_values["dominant_tone"],
                "created_at": datetime.utcnow().isoformat()
            },
            # Attempt 3: Just the required columns
            {
                "client_id": client_id,
                "redditor_username": synthetic_username,
                "subreddit": subreddit,
                "created_at": datetime.utcnow().isoformat()
            }
        ]

        inserted_data = None
        last_error = None

        # First, try to delete any existing profile for this client/subreddit
        try:
            supabase.table("voice_profiles").delete().eq("client_id", client_id).eq("subreddit", subreddit).execute()
            logger.info(f"Deleted existing voice profile for r/{subreddit}")
        except Exception as e:
            logger.warning(f"No existing profile to delete or delete failed: {e}")

        for i, data in enumerate(column_attempts):
            try:
                # Use insert instead of upsert (since we just deleted any existing)
                supabase.table("voice_profiles").insert(data).execute()
                inserted_data = data
                logger.info(f"✅ Created voice profile with attempt {i+1} for r/{subreddit}")
                break
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Voice profile attempt {i+1} failed: {e}")
                continue

        if not inserted_data:
            return {
                "success": False,
                "error": f"All column combinations failed. Last error: {last_error}"
            }

        return {
            "success": True,
            "version": "v3",
            "client_id": client_id,
            "subreddit": subreddit,
            "profile_created": True,
            "columns_used": list(inserted_data.keys()),
            "profile_values": profile_values
        }

    except Exception as e:
        logger.error(f"Manual voice profile creation failed: {e}")
        return {
            "version": "v3",
            "success": False,
            "error": str(e)
        }


@router.post("/test-rag-search")
async def test_rag_search(request: dict):
    """
    Test RAG knowledge base search with a query.

    Body:
    {
        "client_id": "uuid",
        "query": "How do electric fireplaces compare to gas?",
        "threshold": 0.50
    }
    """
    try:
        client_id = request.get("client_id")
        query = request.get("query", "electric fireplace heating efficiency")
        threshold = request.get("threshold", 0.50)

        if not client_id:
            return {"error": "client_id required"}

        # Direct test with embedding
        from openai import OpenAI
        import os

        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        supabase = get_supabase()

        # Generate embedding - MUST match model used for stored embeddings
        embedding_response = openai_client.embeddings.create(
            model="text-embedding-ada-002",  # Same as populate_embeddings.py
            input=query[:8000]
        )
        query_embedding = embedding_response.data[0].embedding
        embedding_dim = len(query_embedding)

        # Direct RPC call
        rpc_result = supabase.rpc(
            'match_knowledge_embeddings',
            {
                'query_embedding': query_embedding,
                'client_id': client_id,
                'similarity_threshold': threshold,
                'match_count': 5
            }
        ).execute()

        # Also test zero threshold to verify function works
        rpc_result_zero = supabase.rpc(
            'match_knowledge_embeddings',
            {
                'query_embedding': query_embedding,
                'client_id': client_id,
                'similarity_threshold': 0.0,  # Get ALL matches
                'match_count': 5
            }
        ).execute()

        return {
            "success": True,
            "client_id": client_id,
            "query": query,
            "threshold": threshold,
            "embedding_dimensions": embedding_dim,
            "insights_found_at_threshold": len(rpc_result.data) if rpc_result.data else 0,
            "insights_found_at_zero": len(rpc_result_zero.data) if rpc_result_zero.data else 0,
            "insights_at_threshold": rpc_result.data or [],
            "insights_at_zero": [
                {
                    "chunk_text": r.get("chunk_text", "")[:200],
                    "similarity": r.get("similarity")
                } for r in (rpc_result_zero.data or [])
            ]
        }

    except Exception as e:
        logger.error(f"RAG search test failed: {e}")
        import traceback
        return {"success": False, "error": str(e), "traceback": traceback.format_exc()}


@router.get("/search-opportunities/{client_id}")
async def search_opportunities(client_id: str, keywords: str = None, limit: int = 20):
    """
    Search opportunities for a client by keywords.

    Use this to find product-relevant opportunities for testing.

    Args:
        client_id: Client UUID
        keywords: Comma-separated keywords to search (e.g., "fireplace,tv lift,heating")
        limit: Max results (default 20)

    Example:
        GET /api/admin/search-opportunities/999ac53f-...?keywords=fireplace,electric,tv&limit=10
    """
    try:
        supabase = get_supabase()

        # Get all opportunities for client
        query = supabase.table("opportunities")\
            .select("opportunity_id, thread_title, subreddit, opportunity_score, original_post_text, date_found")\
            .eq("client_id", client_id)\
            .order("date_found", desc=True)\
            .limit(500)  # Get more to filter

        result = query.execute()

        if not result.data:
            return {"success": True, "count": 0, "opportunities": [], "message": "No opportunities found"}

        opportunities = result.data

        # Filter by keywords if provided
        if keywords:
            keyword_list = [k.strip().lower() for k in keywords.split(",")]
            filtered = []
            for opp in opportunities:
                title = (opp.get("thread_title") or "").lower()
                content = (opp.get("original_post_text") or "").lower()
                combined = f"{title} {content}"

                for kw in keyword_list:
                    if kw in combined:
                        opp["matched_keyword"] = kw
                        filtered.append(opp)
                        break

            opportunities = filtered

        # Limit results
        opportunities = opportunities[:limit]

        return {
            "success": True,
            "client_id": client_id,
            "keywords_searched": keywords,
            "count": len(opportunities),
            "opportunities": [
                {
                    "opportunity_id": o.get("opportunity_id"),
                    "thread_title": o.get("thread_title"),
                    "subreddit": o.get("subreddit"),
                    "score": o.get("opportunity_score"),
                    "matched_keyword": o.get("matched_keyword"),
                    "date_found": o.get("date_found")
                } for o in opportunities
            ]
        }

    except Exception as e:
        logger.error(f"Search opportunities failed: {e}")
        return {"success": False, "error": str(e)}


@router.post("/reprocess-embeddings/{client_id}")
async def reprocess_document_embeddings(client_id: str):
    """
    Reprocess documents from document_uploads and generate embeddings in document_embeddings.

    This fixes the gap where documents were uploaded but embeddings weren't created.

    Process:
    1. Get all completed documents from document_uploads
    2. Try to get chunks from document_chunks OR vector_embeddings
    3. Generate OpenAI embeddings for each chunk
    4. Insert into document_embeddings table (which RAG queries)
    """
    from openai import OpenAI
    import os

    try:
        supabase = get_supabase()
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Get client info
        client = supabase.table("clients").select("company_name").eq("client_id", client_id).execute()
        if not client.data:
            return {"error": f"Client {client_id} not found"}
        company_name = client.data[0].get("company_name")

        logger.info(f"🔄 Reprocessing embeddings for {company_name} ({client_id})")

        # Get completed documents from document_uploads
        docs = supabase.table("document_uploads")\
            .select("id, filename, file_type, chunk_count, processing_status")\
            .eq("client_id", client_id)\
            .eq("processing_status", "completed")\
            .execute()

        if not docs.data:
            return {
                "success": False,
                "error": "No completed documents found in document_uploads",
                "client_id": client_id
            }

        results = []
        total_embeddings_created = 0
        chunks_sources_checked = []

        for doc in docs.data:
            doc_id = doc["id"]
            filename = doc["filename"]
            chunks_data = []

            try:
                # Try document_chunks first
                try:
                    chunks = supabase.table("document_chunks")\
                        .select("id, chunk_text, chunk_index")\
                        .eq("document_id", doc_id)\
                        .order("chunk_index")\
                        .execute()
                    if chunks.data:
                        chunks_data = chunks.data
                        chunks_sources_checked.append("document_chunks")
                except Exception:
                    pass

                # Try vector_embeddings (already has chunks with embeddings in different format)
                if not chunks_data:
                    try:
                        vec_emb = supabase.table("vector_embeddings")\
                            .select("id, chunk_id, embedding")\
                            .eq("client_id", client_id)\
                            .limit(50)\
                            .execute()
                        if vec_emb.data:
                            # Get chunk text from document_chunks using chunk_id
                            for ve in vec_emb.data:
                                chunk_id = ve.get("chunk_id")
                                if chunk_id:
                                    chunk_data = supabase.table("document_chunks")\
                                        .select("chunk_text, chunk_index, document_id")\
                                        .eq("id", chunk_id)\
                                        .execute()
                                    if chunk_data.data and chunk_data.data[0].get("document_id") == doc_id:
                                        chunks_data.append({
                                            "chunk_text": chunk_data.data[0]["chunk_text"],
                                            "chunk_index": chunk_data.data[0]["chunk_index"],
                                            "existing_embedding": ve.get("embedding")
                                        })
                            if chunks_data:
                                chunks_sources_checked.append("vector_embeddings+document_chunks")
                    except Exception as ve_err:
                        logger.warning(f"vector_embeddings check failed: {ve_err}")

                if not chunks_data:
                    logger.warning(f"No chunks found for document {filename} ({doc_id})")
                    results.append({
                        "document_id": doc_id,
                        "filename": filename,
                        "status": "skipped",
                        "reason": "No chunks found in document_chunks or vector_embeddings"
                    })
                    continue

                embeddings_created = 0

                for chunk in chunks_data:
                    chunk_text = chunk.get("chunk_text", "")
                    chunk_index = chunk.get("chunk_index", 0)

                    if not chunk_text or len(chunk_text) < 10:
                        continue

                    # Check if embedding already exists in document_embeddings
                    existing = supabase.table("document_embeddings")\
                        .select("id")\
                        .eq("document_id", doc_id)\
                        .eq("chunk_index", chunk_index)\
                        .execute()

                    if existing.data:
                        logger.info(f"  Embedding already exists for chunk {chunk_index}")
                        continue

                    # Use existing embedding if available, otherwise generate new one
                    embedding = chunk.get("existing_embedding")
                    if not embedding:
                        try:
                            response = openai_client.embeddings.create(
                                model="text-embedding-ada-002",
                                input=chunk_text[:8000]
                            )
                            embedding = response.data[0].embedding
                        except Exception as emb_error:
                            logger.error(f"Error creating embedding for chunk {chunk_index}: {emb_error}")
                            continue

                    # Insert into document_embeddings
                    embedding_record = {
                        "document_id": doc_id,
                        "client_id": client_id,
                        "chunk_text": chunk_text,
                        "chunk_index": chunk_index,
                        "embedding": embedding,
                        "metadata": {
                            "filename": filename,
                            "char_count": len(chunk_text),
                            "source": "reprocess_endpoint"
                        },
                        "created_at": datetime.utcnow().isoformat()
                    }

                    supabase.table("document_embeddings").insert(embedding_record).execute()
                    embeddings_created += 1
                    total_embeddings_created += 1

                results.append({
                    "document_id": doc_id,
                    "filename": filename,
                    "status": "success",
                    "chunks_found": len(chunks_data),
                    "embeddings_created": embeddings_created
                })

            except Exception as doc_error:
                logger.error(f"Error processing document {filename}: {doc_error}")
                results.append({
                    "document_id": doc_id,
                    "filename": filename,
                    "status": "error",
                    "error": str(doc_error)
                })

        logger.info(f"✅ Reprocessing complete: {total_embeddings_created} embeddings created")

        return {
            "success": True,
            "client_id": client_id,
            "company_name": company_name,
            "documents_processed": len(results),
            "total_embeddings_created": total_embeddings_created,
            "chunks_sources_checked": list(set(chunks_sources_checked)),
            "results": results
        }

    except Exception as e:
        logger.error(f"Reprocess embeddings failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/populate-embeddings/{client_id}")
async def populate_embeddings_from_chunks(client_id: str):
    """
    SIMPLE endpoint to populate document_embeddings from document_chunks.

    This is the fix for RAG not working - chunks exist but embeddings don't.

    Process:
    1. Read chunks from document_chunks for this client
    2. Generate OpenAI embeddings for each chunk_text
    3. Insert into document_embeddings table (which RAG queries)
    """
    from openai import OpenAI
    import os

    try:
        supabase = get_supabase()
        openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Get client info
        client = supabase.table("clients").select("company_name").eq("client_id", client_id).execute()
        company_name = client.data[0].get("company_name") if client.data else "Unknown"

        logger.info(f"🔄 Populating embeddings for {company_name} ({client_id})")

        # Get chunks from document_chunks
        chunks = supabase.table("document_chunks")\
            .select("id, document_id, chunk_text, chunk_index, client_id")\
            .eq("client_id", client_id)\
            .order("chunk_index")\
            .execute()

        if not chunks.data:
            return {
                "success": False,
                "error": "No chunks found in document_chunks table",
                "client_id": client_id
            }

        logger.info(f"📄 Found {len(chunks.data)} chunks in document_chunks")

        # Get document filenames for metadata
        doc_ids = list(set(c["document_id"] for c in chunks.data))
        docs = supabase.table("document_uploads")\
            .select("id, filename")\
            .in_("id", doc_ids)\
            .execute()

        doc_filenames = {d["id"]: d["filename"] for d in (docs.data or [])}

        embeddings_created = 0
        skipped = 0
        errors = []

        for chunk in chunks.data:
            document_id = chunk["document_id"]
            chunk_text = chunk["chunk_text"]
            chunk_index = chunk["chunk_index"]
            filename = doc_filenames.get(document_id, "unknown")

            # Check if embedding already exists
            existing = supabase.table("document_embeddings")\
                .select("id")\
                .eq("document_id", document_id)\
                .eq("chunk_index", chunk_index)\
                .execute()

            if existing.data:
                skipped += 1
                continue

            # Generate embedding
            try:
                response = openai_client.embeddings.create(
                    model="text-embedding-ada-002",
                    input=chunk_text[:8000]
                )
                embedding = response.data[0].embedding

                # Insert into document_embeddings
                embedding_record = {
                    "document_id": document_id,
                    "client_id": client_id,
                    "chunk_text": chunk_text,
                    "chunk_index": chunk_index,
                    "embedding": embedding,
                    "metadata": {
                        "filename": filename,
                        "char_count": len(chunk_text),
                        "source": "populate_embeddings_endpoint"
                    },
                    "created_at": datetime.utcnow().isoformat()
                }

                supabase.table("document_embeddings").insert(embedding_record).execute()
                embeddings_created += 1
                logger.info(f"  ✅ Created embedding for chunk {chunk_index} of {filename}")

            except Exception as e:
                error_msg = f"Chunk {chunk_index}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"  ❌ {error_msg}")

        logger.info(f"✅ Populate embeddings complete: {embeddings_created} created, {skipped} skipped")

        return {
            "success": True,
            "client_id": client_id,
            "company_name": company_name,
            "chunks_found": len(chunks.data),
            "embeddings_created": embeddings_created,
            "skipped_existing": skipped,
            "errors": errors
        }

    except Exception as e:
        logger.error(f"Populate embeddings failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@router.post("/sync-embeddings-tables")
async def sync_embeddings_tables():
    """
    One-time sync: Copy embeddings from vector_embeddings to document_embeddings.

    This fixes existing clients where embeddings were created before the dual-write fix.
    The RAG function match_knowledge_embeddings queries document_embeddings,
    but old uploads only wrote to vector_embeddings.

    Process:
    1. Get all rows from vector_embeddings (with chunk data from document_chunks)
    2. For each row, check if it already exists in document_embeddings
    3. If not, insert into document_embeddings
    """
    try:
        supabase = get_supabase()

        logger.info("🔄 Starting embeddings table sync...")

        # Get all vector_embeddings with their chunk data
        vector_embs = supabase.table("vector_embeddings")\
            .select("id, chunk_id, client_id, embedding, document_type, created_at")\
            .execute()

        if not vector_embs.data:
            return {
                "success": True,
                "message": "No embeddings in vector_embeddings to sync",
                "synced": 0
            }

        logger.info(f"Found {len(vector_embs.data)} embeddings in vector_embeddings")

        synced = 0
        skipped = 0
        errors = []

        for ve in vector_embs.data:
            try:
                chunk_id = ve.get("chunk_id")
                client_id = ve.get("client_id")
                embedding = ve.get("embedding")

                if not chunk_id or not embedding:
                    skipped += 1
                    continue

                # Get chunk details
                chunk = supabase.table("document_chunks")\
                    .select("document_id, chunk_text, chunk_index")\
                    .eq("id", chunk_id)\
                    .execute()

                if not chunk.data:
                    skipped += 1
                    continue

                chunk_data = chunk.data[0]
                document_id = chunk_data.get("document_id")
                chunk_text = chunk_data.get("chunk_text")
                chunk_index = chunk_data.get("chunk_index", 0)

                # Check if already exists in document_embeddings
                existing = supabase.table("document_embeddings")\
                    .select("id")\
                    .eq("document_id", document_id)\
                    .eq("chunk_index", chunk_index)\
                    .eq("client_id", client_id)\
                    .execute()

                if existing.data:
                    skipped += 1
                    continue

                # Insert into document_embeddings
                rag_record = {
                    "document_id": document_id,
                    "client_id": client_id,
                    "chunk_text": chunk_text,
                    "chunk_index": chunk_index,
                    "embedding": embedding,
                    "metadata": {
                        "document_type": ve.get("document_type", "unknown"),
                        "char_count": len(chunk_text) if chunk_text else 0,
                        "source": "sync_embeddings_tables"
                    },
                    "created_at": ve.get("created_at") or datetime.utcnow().isoformat()
                }

                supabase.table("document_embeddings").insert(rag_record).execute()
                synced += 1

            except Exception as row_e:
                errors.append(str(row_e))
                if len(errors) > 10:
                    break  # Stop if too many errors

        logger.info(f"✅ Sync complete: {synced} synced, {skipped} skipped, {len(errors)} errors")

        return {
            "success": True,
            "synced": synced,
            "skipped": skipped,
            "errors": errors[:5] if errors else [],
            "total_in_vector_embeddings": len(vector_embs.data)
        }

    except Exception as e:
        logger.error(f"Sync embeddings tables failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }
