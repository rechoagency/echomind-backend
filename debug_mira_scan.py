"""
Debug script to test Reddit scanning for Mira
Run: python debug_mira_scan.py
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

import praw
from datetime import datetime
from supabase_client import get_supabase_client

# Initialize
supabase = get_supabase_client()
MIRA_CLIENT_ID = "3cee3b35-33e2-4a0c-8a78-dbccffbca434"

def main():
    print("=" * 70)
    print("MIRA REDDIT SCAN DEBUG")
    print("=" * 70)

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
    print(f"\nKeywords: {keywords[:10]}...")
    print(f"\nSubreddits: {subreddits}")

    # Initialize Reddit
    print("\n" + "=" * 70)
    print("Testing Reddit Connection")
    print("=" * 70)

    client_id = os.getenv("REDDIT_CLIENT_ID")
    print(f"REDDIT_CLIENT_ID: {client_id[:5] if client_id else 'NOT SET'}...")

    try:
        reddit = praw.Reddit(
            client_id=os.getenv("REDDIT_CLIENT_ID"),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            user_agent=os.getenv("REDDIT_USER_AGENT", "EchoMind/1.0")
        )
        print("Reddit initialized successfully")
    except Exception as e:
        print(f"ERROR initializing Reddit: {e}")
        return

    # Test each subreddit
    print("\n" + "=" * 70)
    print("Testing Subreddit Access")
    print("=" * 70)

    total_matches = 0

    for sub_name in subreddits[:5]:
        sub_name = sub_name.replace('r/', '')
        print(f"\n--- r/{sub_name} ---")

        try:
            subreddit = reddit.subreddit(sub_name)
            subs = subreddit.subscribers
            print(f"  Accessible: YES ({subs:,} subscribers)")

            posts_found = 0
            posts_in_48h = 0
            matches = 0

            for post in subreddit.new(limit=50):
                posts_found += 1
                post_age_hours = (datetime.utcnow().timestamp() - post.created_utc) / 3600

                if post_age_hours <= 48:
                    posts_in_48h += 1
                    text = f"{post.title} {post.selftext}".lower()

                    matched_kws = []
                    for kw in keywords:
                        if kw.lower() in text:
                            matched_kws.append(kw)

                    if matched_kws:
                        matches += 1
                        if matches <= 3:
                            print(f"  MATCH: '{matched_kws[0]}' in '{post.title[:60]}...'")

            print(f"  Posts found: {posts_found}")
            print(f"  Posts <48h: {posts_in_48h}")
            print(f"  Keyword matches: {matches}")
            total_matches += matches

        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n" + "=" * 70)
    print(f"TOTAL KEYWORD MATCHES FOUND: {total_matches}")
    print("=" * 70)

if __name__ == "__main__":
    main()
