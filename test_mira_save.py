"""
Test saving opportunities for Mira - diagnose database insert issues
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

import praw
import uuid
import json
from datetime import datetime
from supabase_client import get_supabase_client

MIRA_CLIENT_ID = "3cee3b35-33e2-4a0c-8a78-dbccffbca434"

def main():
    print("=" * 70)
    print("MIRA OPPORTUNITY SAVE TEST")
    print("=" * 70)

    supabase = get_supabase_client()

    # Get client config
    client = supabase.table("clients").select("*").eq("client_id", MIRA_CLIENT_ID).execute()
    if not client.data:
        print("ERROR: Client not found")
        return

    client_data = client.data[0]
    company_name = client_data.get("company_name")
    subreddits = client_data.get("target_subreddits", [])
    keywords = client_data.get("target_keywords", [])

    print(f"\nClient: {company_name}")
    print(f"Subreddits: {len(subreddits)}")
    print(f"Keywords: {len(keywords)}")

    # Get existing URLs
    existing_result = supabase.table("opportunities")\
        .select("thread_url")\
        .eq("client_id", MIRA_CLIENT_ID)\
        .execute()
    existing_urls = set(opp["thread_url"] for opp in existing_result.data) if existing_result.data else set()
    print(f"Existing opportunities: {len(existing_urls)}")

    # Initialize Reddit
    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent=os.getenv("REDDIT_USER_AGENT", "EchoMind/1.0")
    )

    # Scan ONE subreddit
    sub_name = subreddits[0].replace('r/', '')
    print(f"\n--- Scanning r/{sub_name} ---")

    subreddit = reddit.subreddit(sub_name)
    subscribers = subreddit.subscribers
    print(f"Subscribers: {subscribers:,}")

    posts_scanned = 0
    matches_found = 0
    saved = 0
    errors = []

    for post in subreddit.new(limit=25):
        posts_scanned += 1
        post_age_hours = (datetime.utcnow().timestamp() - post.created_utc) / 3600

        if post_age_hours > 48:
            continue

        thread_url = f"https://reddit.com{post.permalink}"

        if thread_url in existing_urls:
            continue

        # Check keyword matches
        text = f"{post.title} {post.selftext}"
        matched_keywords = [kw for kw in keywords if kw.lower() in text.lower()]

        if matched_keywords:
            matches_found += 1
            print(f"\n  Match #{matches_found}: '{matched_keywords[0]}'")
            print(f"  Title: {post.title[:60]}...")

            # Build opportunity
            opportunity = {
                "opportunity_id": str(uuid.uuid4()),
                "client_id": MIRA_CLIENT_ID,
                "thread_id": post.id,
                "reddit_post_id": post.id,
                "subreddit": sub_name,
                "subreddit_members": subscribers,
                "author_username": str(post.author) if post.author else "[deleted]",
                "thread_title": post.title,
                "thread_url": thread_url,
                "original_post_text": post.selftext[:1000] if post.selftext else "",
                "date_posted": datetime.fromtimestamp(post.created_utc).isoformat(),
                "matched_keywords": json.dumps(matched_keywords),
                "engagement_score": min(100, (post.score + post.num_comments) // 5),
                "relevance_score": 50,
                "timing_score": 85 if post_age_hours < 6 else 70 if post_age_hours < 24 else 50,
                "commercial_intent_score": 50,
                "overall_priority": 0,
                "urgency_level": "MEDIUM",
                "content_type": "REPLY",
                "status": "pending",
                "date_found": datetime.utcnow().isoformat()
            }

            # Try to save
            try:
                result = supabase.table("opportunities").insert(opportunity).execute()
                saved += 1
                existing_urls.add(thread_url)
                print(f"  SAVED successfully!")
            except Exception as e:
                errors.append(str(e))
                print(f"  SAVE FAILED: {e}")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Posts scanned: {posts_scanned}")
    print(f"Matches found: {matches_found}")
    print(f"Successfully saved: {saved}")
    print(f"Save errors: {len(errors)}")

    if errors:
        print("\nErrors:")
        for e in errors:
            print(f"  - {e[:200]}")

if __name__ == "__main__":
    main()
