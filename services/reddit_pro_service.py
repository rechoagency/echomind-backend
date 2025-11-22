"""
Reddit Pro Integration Service
Integrates with Reddit Pro for enhanced social listening
"""
import os
import logging
import httpx
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class RedditProService:
    """
    Service for Reddit Pro integration
    Provides enhanced monitoring and analytics
    """
    
    def __init__(self):
        self.api_key = os.getenv("REDDIT_PRO_API_KEY")
        self.base_url = "https://business.reddit.com/api/v1"
        self.enabled = bool(self.api_key)
        
        if not self.enabled:
            logger.warning("⚠️ Reddit Pro API key not configured - using standard Reddit API only")
            logger.warning("👉 To enable Reddit Pro features, add REDDIT_PRO_API_KEY to Railway")
        else:
            logger.info("✅ Reddit Pro integration enabled")
    
    async def track_keywords(
        self,
        keywords: List[str],
        subreddits: Optional[List[str]] = None,
        lookback_days: int = 7
    ) -> Dict:
        """
        Track keywords using Reddit Pro API
        
        Args:
            keywords: List of keywords to track
            subreddits: Optional list of subreddits to filter
            lookback_days: Days to look back (default 7)
        
        Returns:
            Dict with tracking results and mentions
        """
        if not self.enabled:
            return {
                "enabled": False,
                "message": "Reddit Pro not configured",
                "fallback": "using_standard_api"
            }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/keywords/track",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "keywords": keywords,
                        "subreddits": subreddits,
                        "start_date": (datetime.now() - timedelta(days=lookback_days)).isoformat(),
                        "end_date": datetime.now().isoformat()
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"✅ Reddit Pro tracked {len(keywords)} keywords - found {data.get('total_mentions', 0)} mentions")
                    return data
                else:
                    logger.error(f"❌ Reddit Pro API error: {response.status_code}")
                    return {"error": f"API returned {response.status_code}"}
                    
        except Exception as e:
            logger.error(f"❌ Reddit Pro API request failed: {str(e)}")
            return {"error": str(e)}
    
    async def get_sentiment_analysis(
        self,
        keyword: str,
        timeframe: str = "7d"
    ) -> Dict:
        """
        Get sentiment analysis for a keyword using Reddit Pro
        
        Args:
            keyword: Keyword to analyze
            timeframe: Timeframe (7d, 30d, 90d)
        
        Returns:
            Dict with sentiment analysis results
        """
        if not self.enabled:
            return {
                "enabled": False,
                "message": "Reddit Pro not configured - using OpenAI sentiment analysis"
            }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/sentiment/{keyword}",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    params={"timeframe": timeframe},
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"✅ Reddit Pro sentiment for '{keyword}': {data.get('overall_sentiment', 'N/A')}")
                    return data
                else:
                    logger.error(f"❌ Reddit Pro sentiment API error: {response.status_code}")
                    return {"error": f"API returned {response.status_code}"}
                    
        except Exception as e:
            logger.error(f"❌ Reddit Pro sentiment request failed: {str(e)}")
            return {"error": str(e)}
    
    async def get_trending_topics(
        self,
        subreddits: List[str],
        limit: int = 10
    ) -> List[Dict]:
        """
        Get trending topics in specified subreddits
        
        Args:
            subreddits: List of subreddit names
            limit: Max number of trending topics
        
        Returns:
            List of trending topics with metadata
        """
        if not self.enabled:
            return []
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/trending",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "subreddits": subreddits,
                        "limit": limit
                    },
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    data = response.json()
                    topics = data.get("topics", [])
                    logger.info(f"✅ Reddit Pro found {len(topics)} trending topics")
                    return topics
                else:
                    logger.error(f"❌ Reddit Pro trending API error: {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"❌ Reddit Pro trending request failed: {str(e)}")
            return []
    
    def get_setup_instructions(self) -> Dict:
        """Get instructions for setting up Reddit Pro"""
        return {
            "enabled": self.enabled,
            "steps": [
                "1. Visit https://business.reddit.com/",
                "2. Sign up for Reddit Pro (free tier available)",
                "3. Go to API Settings and generate an API key",
                "4. Add REDDIT_PRO_API_KEY to Railway environment variables",
                "5. Redeploy the backend",
                "6. Reddit Pro features will be automatically enabled"
            ],
            "benefits": [
                "✅ Enhanced keyword tracking with historical data",
                "✅ Advanced sentiment analysis beyond GPT-4",
                "✅ Trending topic discovery",
                "✅ Competitive intelligence",
                "✅ Better opportunity discovery"
            ],
            "cost": "Free tier available with limited API calls"
        }

# Singleton instance
reddit_pro_service = RedditProService()

# Export for easy import
__all__ = ["reddit_pro_service", "RedditProService"]
