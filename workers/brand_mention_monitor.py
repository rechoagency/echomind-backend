"""
Brand Mention Monitor Worker - FIXED VERSION
Scans Reddit and creates opportunities directly (not brand_mentions)
"""

import os
import praw
from openai import OpenAI
from datetime import datetime, timedelta
from supabase_client import get_supabase_client
import json
import uuid

# Initialize clients
supabase = get_supabase_client()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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


def scan_for_opportunities(client_id, company_name, subreddits, keywords):
    """Scan subreddits and create opportunities"""
    opportunities_found = []
    
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
                
                # Check if any keyword appears in title or body
                text = f"{post.title} {post.selftext}".lower()
                matched_keywords = [kw for kw in keywords if kw.lower() in text]
                
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
                        "thread_url": f"https://reddit.com{post.permalink}",
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
