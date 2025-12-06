"""
Brand Mention Monitor Worker - FIXED VERSION
Scans Reddit and creates opportunities directly (not brand_mentions)
"""

import os
import re
import praw
from openai import OpenAI
from datetime import datetime, timedelta
from supabase_client import get_supabase_client
import json
import uuid

# Initialize clients
supabase = get_supabase_client()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def normalize_word(word):
    """
    Simple stemming - remove common suffixes for better matching.
    Handles: plurals (s, es, ies), ing, ed, ly
    """
    word = word.lower().strip()

    # Handle special cases
    if word.endswith('ies') and len(word) > 4:
        return word[:-3] + 'y'  # fireplaces -> fireplace, babies -> baby
    if word.endswith('es') and len(word) > 3:
        # Check for words like "fireplaces" -> "fireplace"
        if word[:-2].endswith(('c', 's', 'x', 'z', 'sh', 'ch')):
            return word[:-2]
        return word[:-1]  # Just remove the 's'
    if word.endswith('s') and len(word) > 2 and not word.endswith('ss'):
        return word[:-1]
    if word.endswith('ing') and len(word) > 4:
        return word[:-3]
    if word.endswith('ed') and len(word) > 3:
        return word[:-2]

    return word


def keyword_matches(keyword, text):
    """
    Check if keyword matches text using flexible matching:
    1. Direct substring match
    2. Normalized (stemmed) word matching for plural/singular

    Returns True if keyword matches text.
    """
    keyword_lower = keyword.lower()
    text_lower = text.lower()

    # Direct substring match (original behavior)
    if keyword_lower in text_lower:
        return True

    # Normalize the keyword and check each word in text
    keyword_normalized = normalize_word(keyword_lower)

    # For multi-word keywords, check if all words match
    keyword_words = keyword_lower.split()
    if len(keyword_words) > 1:
        # Multi-word keyword: check if all words appear (normalized)
        text_words = set(normalize_word(w) for w in re.findall(r'\w+', text_lower))
        keyword_words_normalized = [normalize_word(w) for w in keyword_words]
        return all(kw in text_words or any(kw in tw for tw in text_words) for kw in keyword_words_normalized)

    # Single word keyword: check normalized version against text words
    text_words = re.findall(r'\w+', text_lower)
    for word in text_words:
        word_normalized = normalize_word(word)
        # Check both directions: keyword stem in word, or word stem in keyword
        if keyword_normalized == word_normalized:
            return True
        if keyword_normalized in word or word_normalized in keyword_lower:
            return True

    return False

reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent=os.getenv("REDDIT_USER_AGENT", "EchoMind/1.0 by recho-agency")
)


def get_active_clients():
    """Get all active clients"""
    response = supabase.table("clients")\
        .select("client_id, company_name, target_subreddits, target_keywords")\
        .eq("subscription_status", "active")\
        .execute()
    
    return response.data


def get_existing_thread_urls(client_id):
    """Get set of existing thread URLs for a client to avoid duplicates"""
    try:
        result = supabase.table("opportunities")\
            .select("thread_url")\
            .eq("client_id", client_id)\
            .execute()
        return set(opp["thread_url"] for opp in result.data) if result.data else set()
    except Exception as e:
        print(f"    Warning: Could not fetch existing opportunities: {e}")
        return set()


def scan_for_opportunities(client_id, company_name, subreddits, keywords):
    """Scan subreddits and create opportunities"""
    opportunities_found = []

    # Get existing thread URLs to avoid duplicates
    existing_urls = get_existing_thread_urls(client_id)
    print(f"  Found {len(existing_urls)} existing opportunities to skip")

    print(f"  Scanning {len(subreddits)} subreddits for opportunities...")

    for subreddit_name in subreddits[:10]:  # Process up to 10 subreddits
        # Remove 'r/' prefix if present
        subreddit_name = subreddit_name.replace('r/', '')

        try:
            subreddit = reddit.subreddit(subreddit_name)

            # Get recent posts (last 48 hours)
            for post in subreddit.new(limit=100):
                post_age_hours = (datetime.utcnow().timestamp() - post.created_utc) / 3600
                if post_age_hours > 48:
                    continue

                thread_url = f"https://reddit.com{post.permalink}"

                # Skip if we already have this thread for this client
                if thread_url in existing_urls:
                    continue

                # Check if any keyword matches using flexible matching
                text = f"{post.title} {post.selftext}"
                matched_keywords = [kw for kw in keywords if keyword_matches(kw, text)]

                if matched_keywords:
                    # Create opportunity directly
                    opportunity = {
                        "opportunity_id": str(uuid.uuid4()),
                        "client_id": client_id,
                        "thread_id": post.id,  # Required NOT NULL field
                        "reddit_post_id": post.id,
                        "subreddit": subreddit_name,
                        "subreddit_members": subreddit.subscribers,
                        "author_username": str(post.author) if post.author else "[deleted]",
                        "thread_title": post.title,
                        "thread_url": thread_url,
                        "original_post_text": post.selftext[:1000],
                        "date_posted": datetime.fromtimestamp(post.created_utc).isoformat(),
                        "matched_keywords": json.dumps(matched_keywords),
                        "engagement_score": min(100, (post.score + post.num_comments) // 5),  # Simple score
                        "relevance_score": 50,  # Will be scored later by opportunity_scoring_worker
                        "timing_score": 85 if post_age_hours < 6 else 70 if post_age_hours < 24 else 50,
                        "commercial_intent_score": calculate_intent_score(text),
                        "overall_priority": 0,  # Will be calculated by scoring worker
                        "urgency_level": "MEDIUM",
                        "content_type": "REPLY" if post.num_comments < 50 else "POST",
                        "status": "pending",
                        "date_found": datetime.utcnow().isoformat()
                    }

                    opportunities_found.append(opportunity)
                    existing_urls.add(thread_url)  # Track to avoid duplicates within same scan
                    print(f"    Found opportunity in r/{subreddit_name}: {post.title[:50]}...")

        except Exception as e:
            print(f"    Error scanning r/{subreddit_name}: {e}")
            continue

    return opportunities_found


def calculate_intent_score(text):
    """Calculate commercial intent score from keywords"""
    intent_keywords = [
        'recommend', 'recommendation', 'best', 'which', 'should i buy',
        'looking for', 'need help', 'suggestions', 'advice', 'worth it'
    ]
    
    matches = sum(1 for keyword in intent_keywords if keyword in text.lower())
    return min(100, matches * 15)


def save_opportunities(opportunities):
    """Save opportunities to database"""
    if not opportunities:
        return
    
    try:
        supabase.table("opportunities").insert(opportunities).execute()
        print(f"  ✅ Saved {len(opportunities)} opportunities to database")
    except Exception as e:
        print(f"  ❌ Error saving opportunities: {e}")


async def monitor_all_clients():
    """Monitor for opportunities for all clients - Called by scheduler"""
    return run_opportunity_monitor()

def run_opportunity_monitor():
    """Main function: Scan Reddit and create opportunities for all clients"""
    print("=" * 70)
    print("REDDIT OPPORTUNITY MONITOR (FIXED)")
    print("=" * 70)
    print(f"Running at {datetime.utcnow().isoformat()}")
    
    clients = get_active_clients()
    print(f"Monitoring {len(clients)} active clients\n")
    
    for client in clients:
        client_id = client["client_id"]
        company_name = client["company_name"]
        subreddits = client.get("target_subreddits", [])
        keywords = client.get("target_keywords", [])
        
        if not subreddits or not keywords:
            print(f"Skipping {company_name}: No subreddits or keywords configured")
            continue
        
        print(f"📊 Scanning for {company_name}...")
        print(f"  Keywords: {', '.join(keywords[:5])}...")
        
        opportunities = scan_for_opportunities(client_id, company_name, subreddits, keywords)
        
        if opportunities:
            save_opportunities(opportunities)
            print(f"  ✅ Created {len(opportunities)} opportunities for {company_name}\n")
        else:
            print(f"  No opportunities found for {company_name}\n")
    
    print("=" * 70)
    print("REDDIT OPPORTUNITY MONITOR COMPLETE")
    print("=" * 70)

if __name__ == "__main__":
    run_opportunity_monitor()
