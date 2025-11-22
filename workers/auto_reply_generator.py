"""
Auto-Reply Generator Worker - Simplified for existing schema
Detects replies to client posts and generates contextual responses
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
        .select("client_id, company_name, target_subreddits")\
        .eq("subscription_status", "active")\
        .execute()
    
    return response.data


def get_client_posts(client_id, subreddits):
    """Get recent posts from opportunities table"""
    try:
        # Get posts from last 7 days
        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
        
        response = supabase.table("opportunities")\
            .select("reddit_post_id, subreddit, post_url")\
            .eq("client_id", client_id)\
            .gte("created_at", week_ago)\
            .execute()
        
        return response.data
        
    except Exception as e:
        print(f"  Error fetching client posts: {e}")
        return []


def check_for_replies(post_id, subreddit_name):
    """Check if post has new replies"""
    try:
        submission = reddit.submission(id=post_id)
        submission.comments.replace_more(limit=0)
        
        # Get all comments
        comments = []
        for comment in submission.comments.list():
            if comment.author and str(comment.author) != "[deleted]":
                comments.append({
                    "comment_id": comment.id,
                    "author": str(comment.author),
                    "body": comment.body,
                    "created_utc": comment.created_utc
                })
        
        return comments
        
    except Exception as e:
        print(f"    Error checking replies for {post_id}: {e}")
        return []


def generate_reply(original_post_text, comment_text, company_name, products):
    """Generate reply using GPT-4"""
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[{
                "role": "system",
                "content": f"""You are a helpful community member responding to questions about {company_name}.
                
Generate a natural, helpful reply that:
- Addresses their specific question/concern
- Is conversational and empathetic
- Mentions relevant products naturally if appropriate: {', '.join(products[:3])}
- Keeps it brief (2-3 sentences)
- Sounds human, not like marketing copy"""
            }, {
                "role": "user",
                "content": f"Original post context: {original_post_text[:300]}\n\nComment to respond to: {comment_text}"
            }],
            max_tokens=150
        )
        
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"      Reply generation error: {e}")
        return None


def save_auto_reply(client_id, parent_post_id, reply_to_comment_id, subreddit, generated_reply):
    """Save generated reply to database"""
    try:
        reply_data = {
            "client_id": client_id,
            "parent_post_id": parent_post_id,
            "reply_to_comment_id": reply_to_comment_id,
            "subreddit": subreddit,
            "generated_reply": generated_reply,
            "status": "pending"
        }
        
        supabase.table("auto_replies").insert(reply_data).execute()
        print(f"      ✅ Saved reply for approval")
        
    except Exception as e:
        print(f"      Error saving reply: {e}")


async def generate_all_auto_replies():
    """Generate auto-replies for all clients - Called by scheduler"""
    return run_auto_reply_generator()

def run_auto_reply_generator():
    """Main function: Generate replies for client posts"""
    print("=" * 70)
    print("AUTO-REPLY GENERATOR")
    print("=" * 70)
    print(f"Running at {datetime.utcnow().isoformat()}")
    
    clients = get_active_clients()
    print(f"Checking {len(clients)} active clients\n")
    
    total_replies_generated = 0
    
    for client in clients:
        client_id = client["client_id"]
        company_name = client["company_name"]
        subreddits = client.get("target_subreddits", [])
        
        print(f"💬 Checking {company_name}...")
        
        # Get client's recent posts
        posts = get_client_posts(client_id, subreddits)
        
        if not posts:
            print(f"  No recent posts found")
            continue
        
        print(f"  Found {len(posts)} recent posts to check")
        
        # Check each post for replies
        for post in posts[:10]:  # Limit to 10 most recent posts
            post_id = post["reddit_post_id"]
            subreddit = post["subreddit"]
            
            comments = check_for_replies(post_id, subreddit)
            
            if comments:
                print(f"    Post {post_id}: {len(comments)} comments")
                
                # Generate reply for first unanswered comment
                for comment in comments[:3]:  # Limit to 3 per post
                    # Check if we already generated a reply for this comment
                    existing = supabase.table("auto_replies")\
                        .select("id")\
                        .eq("reply_to_comment_id", comment["comment_id"])\
                        .execute()
                    
                    if existing.data:
                        continue  # Already have a reply for this
                    
                    # Generate new reply
                    generated = generate_reply(
                        post.get("post_url", ""),
                        comment["body"],
                        company_name,
                        ["postpartum", "breastfeeding", "pregnancy"]
                    )
                    
                    if generated:
                        save_auto_reply(client_id, post_id, comment["comment_id"], subreddit, generated)
                        total_replies_generated += 1
    
    print(f"\n✅ Auto-reply generation complete: {total_replies_generated} replies pending approval")


if __name__ == "__main__":
    run_auto_reply_generator()
