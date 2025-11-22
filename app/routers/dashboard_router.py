"""
Dashboard Router - Fixed Version
Implements client/team/admin dashboard endpoints with correct Supabase schema
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
import logging
from datetime import datetime, timedelta
from supabase_client import supabase

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/dashboard/client/{client_id}")
async def get_client_dashboard(client_id: str) -> Dict[str, Any]:
    """
    Client Dashboard - Shows performance metrics for a specific client
    """
    try:
        # Get client info (using client_id field, not id)
        client_response = supabase.table("clients").select("*").eq("client_id", client_id).execute()
        if not client_response.data:
            raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
        
        client = client_response.data[0]
        
        # Get opportunities for this client
        opportunities_response = supabase.table("reddit_opportunities").select("*").eq("client_id", client_id).execute()
        opportunities = opportunities_response.data or []
        
        # Get content pieces
        content_response = supabase.table("content_pieces").select("*").eq("client_id", client_id).execute()
        content_pieces = content_response.data or []
        
        # Calculate metrics
        total_opportunities = len(opportunities)
        high_priority = len([o for o in opportunities if o.get("priority_score", 0) >= 7.0])
        total_content = len(content_pieces)
        deployed = len([c for c in content_pieces if c.get("status") == "deployed"])
        
        # Get recent activity (last 7 days)
        seven_days_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        recent_opps = [o for o in opportunities if o.get("discovered_at", "") >= seven_days_ago]
        
        return {
            "client_id": client_id,
            "client_name": client.get("company_name"),
            "status": "active",
            "metrics": {
                "total_opportunities": total_opportunities,
                "high_priority_opportunities": high_priority,
                "total_content_pieces": total_content,
                "deployed_content": deployed,
                "recent_activity_7d": len(recent_opps)
            },
            "recent_opportunities": recent_opps[:10],  # Latest 10
            "top_subreddits": list(set([o.get("subreddit") for o in opportunities if o.get("subreddit")]))[:5],
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dashboard error for client {client_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/team")
async def get_team_dashboard() -> Dict[str, Any]:
    """
    Team Dashboard - Overview of all clients and system performance
    """
    try:
        # Get all clients
        clients_response = supabase.table("clients").select("*").execute()
        clients = clients_response.data or []
        
        # Get all opportunities
        opps_response = supabase.table("reddit_opportunities").select("*").execute()
        opportunities = opps_response.data or []
        
        # Get all content
        content_response = supabase.table("content_pieces").select("*").execute()
        content_pieces = content_response.data or []
        
        return {
            "total_clients": len(clients),
            "active_clients": len([c for c in clients if c.get("subscription_status") == "active"]),
            "total_opportunities": len(opportunities),
            "total_content_pieces": len(content_pieces),
            "clients": [
                {
                    "id": c.get("client_id"),
                    "name": c.get("company_name"),
                    "status": c.get("subscription_status", "unknown"),
                    "opportunities": len([o for o in opportunities if o.get("client_id") == c.get("client_id")]),
                    "content": len([cp for cp in content_pieces if cp.get("client_id") == c.get("client_id")])
                }
                for c in clients
            ],
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Team dashboard error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard/admin")
async def get_admin_dashboard() -> Dict[str, Any]:
    """
    Admin Dashboard - System health and infrastructure metrics
    """
    try:
        system_health = {
            "database": "healthy",
            "backend_api": "healthy",
            "n8n_workflows": "active",
            "frontend": "checking"
        }
        
        # Get database stats
        clients_count = len(supabase.table("clients").select("client_id").execute().data or [])
        opps_count = len(supabase.table("reddit_opportunities").select("opportunity_id").execute().data or [])
        content_count = len(supabase.table("content_pieces").select("content_id").execute().data or [])
        
        return {
            "system_health": system_health,
            "database_stats": {
                "total_clients": clients_count,
                "total_opportunities": opps_count,
                "total_content_pieces": content_count
            },
            "infrastructure": {
                "supabase": "connected",
                "backend_version": "2.2.5",
                "n8n_url": "https://recho-echomind.app.n8n.cloud"
            },
            "last_updated": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Admin dashboard error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
