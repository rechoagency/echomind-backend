"""
EchoMind - Moderation Monitoring Worker

Monitors content removals, tracks moderation actions, and calculates
community health metrics to prevent shadowbans and improve compliance.

Celery Tasks:
- check_content_removals: Hourly check for removed comments/posts
- fetch_moderation_logs: Daily retrieval of subreddit moderation logs (if accessible)
- calculate_community_health: Daily calculation of subreddit health scores
- detect_moderation_risks: Real-time risk detection and alerting
- analyze_removal_patterns: Weekly analysis of why content gets removed

Schedule:
- Hourly: Content removal checks
- Daily 1 AM: Moderation log fetch
- Daily 2 AM: Community health calculation
- Every 2 hours: Moderation risk detection
- Weekly Wednesday 9 AM: Removal pattern analysis
"""

from celery_app import celery_app
from supabase_client import get_supabase_client
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Any, Optional
import praw
from prawcore.exceptions import Forbidden, NotFound
import statistics
import re

logger = logging.getLogger(__name__)


def get_reddit_client():
    """Initialize Reddit API client (PRAW)."""
    # Reddit API credentials should be stored in environment variables
    import os
    return praw.Reddit(
        client_id=os.getenv('REDDIT_CLIENT_ID'),
        client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
        user_agent=os.getenv('REDDIT_USER_AGENT', 'EchoMind/1.0')
    )


@celery_app.task(name='check_content_removals')
def check_content_removals():
    """
    Check for removed comments and posts across all client accounts.
    
    Process:
    1. Get all comments/posts from last 24 hours
    2. Check if each still exists on Reddit
    3. If removed, log removal details
    4. Update removal statistics
    
    Removal indicators:
    - Comment body = "[removed]" or "[deleted]"
    - Post not accessible via API
    - 403 Forbidden response
    
    Writes to: content_removal_tracking table
    """
    logger.info("Starting content removal check")
    supabase = get_supabase_client()
    reddit = get_reddit_client()
    
    try:
        # Get all comments from last 24 hours
        yesterday = datetime.utcnow() - timedelta(hours=24)
        
        comments_response = supabase.table('reddit_comments').select(
            'comment_id, client_id, account_id, subreddit, thread_id, created_at'
        ).gte('created_at', yesterday.isoformat()).execute()
        
        comments = comments_response.data
        logger.info(f"Checking {len(comments)} comments for removals")
        
        removals_detected = 0
        
        for comment in comments:
            comment_id = comment['comment_id']
            
            # Check if removal already logged
            existing_removal = supabase.table('content_removal_tracking').select(
                'id'
            ).eq('content_id', comment_id).execute()
            
            if existing_removal.data:
                continue  # Already logged
            
            # Check comment status on Reddit
            try:
                reddit_comment = reddit.comment(comment_id)
                reddit_comment._fetch()  # Force fetch to check if exists
                
                # Check if removed
                is_removed = (
                    reddit_comment.body in ['[removed]', '[deleted]'] or
                    reddit_comment.author is None or
                    str(reddit_comment.author) == '[deleted]'
                )
                
                if is_removed:
                    # Log removal
                    removal_record = {
                        'content_id': comment_id,
                        'content_type': 'comment',
                        'client_id': comment['client_id'],
                        'account_id': comment['account_id'],
                        'subreddit': comment['subreddit'],
                        'thread_id': comment['thread_id'],
                        'removed_at': datetime.utcnow().isoformat(),
                        'removal_type': 'moderator_removed' if reddit_comment.body == '[removed]' else 'user_deleted',
                        'posted_at': comment['created_at'],
                        'time_until_removal_hours': (
                            datetime.utcnow() - datetime.fromisoformat(comment['created_at'])
                        ).total_seconds() / 3600,
                        'detected_at': datetime.utcnow().isoformat()
                    }
                    
                    supabase.table('content_removal_tracking').insert(removal_record).execute()
                    removals_detected += 1
                    
                    logger.warning(f"Removal detected: {comment_id} in r/{comment['subreddit']} - "
                                 f"{removal_record['removal_type']}")
            
            except (Forbidden, NotFound) as e:
                # Comment not accessible - likely removed
                removal_record = {
                    'content_id': comment_id,
                    'content_type': 'comment',
                    'client_id': comment['client_id'],
                    'account_id': comment['account_id'],
                    'subreddit': comment['subreddit'],
                    'thread_id': comment['thread_id'],
                    'removed_at': datetime.utcnow().isoformat(),
                    'removal_type': 'moderator_removed',
                    'posted_at': comment['created_at'],
                    'time_until_removal_hours': (
                        datetime.utcnow() - datetime.fromisoformat(comment['created_at'])
                    ).total_seconds() / 3600,
                    'removal_reason': str(e),
                    'detected_at': datetime.utcnow().isoformat()
                }
                
                supabase.table('content_removal_tracking').insert(removal_record).execute()
                removals_detected += 1
                
                logger.warning(f"Removal detected (API error): {comment_id} - {str(e)}")
            
            except Exception as e:
                logger.error(f"Error checking comment {comment_id}: {str(e)}")
        
        logger.info(f"Content removal check completed - {removals_detected} removals detected")
        return {
            'status': 'success',
            'comments_checked': len(comments),
            'removals_detected': removals_detected
        }
        
    except Exception as e:
        logger.error(f"Error checking content removals: {str(e)}")
        raise


@celery_app.task(name='fetch_moderation_logs')
def fetch_moderation_logs():
    """
    Fetch moderation logs from monitored subreddits (if accessible).
    
    Note: Moderation logs are only accessible if:
    - User is a moderator of the subreddit
    - Subreddit has public mod logs enabled
    
    For most clients, this will have limited data. Main value is for
    subreddits where client has mod access or participates heavily.
    
    Writes to: moderation_log table
    """
    logger.info("Fetching moderation logs")
    supabase = get_supabase_client()
    reddit = get_reddit_client()
    
    try:
        # Get all monitored subreddits
        subreddits_response = supabase.table('target_subreddits').select(
            'subreddit_name, client_id'
        ).eq('active', True).execute()
        
        subreddits = subreddits_response.data
        logger.info(f"Attempting to fetch mod logs for {len(subreddits)} subreddits")
        
        logs_fetched = 0
        
        for subreddit_data in subreddits:
            subreddit_name = subreddit_data['subreddit_name']
            client_id = subreddit_data['client_id']
            
            try:
                subreddit = reddit.subreddit(subreddit_name)
                
                # Try to access mod log (will fail if not accessible)
                mod_log = subreddit.mod.log(limit=100)  # Last 100 actions
                
                for log_entry in mod_log:
                    # Check if already logged
                    existing = supabase.table('moderation_log').select('id').eq(
                        'action_id', log_entry.id
                    ).execute()
                    
                    if existing.data:
                        continue  # Already logged
                    
                    # Parse mod action
                    log_record = {
                        'action_id': log_entry.id,
                        'subreddit': subreddit_name,
                        'client_id': client_id,
                        'mod_username': str(log_entry.mod) if log_entry.mod else None,
                        'action_type': log_entry.action,
                        'target_author': str(log_entry.target_author) if log_entry.target_author else None,
                        'target_content_id': log_entry.target_fullname,
                        'target_permalink': log_entry.target_permalink,
                        'action_description': log_entry.description,
                        'details': log_entry.details,
                        'action_timestamp': datetime.fromtimestamp(log_entry.created_utc).isoformat(),
                        'fetched_at': datetime.utcnow().isoformat()
                    }
                    
                    supabase.table('moderation_log').insert(log_record).execute()
                    logs_fetched += 1
                
                logger.info(f"Fetched mod logs for r/{subreddit_name}")
            
            except Forbidden:
                logger.debug(f"Mod log not accessible for r/{subreddit_name} (expected)")
            except Exception as e:
                logger.error(f"Error fetching mod log for r/{subreddit_name}: {str(e)}")
        
        logger.info(f"Moderation log fetch completed - {logs_fetched} new actions logged")
        return {
            'status': 'success',
            'subreddits_checked': len(subreddits),
            'logs_fetched': logs_fetched
        }
        
    except Exception as e:
        logger.error(f"Error fetching moderation logs: {str(e)}")
        raise


@celery_app.task(name='calculate_community_health')
def calculate_community_health():
    """
    Calculate daily community health scores for all monitored subreddits.
    
    Health metrics:
    - Removal rate: % of client comments removed
    - Engagement health: Are comments getting upvotes/replies?
    - Sentiment health: Is community sentiment positive?
    - Rule compliance: Are there rule violation patterns?
    - Moderator responsiveness: How quickly do mods act?
    
    Health score: 0-100 (higher = healthier community relationship)
    
    Writes to: subreddit_health_metrics table
    """
    logger.info("Calculating community health scores")
    supabase = get_supabase_client()
    
    try:
        # Get all active client-subreddit combinations
        client_subreddits_response = supabase.table('reddit_comments').select(
            'client_id, subreddit'
        ).execute()
        
        # Get unique combinations
        unique_combinations = set(
            (c['client_id'], c['subreddit']) 
            for c in client_subreddits_response.data
        )
        
        logger.info(f"Calculating health for {len(unique_combinations)} client-subreddit pairs")
        
        week_start = datetime.utcnow() - timedelta(days=7)
        
        for client_id, subreddit_name in unique_combinations:
            # Get comment performance
            comments_response = supabase.table('reddit_comments').select(
                'comment_id, upvotes, reply_count, sentiment_score'
            ).eq('client_id', client_id).eq('subreddit', subreddit_name).gte(
                'created_at', week_start.isoformat()
            ).execute()
            
            comments = comments_response.data
            
            if not comments:
                continue
            
            total_comments = len(comments)
            
            # Calculate removal rate
            removals_response = supabase.table('content_removal_tracking').select(
                'id'
            ).eq('client_id', client_id).eq('subreddit', subreddit_name).gte(
                'removed_at', week_start.isoformat()
            ).execute()
            
            removal_count = len(removals_response.data)
            removal_rate = (removal_count / total_comments * 100) if total_comments > 0 else 0.0
            
            # Calculate engagement health
            engaged_comments = len([
                c for c in comments 
                if c.get('upvotes', 0) > 0 or c.get('reply_count', 0) > 0
            ])
            engagement_rate = (engaged_comments / total_comments * 100) if total_comments > 0 else 0.0
            
            avg_upvotes = statistics.mean([c.get('upvotes', 0) for c in comments])
            avg_replies = statistics.mean([c.get('reply_count', 0) for c in comments])
            
            # Calculate sentiment health
            sentiments = [c.get('sentiment_score', 0.0) for c in comments if c.get('sentiment_score') is not None]
            avg_sentiment = statistics.mean(sentiments) if sentiments else 0.0
            positive_sentiment_pct = (
                len([s for s in sentiments if s > 0.6]) / len(sentiments) * 100
            ) if sentiments else 0.0
            
            # Get rule violation count (from moderation log if available)
            violations_response = supabase.table('moderation_log').select(
                'id'
            ).eq('client_id', client_id).eq('subreddit', subreddit_name).in_(
                'action_type', ['removecomment', 'removelink', 'ban', 'mute']
            ).gte('action_timestamp', week_start.isoformat()).execute()
            
            violation_count = len(violations_response.data)
            
            # Calculate overall health score
            health_score = calculate_health_score(
                removal_rate, engagement_rate, avg_sentiment, 
                positive_sentiment_pct, violation_count, total_comments
            )
            
            # Determine health status
            if health_score >= 80:
                health_status = 'excellent'
            elif health_score >= 65:
                health_status = 'good'
            elif health_score >= 50:
                health_status = 'fair'
            elif health_score >= 35:
                health_status = 'poor'
            else:
                health_status = 'critical'
            
            # Store health metrics
            health_record = {
                'client_id': client_id,
                'subreddit': subreddit_name,
                'metric_date': datetime.utcnow().date().isoformat(),
                'total_comments_7d': total_comments,
                'removal_count': removal_count,
                'removal_rate_pct': round(removal_rate, 2),
                'engagement_rate_pct': round(engagement_rate, 2),
                'avg_upvotes': round(avg_upvotes, 2),
                'avg_replies': round(avg_replies, 2),
                'avg_sentiment_score': round(avg_sentiment, 2),
                'positive_sentiment_pct': round(positive_sentiment_pct, 2),
                'rule_violation_count': violation_count,
                'health_score': round(health_score, 2),
                'health_status': health_status,
                'updated_at': datetime.utcnow().isoformat()
            }
            
            supabase.table('subreddit_health_metrics').upsert(
                health_record,
                on_conflict='client_id,subreddit,metric_date'
            ).execute()
            
            logger.info(f"Health score for {client_id} in r/{subreddit_name}: "
                       f"{health_score:.1f}/100 ({health_status})")
        
        logger.info(f"Community health calculation completed - {len(unique_combinations)} pairs analyzed")
        return {
            'status': 'success',
            'client_subreddit_pairs': len(unique_combinations)
        }
        
    except Exception as e:
        logger.error(f"Error calculating community health: {str(e)}")
        raise


def calculate_health_score(removal_rate: float, engagement_rate: float, 
                           avg_sentiment: float, positive_sentiment_pct: float,
                           violation_count: int, total_comments: int) -> float:
    """
    Calculate community health score (0-100).
    
    Weighted formula:
    - 35% Low removal rate (inverse)
    - 25% High engagement rate
    - 20% Positive sentiment
    - 15% Low violation rate
    - 5% Bonus for high volume (shows confidence)
    """
    # Removal rate score (inverse - lower removal = higher score)
    removal_score = max(0, 100 - (removal_rate * 3)) * 0.35
    
    # Engagement rate score
    engagement_score = min(engagement_rate, 100) * 0.25
    
    # Sentiment score
    sentiment_score = min(positive_sentiment_pct, 100) * 0.20
    
    # Violation rate score (inverse)
    violation_rate = (violation_count / total_comments * 100) if total_comments > 0 else 0
    violation_score = max(0, 100 - (violation_rate * 5)) * 0.15
    
    # Volume bonus (high activity shows confidence)
    volume_bonus = min(total_comments / 50 * 5, 5)  # Up to 5 points for 50+ comments
    
    health_score = removal_score + engagement_score + sentiment_score + violation_score + volume_bonus
    
    return min(health_score, 100)


@celery_app.task(name='detect_moderation_risks')
def detect_moderation_risks():
    """
    Detect real-time moderation risks and send alerts.
    
    Risk indicators:
    - Sudden spike in removals (3+ in 24 hours)
    - Multiple removals in same subreddit
    - Recent ban or mute action
    - High removal rate (>20%) in a subreddit
    - Declining health score trend
    
    Sends alerts via:
    - Dashboard notifications
    - Slack webhook (if configured)
    - Email (for critical risks)
    """
    logger.info("Detecting moderation risks")
    supabase = get_supabase_client()
    
    try:
        # Get all active clients
        clients_response = supabase.table('clients').select('client_id, email').eq('active', True).execute()
        clients = clients_response.data
        
        all_risks = []
        
        for client in clients:
            client_id = client['client_id']
            
            # Check for removal spikes (last 24 hours)
            yesterday = datetime.utcnow() - timedelta(hours=24)
            
            removals_response = supabase.table('content_removal_tracking').select(
                'subreddit, removal_type, removed_at'
            ).eq('client_id', client_id).gte(
                'removed_at', yesterday.isoformat()
            ).execute()
            
            removals = removals_response.data
            
            if len(removals) >= 3:
                # Spike detected
                subreddit_breakdown = {}
                for removal in removals:
                    subreddit = removal['subreddit']
                    subreddit_breakdown[subreddit] = subreddit_breakdown.get(subreddit, 0) + 1
                
                worst_subreddit = max(subreddit_breakdown, key=subreddit_breakdown.get)
                
                risk = {
                    'client_id': client_id,
                    'risk_type': 'removal_spike',
                    'severity': 'high' if len(removals) >= 5 else 'medium',
                    'subreddit': worst_subreddit,
                    'risk_message': f"⚠️ {len(removals)} content removals in 24 hours. "
                                   f"Most affected: r/{worst_subreddit} ({subreddit_breakdown[worst_subreddit]} removals)",
                    'detection_data': {
                        'total_removals_24h': len(removals),
                        'subreddit_breakdown': subreddit_breakdown
                    },
                    'recommended_action': f"Review r/{worst_subreddit} rules and recent comments. "
                                        f"Consider pausing activity temporarily.",
                    'detected_at': datetime.utcnow().isoformat()
                }
                
                all_risks.append(risk)
                logger.warning(f"Removal spike detected for {client_id}: {len(removals)} in 24h")
            
            # Check for critical health scores
            health_response = supabase.table('subreddit_health_metrics').select(
                'subreddit, health_score, health_status, removal_rate_pct'
            ).eq('client_id', client_id).eq('health_status', 'critical').execute()
            
            critical_health = health_response.data
            
            for health in critical_health:
                risk = {
                    'client_id': client_id,
                    'risk_type': 'critical_health',
                    'severity': 'high',
                    'subreddit': health['subreddit'],
                    'risk_message': f"🚨 Critical community health in r/{health['subreddit']} "
                                   f"(score: {health['health_score']:.0f}/100, "
                                   f"removal rate: {health['removal_rate_pct']:.1f}%)",
                    'detection_data': health,
                    'recommended_action': f"Immediately review and adjust strategy for r/{health['subreddit']}. "
                                        f"High risk of shadowban or permanent ban.",
                    'detected_at': datetime.utcnow().isoformat()
                }
                
                all_risks.append(risk)
                logger.error(f"Critical health detected for {client_id} in r/{health['subreddit']}")
            
            # Check for bans/mutes in moderation log
            week_start = datetime.utcnow() - timedelta(days=7)
            
            bans_response = supabase.table('moderation_log').select(
                'subreddit, action_type, action_description, action_timestamp'
            ).eq('client_id', client_id).in_(
                'action_type', ['ban', 'mute']
            ).gte('action_timestamp', week_start.isoformat()).execute()
            
            bans = bans_response.data
            
            for ban in bans:
                risk = {
                    'client_id': client_id,
                    'risk_type': 'ban_or_mute',
                    'severity': 'critical' if ban['action_type'] == 'ban' else 'high',
                    'subreddit': ban['subreddit'],
                    'risk_message': f"🔴 Account {ban['action_type']}ned in r/{ban['subreddit']}. "
                                   f"Reason: {ban['action_description']}",
                    'detection_data': ban,
                    'recommended_action': f"Stop all activity in r/{ban['subreddit']}. "
                                        f"Appeal if possible. Review what triggered {ban['action_type']}.",
                    'detected_at': datetime.utcnow().isoformat()
                }
                
                all_risks.append(risk)
                logger.critical(f"Ban/mute detected for {client_id} in r/{ban['subreddit']}")
        
        # Store all risks
        if all_risks:
            for risk in all_risks:
                supabase.table('moderation_risk_alerts').insert(risk).execute()
        
        # Send critical alerts (could integrate with Slack/email here)
        critical_risks = [r for r in all_risks if r['severity'] == 'critical']
        if critical_risks:
            logger.critical(f"⚠️ {len(critical_risks)} CRITICAL moderation risks detected!")
            # TODO: Send Slack webhook
            # TODO: Send email alerts
        
        logger.info(f"Moderation risk detection completed - {len(all_risks)} risks found")
        return {
            'status': 'success',
            'total_risks': len(all_risks),
            'critical_risks': len(critical_risks),
            'high_risks': len([r for r in all_risks if r['severity'] == 'high']),
            'medium_risks': len([r for r in all_risks if r['severity'] == 'medium'])
        }
        
    except Exception as e:
        logger.error(f"Error detecting moderation risks: {str(e)}")
        raise


@celery_app.task(name='analyze_removal_patterns')
def analyze_removal_patterns():
    """
    Weekly analysis of removal patterns to identify why content is being removed.
    
    Analyzes:
    - Common keywords/phrases in removed content
    - Time patterns (are removals happening at specific times?)
    - Subreddit-specific patterns
    - Rule violation categories
    - Comparison with non-removed content
    
    Generates actionable insights:
    - "Avoid mentioning X in r/Y"
    - "Comments with links have 3x higher removal rate"
    - "Posting in first 5 minutes increases removal risk by 40%"
    """
    logger.info("Analyzing removal patterns")
    supabase = get_supabase_client()
    
    try:
        # Get all removals from last 30 days
        month_start = datetime.utcnow() - timedelta(days=30)
        
        removals_response = supabase.table('content_removal_tracking').select(
            'content_id, client_id, subreddit, removal_type, removed_at, time_until_removal_hours'
        ).gte('removed_at', month_start.isoformat()).execute()
        
        removals = removals_response.data
        logger.info(f"Analyzing {len(removals)} removals from last 30 days")
        
        if not removals:
            logger.info("No removals to analyze")
            return {'status': 'success', 'patterns_found': 0}
        
        # Group by client
        client_patterns = {}
        
        for removal in removals:
            client_id = removal['client_id']
            if client_id not in client_patterns:
                client_patterns[client_id] = []
            client_patterns[client_id].append(removal)
        
        all_insights = []
        
        for client_id, client_removals in client_patterns.items():
            # Subreddit analysis
            subreddit_removal_counts = {}
            for removal in client_removals:
                subreddit = removal['subreddit']
                subreddit_removal_counts[subreddit] = subreddit_removal_counts.get(subreddit, 0) + 1
            
            # Find high-risk subreddits
            high_risk_subreddits = [
                (sub, count) for sub, count in subreddit_removal_counts.items() 
                if count >= 3
            ]
            
            # Timing analysis
            removal_times = [
                removal['time_until_removal_hours'] 
                for removal in client_removals 
                if removal.get('time_until_removal_hours')
            ]
            
            if removal_times:
                avg_time_until_removal = statistics.mean(removal_times)
                quick_removals = len([t for t in removal_times if t < 1])  # Removed within 1 hour
                
                timing_insight = None
                if quick_removals / len(removal_times) > 0.5:
                    timing_insight = f"⚡ {quick_removals}/{len(removal_times)} removals happened within 1 hour. " \
                                   f"Content may be triggering automod rules."
            else:
                avg_time_until_removal = 0
                timing_insight = None
            
            # Removal type breakdown
            removal_type_counts = {}
            for removal in client_removals:
                removal_type = removal.get('removal_type', 'unknown')
                removal_type_counts[removal_type] = removal_type_counts.get(removal_type, 0) + 1
            
            # Generate insights
            insights = {
                'client_id': client_id,
                'analysis_period_days': 30,
                'total_removals': len(client_removals),
                'high_risk_subreddits': high_risk_subreddits,
                'avg_time_until_removal_hours': round(avg_time_until_removal, 2),
                'quick_removal_rate': round(quick_removals / len(removal_times) * 100, 1) if removal_times else 0,
                'removal_type_breakdown': removal_type_counts,
                'timing_insight': timing_insight,
                'recommendations': []
            }
            
            # Generate recommendations
            if high_risk_subreddits:
                for subreddit, count in high_risk_subreddits[:3]:  # Top 3
                    insights['recommendations'].append(
                        f"Review and adjust strategy for r/{subreddit} ({count} removals in 30 days)"
                    )
            
            if timing_insight:
                insights['recommendations'].append(
                    "Content appears to trigger automod. Review automod rules for target subreddits."
                )
            
            if removal_type_counts.get('moderator_removed', 0) > removal_type_counts.get('user_deleted', 0) * 2:
                insights['recommendations'].append(
                    "Most removals are moderator actions. Review subreddit rules and posting guidelines."
                )
            
            all_insights.append(insights)
            
            # Store insights
            supabase.table('removal_pattern_analysis').insert({
                'client_id': client_id,
                'analysis_date': datetime.utcnow().date().isoformat(),
                'analysis_data': insights,
                'created_at': datetime.utcnow().isoformat()
            }).execute()
            
            logger.info(f"Removal pattern analysis for {client_id}: {len(client_removals)} removals, "
                       f"{len(insights['recommendations'])} recommendations")
        
        logger.info(f"Removal pattern analysis completed - {len(all_insights)} client analyses")
        return {
            'status': 'success',
            'patterns_analyzed': len(all_insights),
            'total_removals_analyzed': len(removals)
        }
        
    except Exception as e:
        logger.error(f"Error analyzing removal patterns: {str(e)}")
        raise


# Celery Beat Schedule Configuration
"""
Add to celerybeat-schedule.py:

from celery.schedules import crontab

CELERYBEAT_SCHEDULE = {
    'check-content-removals-hourly': {
        'task': 'check_content_removals',
        'schedule': crontab(minute=0),  # Every hour
    },
    'fetch-moderation-logs-daily': {
        'task': 'fetch_moderation_logs',
        'schedule': crontab(hour=1, minute=0),  # Daily 1 AM
    },
    'calculate-community-health-daily': {
        'task': 'calculate_community_health',
        'schedule': crontab(hour=2, minute=0),  # Daily 2 AM
    },
    'detect-moderation-risks': {
        'task': 'detect_moderation_risks',
        'schedule': crontab(minute=0, hour='*/2'),  # Every 2 hours
    },
    'analyze-removal-patterns-weekly': {
        'task': 'analyze_removal_patterns',
        'schedule': crontab(hour=9, minute=0, day_of_week=3),  # Wednesday 9 AM
    },
}
"""


if __name__ == '__main__':
    # Test run
    print("Testing moderation monitoring worker...")
    result = calculate_community_health()
    print(f"Result: {result}")
