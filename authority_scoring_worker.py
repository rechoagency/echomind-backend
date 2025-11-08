"""
EchoMind - Thread Authority Scoring Worker

Tracks comment position within threads, calculates authority metrics,
and identifies high-authority commenting patterns.

Celery Tasks:
- update_thread_authority_metrics: Real-time authority calculation when comment posted
- calculate_weekly_authority_summary: Weekly aggregation of authority performance
- identify_high_authority_threads: Find threads where user has top comment
- track_comment_position_improvements: Analyze position trends over time

Schedule:
- Real-time: Triggered after each comment post (via Reddit Answers/Pro automation)
- Weekly Sunday 10 AM: Authority summary calculation
- Daily 12 PM: High authority thread identification
- Weekly Monday 11 AM: Position improvement tracking
"""

from celery_app import celery_app
from supabase_client import get_supabase_client
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Any, Optional
import statistics

logger = logging.getLogger(__name__)


@celery_app.task(name='update_thread_authority_metrics')
def update_thread_authority_metrics(comment_id: str, thread_url: str, 
                                   client_id: str, subreddit: str):
    """
    Calculate and store authority metrics for a newly posted comment.
    
    Called immediately after posting a comment via Reddit Answers/Pro.
    
    Metrics calculated:
    - comment_position: Position in thread (1 = first comment, 2 = second, etc.)
    - total_comments_in_thread: Total comments at time of posting
    - is_top_comment: Boolean if position = 1
    - time_since_thread_created: Minutes between thread creation and comment
    - authority_score: Composite score (0-10) based on position, timing, engagement
    
    Args:
        comment_id: Reddit comment ID
        thread_url: Full URL to the Reddit thread
        client_id: Client who posted the comment
        subreddit: Subreddit name
    """
    logger.info(f"Calculating authority metrics for comment {comment_id}")
    supabase = get_supabase_client()
    
    try:
        # Get comment details from database
        comment_response = supabase.table('reddit_comments').select(
            'created_at, thread_id, account_id'
        ).eq('comment_id', comment_id).single().execute()
        
        if not comment_response.data:
            logger.error(f"Comment {comment_id} not found in database")
            return {'status': 'error', 'message': 'Comment not found'}
        
        comment_data = comment_response.data
        thread_id = comment_data['thread_id']
        account_id = comment_data['account_id']
        commented_at = datetime.fromisoformat(comment_data['created_at'])
        
        # Get thread details
        thread_response = supabase.table('reddit_threads').select(
            'created_at, comment_count'
        ).eq('thread_id', thread_id).single().execute()
        
        if not thread_response.data:
            logger.warning(f"Thread {thread_id} not found, using defaults")
            thread_created_at = commented_at - timedelta(hours=1)  # Default assumption
            total_comments = 1
        else:
            thread_data = thread_response.data
            thread_created_at = datetime.fromisoformat(thread_data['created_at'])
            total_comments = thread_data['comment_count']
        
        # Calculate position (query all comments in this thread, ordered by creation time)
        thread_comments_response = supabase.table('reddit_comments').select(
            'comment_id, created_at'
        ).eq('thread_id', thread_id).order('created_at', desc=False).execute()
        
        thread_comments = thread_comments_response.data
        comment_position = next(
            (idx + 1 for idx, c in enumerate(thread_comments) if c['comment_id'] == comment_id),
            1  # Default to position 1 if not found
        )
        
        # Calculate timing
        time_since_thread_created_minutes = (commented_at - thread_created_at).total_seconds() / 60
        
        # Determine if top comment
        is_top_comment = (comment_position == 1)
        
        # Calculate authority score (0-10)
        authority_score = calculate_authority_score(
            comment_position, 
            total_comments, 
            time_since_thread_created_minutes
        )
        
        # Store authority metrics
        authority_record = {
            'comment_id': comment_id,
            'thread_id': thread_id,
            'client_id': client_id,
            'account_id': account_id,
            'subreddit': subreddit,
            'comment_position': comment_position,
            'total_comments_in_thread': total_comments,
            'is_top_comment': is_top_comment,
            'time_since_thread_created_minutes': round(time_since_thread_created_minutes, 2),
            'authority_score': authority_score,
            'commented_at': commented_at.isoformat(),
            'created_at': datetime.utcnow().isoformat()
        }
        
        supabase.table('thread_authority_metrics').insert(authority_record).execute()
        
        logger.info(f"Authority metrics stored - Position: {comment_position}/{total_comments}, "
                   f"Score: {authority_score:.2f}, Top: {is_top_comment}")
        
        return {
            'status': 'success',
            'comment_id': comment_id,
            'position': comment_position,
            'authority_score': authority_score,
            'is_top_comment': is_top_comment
        }
        
    except Exception as e:
        logger.error(f"Error calculating authority metrics: {str(e)}")
        raise


def calculate_authority_score(position: int, total_comments: int, 
                              time_since_created_minutes: float) -> float:
    """
    Calculate authority score (0-10) based on comment position, timing, and context.
    
    Scoring logic:
    - Position 1 (top comment): 10.0 points
    - Position 2-3: 8.0-9.0 points
    - Position 4-10: 5.0-7.0 points
    - Position 11+: 2.0-4.0 points
    - Early timing bonus (within 30 min): +1.0 point
    - Thread activity bonus (100+ comments): +0.5 points
    
    Returns: Float between 0.0 and 10.0
    """
    # Base score from position
    if position == 1:
        base_score = 10.0
    elif position <= 3:
        base_score = 9.0 - (position - 1) * 0.5
    elif position <= 10:
        base_score = 7.0 - (position - 4) * 0.3
    elif position <= 20:
        base_score = 4.0 - (position - 11) * 0.1
    else:
        base_score = 2.0 - min(position - 21, 20) * 0.05  # Gradually decrease
    
    # Timing bonus (early responses get higher authority)
    timing_bonus = 0.0
    if time_since_created_minutes <= 15:
        timing_bonus = 1.0
    elif time_since_created_minutes <= 30:
        timing_bonus = 0.75
    elif time_since_created_minutes <= 60:
        timing_bonus = 0.5
    elif time_since_created_minutes <= 120:
        timing_bonus = 0.25
    
    # Thread activity bonus (high-traffic threads are more competitive)
    activity_bonus = 0.0
    if total_comments >= 100:
        activity_bonus = 0.5
    elif total_comments >= 50:
        activity_bonus = 0.3
    elif total_comments >= 20:
        activity_bonus = 0.1
    
    final_score = base_score + timing_bonus + activity_bonus
    
    # Cap at 10.0
    return min(round(final_score, 2), 10.0)


@celery_app.task(name='calculate_weekly_authority_summary')
def calculate_weekly_authority_summary():
    """
    Calculate weekly authority performance summary for all clients.
    
    Aggregates:
    - Total comments posted
    - Top comment frequency (% of comments that are position 1)
    - Average comment position
    - Average authority score
    - Position distribution (top 3, top 10, 11+)
    - Early response rate (within 30 minutes)
    
    Writes to: authority_performance_summary table
    """
    logger.info("Calculating weekly authority summary")
    supabase = get_supabase_client()
    
    try:
        # Get all active clients
        clients_response = supabase.table('clients').select('client_id').eq('active', True).execute()
        clients = clients_response.data
        
        week_start = datetime.utcnow() - timedelta(days=7)
        
        for client in clients:
            client_id = client['client_id']
            
            # Get all authority metrics for this client in the past week
            metrics_response = supabase.table('thread_authority_metrics').select(
                '*'
            ).eq('client_id', client_id).gte(
                'commented_at', week_start.isoformat()
            ).execute()
            
            metrics = metrics_response.data
            
            if not metrics:
                logger.info(f"No authority metrics for client {client_id} this week")
                continue
            
            # Calculate summary statistics
            total_comments = len(metrics)
            top_comment_count = len([m for m in metrics if m['is_top_comment']])
            top_comment_frequency = (top_comment_count / total_comments * 100) if total_comments > 0 else 0.0
            
            positions = [m['comment_position'] for m in metrics]
            avg_position = statistics.mean(positions)
            median_position = statistics.median(positions)
            
            authority_scores = [m['authority_score'] for m in metrics]
            avg_authority_score = statistics.mean(authority_scores)
            
            # Position distribution
            top_3_count = len([p for p in positions if p <= 3])
            top_10_count = len([p for p in positions if p <= 10])
            beyond_10_count = len([p for p in positions if p > 10])
            
            top_3_pct = (top_3_count / total_comments * 100) if total_comments > 0 else 0.0
            top_10_pct = (top_10_count / total_comments * 100) if total_comments > 0 else 0.0
            
            # Early response rate (within 30 minutes)
            early_responses = len([m for m in metrics if m['time_since_thread_created_minutes'] <= 30])
            early_response_rate = (early_responses / total_comments * 100) if total_comments > 0 else 0.0
            
            # Subreddit breakdown (which subreddits have best authority)
            subreddit_authority = {}
            for metric in metrics:
                subreddit = metric['subreddit']
                if subreddit not in subreddit_authority:
                    subreddit_authority[subreddit] = []
                subreddit_authority[subreddit].append(metric['authority_score'])
            
            best_subreddit = None
            best_subreddit_score = 0.0
            for subreddit, scores in subreddit_authority.items():
                avg_score = statistics.mean(scores)
                if avg_score > best_subreddit_score:
                    best_subreddit = subreddit
                    best_subreddit_score = avg_score
            
            # Store summary
            summary_record = {
                'client_id': client_id,
                'week_start_date': week_start.isoformat(),
                'week_end_date': datetime.utcnow().isoformat(),
                'total_comments': total_comments,
                'top_comment_count': top_comment_count,
                'top_comment_frequency_pct': round(top_comment_frequency, 2),
                'avg_comment_position': round(avg_position, 2),
                'median_comment_position': round(median_position, 2),
                'avg_authority_score': round(avg_authority_score, 2),
                'top_3_position_count': top_3_count,
                'top_3_position_pct': round(top_3_pct, 2),
                'top_10_position_count': top_10_count,
                'top_10_position_pct': round(top_10_pct, 2),
                'beyond_10_position_count': beyond_10_count,
                'early_response_count': early_responses,
                'early_response_rate_pct': round(early_response_rate, 2),
                'best_performing_subreddit': best_subreddit,
                'best_subreddit_avg_authority': round(best_subreddit_score, 2),
                'updated_at': datetime.utcnow().isoformat()
            }
            
            supabase.table('authority_performance_summary').upsert(
                summary_record,
                on_conflict='client_id,week_start_date'
            ).execute()
            
            logger.info(f"Authority summary for {client_id} - "
                       f"{total_comments} comments, {top_comment_frequency:.1f}% top position, "
                       f"avg score: {avg_authority_score:.2f}")
        
        logger.info("Weekly authority summary calculation completed")
        return {'status': 'success', 'clients_processed': len(clients)}
        
    except Exception as e:
        logger.error(f"Error calculating authority summary: {str(e)}")
        raise


@celery_app.task(name='identify_high_authority_threads')
def identify_high_authority_threads():
    """
    Identify threads where user achieved high authority (top 3 position).
    
    Useful for:
    - Understanding what types of threads user performs well in
    - Identifying successful content patterns
    - Prioritizing similar threads in the future
    
    Analyzes:
    - Thread topics and keywords
    - Subreddit characteristics
    - Timing patterns
    - Common elements in high-authority threads
    """
    logger.info("Identifying high authority threads")
    supabase = get_supabase_client()
    
    try:
        # Get all high authority metrics (position <= 3) from last 7 days
        week_start = datetime.utcnow() - timedelta(days=7)
        
        high_authority_response = supabase.table('thread_authority_metrics').select(
            'thread_id, client_id, subreddit, comment_position, authority_score, is_top_comment'
        ).lte('comment_position', 3).gte(
            'commented_at', week_start.isoformat()
        ).order('authority_score', desc=True).execute()
        
        high_authority_metrics = high_authority_response.data
        
        logger.info(f"Found {len(high_authority_metrics)} high authority comments (top 3 position)")
        
        # Group by client
        client_threads = {}
        for metric in high_authority_metrics:
            client_id = metric['client_id']
            if client_id not in client_threads:
                client_threads[client_id] = []
            client_threads[client_id].append(metric)
        
        # Analyze patterns for each client
        all_insights = []
        
        for client_id, threads in client_threads.items():
            # Subreddit analysis
            subreddit_performance = {}
            for thread in threads:
                subreddit = thread['subreddit']
                if subreddit not in subreddit_performance:
                    subreddit_performance[subreddit] = {
                        'count': 0,
                        'top_comment_count': 0,
                        'avg_authority': []
                    }
                subreddit_performance[subreddit]['count'] += 1
                if thread['is_top_comment']:
                    subreddit_performance[subreddit]['top_comment_count'] += 1
                subreddit_performance[subreddit]['avg_authority'].append(thread['authority_score'])
            
            # Calculate averages
            for subreddit, perf in subreddit_performance.items():
                perf['avg_authority_score'] = statistics.mean(perf['avg_authority'])
                perf['top_comment_rate'] = (perf['top_comment_count'] / perf['count'] * 100)
            
            # Sort by performance
            sorted_subreddits = sorted(
                subreddit_performance.items(),
                key=lambda x: x[1]['avg_authority_score'],
                reverse=True
            )
            
            # Create insights
            if sorted_subreddits:
                best_subreddit, best_perf = sorted_subreddits[0]
                
                insight_text = (
                    f"High authority threads: {len(threads)} comments in top 3 position. "
                    f"Best performance in r/{best_subreddit} "
                    f"({best_perf['count']} comments, {best_perf['avg_authority_score']:.2f} avg authority, "
                    f"{best_perf['top_comment_rate']:.0f}% top comment rate)"
                )
                
                all_insights.append({
                    'client_id': client_id,
                    'insight_type': 'high_authority_analysis',
                    'total_high_authority_comments': len(threads),
                    'best_performing_subreddit': best_subreddit,
                    'best_subreddit_metrics': best_perf,
                    'insight_text': insight_text,
                    'subreddit_breakdown': dict(sorted_subreddits[:5]),  # Top 5 subreddits
                    'created_at': datetime.utcnow().isoformat()
                })
        
        # Store insights (could be in performance_insights table)
        if all_insights:
            for insight in all_insights:
                supabase.table('authority_insights').insert(insight).execute()
        
        logger.info(f"High authority analysis completed - {len(all_insights)} client insights generated")
        return {
            'status': 'success',
            'high_authority_comments': len(high_authority_metrics),
            'client_insights_generated': len(all_insights)
        }
        
    except Exception as e:
        logger.error(f"Error identifying high authority threads: {str(e)}")
        raise


@celery_app.task(name='track_comment_position_improvements')
def track_comment_position_improvements():
    """
    Track comment position improvements over time.
    
    Analyzes:
    - Weekly trend in average position (improving = moving toward position 1)
    - Top comment frequency trend
    - Authority score trend
    - Subreddit-specific improvements
    
    Generates alerts for:
    - Significant improvements (celebrate wins!)
    - Declining performance (investigate causes)
    """
    logger.info("Tracking comment position improvements")
    supabase = get_supabase_client()
    
    try:
        # Get all active clients
        clients_response = supabase.table('clients').select('client_id').eq('active', True).execute()
        clients = clients_response.data
        
        # Compare last 2 weeks
        this_week_start = datetime.utcnow() - timedelta(days=7)
        last_week_start = datetime.utcnow() - timedelta(days=14)
        
        all_trends = []
        
        for client in clients:
            client_id = client['client_id']
            
            # Get this week's summary
            this_week_response = supabase.table('authority_performance_summary').select(
                '*'
            ).eq('client_id', client_id).gte(
                'week_start_date', this_week_start.isoformat()
            ).order('week_start_date', desc=True).limit(1).execute()
            
            # Get last week's summary
            last_week_response = supabase.table('authority_performance_summary').select(
                '*'
            ).eq('client_id', client_id).gte(
                'week_start_date', last_week_start.isoformat()
            ).lt(
                'week_start_date', this_week_start.isoformat()
            ).order('week_start_date', desc=True).limit(1).execute()
            
            if not this_week_response.data or not last_week_response.data:
                logger.info(f"Insufficient data for trend analysis - client {client_id}")
                continue
            
            this_week = this_week_response.data[0]
            last_week = last_week_response.data[0]
            
            # Calculate changes
            position_change = last_week['avg_comment_position'] - this_week['avg_comment_position']  # Negative = improvement
            top_comment_change = this_week['top_comment_frequency_pct'] - last_week['top_comment_frequency_pct']
            authority_change = this_week['avg_authority_score'] - last_week['avg_authority_score']
            early_response_change = this_week['early_response_rate_pct'] - last_week['early_response_rate_pct']
            
            # Determine trend status
            if position_change > 1 and top_comment_change > 5:
                trend_status = 'significant_improvement'
                trend_message = f"🎉 Great improvement! Average position improved by {position_change:.1f} spots, " \
                               f"top comment rate +{top_comment_change:.1f}%"
            elif position_change > 0.5:
                trend_status = 'improvement'
                trend_message = f"📈 Improving! Position up by {position_change:.1f} spots"
            elif position_change < -1 and top_comment_change < -5:
                trend_status = 'significant_decline'
                trend_message = f"⚠️ Performance declining. Position down {abs(position_change):.1f} spots, " \
                               f"top comment rate {top_comment_change:.1f}%"
            elif position_change < -0.5:
                trend_status = 'decline'
                trend_message = f"📉 Slight decline. Position down {abs(position_change):.1f} spots"
            else:
                trend_status = 'stable'
                trend_message = f"➡️ Stable performance. Position change: {position_change:+.1f}"
            
            trend_record = {
                'client_id': client_id,
                'period_start': last_week_start.isoformat(),
                'period_end': datetime.utcnow().isoformat(),
                'trend_status': trend_status,
                'position_change': round(position_change, 2),
                'top_comment_freq_change_pct': round(top_comment_change, 2),
                'authority_score_change': round(authority_change, 2),
                'early_response_rate_change_pct': round(early_response_change, 2),
                'this_week_avg_position': round(this_week['avg_comment_position'], 2),
                'last_week_avg_position': round(last_week['avg_comment_position'], 2),
                'this_week_top_comment_pct': round(this_week['top_comment_frequency_pct'], 2),
                'last_week_top_comment_pct': round(last_week['top_comment_frequency_pct'], 2),
                'trend_message': trend_message,
                'created_at': datetime.utcnow().isoformat()
            }
            
            all_trends.append(trend_record)
            
            logger.info(f"Trend for {client_id}: {trend_status} - {trend_message}")
        
        # Store trends
        if all_trends:
            for trend in all_trends:
                supabase.table('authority_position_trends').insert(trend).execute()
        
        logger.info(f"Position improvement tracking completed - {len(all_trends)} trends analyzed")
        return {
            'status': 'success',
            'trends_analyzed': len(all_trends),
            'improvements': len([t for t in all_trends if 'improvement' in t['trend_status']]),
            'declines': len([t for t in all_trends if 'decline' in t['trend_status']])
        }
        
    except Exception as e:
        logger.error(f"Error tracking position improvements: {str(e)}")
        raise


# Celery Beat Schedule Configuration
"""
Add to celerybeat-schedule.py:

from celery.schedules import crontab

CELERYBEAT_SCHEDULE = {
    # Note: update_thread_authority_metrics is called real-time from Reddit automation
    # Not scheduled via Celery Beat
    
    'calculate-weekly-authority-summary': {
        'task': 'calculate_weekly_authority_summary',
        'schedule': crontab(hour=10, minute=0, day_of_week=0),  # Sunday 10 AM
    },
    'identify-high-authority-threads-daily': {
        'task': 'identify_high_authority_threads',
        'schedule': crontab(hour=12, minute=0),  # Daily 12 PM
    },
    'track-comment-position-improvements': {
        'task': 'track_comment_position_improvements',
        'schedule': crontab(hour=11, minute=0, day_of_week=1),  # Monday 11 AM
    },
}
"""


if __name__ == '__main__':
    # Test run
    print("Testing authority scoring worker...")
    result = calculate_weekly_authority_summary()
    print(f"Result: {result}")
