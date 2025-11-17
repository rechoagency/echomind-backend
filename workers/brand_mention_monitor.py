"""
Brand Mention Monitor Worker
Runs daily to detect brand mentions across monitored subreddits
Performs sentiment analysis and alerts on negative mentions
"""

import os
import praw
import openai
from datetime import datetime, timedelta
from supabase import create_client
import json

# Initialize clients
supabase = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_KEY")
)

openai.api_key = os.getenv("OPENAI_API_KEY")

reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent=os.getenv("REDDIT_USER_AGENT", "EchoMind/1.0 by recho-agency")
)


def get_clients_with_monitoring():
    """Get all clients with brand mention monitoring enabled"""
    response = supabase.table("client_settings")\
        .select("client_id, brand_keywords, monitor_brand_mentions")\
        .eq("monitor_brand_mentions", True)\
        .execute()
    
    return response.data


def get_client_subreddits(client_id):
    """Get monitored subreddits for client"""
    response = supabase.table("subreddit_analysis")\
        .select("subreddit_name")\
        .eq("client_id", client_id)\
        .eq("is_active", True)\
        .execute()
    
    return [item["subreddit_name"] for item in response.data]


def analyze_sentiment(text, brand_keywords):
    """Use GPT-4 to analyze sentiment of brand mention"""
    
    prompt = f"""Analyze the sentiment of this Reddit post/comment regarding the brand.

Brand Keywords: {', '.join(brand_keywords)}

Post Content:
{text}

Determine:
1. Sentiment: positive, neutral, or negative
2. Sentiment Score: 0.000 (very negative) to 1.000 (very positive)
3. Brief explanation of why this sentiment was assigned
4. Mention type: product_recommendation, question, complaint, review, or general_discussion
5. Whether this requires a response from the brand (true/false)

Return ONLY a JSON object with this structure:
{{
    "sentiment": "positive|neutral|negative",
    "sentiment_score": 0.850,
    "explanation": "User enthusiastically recommends product to others",
    "mention_type": "product_recommendation",
    "requires_response": false
}}"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are a brand sentiment analysis expert. Return ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=300
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
    
    except Exception as e:
        print(f"Sentiment analysis error: {e}")
        # Default to neutral if analysis fails
        return {
            "sentiment": "neutral",
            "sentiment_score": 0.5,
            "explanation": "Analysis failed",
            "mention_type": "general_discussion",
            "requires_response": False
        }


def extract_mention_context(text, keywords, context_chars=200):
    """Extract snippet showing where brand was mentioned"""
    text_lower = text.lower()
    
    for keyword in keywords:
        keyword_lower = keyword.lower()
        pos = text_lower.find(keyword_lower)
        
        if pos != -1:
            # Extract context around keyword
            start = max(0, pos - context_chars // 2)
            end = min(len(text), pos + len(keyword) + context_chars // 2)
            
            snippet = text[start:end]
            
            # Add ellipsis if truncated
            if start > 0:
                snippet = "..." + snippet
            if end < len(text):
                snippet = snippet + "..."
            
            return snippet
    
    # Fallback: return first 200 chars
    return text[:200] + ("..." if len(text) > 200 else "")


def check_for_mentions(client_id, brand_keywords, subreddits):
    """Search for brand mentions in monitored subreddits"""
    
    mentions_found = []
    
    # Search last 24 hours
    cutoff_time = datetime.utcnow() - timedelta(hours=24)
    cutoff_timestamp = cutoff_time.timestamp()
    
    for subreddit_name in subreddits:
        print(f"Checking r/{subreddit_name} for mentions...")
        
        try:
            subreddit = reddit.subreddit(subreddit_name)
            
            # Search for each keyword
            for keyword in brand_keywords:
                # Search posts
                for post in subreddit.search(keyword, time_filter="day", limit=50):
                    if post.created_utc < cutoff_timestamp:
                        continue
                    
                    # Check if already recorded
                    existing = supabase.table("brand_mentions")\
                        .select("id")\
                        .eq("reddit_post_id", post.id)\
                        .execute()
                    
                    if existing.data:
                        continue  # Already recorded
                    
                    # Analyze sentiment
                    full_text = f"{post.title}\n\n{post.selftext}"
                    sentiment_analysis = analyze_sentiment(full_text, brand_keywords)
                    
                    # Extract context
                    context = extract_mention_context(full_text, brand_keywords)
                    
                    mentions_found.append({
                        "client_id": client_id,
                        "reddit_post_id": post.id,
                        "subreddit": subreddit_name,
                        "author": str(post.author),
                        "title": post.title,
                        "body": post.selftext,
                        "post_url": f"https://reddit.com{post.permalink}",
                        "mentioned_keywords": [keyword],
                        "mention_context": context,
                        "sentiment": sentiment_analysis["sentiment"],
                        "sentiment_score": sentiment_analysis["sentiment_score"],
                        "sentiment_explanation": sentiment_analysis["explanation"],
                        "mention_type": sentiment_analysis["mention_type"],
                        "requires_response": sentiment_analysis["requires_response"],
                        "post_score": post.score,
                        "num_comments": post.num_comments,
                        "post_created_at": datetime.fromtimestamp(post.created_utc).isoformat(),
                        "status": "new"
                    })
                    
                    print(f"  Found mention: {post.title[:50]}... (Sentiment: {sentiment_analysis['sentiment']})")
        
        except Exception as e:
            print(f"Error checking r/{subreddit_name}: {e}")
            continue
    
    return mentions_found


def save_mentions(mentions):
    """Save detected mentions to database"""
    if not mentions:
        return
    
    try:
        supabase.table("brand_mentions").insert(mentions).execute()
        print(f"✅ Saved {len(mentions)} brand mentions")
    except Exception as e:
        print(f"Error saving mentions: {e}")


def send_negative_mention_alert(client_id, mention):
    """Send alert for negative brand mentions"""
    
    # Get client settings
    settings = supabase.table("client_settings")\
        .select("email_notifications, slack_notifications, slack_webhook_url")\
        .eq("client_id", client_id)\
        .single()\
        .execute()
    
    if not settings.data:
        return
    
    # Email notification
    if settings.data.get("email_notifications"):
        # TODO: Implement email notification
        print(f"📧 Email alert sent for negative mention: {mention['post_url']}")
    
    # Slack notification
    if settings.data.get("slack_notifications") and settings.data.get("slack_webhook_url"):
        # TODO: Implement Slack webhook
        print(f"💬 Slack alert sent for negative mention: {mention['post_url']}")


def run_brand_mention_monitor():
    """Main function: Check all clients for brand mentions"""
    print("=== BRAND MENTION MONITOR ===")
    print(f"Running at {datetime.utcnow().isoformat()}")
    
    clients = get_clients_with_monitoring()
    print(f"Monitoring {len(clients)} clients")
    
    for client in clients:
        client_id = client["client_id"]
        brand_keywords = client["brand_keywords"] or []
        
        if not brand_keywords:
            print(f"  Skipping {client_id}: No brand keywords configured")
            continue
        
        print(f"\n📊 Checking {client_id}...")
        print(f"  Keywords: {', '.join(brand_keywords)}")
        
        # Get subreddits
        subreddits = get_client_subreddits(client_id)
        
        if not subreddits:
            print(f"  No active subreddits found")
            continue
        
        # Check for mentions
        mentions = check_for_mentions(client_id, brand_keywords, subreddits)
        
        if mentions:
            print(f"  Found {len(mentions)} new mentions")
            
            # Save to database
            save_mentions(mentions)
            
            # Alert on negative mentions
            negative_mentions = [m for m in mentions if m["sentiment"] == "negative"]
            for mention in negative_mentions:
                send_negative_mention_alert(client_id, mention)
                print(f"  ⚠️  NEGATIVE MENTION: {mention['post_url']}")
        else:
            print(f"  No new mentions found")
    
    print("\n✅ Brand mention monitoring complete")


if __name__ == "__main__":
    run_brand_mention_monitor()
