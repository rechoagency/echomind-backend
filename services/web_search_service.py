"""
Web Search Enrichment Service
Adds real-time facts and specific details to content generation via web search.

Uses SerpAPI or direct search to gather:
1. Current product prices and specs
2. Recent reviews and opinions
3. Competitor comparisons
4. Industry news relevant to the topic
"""

import os
import logging
import httpx
import asyncio
from typing import Dict, List, Any, Optional
from datetime import datetime
import json
import re

logger = logging.getLogger(__name__)


class WebSearchService:
    """
    Enriches content generation with real-time web search data.
    """

    def __init__(self):
        self.serpapi_key = os.getenv("SERPAPI_KEY")
        self.enabled = bool(self.serpapi_key)
        self.timeout = 10

        if not self.enabled:
            logger.warning("WebSearchService: SERPAPI_KEY not configured - web enrichment disabled")

    async def search_for_enrichment(
        self,
        query: str,
        company_name: str,
        products: List[str] = None,
        num_results: int = 5
    ) -> Dict[str, Any]:
        """
        Search web for enrichment data related to a topic.

        Args:
            query: The search query (based on thread topic)
            company_name: Client's company for targeted searches
            products: Product names to search for specifics
            num_results: Number of results to fetch

        Returns:
            Enrichment data with facts, prices, specs
        """
        if not self.enabled:
            return {"enabled": False, "data": []}

        try:
            enrichment = {
                "enabled": True,
                "topic_facts": [],
                "product_details": [],
                "competitor_mentions": [],
                "recent_discussions": [],
                "searched_at": datetime.utcnow().isoformat()
            }

            # Search for topic-related facts
            topic_results = await self._search_serpapi(
                query,
                num_results=num_results
            )
            enrichment["topic_facts"] = self._extract_facts(topic_results)

            # Search for product-specific details if products provided
            if products:
                for product in products[:2]:  # Limit to 2 products
                    product_query = f"{company_name} {product} specs price"
                    product_results = await self._search_serpapi(
                        product_query,
                        num_results=3
                    )
                    enrichment["product_details"].extend(
                        self._extract_product_info(product_results, product)
                    )

            return enrichment

        except Exception as e:
            logger.error(f"Web search enrichment failed: {str(e)}")
            return {"enabled": True, "error": str(e), "data": []}

    async def get_product_facts(
        self,
        company_name: str,
        product_name: str
    ) -> Dict[str, Any]:
        """
        Get specific facts about a product from web search.

        Returns dict with:
        - price_range: Approximate price
        - key_specs: Important specifications
        - pros_cons: What people say
        - alternatives: Competitor products mentioned
        """
        if not self.enabled:
            return {}

        try:
            # Search for product reviews and specs
            query = f"{company_name} {product_name} review specs"
            results = await self._search_serpapi(query, num_results=5)

            facts = {
                "product": product_name,
                "company": company_name,
                "price_range": None,
                "key_specs": [],
                "pros": [],
                "cons": [],
                "alternatives": []
            }

            for result in results:
                snippet = result.get("snippet", "").lower()
                title = result.get("title", "").lower()

                # Extract price mentions
                price_match = re.search(r'\$[\d,]+(?:\.\d{2})?', result.get("snippet", ""))
                if price_match and not facts["price_range"]:
                    facts["price_range"] = price_match.group()

                # Extract spec-like mentions (numbers with units)
                spec_matches = re.findall(
                    r'\d+(?:\.\d+)?\s*(?:inch|inches|watts?|btu|square feet|sq\.?\s*ft)',
                    snippet,
                    re.IGNORECASE
                )
                for spec in spec_matches[:3]:
                    if spec not in facts["key_specs"]:
                        facts["key_specs"].append(spec)

            return facts

        except Exception as e:
            logger.error(f"Product facts search failed: {str(e)}")
            return {}

    async def _search_serpapi(
        self,
        query: str,
        num_results: int = 5
    ) -> List[Dict]:
        """Execute search via SerpAPI"""
        if not self.serpapi_key:
            return []

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://serpapi.com/search",
                    params={
                        "q": query,
                        "api_key": self.serpapi_key,
                        "num": num_results,
                        "engine": "google"
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get("organic_results", [])
                else:
                    logger.warning(f"SerpAPI returned status {response.status_code}")
                    return []

        except Exception as e:
            logger.error(f"SerpAPI request failed: {str(e)}")
            return []

    def _extract_facts(self, results: List[Dict]) -> List[str]:
        """Extract useful facts from search results"""
        facts = []

        for result in results:
            snippet = result.get("snippet", "")
            if snippet:
                # Look for specific facts (numbers, percentages, dates)
                if any(c.isdigit() for c in snippet):
                    # Clean and truncate
                    fact = snippet.strip()[:200]
                    if fact not in facts:
                        facts.append(fact)

        return facts[:5]  # Limit to 5 facts

    def _extract_product_info(
        self,
        results: List[Dict],
        product_name: str
    ) -> List[Dict]:
        """Extract product-specific information"""
        product_info = []

        for result in results:
            snippet = result.get("snippet", "")
            title = result.get("title", "")
            link = result.get("link", "")

            info = {
                "product": product_name,
                "source": title[:50],
                "detail": snippet[:200] if snippet else None,
                "url": link
            }

            if info["detail"]:
                product_info.append(info)

        return product_info[:3]


# Singleton instance
web_search_service = WebSearchService()


async def enrich_with_web_search(
    topic: str,
    company_name: str,
    products: List[str] = None
) -> Dict[str, Any]:
    """
    Convenience function for web search enrichment.

    Args:
        topic: Topic/query to search for
        company_name: Client's company name
        products: Optional list of product names

    Returns:
        Enrichment data for content generation
    """
    return await web_search_service.search_for_enrichment(
        query=topic,
        company_name=company_name,
        products=products
    )
