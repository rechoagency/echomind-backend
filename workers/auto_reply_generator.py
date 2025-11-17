"""
Auto-Reply Generator Worker
Detects replies to our Reddit posts and generates contextual responses
Requires approval before posting (unless auto_reply_requires_approval = false)
"""

import os
import praw
import openai
from datetime import datetime, timedelta
from supabase import create_client
import json
import re

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


def get_clients_with_auto_reply():
    """Get all clients with auto-reply enabled"""
    response = supabase.table("client_settings")\
        .select("client_id, auto_reply_enabled, auto_reply_requires_approval, brand_mention_percentage")\
        .eq("auto_reply_enabled", True)\
        .execute()
    
    return response.data


def get_our_recent_posts(client_id, hours=24):
    """Get our posts from last N hours that we should monitor for replies"""
    
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    response = supabase.table("content_queue")\
        .select("reddit_post_id, post_url, content, subreddit")\
        .eq("client_id", client_id)\
        .eq("status", "posted")\
        .gte("posted_at", cutoff.isoformat())\
        .execute()
    
    return response.data


def get_post_replies(post_id):
    """Get all replies to a specific post"""
    try:
        submission = reddit.submission(id=post_id)
        submission.comments.replace_more(limit=0)  # Don't expand "load more comments"
        
        replies = []
        for comment in submission.comments.list():
            replies.append({
                "id": comment.id,
                "author": str(comment.author),
                "body": comment.body,
                "created_utc": comment.created_utc,
                "score": comment.score,
                "permalink": f"https://reddit.com{comment.permalink}"
            })
        
        return replies
    
    except Exception as e:
        print(f"Error fetching replies for {post_id}: {e}")
        return []


def analyze_reply(reply_content, original_post_content):
    """Analyze reply sentiment and intent"""
    
    prompt = f"""Analyze this Reddit reply to our post.

Our Original Post:
{original_post_content[:500]}

Their Reply:
{reply_content}

Determine:
1. Sentiment: positive, neutral, negative, or question
2. Intent: question, feedback, objection, gratitude, discussion
3. Whether they need product information (true/false)

Return ONLY a JSON object:
{{
    "sentiment": "positive|neutral|negative|question",
    "intent": "question|feedback|objection|gratitude|discussion",
    "requires_product_info": false
}}"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are a reply analysis expert. Return ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=150
        )
        
        result = json.loads(response.choices[0].message.content)
        return result
    
    except Exception as e:
        print(f"Reply analysis error: {e}")
        return {
            "sentiment": "neutral",
            "intent": "discussion",
            "requires_product_info": False
        }


def get_voice_profile(client_id, subreddit):
    """Get a voice profile for this subreddit"""
    response = supabase.table("voice_profiles")\
        .select("*")\
        .eq("client_id", client_id)\
        .eq("subreddit", subreddit)\
        .order("karma_score", desc=True)\
        .limit(1)\
        .execute()
    
    return response.data[0] if response.data else None


def get_relevant_products(client_id, reply_content):
    """Find products relevant to the reply content using vector search"""
    
    # Generate embedding for reply
    try:
        embedding_response = openai.Embedding.create(
            model="text-embedding-3-small",
            input=reply_content
        )
        query_embedding = embedding_response["data"][0]["embedding"]
        
        # Vector similarity search (using pgvector)
        # Note: This requires RPC function in Supabase
        response = supabase.rpc(
            "match_products",
            {
                "query_embedding": query_embedding,
                "match_threshold": 0.7,
                "match_count": 2,
                "filter_client_id": client_id
            }
        ).execute()
        
        return response.data if response.data else []
    
    except Exception as e:
        print(f"Product matching error: {e}")
        return []


def get_brand_voice(client_id):
    """Get brand voice guidelines"""
    response = supabase.table("clients")\
        .select("brand_voice")\
        .eq("id", client_id)\
        .single()\
        .execute()
    
    return response.data.get("brand_voice", "") if response.data else ""


def generate_response(client_id, original_post, reply_content, reply_analysis, voice_profile, matched_products, brand_voice):
    """Generate contextual response using GPT-4"""
    
    # Build voice instructions
    voice_instructions = ""
    if voice_profile:
        voice_instructions = f"""
Voice Style to Match (from subreddit analysis):
- Avg sentence length: {voice_profile.get('avg_sentence_length', 15)} words
- Capitalization: {voice_profile.get('capitalization_style', 'mixed')}
- Uses contractions: {voice_profile.get('uses_contractions', True)}
- Common phrases: {', '.join(voice_profile.get('common_phrases', [])[:5])}
- Vocabulary: {voice_profile.get('vocabulary_complexity', 'moderate')}
"""
    
    # Build product context
    product_context = ""
    if matched_products and reply_analysis.get("requires_product_info"):
        product_context = "\n\nRelevant Products (mention ONLY if naturally fits the conversation):\n"
        for product in matched_products[:2]:
            product_context += f"- {product['name']}: {product['description']} (${product['price']})\n"
    
    prompt = f"""Generate a natural Reddit reply to this comment.

BRAND VOICE GUIDELINES:
{brand_voice}

{voice_instructions}

CRITICAL RULES:
1. Write as the BRAND EXPERT, not a customer with personal experience
2. NEVER use AI patterns: "I understand", "I appreciate", "Feel free to reach out"
3. Use natural typos: dont, cant, youre (NO apostrophes)
4. Match the thread's capitalization style
5. If they asked a question, answer it directly first
6. Products should be mentioned GENTLY and EDUCATIONALLY (not pushy)
7. Keep response under 150 words
8. Sound like a real person who works for the brand

THEIR REPLY:
{reply_content}

CONTEXT (Our Original Post):
{original_post[:300]}

REPLY ANALYSIS:
- Sentiment: {reply_analysis.get('sentiment')}
- Intent: {reply_analysis.get('intent')}
{product_context}

Generate a helpful, natural response:"""

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You are a Reddit community expert writing on behalf of a supportive brand. Write naturally, not like AI."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,  # Higher temp for natural variation
            max_tokens=300
        )
        
        generated = response.choices[0].message.content.strip()
        
        # Remove any AI-isms that slipped through
        ai_patterns = [
            "I understand",
            "I appreciate",
            "Feel free",
            "Don't hesitate",
            "I'm here to help",
            "Let me help"
        ]
        
        for pattern in ai_patterns:
            generated = re.sub(pattern, "", generated, flags=re.IGNORECASE)
        
        return generated, prompt
    
    except Exception as e:
        print(f"Response generation error: {e}")
        return None, None


def check_for_new_replies(client_id, brand_mention_percentage):
    """Check our posts for new replies and generate responses"""
    
    # Get our recent posts
    our_posts = get_our_recent_posts(client_id, hours=48)
    
    if not our_posts:
        print(f"  No recent posts found for {client_id}")
        return
    
    print(f"  Checking {len(our_posts)} recent posts for replies...")
    
    new_replies_generated = 0
    
    for post in our_posts:
        post_id = post["reddit_post_id"]
        
        # Get all replies to this post
        replies = get_post_replies(post_id)
        
        for reply in replies:
            # Check if we already processed this reply
            existing = supabase.table("auto_replies")\
                .select("id")\
                .eq("reply_id", reply["id"])\
                .execute()
            
            if existing.data:
                continue  # Already processed
            
            print(f"    New reply from u/{reply['author']}")
            
            # Analyze reply
            reply_analysis = analyze_reply(reply["body"], post["content"])
            
            # Get voice profile for this subreddit
            voice_profile = get_voice_profile(client_id, post["subreddit"])
            
            # Get matched products (if needed)
            matched_products = []
            if reply_analysis.get("requires_product_info"):
                matched_products = get_relevant_products(client_id, reply["body"])
            
            # Get brand voice
            brand_voice = get_brand_voice(client_id)
            
            # Generate response
            generated_response, generation_prompt = generate_response(
                client_id,
                post["content"],
                reply["body"],
                reply_analysis,
                voice_profile,
                matched_products,
                brand_voice
            )
            
            if not generated_response:
                print(f"    ❌ Failed to generate response")
                continue
            
            # Save to database
            auto_reply_data = {
                "client_id": client_id,
                "original_post_id": post_id,
                "original_post_url": post["post_url"],
                "original_post_content": post["content"],
                "reply_id": reply["id"],
                "reply_author": reply["author"],
                "reply_content": reply["body"],
                "reply_url": reply["permalink"],
                "reply_created_at": datetime.fromtimestamp(reply["created_utc"]).isoformat(),
                "reply_sentiment": reply_analysis["sentiment"],
                "reply_intent": reply_analysis["intent"],
                "requires_product_info": reply_analysis["requires_product_info"],
                "generated_response": generated_response,
                "generation_model": "gpt-4-turbo-preview",
                "generation_prompt": generation_prompt,
                "matched_products": json.dumps([{"product_id": str(p["id"]), "name": p["name"]} for p in matched_products]),
                "status": "pending"
            }
            
            try:
                supabase.table("auto_replies").insert(auto_reply_data).execute()
                new_replies_generated += 1
                print(f"    ✅ Response generated and pending approval")
            except Exception as e:
                print(f"    ❌ Error saving auto-reply: {e}")
    
    return new_replies_generated


def run_auto_reply_generator():
    """Main function: Check all client posts for new replies"""
    print("=== AUTO-REPLY GENERATOR ===")
    print(f"Running at {datetime.utcnow().isoformat()}")
    
    clients = get_clients_with_auto_reply()
    print(f"Monitoring {len(clients)} clients")
    
    total_generated = 0
    
    for client in clients:
        client_id = client["client_id"]
        brand_mention_pct = client.get("brand_mention_percentage", 30)
        
        print(f"\n📊 Checking {client_id}...")
        
        count = check_for_new_replies(client_id, brand_mention_pct)
        if count:
            total_generated += count
    
    print(f"\n✅ Auto-reply generation complete")
    print(f"   Generated {total_generated} responses pending approval")


if __name__ == "__main__":
    run_auto_reply_generator()
