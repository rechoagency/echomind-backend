"""
EchoMind Keyword Tracking Worker
Tracks keyword mentions, calculates velocity, identifies trends
"""

import os
from datetime import datetime, date, timedelta
from typing import List, Dict, Optional
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
celery_app = Celery('keyword_tracking', broker=os.getenv('CELERY_BROKER_URL'))

# Database setup
DATABASE_URL = os.getenv('DATABASE_URL')
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


# ============================================================================
# KEYWORD EXTRACTION AND TRACKING
# ============================================================================

@celery_app.task(name='extract_and_track_keywords')
def extract_and_track_keywords(client_id: str, text: str, source_type: str, 
                                source_reddit_id: str, subreddit: str):
    """
    Extract keywords from text and record mentions
    Called when new questions/answers are discovered
    """
    db = SessionLocal()
    try:
        # Get client's target keywords
        result = db.execute(text("""
            SELECT target_keywords FROM clients WHERE client_id = :client_id
        """), {"client_id": client_id})
        
        row = result.fetchone()
        if not row:
            return
        
        target_keywords = row.target_keywords
        
        # Extract keyword mentions from text
        text_lower = text.lower()
        
        for keyword in target_keywords:
            if keyword.lower() in text_lower:
                # Extract surrounding context
                surrounding_text = extract_context(text, keyword)
                
                # Calculate sentiment (simple placeholder)
                sentiment = calculate_simple_sentiment(surrounding_text)
                
                # Record mention
                db.execute(text("""
                    INSERT INTO keyword_mention_instances (
                        client_id,
                        keyword,
                        source_type,
                        source_reddit_id,
                        source_url,
                        subreddit,
                        surrounding_text,
                        full_text,
                        sentiment,
                        discovered_at
                    ) VALUES (
                        :client_id, :keyword, :source_type, :source_reddit_id,
                        :source_url, :subreddit, :surrounding_text, :full_text,
                        :sentiment, :discovered_at
                    )
                """), {
                    "client_id": client_id,
                    "keyword": keyword,
                    "source_type": source_type,
                    "source_reddit_id": source_reddit_id,
                    "source_url": f"https://reddit.com/{source_reddit_id}",
                    "subreddit": subreddit,
                    "surrounding_text": surrounding_text,
                    "full_text": text[:1000],  # Limit to 1000 chars
                    "sentiment": sentiment,
                    "discovered_at": datetime.now()
                })
        
        db.commit()
        logger.info(f"Tracked keywords for {source_type} in {subreddit}")
        
    except Exception as e:
        logger.error(f"Error tracking keywords: {e}")
        db.rollback()
    finally:
        db.close()


def extract_context(text: str, keyword: str, context_chars: int = 100) -> str:
    """Extract surrounding text around keyword"""
    text_lower = text.lower()
    keyword_lower = keyword.lower()
    
    pos = text_lower.find(keyword_lower)
    if pos == -1:
        return ""
    
    start = max(0, pos - context_chars)
    end = min(len(text), pos + len(keyword) + context_chars)
    
    return text[start:end]


def calculate_simple_sentiment(text: str) -> str:
    """Simple sentiment calculation based on keyword presence"""
    positive_words = ['great', 'excellent', 'amazing', 'love', 'best', 'perfect', 'awesome']
    negative_words = ['bad', 'terrible', 'worst', 'hate', 'awful', 'poor', 'disappointed']
    
    text_lower = text.lower()
    positive_count = sum(1 for word in positive_words if word in text_lower)
    negative_count = sum(1 for word in negative_words if word in text_lower)
    
    if positive_count > negative_count:
        return 'positive'
    elif negative_count > positive_count:
        return 'negative'
    else:
        return 'neutral'


# ============================================================================
# WEEKLY VELOCITY CALCULATIONS
# ============================================================================

@celery_app.task(name='calculate_weekly_keyword_velocity')
def calculate_weekly_keyword_velocity():
    """
    Calculate keyword velocity for the current week
    Runs every Monday morning
    """
    logger.info("Calculating weekly keyword velocity")
    
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT calculate_weekly_keyword_velocity()"))
        count = result.scalar()
        
        logger.info(f"✅ Calculated velocity for {count} keywords")
        return {"keywords_processed": count}
        
    except Exception as e:
        logger.error(f"Error calculating keyword velocity: {e}")
        return {"error": str(e)}
    finally:
        db.close()


@celery_app.task(name='identify_trending_keywords')
def identify_trending_keywords():
    """
    Identify keywords that are trending (24h spike)
    Runs every hour
    """
    db = SessionLocal()
    try:
        # Get trending keywords
        result = db.execute(text("""
            SELECT 
                client_id,
                keyword,
                mentions_24h,
                change_24h,
                alert_level,
                hottest_subreddit
            FROM trending_keywords_realtime
            WHERE alert_level IN ('SPIKE - 2x increase in 24h', 'TRENDING - 1.5x increase in 24h')
            ORDER BY mentions_24h DESC
            LIMIT 10
        """))
        
        trending = result.fetchall()
        
        if trending:
            logger.info(f"🔥 Found {len(trending)} trending keywords")
            for trend in trending:
                logger.info(f"  - {trend.keyword}: {trend.mentions_24h} mentions (+{trend.change_24h}) in {trend.hottest_subreddit}")
                
                # Could send alerts here (Slack, email, etc.)
        
        return {"trending_keywords": len(trending)}
        
    except Exception as e:
        logger.error(f"Error identifying trending keywords: {e}")
        return {"error": str(e)}
    finally:
        db.close()


# ============================================================================
# KEYWORD DISCOVERY (Auto-detect new keywords)
# ============================================================================

@celery_app.task(name='discover_new_keywords')
def discover_new_keywords():
    """
    Auto-discover new keywords from questions/answers
    Using NLP to find frequently occurring phrases
    """
    db = SessionLocal()
    try:
        # Get all text from last 7 days
        result = db.execute(text("""
            SELECT 
                client_id,
                question_title || ' ' || question_body as text
            FROM reddit_answers_questions
            WHERE discovered_at >= NOW() - INTERVAL '7 days'
        """))
        
        rows = result.fetchall()
        
        # Extract n-grams (2-3 word phrases)
        client_phrases = {}
        for row in rows:
            if row.client_id not in client_phrases:
                client_phrases[row.client_id] = []
            
            phrases = extract_ngrams(row.text, n=2) + extract_ngrams(row.text, n=3)
            client_phrases[row.client_id].extend(phrases)
        
        # Find most common phrases per client
        for client_id, phrases in client_phrases.items():
            phrase_counts = Counter(phrases)
            top_phrases = phrase_counts.most_common(20)
            
            logger.info(f"Client {client_id}: Top phrases discovered")
            for phrase, count in top_phrases[:5]:
                logger.info(f"  - '{phrase}': {count} occurrences")
        
        return {"clients_analyzed": len(client_phrases)}
        
    except Exception as e:
        logger.error(f"Error discovering keywords: {e}")
        return {"error": str(e)}
    finally:
        db.close()


def extract_ngrams(text: str, n: int = 2) -> List[str]:
    """Extract n-grams from text"""
    # Clean and tokenize
    text = re.sub(r'[^\w\s]', '', text.lower())
    words = text.split()
    
    # Remove common stop words
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}
    words = [w for w in words if w not in stop_words and len(w) > 2]
    
    # Extract n-grams
    ngrams = []
    for i in range(len(words) - n + 1):
        ngram = ' '.join(words[i:i+n])
        ngrams.append(ngram)
    
    return ngrams


# ============================================================================
# SCHEDULED TASKS
# ============================================================================

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Every Monday at 3 AM
    sender.add_periodic_task(
        crontab(hour=3, minute=0, day_of_week=1),
        calculate_weekly_keyword_velocity.s(),
        name='weekly_keyword_velocity'
    )
    
    # Every hour
    sender.add_periodic_task(
        crontab(minute=0),
        identify_trending_keywords.s(),
        name='hourly_trending_check'
    )
    
    # Every day at 4 AM
    sender.add_periodic_task(
        crontab(hour=4, minute=0),
        discover_new_keywords.s(),
        name='daily_keyword_discovery'
    )


if __name__ == '__main__':
    # Test run
    calculate_weekly_keyword_velocity()
