"""
Analytics Router - Content delivery and strategy compliance analytics
"""

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
import logging

from content_tracking_service import ContentTrackingService

router = APIRouter(prefix="/analytics", tags=["analytics"])
logger = logging.getLogger(__name__)


class ContentUsageUpdate(BaseModel):
    """Model for marking content as used/skipped"""
    content_id: str = Field(..., description="UUID of content_delivered record")
    status: str = Field(..., description="'used' or 'skipped'")
    reddit_post_url: Optional[str] = Field(None, description="URL of actual Reddit post")
    marked_by: Optional[str] = Field(None, description="User who marked it")


class DeliverySummaryResponse(BaseModel):
    """Response model for delivery summary"""
    period_start: str
    period_end: str
    total_delivered: int
    monday_deliveries: int
    thursday_deliveries: int
    
    # Content type metrics
    replies: int
    posts: int
    reply_percentage: float
    post_percentage: float
    
    # Brand mention metrics
    brand_mentions: int
    brand_mention_percentage: float
    
    # Product mention metrics
    product_mentions: int
    product_mention_percentage: float
    
    # Usage metrics
    used: int
    skipped: int
    pending: int
    usage_rate: float
    
    # Target settings
    target_reply_percentage: Optional[float]
    target_brand_percentage: Optional[float]
    target_product_percentage: Optional[float]
    
    # Variance (compliance)
    reply_variance: Optional[float]
    brand_variance: Optional[float]
    product_variance: Optional[float]
    
    # Scoring
    avg_relevance_score: float
    avg_priority: float
    
    # Top performers
    top_subreddits: List[dict]
    top_products: List[dict]


@router.get("/{client_id}/summary", response_model=DeliverySummaryResponse)
async def get_delivery_summary(
    client_id: str = Path(..., description="Client UUID"),
    days: int = Query(7, ge=1, le=90, description="Number of days to look back")
):
    """
    Get content delivery summary for a client
    
    Returns analytics including:
    - Total pieces delivered (Mon/Thu breakdown)
    - Reply vs post percentages
    - Brand and product mention rates
    - Usage tracking (used/skipped/pending)
    - Strategy compliance (actual vs target)
    - Top performing subreddits and products
    """
    
    try:
        service = ContentTrackingService()
        
        period_end = datetime.utcnow()
        period_start = period_end - timedelta(days=days)
        
        summary = await service.get_delivery_summary(
            client_id=client_id,
            period_start=period_start,
            period_end=period_end
        )
        
        return DeliverySummaryResponse(**summary)
        
    except Exception as e:
        logger.error(f"Error fetching delivery summary for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch summary: {str(e)}")


@router.get("/{client_id}/delivered")
async def get_delivered_content(
    client_id: str = Path(..., description="Client UUID"),
    status: Optional[str] = Query(None, description="Filter by status: delivered/used/skipped"),
    limit: int = Query(50, ge=1, le=200, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset")
):
    """
    Get list of delivered content pieces with filters
    
    Useful for:
    - Reviewing recent deliveries
    - Seeing pending content
    - Tracking what was used vs skipped
    """
    
    try:
        service = ContentTrackingService()
        
        # Build query
        query = service.supabase.table('content_delivered')\
            .select('*')\
            .eq('client_id', client_id)\
            .order('delivery_date', desc=True)\
            .limit(limit)\
            .offset(offset)
        
        if status:
            query = query.eq('status', status)
        
        result = query.execute()
        
        return {
            'content': result.data,
            'count': len(result.data),
            'limit': limit,
            'offset': offset
        }
        
    except Exception as e:
        logger.error(f"Error fetching delivered content for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch content: {str(e)}")


@router.post("/{client_id}/mark-usage")
async def mark_content_usage(
    usage: ContentUsageUpdate,
    client_id: str = Path(..., description="Client UUID")
):
    """
    Mark a content piece as used or skipped
    
    Use this when:
    - Client actually posts the content to Reddit (mark as 'used')
    - Client decides not to use the content (mark as 'skipped')
    
    This enables usage tracking and strategy optimization
    """
    
    try:
        service = ContentTrackingService()
        
        if usage.status == 'used':
            success = await service.mark_content_used(
                content_id=usage.content_id,
                reddit_post_url=usage.reddit_post_url,
                marked_by=usage.marked_by
            )
        elif usage.status == 'skipped':
            success = await service.mark_content_skipped(
                content_id=usage.content_id,
                marked_by=usage.marked_by
            )
        else:
            raise HTTPException(status_code=400, detail="Status must be 'used' or 'skipped'")
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update content status")
        
        return {
            'success': True,
            'content_id': usage.content_id,
            'status': usage.status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error marking content usage: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to mark usage: {str(e)}")


@router.get("/{client_id}/compliance")
async def get_strategy_compliance(
    client_id: str = Path(..., description="Client UUID"),
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze")
):
    """
    Get strategy compliance report
    
    Compares actual delivery metrics vs target slider settings:
    - Reply vs Post compliance
    - Brand mention compliance
    - Product mention compliance
    
    Returns variance scores (positive = over target, negative = under target)
    """
    
    try:
        service = ContentTrackingService()
        
        period_end = datetime.utcnow()
        period_start = period_end - timedelta(days=days)
        
        summary = await service.get_delivery_summary(
            client_id=client_id,
            period_start=period_start,
            period_end=period_end
        )
        
        # Extract compliance metrics
        compliance = {
            'period_days': days,
            'total_delivered': summary['total_delivered'],
            
            'reply_post_compliance': {
                'actual_reply_pct': summary['reply_percentage'],
                'target_reply_pct': summary.get('target_reply_percentage'),
                'variance': summary.get('reply_variance'),
                'in_compliance': abs(summary.get('reply_variance', 0)) <= 10 if summary.get('reply_variance') is not None else None
            },
            
            'brand_mention_compliance': {
                'actual_brand_pct': summary['brand_mention_percentage'],
                'target_brand_pct': summary.get('target_brand_percentage'),
                'variance': summary.get('brand_variance'),
                'in_compliance': abs(summary.get('brand_variance', 0)) <= 10 if summary.get('brand_variance') is not None else None
            },
            
            'product_mention_compliance': {
                'actual_product_pct': summary['product_mention_percentage'],
                'target_product_pct': summary.get('target_product_percentage'),
                'variance': summary.get('product_variance'),
                'in_compliance': abs(summary.get('product_variance', 0)) <= 10 if summary.get('product_variance') is not None else None
            },
            
            'overall_compliance_score': None  # Will be calculated
        }
        
        # Calculate overall compliance score (0-100)
        variances = [
            abs(compliance['reply_post_compliance']['variance'] or 0),
            abs(compliance['brand_mention_compliance']['variance'] or 0),
            abs(compliance['product_mention_compliance']['variance'] or 0)
        ]
        
        if any(v is not None for v in variances):
            avg_variance = sum(v for v in variances if v is not None) / len([v for v in variances if v is not None])
            compliance['overall_compliance_score'] = max(0, 100 - avg_variance)
        
        return compliance
        
    except Exception as e:
        logger.error(f"Error fetching compliance data for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch compliance: {str(e)}")


@router.get("/{client_id}/weekly-breakdown")
async def get_weekly_breakdown(
    client_id: str = Path(..., description="Client UUID"),
    weeks: int = Query(4, ge=1, le=12, description="Number of weeks to show")
):
    """
    Get week-by-week breakdown of content delivery
    
    Shows trends over time:
    - Delivery counts per week
    - Reply/post ratios
    - Brand/product mention trends
    - Usage rates
    """
    
    try:
        service = ContentTrackingService()
        
        weekly_data = []
        
        for week_offset in range(weeks):
            period_end = datetime.utcnow() - timedelta(weeks=week_offset)
            period_start = period_end - timedelta(weeks=1)
            
            summary = await service.get_delivery_summary(
                client_id=client_id,
                period_start=period_start,
                period_end=period_end
            )
            
            weekly_data.append({
                'week_start': period_start.strftime('%Y-%m-%d'),
                'week_end': period_end.strftime('%Y-%m-%d'),
                'total_delivered': summary['total_delivered'],
                'reply_percentage': summary['reply_percentage'],
                'brand_mention_percentage': summary['brand_mention_percentage'],
                'product_mention_percentage': summary['product_mention_percentage'],
                'usage_rate': summary['usage_rate']
            })
        
        # Reverse to show oldest to newest
        weekly_data.reverse()
        
        return {
            'weeks': weekly_data,
            'total_weeks': weeks
        }
        
    except Exception as e:
        logger.error(f"Error fetching weekly breakdown for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch breakdown: {str(e)}")


@router.post("/{client_id}/compute-summary")
async def trigger_summary_computation(
    client_id: str = Path(..., description="Client UUID"),
    period_type: str = Query('week', description="Period type: week/month/all-time")
):
    """
    Manually trigger analytics summary computation
    
    This is normally done automatically after each delivery,
    but can be triggered manually to refresh cached summaries
    """
    
    try:
        service = ContentTrackingService()
        
        success = await service.compute_and_store_summary(
            client_id=client_id,
            period_type=period_type
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to compute summary")
        
        return {
            'success': True,
            'client_id': client_id,
            'period_type': period_type,
            'computed_at': datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error computing summary for {client_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to compute summary: {str(e)}")
