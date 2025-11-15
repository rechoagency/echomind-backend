"""
Dashboard API Router
Provides endpoints for client dashboard:
- List all clients
- Client metrics and analytics
- Opportunity management
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

supabase = None

def get_supabase():
    global supabase
    if supabase is None:
        from supabase_client import get_supabase_client
        supabase = get_supabase_client()
    return supabase


@router.get("/clients")
async def list_clients(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0)
):
    """
    List all clients with summary metrics
    """
    try:
        supabase = get_supabase()
        
        # Get clients
        query = supabase.table("clients").select("*").order("created_at", desc=True)
        
        if status:
            query = query.eq("subscription_status", status)
        
        query = query.range(offset, offset + limit - 1)
        clients_result = query.execute()
        
        if not clients_result.data:
            return {
                "success": True,
                "clients": [],
                "total": 0
            }
        
        # Enrich with metrics
        enriched_clients = []
        
        for client in clients_result.data:
            client_id = client["client_id"]
            
            # Get opportunity count
            opp_count = supabase.table("opportunities")\
                .select("id", count="exact")\
                .eq("client_id", client_id)\
                .execute()
            
            # Get document count
            doc_count = supabase.table("document_uploads")\
                .select("id", count="exact")\
                .eq("client_id", client_id)\
                .execute()
            
            # Get high-priority opportunity count
            high_priority = supabase.table("opportunities")\
                .select("id", count="exact")\
                .eq("client_id", client_id)\
                .in_("priority", ["URGENT", "HIGH"])\
                .execute()
            
            enriched_clients.append({
                **client,
                "metrics": {
                    "total_opportunities": len(opp_count.data) if opp_count.data else 0,
                    "high_priority_opportunities": len(high_priority.data) if high_priority.data else 0,
                    "documents_uploaded": len(doc_count.data) if doc_count.data else 0,
                    "days_active": (datetime.utcnow() - datetime.fromisoformat(client["created_at"].replace("Z", "+00:00"))).days
                }
            })
        
        return {
            "success": True,
            "clients": enriched_clients,
            "total": len(enriched_clients)
        }
        
    except Exception as e:
        logger.error(f"Error listing clients: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/client/{client_id}/metrics")
async def get_client_metrics(client_id: str):
    """
    Get detailed metrics for a specific client
    """
    try:
        supabase = get_supabase()
        
        # Get client
        client = supabase.table("clients").select("*").eq("client_id", client_id).execute()
        if not client.data:
            raise HTTPException(status_code=404, detail="Client not found")
        
        # Opportunities by priority
        priorities = {}
        for priority in ["URGENT", "HIGH", "MEDIUM", "LOW"]:
            count = supabase.table("opportunities")\
                .select("id", count="exact")\
                .eq("client_id", client_id)\
                .eq("priority", priority)\
                .execute()
            priorities[priority.lower()] = len(count.data) if count.data else 0
        
        # Average scores
        opportunities = supabase.table("opportunities")\
            .select("buying_intent_score, pain_point_score, organic_lift_potential, opportunity_score")\
            .eq("client_id", client_id)\
            .not_.is_("opportunity_score", "null")\
            .execute()
        
        avg_scores = {
            "buying_intent": 0,
            "pain_point": 0,
            "organic_lift": 0,
            "composite": 0
        }
        
        if opportunities.data:
            total = len(opportunities.data)
            avg_scores = {
                "buying_intent": round(sum(o.get("buying_intent_score", 0) for o in opportunities.data) / total, 1),
                "pain_point": round(sum(o.get("pain_point_score", 0) for o in opportunities.data) / total, 1),
                "organic_lift": round(sum(o.get("organic_lift_potential", 0) for o in opportunities.data) / total, 1),
                "composite": round(sum(o.get("opportunity_score", 0) for o in opportunities.data) / total, 1)
            }
        
        # Product matchback success rate
        matched = supabase.table("opportunities")\
            .select("id", count="exact")\
            .eq("client_id", client_id)\
            .not_.is_("product_matches", "null")\
            .execute()
        
        total_opps = supabase.table("opportunities")\
            .select("id", count="exact")\
            .eq("client_id", client_id)\
            .execute()
        
        matchback_rate = 0
        if total_opps.data:
            matchback_rate = round((len(matched.data) / len(total_opps.data)) * 100, 1) if matched.data else 0
        
        # Subreddit distribution
        subreddits = supabase.table("opportunities")\
            .select("subreddit")\
            .eq("client_id", client_id)\
            .execute()
        
        subreddit_counts = {}
        if subreddits.data:
            for opp in subreddits.data:
                sub = opp.get("subreddit", "unknown")
                subreddit_counts[sub] = subreddit_counts.get(sub, 0) + 1
        
        # Sort by count
        top_subreddits = sorted(subreddit_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            "success": True,
            "client": client.data[0],
            "metrics": {
                "opportunities_by_priority": priorities,
                "average_scores": avg_scores,
                "product_matchback_rate": matchback_rate,
                "top_subreddits": [{"name": s[0], "count": s[1]} for s in top_subreddits],
                "total_opportunities": len(total_opps.data) if total_opps.data else 0
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting client metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/client/{client_id}/opportunities")
async def get_client_opportunities(
    client_id: str,
    priority: Optional[str] = Query(None, description="Filter by priority"),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0)
):
    """
    Get opportunities for a client with filtering
    """
    try:
        supabase = get_supabase()
        
        # Build query
        query = supabase.table("opportunities")\
            .select("*")\
            .eq("client_id", client_id)\
            .order("opportunity_score", desc=True)
        
        if priority:
            query = query.eq("priority", priority.upper())
        
        query = query.range(offset, offset + limit - 1)
        
        opportunities = query.execute()
        
        return {
            "success": True,
            "client_id": client_id,
            "opportunities": opportunities.data if opportunities.data else [],
            "count": len(opportunities.data) if opportunities.data else 0
        }
        
    except Exception as e:
        logger.error(f"Error getting opportunities: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/client/{client_id}/calendar")
async def get_client_calendar(client_id: str):
    """
    Get current content calendar for client
    """
    try:
        supabase = get_supabase()
        
        # Get most recent calendar
        calendar = supabase.table("content_calendars")\
            .select("*")\
            .eq("client_id", client_id)\
            .order("created_at", desc=True)\
            .limit(1)\
            .execute()
        
        if not calendar.data:
            return {
                "success": True,
                "calendar": None,
                "message": "No calendar generated yet"
            }
        
        return {
            "success": True,
            "calendar": calendar.data[0]
        }
        
    except Exception as e:
        logger.error(f"Error getting calendar: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_dashboard_stats():
    """
    Get overall dashboard statistics
    """
    try:
        supabase = get_supabase()
        
        # Total clients
        clients = supabase.table("clients").select("client_id", count="exact").execute()
        
        # Active clients
        active = supabase.table("clients")\
            .select("client_id", count="exact")\
            .eq("subscription_status", "active")\
            .execute()
        
        # Total opportunities
        opportunities = supabase.table("opportunities").select("id", count="exact").execute()
        
        # High priority opportunities
        high_priority = supabase.table("opportunities")\
            .select("id", count="exact")\
            .in_("priority", ["URGENT", "HIGH"])\
            .execute()
        
        return {
            "success": True,
            "stats": {
                "total_clients": len(clients.data) if clients.data else 0,
                "active_clients": len(active.data) if active.data else 0,
                "total_opportunities": len(opportunities.data) if opportunities.data else 0,
                "high_priority_opportunities": len(high_priority.data) if high_priority.data else 0
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting dashboard stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
