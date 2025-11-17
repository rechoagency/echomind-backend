"""
Brand Mention Monitor Worker - Simplified for existing schema
Scans target_subreddits and target_keywords from clients table
"""

import os
import praw
from openai import OpenAI
from datetime import datetime, timedelta
from supabase_client import get_supabase_client
import json

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


def scan_for_mentions(client_id, company_name, subreddits, keywords):
    """Scan subreddits for brand mentions"""
    mentions_found = []
    
    print(f"  Scanning {len(subreddits)} subreddits for mentions of '{company_name}'...")
    
    for subreddit_name in subreddits[:5]:  # Limit to 5 subreddits for now
        try:
            subreddit = reddit.subreddit(subreddit_name)
            
            # Get recent posts (last 24 hours)
            for post in subreddit.new(limit=50):
                post_age_hours = (datetime.utcnow().timestamp() - post.created_utc) / 3600
                if post_age_hours > 24:
                    continue
                
                # Check if any keyword appears in title or body
                text = f"{post.title} {post.selftext}".lower()
                matched_keywords = [kw for kw in keywords if kw.lower() in text]
                
                if matched_keywords:
                    # Analyze sentiment with GPT-4
                    sentiment = analyze_sentiment(text, company_name)
                    
                    mention = {
                        "client_id": client_id,
                        "reddit_post_id": post.id,
                        "subreddit": subreddit_name,
                        "author": str(post.author) if post.author else "[deleted]",
                        "title": post.title,
                        "body": post.selftext[:500],
                        "url": f"https://reddit.com{post.permalink}",
                        "sentiment": sentiment,
                        "commercial_intent_score": calculate_intent_score(text),
                        "matched_products": json.dumps({"keywords": matched_keywords}),
                    }
                    
                    mentions_found.append(mention)
                    print(f"    Found mention in r/{subreddit_name}: {sentiment}")
                    
        except Exception as e:
            print(f"    Error scanning r/{subreddit_name}: {e}")
            continue
    
    return mentions_found


def analyze_sentiment(text, brand_name):
    """Analyze sentiment using GPT-4"""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{
                "role": "system",
                "content": f"Analyze the sentiment of this Reddit post about {brand_name}. Respond with ONLY one word: positive, neutral, or negative"
            }, {
                "role": "user",
                "content": text[:500]
            }],
            max_tokens=10
        )
        
        sentiment = response.choices[0].message.content.strip().lower()
        return sentiment if sentiment in ["positive", "neutral", "negative"] else "neutral"
        
    except Exception as e:
        print(f"      Sentiment analysis error: {e}")
        return "neutral"


def calculate_intent_score(text):
    """Calculate commercial intent score (0-100)"""
    buying_signals = [
        "looking for", "need", "want", "buy", "purchase", "recommend",
        "suggestion", "advice", "help", "best", "review", "worth it"
    ]
    
    text_lower = text.lower()
    matches = sum(1 for signal in buying_signals if signal in text_lower)
    
    return min(matches * 15, 100)


def save_mentions(mentions):
    """Save mentions to database"""
    if not mentions:
        return
    
    try:
        supabase.table("brand_mentions").insert(mentions).execute()
        print(f"  Saved {len(mentions)} mentions to database")
    except Exception as e:
        print(f"  Error saving mentions: {e}")


def run_brand_mention_monitor():
    """Main function: Check all clients for brand mentions"""
    print("=" * 70)
    print("BRAND MENTION MONITOR")
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
        
        print(f"📊 Checking {company_name}...")
        print(f"  Keywords: {', '.join(keywords[:5])}...")
        
        mentions = scan_for_mentions(client_id, company_name, subreddits, keywords)
        
        if mentions:
            save_mentions(mentions)
        else:
            print(f"  No mentions found")
    
    print("\n✅ Brand mention monitoring complete")


if __name__ == "__main__":
    run_brand_mention_monitor()
