"""
EchoMind Sentiment Analysis Worker
Real-time sentiment tracking and heatmap data generation
"""

import os
from datetime import datetime, date, timedelta
from typing import Dict, Optional
from celery import Celery
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Celery setup
celery_app = Celery('sentiment_analysis', broker=os.getenv('CELERY_BROKER_URL'))

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


# ============================================================================
# SENTIMENT ANALYSIS
# ============================================================================

@celery_app.task(name='analyze_content_sentiment')
def analyze_content_sentiment(client_id: str, text: str, source_type: str,
                              source_reddit_id: str, subreddit: str, 
                              score: int = 0, upvotes: int = 0):
    """
    Analyze sentiment of question/answer/comment
    Records in sentiment_snapshots table
    """
    db = SessionLocal()
    try:
        # Calculate sentiment
        sentiment_result = calculate_detailed_sentiment(text)
        
        # Record snapshot
        db.execute(text("""
            INSERT INTO sentiment_snapshots (
                client_id,
                source_type,
                source_reddit_id,
                subreddit,
                sentiment_score,
                sentiment_label,
                confidence_score,
                emotions,
                text_snippet,
                score,
                upvotes,
                discovered_at
            ) VALUES (
                :client_id, :source_type, :source_reddit_id, :subreddit,
                :sentiment_score, :sentiment_label, :confidence, :emotions,
                :text_snippet, :score, :upvotes, :discovered_at
            )
        """), {
            "client_id": client_id,
            "source_type": source_type,
            "source_reddit_id": source_reddit_id,
            "subreddit": subreddit,
            "sentiment_score": sentiment_result['score'],
            "sentiment_label": sentiment_result['label'],
            "confidence": sentiment_result['confidence'],
            "emotions": str(sentiment_result['emotions']),  # JSON string
            "text_snippet": text[:200],
            "score": score,
            "upvotes": upvotes,
            "discovered_at": datetime.now()
        })
        
        db.commit()
        logger.info(f"Analyzed sentiment: {sentiment_result['label']} ({sentiment_result['score']:.2f}) for {source_type}")
        
    except Exception as e:
        logger.error(f"Error analyzing sentiment: {e}")
        db.rollback()
    finally:
        db.close()


def calculate_detailed_sentiment(text: str) -> Dict:
    """
    Calculate detailed sentiment analysis
    Returns: score, label, confidence, emotions
    """
    text_lower = text.lower()
    
    # Sentiment word lists (expanded)
    very_positive = ['amazing', 'excellent', 'outstanding', 'brilliant', 'perfect', 
                     'love', 'fantastic', 'incredible', 'awesome', 'wonderful']
    positive = ['good', 'great', 'nice', 'helpful', 'useful', 'better', 'best',
                'like', 'enjoy', 'appreciate', 'recommend']
    negative = ['bad', 'poor', 'worse', 'disappointing', 'frustrating', 'annoying',
                'dislike', 'avoid', 'problem', 'issue', 'difficult']
    very_negative = ['terrible', 'horrible', 'awful', 'worst', 'hate', 'useless',
                     'garbage', 'pathetic', 'disgusting']
    
    # Count occurrences
    very_pos_count = sum(1 for word in very_positive if word in text_lower)
    pos_count = sum(1 for word in positive if word in text_lower)
    neg_count = sum(1 for word in negative if word in text_lower)
    very_neg_count = sum(1 for word in very_negative if word in text_lower)
    
    # Calculate weighted score (-1.0 to 1.0)
    score = (
        (very_pos_count * 1.0) + 
        (pos_count * 0.5) - 
        (neg_count * 0.5) - 
        (very_neg_count * 1.0)
    )
    
    # Normalize
    total_sentiment_words = very_pos_count + pos_count + neg_count + very_neg_count
    if total_sentiment_words > 0:
        score = score / total_sentiment_words
        confidence = min(0.9, total_sentiment_words * 0.1)  # More words = higher confidence
    else:
        score = 0.0
        confidence = 0.3  # Low confidence for neutral text
    
    # Determine label
    if score >= 0.5:
        label = 'very_positive'
    elif score >= 0.2:
        label = 'positive'
    elif score >= -0.2:
        label = 'neutral'
    elif score >= -0.5:
        label = 'negative'
    else:
        label = 'very_negative'
    
    # Detect emotions (simple keyword matching)
    emotions = {
        'joy': 0.8 if any(w in text_lower for w in ['happy', 'joy', 'excited', 'love']) else 0.2,
        'anger': 0.8 if any(w in text_lower for w in ['angry', 'furious', 'hate', 'mad']) else 0.1,
        'sadness': 0.7 if any(w in text_lower for w in ['sad', 'depressed', 'disappointed']) else 0.1,
        'fear': 0.6 if any(w in text_lower for w in ['worried', 'scared', 'afraid', 'anxious']) else 0.1
    }
    
    return {
        'score': round(score, 2),
        'label': label,
        'confidence': round(confidence, 2),
        'emotions': emotions
    }


# ============================================================================
# HEATMAP DATA GENERATION
# ============================================================================

@celery_app.task(name='generate_daily_sentiment_heatmap')
def generate_daily_sentiment_heatmap():
    """
    Generate daily sentiment heatmap data
    Runs every day at 6 AM
    """
    logger.info("Generating daily sentiment heatmap")
    
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT calculate_daily_sentiment_heatmap()"))
        count = result.scalar()
        
        logger.info(f"✅ Generated heatmap data for {count} subreddit-days")
        return {"heatmap_records": count}
        
    except Exception as e:
        logger.error(f"Error generating sentiment heatmap: {e}")
        return {"error": str(e)}
    finally:
        db.close()


@celery_app.task(name='generate_hourly_sentiment_patterns')
def generate_hourly_sentiment_patterns():
    """
    Generate hourly sentiment patterns
    Runs every day at 7 AM
    """
    logger.info("Generating hourly sentiment patterns")
    
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT calculate_hourly_sentiment_patterns()"))
        count = result.scalar()
        
        logger.info(f"✅ Generated hourly patterns for {count} subreddit-hours")
        return {"hourly_patterns": count}
        
    except Exception as e:
        logger.error(f"Error generating hourly patterns: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# ============================================================================
# SENTIMENT ALERTS
# ============================================================================

@celery_app.task(name='detect_sentiment_shifts')
def detect_sentiment_shifts():
    """
    Detect sharp sentiment changes
    Alert on sudden negative shifts
    """
    db = SessionLocal()
    try:
        # Get sentiment alerts from 7-day trends
        result = db.execute(text("""
            SELECT 
                client_id,
                subreddit,
                date,
                daily_sentiment,
                trend_direction,
                alert_flag
            FROM sentiment_trends_7day
            WHERE alert_flag IS NOT NULL
            AND date = CURRENT_DATE - INTERVAL '1 day'
            ORDER BY daily_sentiment ASC
        """))
        
        alerts = result.fetchall()
        
        if alerts:
            logger.info(f"⚠️ Found {len(alerts)} sentiment alerts")
            for alert in alerts:
                logger.warning(f"  {alert.alert_flag}: {alert.subreddit} "
                             f"(sentiment: {alert.daily_sentiment:.2f})")
                
                # Could send Slack/email alerts here
        
        return {"alerts": len(alerts)}
        
    except Exception as e:
        logger.error(f"Error detecting sentiment shifts: {e}")
        return {"error": str(e)}
    finally:
        db.close()


@celery_app.task(name='identify_best_posting_times')
def identify_best_posting_times():
    """
    Identify best posting times based on hourly sentiment patterns
    Generates recommendations per subreddit
    """
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT 
                subreddit,
                hour_of_day,
                hour_label,
                avg_sentiment,
                posting_recommendation
            FROM hourly_sentiment_heatmap
            WHERE posting_recommendation = 'Best Time to Post'
            ORDER BY subreddit, avg_sentiment DESC
        """))
        
        best_times = result.fetchall()
        
        if best_times:
            logger.info(f"📅 Identified best posting times:")
            current_subreddit = None
            for time in best_times:
                if time.subreddit != current_subreddit:
                    logger.info(f"\n  {time.subreddit}:")
                    current_subreddit = time.subreddit
                logger.info(f"    - {time.hour_label}: sentiment {time.avg_sentiment:.2f}")
        
        return {"optimal_times": len(best_times)}
        
    except Exception as e:
        logger.error(f"Error identifying posting times: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# ============================================================================
# SCHEDULED TASKS
# ============================================================================

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    from celery.schedules import crontab
    
    # Every day at 6 AM - generate daily heatmap
    sender.add_periodic_task(
        crontab(hour=6, minute=0),
        generate_daily_sentiment_heatmap.s(),
        name='daily_sentiment_heatmap'
    )
    
    # Every day at 7 AM - generate hourly patterns
    sender.add_periodic_task(
        crontab(hour=7, minute=0),
        generate_hourly_sentiment_patterns.s(),
        name='hourly_sentiment_patterns'
    )
    
    # Every 4 hours - detect sentiment shifts
    sender.add_periodic_task(
        crontab(minute=0, hour='*/4'),
        detect_sentiment_shifts.s(),
        name='detect_sentiment_shifts'
    )
    
    # Every day at 8 AM - identify best posting times
    sender.add_periodic_task(
        crontab(hour=8, minute=0),
        identify_best_posting_times.s(),
        name='best_posting_times'
    )


if __name__ == '__main__':
    # Test run
    generate_daily_sentiment_heatmap()
