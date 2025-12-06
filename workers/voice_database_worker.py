"""
Voice Database Worker

Crawls top Redditors in target subreddits to build voice profiles.
Analyzes language patterns, idioms, grammar, tone, sentiment for authentic content generation.

This runs during client onboarding to create subreddit-specific voice profiles.
"""

import os
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import praw
import prawcore
from openai import OpenAI
import numpy as np
from collections import Counter
import re

from supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

class VoiceDatabaseWorker:
    """Builds subreddit-specific voice profiles from top Redditors"""
    
    def __init__(self):
        self.supabase = get_supabase_client()
        self.openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Initialize Reddit API
        self.reddit = praw.Reddit(
            client_id=os.getenv("REDDIT_CLIENT_ID"),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            user_agent=os.getenv("REDDIT_USER_AGENT", "EchoMind/1.0")
        )
        
        # Default crawl settings
        self.TOP_USERS_PER_SUBREDDIT = 1000
        self.COMMENTS_PER_USER = 50
        self.MIN_COMMENT_LENGTH = 20
        
    async def analyze_subreddit_voice(self, subreddit_name: str, client_id: str) -> Dict[str, Any]:
        """
        Analyze voice patterns for a specific subreddit
        
        Args:
            subreddit_name: Name of subreddit (e.g., "BeyondTheBump")
            client_id: UUID of client
            
        Returns:
            Voice profile dictionary
        """
        try:
            logger.info(f"Building voice profile for r/{subreddit_name}")
            
            # Step 1: Get top users in subreddit
            top_users = await self._get_top_subreddit_users(subreddit_name)
            logger.info(f"Found {len(top_users)} top users in r/{subreddit_name}")
            
            # Step 2: Collect comments from top users
            all_comments = []
            for user in top_users[:self.TOP_USERS_PER_SUBREDDIT]:
                comments = await self._get_user_comments(user['username'], subreddit_name)
                all_comments.extend(comments)
            
            logger.info(f"Collected {len(all_comments)} comments from r/{subreddit_name}")
            
            # Step 3: Analyze language patterns
            voice_profile = await self._analyze_language_patterns(all_comments, subreddit_name)
            
            # Step 4: Use GPT-4 to extract tone and style
            enhanced_profile = await self._enhance_with_ai_analysis(voice_profile, all_comments[:100])
            
            # Step 5: Save to database
            await self._save_voice_profile(subreddit_name, client_id, enhanced_profile)
            
            return enhanced_profile
            
        except Exception as e:
            logger.error(f"Error analyzing voice for r/{subreddit_name}: {e}")
            raise
    
    async def _get_top_subreddit_users(self, subreddit_name: str) -> List[Dict]:
        """Get top active users in subreddit"""
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            top_users = []
            user_karma = Counter()
            
            # Sample from hot, top, and new posts
            for submission in subreddit.hot(limit=100):
                submission.comments.replace_more(limit=0)
                for comment in submission.comments.list()[:50]:
                    if hasattr(comment, 'author') and comment.author:
                        user_karma[comment.author.name] += comment.score
            
            # Convert to list sorted by karma
            for username, karma in user_karma.most_common(self.TOP_USERS_PER_SUBREDDIT):
                top_users.append({
                    'username': username,
                    'karma': karma
                })
            
            return top_users
            
        except Exception as e:
            logger.error(f"Error getting top users from r/{subreddit_name}: {e}")
            return []
    
    async def _get_user_comments(self, username: str, subreddit_name: str) -> List[str]:
        """Get recent comments from user in specific subreddit"""
        try:
            user = self.reddit.redditor(username)
            comments = []
            
            for comment in user.comments.new(limit=self.COMMENTS_PER_USER):
                if hasattr(comment, 'subreddit') and comment.subreddit.display_name == subreddit_name:
                    if len(comment.body) >= self.MIN_COMMENT_LENGTH:
                        comments.append(comment.body)
            
            return comments
            
        except prawcore.exceptions.NotFound:
            logger.warning(f"User {username} not found or deleted")
            return []
        except Exception as e:
            logger.error(f"Error getting comments for {username}: {e}")
            return []
    
    async def _analyze_language_patterns(self, comments: List[str], subreddit_name: str) -> Dict[str, Any]:
        """Analyze linguistic patterns from comments"""
        
        if not comments:
            return self._get_default_voice_profile(subreddit_name)
        
        # Combine all comments for analysis
        full_text = " ".join(comments)
        
        # Basic linguistic analysis
        sentences = [s.strip() for s in re.split(r'[.!?]+', full_text) if s.strip()]
        words = full_text.split()
        
        # Calculate metrics
        avg_sentence_length = np.mean([len(s.split()) for s in sentences]) if sentences else 12
        avg_word_length = np.mean([len(w) for w in words]) if words else 5
        
        # Detect common phrases (2-3 word combinations)
        bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words)-1)]
        trigrams = [f"{words[i]} {words[i+1]} {words[i+2]}" for i in range(len(words)-2)]
        common_phrases = [phrase for phrase, count in Counter(bigrams + trigrams).most_common(20)]
        
        # Detect typo/casual writing frequency
        typo_indicators = sum(1 for w in words if not w.isalpha() and any(c.isalpha() for c in w))
        typo_frequency = typo_indicators / len(words) if words else 0.02
        
        # Detect emoji usage
        emoji_pattern = re.compile(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF]')
        emoji_count = len(emoji_pattern.findall(full_text))
        uses_emojis = "frequent" if emoji_count > len(comments) * 0.3 else "occasional" if emoji_count > 0 else "rare"
        
        # Detect exclamation/question frequency
        exclamation_freq = full_text.count('!') / len(sentences) if sentences else 0.1
        question_freq = full_text.count('?') / len(sentences) if sentences else 0.1
        
        return {
            "subreddit": subreddit_name,
            "sample_size": len(comments),
            "avg_sentence_length": round(avg_sentence_length, 1),
            "avg_word_length": round(avg_word_length, 1),
            "common_phrases": common_phrases[:15],
            "typo_frequency": round(typo_frequency, 3),
            "uses_emojis": uses_emojis,
            "exclamation_frequency": round(exclamation_freq, 2),
            "question_frequency": round(question_freq, 2),
            "analyzed_at": datetime.utcnow().isoformat()
        }
    
    async def _enhance_with_ai_analysis(self, basic_profile: Dict, sample_comments: List[str]) -> Dict[str, Any]:
        """Use GPT-4 to extract tone, sentiment, and style"""
        
        sample_text = "\n\n---\n\n".join(sample_comments[:20])
        
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4-turbo",
                messages=[
                    {"role": "system", "content": "You are a linguistic analyst. Analyze the tone, sentiment, and writing style of Reddit comments."},
                    {"role": "user", "content": f"""Analyze these comments from r/{basic_profile['subreddit']}:

{sample_text}

Provide a JSON response with:
1. "tone": Overall emotional tone (3-5 words)
2. "grammar_style": Description of grammar patterns
3. "sentiment_distribution": Breakdown of emotions (percentages)
4. "signature_idioms": List of 5-10 unique phrases/idioms this community uses
5. "formality_level": LOW/MEDIUM/HIGH
6. "voice_description": 2-sentence description of how this community writes

Format as valid JSON only."""}
                ],
                temperature=0.3,
                max_tokens=500
            )
            
            import json
            ai_analysis = json.loads(response.choices[0].message.content)
            
            # Merge AI analysis with basic profile
            return {**basic_profile, **ai_analysis}
            
        except Exception as e:
            logger.error(f"Error in AI analysis: {e}")
            # Return basic profile with defaults
            return {
                **basic_profile,
                "tone": "supportive, casual, authentic",
                "grammar_style": "conversational with occasional fragments",
                "sentiment_distribution": {"supportive": 40, "frustrated": 30, "hopeful": 20, "tired": 10},
                "signature_idioms": ["honestly", "literally", "I feel you", "solidarity"],
                "formality_level": "LOW",
                "voice_description": "Community members write like tired friends sharing real experiences. Grammar is casual with emotional authenticity."
            }
    
    def _get_default_voice_profile(self, subreddit_name: str) -> Dict[str, Any]:
        """Return default voice profile if analysis fails"""
        return {
            "subreddit": subreddit_name,
            "sample_size": 0,
            "avg_sentence_length": 12.0,
            "avg_word_length": 5.0,
            "common_phrases": ["I think", "honestly", "literally", "that's why"],
            "typo_frequency": 0.02,
            "uses_emojis": "occasional",
            "exclamation_frequency": 0.15,
            "question_frequency": 0.10,
            "tone": "supportive, conversational",
            "grammar_style": "casual with informal patterns",
            "sentiment_distribution": {"supportive": 50, "neutral": 30, "concerned": 20},
            "signature_idioms": ["honestly", "literally", "same here"],
            "formality_level": "LOW",
            "voice_description": "Default casual Reddit community voice. Friendly and authentic.",
            "analyzed_at": datetime.utcnow().isoformat()
        }
    
    async def _save_voice_profile(self, subreddit_name: str, client_id: str, profile: Dict) -> None:
        """Save voice profile to database"""
        try:
            data = {
                "client_id": client_id,
                "subreddit": subreddit_name,
                "voice_profile": profile,
                "created_at": datetime.utcnow().isoformat()
            }

            # Upsert to voice_profiles table
            self.supabase.table("voice_profiles").upsert(data, on_conflict="client_id,subreddit").execute()

            logger.info(f"Saved voice profile for r/{subreddit_name}")

        except Exception as e:
            logger.error(f"Error saving voice profile: {e}")
            raise


async def build_client_voice_database(client_id: str) -> Dict[str, Any]:
    """
    Build complete voice database for a client's target subreddits
    
    Args:
        client_id: UUID of client
        
    Returns:
        Summary of voice profiles created
    """
    worker = VoiceDatabaseWorker()
    
    # Get client's subreddits from client_subreddit_config table
    # (This is where onboarding stores target subreddits)
    supabase = get_supabase_client()
    subreddits_response = supabase.table("client_subreddit_config").select("subreddit_name").eq("client_id", client_id).eq("is_active", True).execute()

    subreddits = [s['subreddit_name'] for s in subreddits_response.data] if subreddits_response.data else []

    # Fallback: If no subreddit config, try to get unique subreddits from opportunities
    if not subreddits:
        logger.info("No subreddit config found, falling back to opportunities table")
        opps_response = supabase.table("opportunities").select("subreddit").eq("client_id", client_id).execute()
        if opps_response.data:
            subreddits = list(set([o['subreddit'] for o in opps_response.data if o.get('subreddit')]))[:10]  # Top 10 unique
            logger.info(f"Found {len(subreddits)} unique subreddits from opportunities")
    
    logger.info(f"Building voice database for {len(subreddits)} subreddits")
    
    results = []
    for subreddit in subreddits:
        try:
            profile = await worker.analyze_subreddit_voice(subreddit, client_id)
            results.append({
                "subreddit": subreddit,
                "status": "success",
                "sample_size": profile.get('sample_size', 0)
            })
        except Exception as e:
            logger.error(f"Failed to build voice profile for r/{subreddit}: {e}")
            results.append({
                "subreddit": subreddit,
                "status": "failed",
                "error": str(e)
            })
    
    return {
        "client_id": client_id,
        "total_subreddits": len(subreddits),
        "successful": sum(1 for r in results if r['status'] == 'success'),
        "failed": sum(1 for r in results if r['status'] == 'failed'),
        "results": results
    }
