"""
EchoMind Topic Extraction Worker
NLP-based topic extraction and velocity tracking
"""

import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional, Set
import re
from collections import Counter
from celery import Celery
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging

# Setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Celery setup
celery_app = Celery('topic_extraction', broker=os.getenv('CELERY_BROKER_URL'))

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


# ============================================================================
# TOPIC EXTRACTION
# ============================================================================

@celery_app.task(name='extract_topics_from_text')
def extract_topics_from_text(client_id: str, text: str, source_type: str,
                             source_reddit_id: str, thread_reddit_id: str,
                             subreddit: str, thread_score: int = 0):
    """
    Extract topics from question/comment text
    Uses simple NLP (noun phrases, keyword matching)
    """
    db = SessionLocal()
    try:
        # Extract potential topics
        topics = extract_topic_phrases(text)
        
        # Calculate sentiment
        sentiment = calculate_text_sentiment(text)
        
        # Check if thread has high engagement
        is_high_engagement = thread_score >= 50
        
        for topic in topics:
            # Get or create topic
            topic_id = get_or_create_topic(db, client_id, topic)
            
            if topic_id:
                # Record mention
                db.execute(text("""
                    INSERT INTO topic_mentions (
                        topic_id,
                        client_id,
                        source_type,
                        source_reddit_id,
                        thread_reddit_id,
                        subreddit,
                        mention_text,
                        thread_score,
                        thread_comments,
                        is_high_engagement,
                        sentiment_score,
                        discovered_at
                    ) VALUES (
                        :topic_id, :client_id, :source_type, :source_reddit_id,
                        :thread_reddit_id, :subreddit, :mention_text, :thread_score,
                        0, :is_high_engagement, :sentiment_score, :discovered_at
                    )
                """), {
                    "topic_id": topic_id,
                    "client_id": client_id,
                    "source_type": source_type,
                    "source_reddit_id": source_reddit_id,
                    "thread_reddit_id": thread_reddit_id,
                    "subreddit": subreddit,
                    "mention_text": text[:200],
                    "thread_score": thread_score,
                    "is_high_engagement": is_high_engagement,
                    "sentiment_score": sentiment,
                    "discovered_at": datetime.now()
                })
        
        db.commit()
        logger.info(f"Extracted {len(topics)} topics from {source_type} in {subreddit}")
        
    except Exception as e:
        logger.error(f"Error extracting topics: {e}")
        db.rollback()
    finally:
        db.close()


def extract_topic_phrases(text: str) -> Set[str]:
    """
    Extract topic phrases from text
    Simple NLP: look for noun phrases, multi-word expressions
    """
    topics = set()
    
    # Clean text
    text_lower = text.lower()
    
    # Common topic patterns (2-3 word phrases)
    # This is simplified - in production would use spaCy or NLTK
    words = re.findall(r'\b[a-z]+\b', text_lower)
    
    # Extract 2-grams and 3-grams
    for i in range(len(words) - 1):
        # 2-word phrases
        phrase = f"{words[i]} {words[i+1]}"
        if is_valid_topic(phrase):
            topics.add(phrase)
        
        # 3-word phrases
        if i < len(words) - 2:
            phrase = f"{words[i]} {words[i+1]} {words[i+2]}"
            if is_valid_topic(phrase):
                topics.add(phrase)
    
    return topics


def is_valid_topic(phrase: str) -> bool:
    """Check if phrase is a valid topic"""
    # Filter out common stop words and short phrases
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
                  'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during'}
    
    words = phrase.split()
    
    # Must be 2-3 words
    if len(words) < 2 or len(words) > 3:
        return False
    
    # Can't start or end with stop word
    if words[0] in stop_words or words[-1] in stop_words:
        return False
    
    # Must have at least one word longer than 3 chars
    if not any(len(w) > 3 for w in words):
        return False
    
    return True


def calculate_text_sentiment(text: str) -> float:
    """Calculate sentiment score (-1.0 to 1.0)"""
    positive_words = ['great', 'excellent', 'amazing', 'love', 'best', 'perfect', 
                     'awesome', 'fantastic', 'wonderful', 'outstanding']
    negative_words = ['bad', 'terrible', 'worst', 'hate', 'awful', 'poor', 
                     'disappointed', 'horrible', 'useless', 'frustrating']
    
    text_lower = text.lower()
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)
    
    total = positive_count + negative_count
    if total == 0:
        return 0.0
    
    return (positive_count - negative_count) / total


def get_or_create_topic(db, client_id: str, topic_name: str) -> Optional[str]:
    """Get existing topic or create new one"""
    try:
        # Check if exists
        result = db.execute(text("""
            SELECT topic_id FROM topic_tracking
            WHERE client_id = :client_id AND topic_name = :topic_name
        """), {"client_id": client_id, "topic_name": topic_name})
        
        row = result.fetchone()
        if row:
            return str(row.topic_id)
        
        # Create new topic
        result = db.execute(text("""
            INSERT INTO topic_tracking (
                client_id,
                topic_name,
                topic_category,
                first_seen_date,
                last_seen_date,
                is_active
            ) VALUES (
                :client_id, :topic_name, 'auto_discovered',
                CURRENT_DATE, CURRENT_DATE, true
            ) RETURNING topic_id
        """), {"client_id": client_id, "topic_name": topic_name})
        
        db.commit()
        row = result.fetchone()
        return str(row.topic_id) if row else None
        
    except Exception as e:
        logger.error(f"Error getting/creating topic: {e}")
        return None


# ============================================================================
# DAILY VELOCITY CALCULATIONS
# ============================================================================

@celery_app.task(name='calculate_daily_topic_velocity')
def calculate_daily_topic_velocity():
    """
    Calculate topic velocity for yesterday
    Runs every day at 5 AM
    """
    logger.info("Calculating daily topic velocity")
    
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT calculate_daily_topic_velocity()"))
        count = result.scalar()
        
        logger.info(f"✅ Calculated velocity for {count} topics")
        return {"topics_processed": count}
        
    except Exception as e:
        logger.error(f"Error calculating topic velocity: {e}")
        return {"error": str(e)}
    finally:
        db.close()


@celery_app.task(name='identify_spiking_topics')
def identify_spiking_topics():
    """
    Identify topics that are spiking
    Runs every 2 hours
    """
    db = SessionLocal()
    try:
        result = db.execute(text("""
            SELECT 
                tt.topic_name,
                tv.mentions_count,
                tv.mentions_change_pct,
                tv.momentum_score,
                tv.opportunity_score,
                tv.top_subreddit,
                tv.alert_level
            FROM topic_velocity tv
            JOIN topic_tracking tt ON tv.topic_id = tt.topic_id
            WHERE tv.period_type = 'daily'
            AND tv.period_start >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            AND tv.momentum_score >= 70
            ORDER BY tv.momentum_score DESC
            LIMIT 10
        """))
        
        spiking = result.fetchall()
        
        if spiking:
            logger.info(f"🔥 Found {len(spiking)} spiking topics")
            for topic in spiking:
                logger.info(f"  - {topic.topic_name}: {topic.mentions_count} mentions "
                          f"(+{topic.mentions_change_pct}%) in {topic.top_subreddit}")
                logger.info(f"    Momentum: {topic.momentum_score}/100, "
                          f"Opportunity: {topic.opportunity_score}/100")
        
        return {"spiking_topics": len(spiking)}
        
    except Exception as e:
        logger.error(f"Error identifying spiking topics: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# ============================================================================
# TOPIC RECOMMENDATIONS
# ============================================================================

@celery_app.task(name='generate_topic_recommendations')
def generate_topic_recommendations():
    """
    Generate posting recommendations based on trending topics
    Sends alerts for urgent opportunities
    """
    db = SessionLocal()
    try:
        # Get urgent opportunities
        result = db.execute(text("""
            SELECT 
                c.client_id,
                c.company_name,
                tt.topic_name,
                tv.momentum_score,
                tv.opportunity_score,
                tv.top_subreddit,
                tv.predicted_peak_time
            FROM topic_velocity tv
            JOIN topic_tracking tt ON tv.topic_id = tt.topic_id
            JOIN clients c ON tt.client_id = c.client_id
            WHERE tv.period_type = 'daily'
            AND tv.period_start >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            AND tv.momentum_score >= 80
            AND tv.opportunity_score >= 70
            ORDER BY tv.momentum_score DESC
        """))
        
        recommendations = result.fetchall()
        
        if recommendations:
            logger.info(f"📬 Generated {len(recommendations)} urgent recommendations")
            for rec in recommendations:
                logger.info(f"  URGENT - {rec.company_name}: Post about '{rec.topic_name}' "
                          f"in {rec.top_subreddit} NOW!")
                
                # Could send Slack/email alerts here
        
        return {"recommendations": len(recommendations)}
        
    except Exception as e:
        logger.error(f"Error generating recommendations: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# ============================================================================
# SCHEDULED TASKS
# ============================================================================

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    from celery.schedules import crontab
    
    # Every day at 5 AM
    sender.add_periodic_task(
        crontab(hour=5, minute=0),
        calculate_daily_topic_velocity.s(),
        name='daily_topic_velocity'
    )
    
    # Every 2 hours
    sender.add_periodic_task(
        crontab(minute=0, hour='*/2'),
        identify_spiking_topics.s(),
        name='identify_spiking_topics'
    )
    
    # Every hour
    sender.add_periodic_task(
        crontab(minute=30),
        generate_topic_recommendations.s(),
        name='topic_recommendations'
    )


if __name__ == '__main__':
    # Test run
    calculate_daily_topic_velocity()
