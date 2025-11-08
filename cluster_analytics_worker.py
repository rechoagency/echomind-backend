"""
EchoMind - Subreddit Cluster Analytics Worker

Calculates cluster performance, analyzes subreddit effectiveness,
and generates optimization recommendations.

Celery Tasks:
- calculate_cluster_performance_weekly: Weekly cluster metrics aggregation
- analyze_subreddit_effectiveness: Evaluate individual subreddit ROI within clusters
- generate_cluster_recommendations: AI-powered cluster optimization suggestions
- identify_underperforming_clusters: Alert on clusters needing attention

Schedule:
- Weekly Monday 9 AM: Full cluster performance calculation
- Daily 10 AM: Subreddit effectiveness analysis
- Weekly Tuesday 9 AM: Generate recommendations
- Daily 11 AM: Identify underperforming clusters
"""

from celery_app import celery_app
from supabase_client import get_supabase_client
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Any
import statistics

logger = logging.getLogger(__name__)


@celery_app.task(name='calculate_cluster_performance_weekly')
def calculate_cluster_performance_weekly():
    """
    Calculate weekly performance metrics for all subreddit clusters.
    
    Aggregates data from:
    - Comment performance (upvotes, replies, sentiment)
    - Engagement metrics (CTR, conversion rate)
    - Voice match accuracy
    - Authority scores
    
    Writes to: subreddit_cluster_performance table
    """
    logger.info("Starting weekly cluster performance calculation")
    supabase = get_supabase_client()
    
    try:
        # Get all active clusters
        clusters_response = supabase.table('subreddit_clusters').select(
            'cluster_id, cluster_name, client_id'
        ).eq('active', True).execute()
        
        clusters = clusters_response.data
        logger.info(f"Processing {len(clusters)} active clusters")
        
        week_start = datetime.utcnow() - timedelta(days=7)
        
        for cluster in clusters:
            cluster_id = cluster['cluster_id']
            client_id = cluster['client_id']
            
            # Get all subreddits in this cluster
            subreddit_details_response = supabase.table('subreddit_performance_detail').select(
                'subreddit_name'
            ).eq('cluster_id', cluster_id).execute()
            
            subreddit_names = [s['subreddit_name'] for s in subreddit_details_response.data]
            
            if not subreddit_names:
                logger.warning(f"No subreddits found for cluster {cluster_id}")
                continue
            
            # Aggregate performance metrics across all subreddits in cluster
            performance_data = aggregate_cluster_metrics(
                supabase, client_id, subreddit_names, week_start
            )
            
            # Calculate cluster-level scores
            cluster_metrics = {
                'cluster_id': cluster_id,
                'week_start_date': week_start.isoformat(),
                'week_end_date': datetime.utcnow().isoformat(),
                'total_comments': performance_data['total_comments'],
                'total_upvotes': performance_data['total_upvotes'],
                'avg_upvotes_per_comment': performance_data['avg_upvotes'],
                'total_replies': performance_data['total_replies'],
                'avg_replies_per_comment': performance_data['avg_replies'],
                'avg_sentiment_score': performance_data['avg_sentiment'],
                'positive_sentiment_pct': performance_data['positive_pct'],
                'voice_match_rate': performance_data['voice_match_rate'],
                'high_value_comment_count': performance_data['high_value_comments'],
                'avg_authority_score': performance_data['avg_authority'],
                'top_comment_frequency': performance_data['top_comment_freq'],
                'engagement_rate': performance_data['engagement_rate'],
                'cluster_health_score': calculate_cluster_health_score(performance_data),
                'updated_at': datetime.utcnow().isoformat()
            }
            
            # Upsert cluster performance record
            supabase.table('subreddit_cluster_performance').upsert(
                cluster_metrics,
                on_conflict='cluster_id,week_start_date'
            ).execute()
            
            logger.info(f"Updated cluster {cluster_id} ({cluster['cluster_name']}) - "
                       f"{performance_data['total_comments']} comments, "
                       f"health score: {cluster_metrics['cluster_health_score']:.2f}")
        
        logger.info("Weekly cluster performance calculation completed")
        return {'status': 'success', 'clusters_processed': len(clusters)}
        
    except Exception as e:
        logger.error(f"Error calculating cluster performance: {str(e)}")
        raise


def aggregate_cluster_metrics(supabase, client_id: str, subreddit_names: List[str], 
                              week_start: datetime) -> Dict[str, Any]:
    """
    Aggregate performance metrics across all subreddits in a cluster.
    
    Returns dict with:
    - total_comments, total_upvotes, avg_upvotes
    - total_replies, avg_replies
    - avg_sentiment, positive_pct
    - voice_match_rate, high_value_comments
    - avg_authority, top_comment_freq
    - engagement_rate
    """
    # Get comment performance data
    comments_response = supabase.table('reddit_comments').select(
        'upvotes, reply_count, sentiment_score, voice_match_score, is_high_value'
    ).eq('client_id', client_id).in_('subreddit', subreddit_names).gte(
        'created_at', week_start.isoformat()
    ).execute()
    
    comments = comments_response.data
    
    if not comments:
        return {
            'total_comments': 0, 'total_upvotes': 0, 'avg_upvotes': 0.0,
            'total_replies': 0, 'avg_replies': 0.0,
            'avg_sentiment': 0.0, 'positive_pct': 0.0,
            'voice_match_rate': 0.0, 'high_value_comments': 0,
            'avg_authority': 0.0, 'top_comment_freq': 0.0,
            'engagement_rate': 0.0
        }
    
    total_comments = len(comments)
    total_upvotes = sum(c.get('upvotes', 0) for c in comments)
    total_replies = sum(c.get('reply_count', 0) for c in comments)
    
    # Sentiment analysis
    sentiments = [c.get('sentiment_score', 0.0) for c in comments if c.get('sentiment_score') is not None]
    avg_sentiment = statistics.mean(sentiments) if sentiments else 0.0
    positive_pct = (len([s for s in sentiments if s > 0.6]) / len(sentiments) * 100) if sentiments else 0.0
    
    # Voice match analysis
    voice_scores = [c.get('voice_match_score', 0.0) for c in comments if c.get('voice_match_score') is not None]
    voice_match_rate = (len([v for v in voice_scores if v > 0.7]) / len(voice_scores) * 100) if voice_scores else 0.0
    
    # High-value comments
    high_value_comments = len([c for c in comments if c.get('is_high_value', False)])
    
    # Get authority scores for this cluster's subreddits
    authority_response = supabase.table('thread_authority_metrics').select(
        'authority_score, is_top_comment'
    ).eq('client_id', client_id).in_('subreddit', subreddit_names).gte(
        'commented_at', week_start.isoformat()
    ).execute()
    
    authority_data = authority_response.data
    authority_scores = [a.get('authority_score', 0.0) for a in authority_data if a.get('authority_score')]
    avg_authority = statistics.mean(authority_scores) if authority_scores else 0.0
    
    top_comment_count = len([a for a in authority_data if a.get('is_top_comment', False)])
    top_comment_freq = (top_comment_count / total_comments * 100) if total_comments > 0 else 0.0
    
    # Engagement rate (comments that got replies or upvotes)
    engaged_comments = len([c for c in comments if c.get('upvotes', 0) > 0 or c.get('reply_count', 0) > 0])
    engagement_rate = (engaged_comments / total_comments * 100) if total_comments > 0 else 0.0
    
    return {
        'total_comments': total_comments,
        'total_upvotes': total_upvotes,
        'avg_upvotes': total_upvotes / total_comments if total_comments > 0 else 0.0,
        'total_replies': total_replies,
        'avg_replies': total_replies / total_comments if total_comments > 0 else 0.0,
        'avg_sentiment': avg_sentiment,
        'positive_pct': positive_pct,
        'voice_match_rate': voice_match_rate,
        'high_value_comments': high_value_comments,
        'avg_authority': avg_authority,
        'top_comment_freq': top_comment_freq,
        'engagement_rate': engagement_rate
    }


def calculate_cluster_health_score(performance_data: Dict[str, Any]) -> float:
    """
    Calculate overall cluster health score (0-100).
    
    Weighted formula:
    - 30% Engagement rate
    - 25% Voice match rate
    - 20% Positive sentiment %
    - 15% Authority score
    - 10% Top comment frequency
    """
    engagement_score = min(performance_data['engagement_rate'], 100) * 0.30
    voice_match_score = min(performance_data['voice_match_rate'], 100) * 0.25
    sentiment_score = min(performance_data['positive_pct'], 100) * 0.20
    authority_score = min(performance_data['avg_authority'] * 10, 100) * 0.15  # Scale 0-10 to 0-100
    top_comment_score = min(performance_data['top_comment_freq'], 100) * 0.10
    
    health_score = (engagement_score + voice_match_score + sentiment_score + 
                   authority_score + top_comment_score)
    
    return round(health_score, 2)


@celery_app.task(name='analyze_subreddit_effectiveness')
def analyze_subreddit_effectiveness():
    """
    Analyze individual subreddit effectiveness within each cluster.
    
    Calculates ROI metrics:
    - Comments per hour invested
    - Upvotes per comment ratio
    - High-value comment rate
    - Relative performance vs cluster average
    
    Updates: subreddit_performance_detail table
    """
    logger.info("Starting subreddit effectiveness analysis")
    supabase = get_supabase_client()
    
    try:
        # Get all subreddit-cluster mappings
        details_response = supabase.table('subreddit_performance_detail').select(
            'id, cluster_id, subreddit_name, client_id'
        ).execute()
        
        details = details_response.data
        logger.info(f"Analyzing {len(details)} subreddit assignments")
        
        week_start = datetime.utcnow() - timedelta(days=7)
        
        # Group by cluster to calculate cluster averages
        cluster_averages = {}
        
        for detail in details:
            cluster_id = detail['cluster_id']
            
            if cluster_id not in cluster_averages:
                # Get cluster average from cluster_performance table
                cluster_perf_response = supabase.table('subreddit_cluster_performance').select(
                    'avg_upvotes_per_comment, engagement_rate, avg_authority_score'
                ).eq('cluster_id', cluster_id).order(
                    'week_start_date', desc=True
                ).limit(1).execute()
                
                if cluster_perf_response.data:
                    cluster_averages[cluster_id] = cluster_perf_response.data[0]
                else:
                    cluster_averages[cluster_id] = {
                        'avg_upvotes_per_comment': 0,
                        'engagement_rate': 0,
                        'avg_authority_score': 0
                    }
            
            # Get subreddit-specific metrics
            subreddit_metrics = get_subreddit_metrics(
                supabase, detail['client_id'], detail['subreddit_name'], week_start
            )
            
            # Calculate relative performance
            cluster_avg = cluster_averages[cluster_id]
            
            relative_upvotes = (
                (subreddit_metrics['avg_upvotes'] / cluster_avg['avg_upvotes_per_comment'] * 100)
                if cluster_avg['avg_upvotes_per_comment'] > 0 else 0
            )
            
            relative_engagement = (
                (subreddit_metrics['engagement_rate'] / cluster_avg['engagement_rate'] * 100)
                if cluster_avg['engagement_rate'] > 0 else 0
            )
            
            relative_authority = (
                (subreddit_metrics['avg_authority'] / cluster_avg['avg_authority_score'] * 100)
                if cluster_avg['avg_authority_score'] > 0 else 0
            )
            
            # Calculate effectiveness score (0-100)
            effectiveness_score = calculate_effectiveness_score(
                subreddit_metrics, relative_upvotes, relative_engagement, relative_authority
            )
            
            # Update subreddit performance detail
            update_data = {
                'comment_count_7d': subreddit_metrics['total_comments'],
                'avg_upvotes': subreddit_metrics['avg_upvotes'],
                'high_value_rate': subreddit_metrics['high_value_rate'],
                'engagement_rate': subreddit_metrics['engagement_rate'],
                'relative_performance_pct': round((relative_upvotes + relative_engagement + relative_authority) / 3, 2),
                'effectiveness_score': effectiveness_score,
                'last_analyzed': datetime.utcnow().isoformat()
            }
            
            supabase.table('subreddit_performance_detail').update(
                update_data
            ).eq('id', detail['id']).execute()
            
            logger.info(f"Updated {detail['subreddit_name']} - effectiveness: {effectiveness_score:.2f}")
        
        logger.info("Subreddit effectiveness analysis completed")
        return {'status': 'success', 'subreddits_analyzed': len(details)}
        
    except Exception as e:
        logger.error(f"Error analyzing subreddit effectiveness: {str(e)}")
        raise


def get_subreddit_metrics(supabase, client_id: str, subreddit_name: str, 
                         week_start: datetime) -> Dict[str, Any]:
    """Get performance metrics for a specific subreddit."""
    comments_response = supabase.table('reddit_comments').select(
        'upvotes, reply_count, is_high_value'
    ).eq('client_id', client_id).eq('subreddit', subreddit_name).gte(
        'created_at', week_start.isoformat()
    ).execute()
    
    comments = comments_response.data
    
    if not comments:
        return {
            'total_comments': 0, 'avg_upvotes': 0.0,
            'high_value_rate': 0.0, 'engagement_rate': 0.0,
            'avg_authority': 0.0
        }
    
    total_comments = len(comments)
    total_upvotes = sum(c.get('upvotes', 0) for c in comments)
    high_value_count = len([c for c in comments if c.get('is_high_value', False)])
    engaged_count = len([c for c in comments if c.get('upvotes', 0) > 0 or c.get('reply_count', 0) > 0])
    
    # Get authority scores
    authority_response = supabase.table('thread_authority_metrics').select(
        'authority_score'
    ).eq('client_id', client_id).eq('subreddit', subreddit_name).gte(
        'commented_at', week_start.isoformat()
    ).execute()
    
    authority_scores = [a.get('authority_score', 0.0) for a in authority_response.data if a.get('authority_score')]
    avg_authority = statistics.mean(authority_scores) if authority_scores else 0.0
    
    return {
        'total_comments': total_comments,
        'avg_upvotes': total_upvotes / total_comments,
        'high_value_rate': high_value_count / total_comments * 100,
        'engagement_rate': engaged_count / total_comments * 100,
        'avg_authority': avg_authority
    }


def calculate_effectiveness_score(metrics: Dict[str, Any], relative_upvotes: float,
                                 relative_engagement: float, relative_authority: float) -> float:
    """
    Calculate subreddit effectiveness score (0-100).
    
    Combines:
    - 40% Relative performance vs cluster
    - 30% High-value comment rate
    - 30% Absolute engagement rate
    """
    relative_score = min((relative_upvotes + relative_engagement + relative_authority) / 3, 100) * 0.40
    high_value_score = min(metrics['high_value_rate'], 100) * 0.30
    engagement_score = min(metrics['engagement_rate'], 100) * 0.30
    
    effectiveness = relative_score + high_value_score + engagement_score
    
    return round(effectiveness, 2)


@celery_app.task(name='generate_cluster_recommendations')
def generate_cluster_recommendations():
    """
    Generate AI-powered optimization recommendations for each cluster.
    
    Analyzes:
    - Cluster health trends
    - Top vs bottom performing subreddits
    - Gaps in coverage
    - Optimal posting patterns
    
    Generates actionable recommendations like:
    - "Increase activity in r/SaaS (150% higher engagement)"
    - "Reduce activity in r/Entrepreneur (underperforming by 40%)"
    - "Add r/startups to Tech cluster (similar audience)"
    """
    logger.info("Generating cluster recommendations")
    supabase = get_supabase_client()
    
    try:
        # Get all clusters with recent performance data
        clusters_response = supabase.table('subreddit_clusters').select(
            'cluster_id, cluster_name, client_id'
        ).eq('active', True).execute()
        
        clusters = clusters_response.data
        all_recommendations = []
        
        for cluster in clusters:
            cluster_id = cluster['cluster_id']
            
            # Get cluster performance trend (last 4 weeks)
            performance_response = supabase.table('subreddit_cluster_performance').select(
                '*'
            ).eq('cluster_id', cluster_id).order(
                'week_start_date', desc=True
            ).limit(4).execute()
            
            performance_history = performance_response.data
            
            if not performance_history:
                logger.warning(f"No performance history for cluster {cluster_id}")
                continue
            
            # Get subreddit effectiveness rankings
            subreddits_response = supabase.table('subreddit_performance_detail').select(
                'subreddit_name, effectiveness_score, relative_performance_pct, comment_count_7d'
            ).eq('cluster_id', cluster_id).order(
                'effectiveness_score', desc=True
            ).execute()
            
            subreddits = subreddits_response.data
            
            # Analyze and generate recommendations
            recommendations = analyze_cluster_and_recommend(
                cluster, performance_history, subreddits
            )
            
            # Store recommendations (could be in a new table or as JSON in clusters table)
            for rec in recommendations:
                rec['cluster_id'] = cluster_id
                rec['generated_at'] = datetime.utcnow().isoformat()
                all_recommendations.append(rec)
            
            logger.info(f"Generated {len(recommendations)} recommendations for {cluster['cluster_name']}")
        
        # Store all recommendations
        if all_recommendations:
            supabase.table('cluster_recommendations').upsert(
                all_recommendations,
                on_conflict='cluster_id,recommendation_type,created_at'
            ).execute()
        
        logger.info(f"Cluster recommendations generated: {len(all_recommendations)} total")
        return {'status': 'success', 'recommendations_generated': len(all_recommendations)}
        
    except Exception as e:
        logger.error(f"Error generating cluster recommendations: {str(e)}")
        raise


def analyze_cluster_and_recommend(cluster: Dict, performance_history: List[Dict],
                                  subreddits: List[Dict]) -> List[Dict]:
    """
    Analyze cluster data and generate specific recommendations.
    
    Returns list of recommendation dicts with:
    - recommendation_type: 'increase_activity', 'decrease_activity', 'add_subreddit', 'time_optimization'
    - priority: 'high', 'medium', 'low'
    - recommendation_text: Human-readable recommendation
    - expected_impact: Estimated impact description
    """
    recommendations = []
    
    # Analyze health trend
    if len(performance_history) >= 2:
        latest = performance_history[0]
        previous = performance_history[1]
        
        health_change = latest['cluster_health_score'] - previous['cluster_health_score']
        
        if health_change < -10:
            recommendations.append({
                'recommendation_type': 'health_alert',
                'priority': 'high',
                'recommendation_text': f"Cluster health declined by {abs(health_change):.1f} points. "
                                     f"Review engagement strategies and content quality.",
                'expected_impact': 'Prevent further performance degradation'
            })
    
    # Identify top and bottom performers
    if subreddits:
        top_performers = subreddits[:3]  # Top 3
        bottom_performers = subreddits[-3:]  # Bottom 3
        
        # Recommend increasing activity in top performers
        for sub in top_performers:
            if sub['effectiveness_score'] > 70:
                recommendations.append({
                    'recommendation_type': 'increase_activity',
                    'priority': 'high',
                    'recommendation_text': f"Increase activity in r/{sub['subreddit_name']} "
                                         f"(effectiveness: {sub['effectiveness_score']:.0f}/100, "
                                         f"{sub['relative_performance_pct']:.0f}% above cluster average)",
                    'expected_impact': f"Potential +{int(sub['effectiveness_score'] - 50)}% engagement gain",
                    'target_subreddit': sub['subreddit_name']
                })
        
        # Recommend reducing or optimizing bottom performers
        for sub in bottom_performers:
            if sub['effectiveness_score'] < 40:
                recommendations.append({
                    'recommendation_type': 'optimize_or_reduce',
                    'priority': 'medium',
                    'recommendation_text': f"Optimize or reduce activity in r/{sub['subreddit_name']} "
                                         f"(effectiveness: {sub['effectiveness_score']:.0f}/100, "
                                         f"{abs(100 - sub['relative_performance_pct']):.0f}% below cluster average)",
                    'expected_impact': 'Reallocate resources to higher-performing subreddits',
                    'target_subreddit': sub['subreddit_name']
                })
    
    # Activity volume recommendations
    if performance_history:
        latest = performance_history[0]
        
        if latest['total_comments'] < 50:
            recommendations.append({
                'recommendation_type': 'increase_volume',
                'priority': 'high',
                'recommendation_text': f"Low activity volume ({latest['total_comments']} comments/week). "
                                     f"Increase to 100+ comments/week for better insights.",
                'expected_impact': 'Improve statistical significance and opportunity detection'
            })
        
        if latest['voice_match_rate'] < 60:
            recommendations.append({
                'recommendation_type': 'improve_voice_matching',
                'priority': 'high',
                'recommendation_text': f"Voice match rate is {latest['voice_match_rate']:.1f}%. "
                                     f"Review voice analyzer settings or refresh voice database.",
                'expected_impact': 'Better alignment with brand voice, higher engagement'
            })
    
    return recommendations


@celery_app.task(name='identify_underperforming_clusters')
def identify_underperforming_clusters():
    """
    Identify clusters that need attention based on:
    - Health score < 50
    - Declining trend (3+ weeks)
    - Low activity volume
    - Poor voice matching
    
    Sends alerts to client dashboard and Slack.
    """
    logger.info("Identifying underperforming clusters")
    supabase = get_supabase_client()
    
    try:
        # Get latest cluster performance for all clusters
        clusters_response = supabase.table('subreddit_cluster_performance').select(
            'cluster_id, cluster_health_score, week_start_date, total_comments, voice_match_rate'
        ).order('week_start_date', desc=True).execute()
        
        # Group by cluster_id and get latest performance
        cluster_latest = {}
        for perf in clusters_response.data:
            cluster_id = perf['cluster_id']
            if cluster_id not in cluster_latest:
                cluster_latest[cluster_id] = perf
        
        underperforming = []
        
        for cluster_id, latest_perf in cluster_latest.items():
            issues = []
            severity = 'low'
            
            # Check health score
            if latest_perf['cluster_health_score'] < 50:
                issues.append(f"Low health score: {latest_perf['cluster_health_score']:.1f}/100")
                severity = 'high'
            elif latest_perf['cluster_health_score'] < 65:
                issues.append(f"Moderate health score: {latest_perf['cluster_health_score']:.1f}/100")
                severity = 'medium'
            
            # Check activity volume
            if latest_perf['total_comments'] < 30:
                issues.append(f"Low activity: {latest_perf['total_comments']} comments/week")
                if severity == 'low':
                    severity = 'medium'
            
            # Check voice matching
            if latest_perf['voice_match_rate'] < 50:
                issues.append(f"Poor voice matching: {latest_perf['voice_match_rate']:.1f}%")
                if severity == 'low':
                    severity = 'medium'
            
            if issues:
                # Get cluster details
                cluster_response = supabase.table('subreddit_clusters').select(
                    'cluster_name, client_id'
                ).eq('cluster_id', cluster_id).single().execute()
                
                cluster_info = cluster_response.data
                
                underperforming.append({
                    'cluster_id': cluster_id,
                    'cluster_name': cluster_info['cluster_name'],
                    'client_id': cluster_info['client_id'],
                    'severity': severity,
                    'issues': issues,
                    'health_score': latest_perf['cluster_health_score'],
                    'detected_at': datetime.utcnow().isoformat()
                })
        
        # Store alerts
        if underperforming:
            for alert in underperforming:
                supabase.table('cluster_performance_alerts').insert({
                    'cluster_id': alert['cluster_id'],
                    'client_id': alert['client_id'],
                    'alert_type': 'underperforming',
                    'severity': alert['severity'],
                    'alert_message': f"{alert['cluster_name']}: {', '.join(alert['issues'])}",
                    'metadata': alert,
                    'created_at': datetime.utcnow().isoformat()
                }).execute()
            
            logger.warning(f"Found {len(underperforming)} underperforming clusters")
        else:
            logger.info("No underperforming clusters detected")
        
        return {
            'status': 'success',
            'underperforming_count': len(underperforming),
            'alerts_created': len(underperforming)
        }
        
    except Exception as e:
        logger.error(f"Error identifying underperforming clusters: {str(e)}")
        raise


# Celery Beat Schedule Configuration
"""
Add to celerybeat-schedule.py:

from celery.schedules import crontab

CELERYBEAT_SCHEDULE = {
    'calculate-cluster-performance-weekly': {
        'task': 'calculate_cluster_performance_weekly',
        'schedule': crontab(hour=9, minute=0, day_of_week=1),  # Monday 9 AM
    },
    'analyze-subreddit-effectiveness-daily': {
        'task': 'analyze_subreddit_effectiveness',
        'schedule': crontab(hour=10, minute=0),  # Daily 10 AM
    },
    'generate-cluster-recommendations-weekly': {
        'task': 'generate_cluster_recommendations',
        'schedule': crontab(hour=9, minute=0, day_of_week=2),  # Tuesday 9 AM
    },
    'identify-underperforming-clusters-daily': {
        'task': 'identify_underperforming_clusters',
        'schedule': crontab(hour=11, minute=0),  # Daily 11 AM
    },
}
"""


if __name__ == '__main__':
    # Test run
    print("Testing cluster analytics worker...")
    result = calculate_cluster_performance_weekly()
    print(f"Result: {result}")
