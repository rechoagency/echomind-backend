"""
Admin Router - Client Management Operations
Includes: Delete clients with confirmation, bulk operations
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List
import logging
import os
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


@router.post("/test-content-generation")
async def test_content_generation_sync():
    """
    Synchronous test endpoint for content generation.
    Runs content generation directly (not in background) so we can see errors.

    This is for debugging only - returns full result including any errors.
    """
    import traceback

    try:
        logger.info("🧪 TEST CONTENT GENERATION - Starting synchronous test")

        # Import the worker
        from workers.content_generation_worker import ContentGenerationWorker

        # Create worker instance
        worker = ContentGenerationWorker()

        # Run synchronously with Mira client
        client_id = "3cee3b35-33e2-4a0c-8a78-dbccffbca434"
        logger.info(f"🧪 Calling process_all_opportunities for client {client_id}")

        result = worker.process_all_opportunities(
            client_id=client_id,
            regenerate=False,
            only_with_products=False
        )

        logger.info(f"🧪 Result: {result}")

        return {
            "success": True,
            "test_type": "synchronous_content_generation",
            "client_id": client_id,
            "result": result
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
