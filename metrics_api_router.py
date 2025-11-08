"""
EchoMind - Metrics API Router

FastAPI routes for accessing all advanced metrics:
- Account karma & health
- Keyword velocity
- Subreddit cluster analytics
- Sentiment heatmaps
- Thread authority scores
- Topic velocity
- Moderation monitoring

All endpoints require client authentication via API key or JWT token.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from supabase_client import get_supabase_client
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


# ============================================================================
# ACCOUNT KARMA & HEALTH ENDPOINTS
# ============================================================================

@router.get("/karma/total/{client_id}")
async def get_total_karma(client_id: str):
    """
    Get total karma across all Reddit accounts for a client.
    
    Returns:
    - total_karma: Sum of all account karma
    - account_count: Number of accounts
    - avg_karma_per_account: Average karma
    - accounts: List of accounts with individual karma
    """
    supabase = get_supabase_client()
    
    try:
        # Get all accounts for client
        accounts_response = supabase.table('reddit_accounts').select(
            'account_id, username, post_karma, comment_karma, total_karma, last_karma_sync'
        ).eq('client_id', client_id).execute()
        
        accounts = accounts_response.data
        
        if not accounts:
            raise HTTPException(status_code=404, detail="No accounts found for client")
        
        total_karma = sum(a['total_karma'] for a in accounts)
        avg_karma = total_karma / len(accounts)
        
        return {
            'client_id': client_id,
            'total_karma': total_karma,
            'account_count': len(accounts),
            'avg_karma_per_account': round(avg_karma, 2),
            'accounts': accounts
        }
        
    except Exception as e:
        logger.error(f"Error fetching total karma: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/karma/trendline/{account_id}")
async def get_karma_trendline(
    account_id: str,
    days: int = Query(30, description="Number of days of history to return")
):
    """
    Get historical karma trendline for a specific Reddit account.
    
    Returns daily karma snapshots for chart visualization.
    """
    supabase = get_supabase_client()
    
    try:
        start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Get karma history
        history_response = supabase.table('reddit_account_karma_history').select(
            'snapshot_date, total_karma, post_karma, comment_karma, karma_gained_today'
        ).eq('account_id', account_id).gte(
            'snapshot_date', start_date
        ).order('snapshot_date', desc=False).execute()
        
        history = history_response.data
        
        if not history:
            raise HTTPException(status_code=404, detail="No karma history found")
        
        # Calculate trend (increasing/decreasing)
        if len(history) >= 2:
            first_karma = history[0]['total_karma']
            last_karma = history[-1]['total_karma']
            karma_change = last_karma - first_karma
            trend = 'increasing' if karma_change > 0 else 'decreasing' if karma_change < 0 else 'stable'
        else:
            karma_change = 0
            trend = 'insufficient_data'
        
        return {
            'account_id': account_id,
            'days_analyzed': days,
            'data_points': len(history),
            'karma_change': karma_change,
            'trend': trend,
            'history': history
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching karma trendline: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/karma/shadowban-check/{account_id}")
async def check_shadowban_status(account_id: str):
    """
    Get shadowban detection status for a Reddit account.
    
    Returns:
    - is_shadowbanned: Boolean
    - last_check: Timestamp of last shadowban check
    - detection_method: How shadowban was detected
    """
    supabase = get_supabase_client()
    
    try:
        account_response = supabase.table('reddit_accounts').select(
            'username, is_shadowbanned, shadowban_detected_at, last_shadowban_check'
        ).eq('account_id', account_id).single().execute()
        
        account = account_response.data
        
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        
        return {
            'account_id': account_id,
            'username': account['username'],
            'is_shadowbanned': account.get('is_shadowbanned', False),
            'shadowban_detected_at': account.get('shadowban_detected_at'),
            'last_check': account.get('last_shadowban_check'),
            'status': 'shadowbanned' if account.get('is_shadowbanned') else 'healthy'
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking shadowban status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# KEYWORD VELOCITY ENDPOINTS
# ============================================================================

@router.get("/keywords/velocity/{client_id}")
async def get_keyword_velocity_dashboard(client_id: str):
    """
    Get keyword velocity dashboard with % change for all tracked keywords.
    
    Shows trending keywords with their week-over-week % change.
    Example: "lab testing" +55%, "quality assurance" +32%
    """
    supabase = get_supabase_client()
    
    try:
        # Get latest velocity data
        velocity_response = supabase.table('keyword_velocity_dashboard').select(
            '*'
        ).eq('client_id', client_id).order(
            'percent_change', desc=True
        ).execute()
        
        velocity_data = velocity_response.data
        
        # Categorize keywords
        trending_up = [k for k in velocity_data if k['percent_change'] > 20]
        trending_down = [k for k in velocity_data if k['percent_change'] < -20]
        stable = [k for k in velocity_data if -20 <= k['percent_change'] <= 20]
        
        return {
            'client_id': client_id,
            'total_keywords_tracked': len(velocity_data),
            'trending_up': len(trending_up),
            'trending_down': len(trending_down),
            'stable': len(stable),
            'keywords': velocity_data,
            'top_trending': trending_up[:10],  # Top 10 trending up
            'top_declining': sorted(trending_down, key=lambda x: x['percent_change'])[:10]  # Top 10 declining
        }
        
    except Exception as e:
        logger.error(f"Error fetching keyword velocity: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/keywords/trending")
async def get_trending_keywords(
    client_id: Optional[str] = Query(None),
    hours: int = Query(24, description="Time window for trending analysis")
):
    """
    Get real-time trending keywords.
    
    Returns keywords with highest velocity in the specified time window.
    """
    supabase = get_supabase_client()
    
    try:
        # Use pre-computed trending_keywords_realtime view
        query = supabase.table('trending_keywords_realtime').select('*')
        
        if client_id:
            query = query.eq('client_id', client_id)
        
        query = query.order('mentions_today', desc=True).limit(20)
        
        trending_response = query.execute()
        trending = trending_response.data
        
        return {
            'time_window_hours': hours,
            'trending_keywords': trending,
            'count': len(trending)
        }
        
    except Exception as e:
        logger.error(f"Error fetching trending keywords: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/keywords/mentions/{keyword}")
async def get_keyword_mentions(
    keyword: str,
    client_id: Optional[str] = Query(None),
    days: int = Query(30, description="Number of days to look back")
):
    """
    Get all mentions of a specific keyword with context.
    
    Returns threads/comments where keyword was mentioned.
    """
    supabase = get_supabase_client()
    
    try:
        start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        query = supabase.table('keyword_mention_instances').select(
            '*'
        ).eq('keyword_text', keyword).gte('mentioned_at', start_date)
        
        if client_id:
            query = query.eq('client_id', client_id)
        
        query = query.order('mentioned_at', desc=True)
        
        mentions_response = query.execute()
        mentions = mentions_response.data
        
        return {
            'keyword': keyword,
            'total_mentions': len(mentions),
            'days_analyzed': days,
            'mentions': mentions
        }
        
    except Exception as e:
        logger.error(f"Error fetching keyword mentions: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CLUSTER ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/clusters/performance/{client_id}")
async def get_cluster_performance_comparison(client_id: str):
    """
    Get performance comparison across all subreddit clusters.
    
    Shows which clusters are performing best and which need attention.
    """
    supabase = get_supabase_client()
    
    try:
        # Get latest cluster performance
        clusters_response = supabase.table('cluster_comparison_dashboard').select(
            '*'
        ).eq('client_id', client_id).execute()
        
        clusters = clusters_response.data
        
        # Sort by health score
        clusters_sorted = sorted(clusters, key=lambda x: x.get('cluster_health_score', 0), reverse=True)
        
        return {
            'client_id': client_id,
            'total_clusters': len(clusters),
            'clusters': clusters_sorted,
            'best_performing': clusters_sorted[0] if clusters_sorted else None,
            'needs_attention': [c for c in clusters if c.get('cluster_health_score', 0) < 50]
        }
        
    except Exception as e:
        logger.error(f"Error fetching cluster performance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/clusters/top-subreddits/{cluster_id}")
async def get_top_subreddits_in_cluster(cluster_id: str, limit: int = Query(10)):
    """
    Get top performing subreddits within a specific cluster.
    """
    supabase = get_supabase_client()
    
    try:
        subreddits_response = supabase.table('subreddit_performance_detail').select(
            '*'
        ).eq('cluster_id', cluster_id).order(
            'effectiveness_score', desc=True
        ).limit(limit).execute()
        
        subreddits = subreddits_response.data
        
        return {
            'cluster_id': cluster_id,
            'subreddit_count': len(subreddits),
            'top_subreddits': subreddits
        }
        
    except Exception as e:
        logger.error(f"Error fetching top subreddits: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SENTIMENT HEATMAP ENDPOINTS
# ============================================================================

@router.get("/sentiment/heatmap/{client_id}")
async def get_sentiment_heatmap(
    client_id: str,
    granularity: str = Query('daily', description="'daily' or 'hourly'"),
    days: int = Query(7, description="Number of days of data")
):
    """
    Get sentiment heatmap data for visualization.
    
    Returns sentiment scores by subreddit and time for heatmap charts.
    """
    supabase = get_supabase_client()
    
    try:
        start_date = (datetime.utcnow() - timedelta(days=days)).date().isoformat()
        
        if granularity == 'daily':
            view_name = 'daily_sentiment_heatmap'
        else:
            view_name = 'hourly_sentiment_heatmap'
        
        heatmap_response = supabase.table(view_name).select(
            '*'
        ).eq('client_id', client_id).gte(
            'date' if granularity == 'daily' else 'hour',
            start_date
        ).execute()
        
        heatmap_data = heatmap_response.data
        
        return {
            'client_id': client_id,
            'granularity': granularity,
            'days_analyzed': days,
            'data_points': len(heatmap_data),
            'heatmap_data': heatmap_data
        }
        
    except Exception as e:
        logger.error(f"Error fetching sentiment heatmap: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sentiment/trends")
async def get_sentiment_trends(
    client_id: Optional[str] = Query(None),
    days: int = Query(7)
):
    """
    Get 7-day sentiment trends showing how sentiment is evolving.
    """
    supabase = get_supabase_client()
    
    try:
        query = supabase.table('sentiment_trends_7day').select('*')
        
        if client_id:
            query = query.eq('client_id', client_id)
        
        trends_response = query.execute()
        trends = trends_response.data
        
        return {
            'days_analyzed': days,
            'trends': trends
        }
        
    except Exception as e:
        logger.error(f"Error fetching sentiment trends: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AUTHORITY SCORING ENDPOINTS
# ============================================================================

@router.get("/authority/dashboard/{client_id}")
async def get_authority_dashboard(client_id: str):
    """
    Get authority scoring dashboard with top comment frequency and position metrics.
    """
    supabase = get_supabase_client()
    
    try:
        # Get latest weekly summary
        summary_response = supabase.table('authority_performance_summary').select(
            '*'
        ).eq('client_id', client_id).order(
            'week_start_date', desc=True
        ).limit(1).execute()
        
        if not summary_response.data:
            raise HTTPException(status_code=404, detail="No authority data found")
        
        summary = summary_response.data[0]
        
        # Get subreddit breakdown
        subreddit_response = supabase.table('subreddit_authority_breakdown').select(
            '*'
        ).eq('client_id', client_id).order(
            'avg_authority_score', desc=True
        ).execute()
        
        subreddits = subreddit_response.data
        
        return {
            'client_id': client_id,
            'summary': summary,
            'subreddit_performance': subreddits,
            'top_performing_subreddits': subreddits[:5] if subreddits else []
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching authority dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/authority/top-comments")
async def get_top_comment_frequency(
    client_id: Optional[str] = Query(None),
    days: int = Query(30)
):
    """
    Get frequency analysis of top comment achievements.
    
    Shows how often user gets position 1, 2, 3, etc.
    """
    supabase = get_supabase_client()
    
    try:
        start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        query = supabase.table('top_comment_frequency_analysis').select(
            '*'
        ).gte('week_start_date', start_date)
        
        if client_id:
            query = query.eq('client_id', client_id)
        
        frequency_response = query.execute()
        frequency_data = frequency_response.data
        
        return {
            'days_analyzed': days,
            'frequency_analysis': frequency_data
        }
        
    except Exception as e:
        logger.error(f"Error fetching top comment frequency: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TOPIC VELOCITY ENDPOINTS
# ============================================================================

@router.get("/topics/trending")
async def get_trending_topics(
    client_id: Optional[str] = Query(None),
    limit: int = Query(20)
):
    """
    Get trending topics with highest velocity.
    
    Shows topics that are spiking in mentions right now.
    """
    supabase = get_supabase_client()
    
    try:
        query = supabase.table('trending_topics_dashboard').select('*')
        
        if client_id:
            query = query.eq('client_id', client_id)
        
        query = query.order('velocity_score', desc=True).limit(limit)
        
        trending_response = query.execute()
        trending = trending_response.data
        
        return {
            'trending_topics': trending,
            'count': len(trending)
        }
        
    except Exception as e:
        logger.error(f"Error fetching trending topics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/topics/recommendations")
async def get_posting_recommendations(client_id: str):
    """
    Get AI-powered posting recommendations based on topic velocity.
    
    Tells you "post about X in r/Y NOW" based on spiking topics.
    """
    supabase = get_supabase_client()
    
    try:
        recommendations_response = supabase.table('post_timing_recommendations').select(
            '*'
        ).eq('client_id', client_id).eq(
            'recommendation_status', 'active'
        ).order('priority_score', desc=True).execute()
        
        recommendations = recommendations_response.data
        
        # Categorize by urgency
        urgent = [r for r in recommendations if r.get('priority_score', 0) > 80]
        high_priority = [r for r in recommendations if 60 < r.get('priority_score', 0) <= 80]
        moderate = [r for r in recommendations if r.get('priority_score', 0) <= 60]
        
        return {
            'client_id': client_id,
            'total_recommendations': len(recommendations),
            'urgent': urgent,
            'high_priority': high_priority,
            'moderate': moderate,
            'all_recommendations': recommendations
        }
        
    except Exception as e:
        logger.error(f"Error fetching posting recommendations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MODERATION MONITORING ENDPOINTS
# ============================================================================

@router.get("/moderation/risks/{client_id}")
async def get_moderation_risks(client_id: str):
    """
    Get active moderation risk alerts.
    
    Shows accounts at risk of bans, high removal rates, etc.
    """
    supabase = get_supabase_client()
    
    try:
        # Get active risk alerts (last 7 days)
        week_start = (datetime.utcnow() - timedelta(days=7)).isoformat()
        
        risks_response = supabase.table('moderation_risk_alerts').select(
            '*'
        ).eq('client_id', client_id).gte(
            'detected_at', week_start
        ).order('detected_at', desc=True).execute()
        
        risks = risks_response.data
        
        # Categorize by severity
        critical = [r for r in risks if r['severity'] == 'critical']
        high = [r for r in risks if r['severity'] == 'high']
        medium = [r for r in risks if r['severity'] == 'medium']
        
        return {
            'client_id': client_id,
            'total_risks': len(risks),
            'critical_count': len(critical),
            'high_count': len(high),
            'medium_count': len(medium),
            'critical_risks': critical,
            'high_risks': high,
            'all_risks': risks
        }
        
    except Exception as e:
        logger.error(f"Error fetching moderation risks: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/moderation/health/{subreddit}")
async def get_subreddit_health(
    subreddit: str,
    client_id: Optional[str] = Query(None)
):
    """
    Get community health metrics for a specific subreddit.
    
    Shows removal rates, engagement health, sentiment, etc.
    """
    supabase = get_supabase_client()
    
    try:
        query = supabase.table('subreddit_health_metrics').select('*').eq(
            'subreddit', subreddit
        )
        
        if client_id:
            query = query.eq('client_id', client_id)
        
        query = query.order('metric_date', desc=True).limit(30)  # Last 30 days
        
        health_response = query.execute()
        health_data = health_response.data
        
        if not health_data:
            raise HTTPException(status_code=404, detail=f"No health data for r/{subreddit}")
        
        # Get latest health score
        latest = health_data[0]
        
        # Calculate trend
        if len(health_data) >= 7:
            week_ago = health_data[6]
            health_trend = latest['health_score'] - week_ago['health_score']
            trend_direction = 'improving' if health_trend > 5 else 'declining' if health_trend < -5 else 'stable'
        else:
            health_trend = 0
            trend_direction = 'insufficient_data'
        
        return {
            'subreddit': subreddit,
            'latest_health': latest,
            'health_trend': round(health_trend, 2),
            'trend_direction': trend_direction,
            'history': health_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching subreddit health: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/moderation/removals/{client_id}")
async def get_removal_history(
    client_id: str,
    days: int = Query(30, description="Number of days to look back")
):
    """
    Get content removal history for a client.
    
    Shows all removed comments/posts with timing and reason.
    """
    supabase = get_supabase_client()
    
    try:
        start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        removals_response = supabase.table('content_removal_tracking').select(
            '*'
        ).eq('client_id', client_id).gte(
            'removed_at', start_date
        ).order('removed_at', desc=True).execute()
        
        removals = removals_response.data
        
        # Analyze removal patterns
        by_subreddit = {}
        by_type = {}
        
        for removal in removals:
            subreddit = removal['subreddit']
            removal_type = removal.get('removal_type', 'unknown')
            
            by_subreddit[subreddit] = by_subreddit.get(subreddit, 0) + 1
            by_type[removal_type] = by_type.get(removal_type, 0) + 1
        
        return {
            'client_id': client_id,
            'days_analyzed': days,
            'total_removals': len(removals),
            'by_subreddit': by_subreddit,
            'by_removal_type': by_type,
            'removals': removals
        }
        
    except Exception as e:
        logger.error(f"Error fetching removal history: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/health")
async def metrics_health_check():
    """Health check endpoint to verify metrics API is operational."""
    return {
        'status': 'healthy',
        'service': 'EchoMind Metrics API',
        'timestamp': datetime.utcnow().isoformat(),
        'endpoints_available': 18
    }
