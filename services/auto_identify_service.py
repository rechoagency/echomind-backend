"""
AUTO_IDENTIFY Service
Discovers relevant subreddits and extracts keywords using AI
"""

import os
import logging
import json
from typing import List, Dict, Optional
from datetime import datetime
from openai import OpenAI
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AutoIdentifyService:
    """Service for AUTO_IDENTIFY subreddit and keyword discovery"""
    
    def __init__(self, supabase_client, openai_api_key: str):
        self.supabase = supabase_client
        self.openai = OpenAI(api_key=openai_api_key)
        self.reddit_search_api = "https://www.reddit.com/search.json"
    
    async def discover_subreddits(self, client: Dict) -> Dict:
        """
        Discover 10-20 relevant subreddits using AI + Reddit API
        
        Args:
            client: Client data from database
            
        Returns:
            Discovery results with subreddit list
        """
        try:
            client_id = client.get("client_id")
            company_name = client.get("company_name")
            industry = client.get("industry")
            website = client.get("website_url")
            products = client.get("products", [])
            
            logger.info(f"🔍 Discovering subreddits for {company_name} ({industry})")
            
            # STEP 1: Use AI to generate subreddit search queries
            search_queries = await self._generate_subreddit_queries(industry, products)
            logger.info(f"Generated {len(search_queries)} search queries")
            
            # STEP 2: Search Reddit for relevant subreddits
            found_subreddits = await self._search_reddit_subreddits(search_queries)
            logger.info(f"Found {len(found_subreddits)} potential subreddits")
            
            # STEP 3: Use AI to filter and rank subreddits
            ranked_subreddits = await self._rank_subreddits(
                found_subreddits, industry, products
            )
            
            # Take top 15
            top_subreddits = ranked_subreddits[:15]
            subreddit_names = [s["name"] for s in top_subreddits]
            
            logger.info(f"✅ Selected {len(subreddit_names)} subreddits: {', '.join(subreddit_names[:5])}...")
            
            # STEP 4: Update database
            # Update client record
            self.supabase.table("clients").update({
                "target_subreddits": subreddit_names,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("client_id", client_id).execute()
            
            # Create subreddit configs
            configs = [{
                "client_id": client_id,
                "subreddit_name": name.lower(),
                "is_active": True,
                "created_at": datetime.utcnow().isoformat()
            } for name in subreddit_names]
            
            self.supabase.table("client_subreddit_config").insert(configs).execute()
            
            return {
                "success": True,
                "subreddits": subreddit_names,
                "count": len(subreddit_names),
                "details": top_subreddits
            }
            
        except Exception as e:
            logger.error(f"❌ Subreddit discovery error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def extract_keywords(self, client: Dict) -> Dict:
        """
        Extract marketing keywords using AI + website analysis
        
        Args:
            client: Client data from database
            
        Returns:
            Extraction results with keyword list
        """
        try:
            client_id = client.get("client_id")
            company_name = client.get("company_name")
            industry = client.get("industry")
            website = client.get("website_url")
            products = client.get("products", [])
            
            logger.info(f"🔍 Extracting keywords for {company_name}")
            
            # STEP 1: Crawl website for content (if available)
            website_content = await self._crawl_website(website)
            
            # STEP 2: Use AI to extract keywords
            keywords = await self._ai_extract_keywords(
                industry, products, website_content
            )
            
            logger.info(f"✅ Extracted {len(keywords)} keywords: {', '.join(keywords[:5])}...")
            
            # STEP 3: Update database
            self.supabase.table("clients").update({
                "target_keywords": keywords,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("client_id", client_id).execute()
            
            # Create keyword configs
            configs = [{
                "client_id": client_id,
                "keyword": kw,
                "is_active": True,
                "created_at": datetime.utcnow().isoformat()
            } for kw in keywords]
            
            self.supabase.table("client_keyword_config").insert(configs).execute()
            
            return {
                "success": True,
                "keywords": keywords,
                "count": len(keywords)
            }
            
        except Exception as e:
            logger.error(f"❌ Keyword extraction error: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _generate_subreddit_queries(self, industry: str, products: List) -> List[str]:
        """Generate search queries for finding subreddits"""
        prompt = f"""Generate 5 Reddit search queries to find relevant subreddits for this business:

Industry: {industry}
Products/Services: {json.dumps(products)}

Focus on:
- Target audience communities
- Problem/solution discussions
- Industry-specific forums
- Related interest groups

Return ONLY a JSON array of search queries.
Example: ["small business advice", "digital marketing tips", "SaaS founders"]"""
        
        response = self.openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5
        )
        
        queries_text = response.choices[0].message.content.strip()
        # Extract JSON array
        if "```json" in queries_text:
            queries_text = queries_text.split("```json")[1].split("```")[0].strip()
        elif "```" in queries_text:
            queries_text = queries_text.split("```")[1].split("```")[0].strip()
        
        return json.loads(queries_text)
    
    async def _search_reddit_subreddits(self, queries: List[str]) -> List[Dict]:
        """Search Reddit for subreddits using queries"""
        found_subreddits = {}
        
        for query in queries:
            try:
                # Search Reddit
                params = {
                    "q": f"{query} subreddit:all",
                    "type": "sr",  # Search for subreddits
                    "limit": 10
                }
                
                headers = {"User-Agent": "EchoMind/1.0"}
                response = requests.get(self.reddit_search_api, params=params, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    subreddits = data.get("data", {}).get("children", [])
                    
                    for sub in subreddits:
                        sub_data = sub.get("data", {})
                        name = sub_data.get("display_name")
                        
                        if name and name not in found_subreddits:
                            found_subreddits[name] = {
                                "name": name,
                                "title": sub_data.get("title", ""),
                                "description": sub_data.get("public_description", ""),
                                "subscribers": sub_data.get("subscribers", 0),
                                "active_users": sub_data.get("active_user_count", 0)
                            }
            
            except Exception as e:
                logger.error(f"Error searching for '{query}': {str(e)}")
                continue
        
        return list(found_subreddits.values())
    
    async def _rank_subreddits(
        self, subreddits: List[Dict], industry: str, products: List
    ) -> List[Dict]:
        """Use AI to rank subreddits by relevance"""
        
        if not subreddits:
            # Fallback: Use AI to suggest subreddits directly
            return await self._ai_suggest_subreddits(industry, products)
        
        # Format subreddit data for AI
        sub_info = "\n".join([
            f"- r/{s['name']}: {s['title']} ({s['subscribers']} subscribers)"
            for s in subreddits[:30]  # Limit to avoid token limits
        ])
        
        prompt = f"""Rank these subreddits by relevance for marketing this business.
Select the 15 MOST relevant subreddits.

Business:
Industry: {industry}
Products: {json.dumps(products)}

Subreddits:
{sub_info}

Return ONLY a JSON array of the top 15 subreddit names (without r/ prefix).
Example: ["Entrepreneur", "SaaS", "startups"]"""
        
        response = self.openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3
        )
        
        ranked_text = response.choices[0].message.content.strip()
        if "```json" in ranked_text:
            ranked_text = ranked_text.split("```json")[1].split("```")[0].strip()
        elif "```" in ranked_text:
            ranked_text = ranked_text.split("```")[1].split("```")[0].strip()
        
        ranked_names = json.loads(ranked_text)
        
        # Return subreddit objects in ranked order
        ranked_subs = []
        for name in ranked_names:
            for sub in subreddits:
                if sub["name"].lower() == name.lower():
                    ranked_subs.append(sub)
                    break
        
        return ranked_subs
    
    async def _ai_suggest_subreddits(self, industry: str, products: List) -> List[Dict]:
        """Fallback: AI suggests subreddits directly"""
        prompt = f"""Suggest 15 highly relevant Reddit subreddits for this business:

Industry: {industry}
Products: {json.dumps(products)}

Focus on active communities where potential customers discuss problems.

Return ONLY a JSON array of objects:
[{{"name": "Entrepreneur", "reason": "startup founders seeking tools"}}, ...]"""
        
        response = self.openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5
        )
        
        suggestions_text = response.choices[0].message.content.strip()
        if "```json" in suggestions_text:
            suggestions_text = suggestions_text.split("```json")[1].split("```")[0].strip()
        elif "```" in suggestions_text:
            suggestions_text = suggestions_text.split("```")[1].split("```")[0].strip()
        
        return json.loads(suggestions_text)
    
    async def _crawl_website(self, website_url: str) -> Optional[str]:
        """Crawl website to extract content"""
        if not website_url:
            return None
        
        try:
            # Add https if missing
            if not website_url.startswith(("http://", "https://")):
                website_url = f"https://{website_url}"
            
            headers = {"User-Agent": "EchoMind/1.0"}
            response = requests.get(website_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                # Basic text extraction (in production, use BeautifulSoup or similar)
                text = response.text[:5000]  # First 5000 chars
                return text
            
        except Exception as e:
            logger.warning(f"Could not crawl website {website_url}: {str(e)}")
        
        return None
    
    async def _ai_extract_keywords(
        self, industry: str, products: List, website_content: Optional[str]
    ) -> List[str]:
        """Use AI to extract keywords"""
        
        content_snippet = website_content[:1000] if website_content else "No website content available"
        
        prompt = f"""Extract 20 marketing keywords for monitoring Reddit discussions.

Business:
Industry: {industry}
Products: {json.dumps(products)}

Website excerpt:
{content_snippet}

Focus on:
- Pain points customers discuss
- Problem-seeking phrases ("how to", "best way to", "struggling with")
- Product category terms
- Alternative/competitor mentions
- Industry-specific jargon

Return ONLY a JSON array of keywords.
Example: ["marketing automation", "Reddit tools", "social media management", "how to automate posts"]"""
        
        response = self.openai.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5
        )
        
        keywords_text = response.choices[0].message.content.strip()
        if "```json" in keywords_text:
            keywords_text = keywords_text.split("```json")[1].split("```")[0].strip()
        elif "```" in keywords_text:
            keywords_text = keywords_text.split("```")[1].split("```")[0].strip()
        
        return json.loads(keywords_text)
