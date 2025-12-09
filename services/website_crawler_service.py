"""
Website Crawler Service
Automatically extracts product information from client websites for RAG knowledge base.

This service:
1. Crawls the client's website (starting from homepage or product pages)
2. Extracts relevant product information, specs, FAQs
3. Uses GPT-4 to structure the content into knowledge chunks
4. Stores embeddings directly in document_embeddings via /api/admin/ingest-knowledge pattern

Designed to run automatically during client onboarding.
"""

import os
import re
import logging
import asyncio
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from urllib.parse import urljoin, urlparse
import uuid

import httpx
from openai import AsyncOpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebsiteCrawlerService:
    """
    Crawls client websites to extract product knowledge for RAG system.
    """

    def __init__(self, supabase_client, openai_api_key: str):
        """
        Initialize the crawler service.

        Args:
            supabase_client: Initialized Supabase client
            openai_api_key: OpenAI API key for content extraction and embeddings
        """
        self.supabase = supabase_client
        self.openai = AsyncOpenAI(api_key=openai_api_key)

        # Crawl settings
        self.max_pages = 30  # Maximum pages to crawl per website
        self.max_depth = 3   # Maximum link depth from starting URL
        self.timeout = 15    # Request timeout in seconds

        # User agent for requests
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; EchoMindBot/1.0; +https://echomind.ai)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5"
        }

        # URL patterns to prioritize for product info
        self.priority_patterns = [
            r"/product",
            r"/collection",
            r"/shop",
            r"/catalog",
            r"/item",
            r"/about",
            r"/faq",
            r"/support",
            r"/spec",
            r"/feature"
        ]

        # URL patterns to skip
        self.skip_patterns = [
            r"/cart",
            r"/checkout",
            r"/account",
            r"/login",
            r"/register",
            r"/blog/\d{4}/",  # Skip dated blog posts
            r"/wp-admin",
            r"/cdn-cgi",
            r"\.(pdf|jpg|jpeg|png|gif|svg|css|js|ico)$"
        ]

    async def crawl_website(
        self,
        client_id: str,
        website_url: str,
        company_name: str,
        products: List[str] = None
    ) -> Dict[str, Any]:
        """
        Main entry point: Crawl a website and extract product knowledge.

        Args:
            client_id: Client UUID
            website_url: Starting URL (homepage or product page)
            company_name: Company name for context
            products: Optional list of product keywords to focus on

        Returns:
            Dictionary with crawl results
        """
        try:
            logger.info(f"🕷️ Starting crawl for {company_name}: {website_url}")

            # Normalize URL
            if not website_url.startswith(('http://', 'https://')):
                website_url = f"https://{website_url}"

            base_domain = urlparse(website_url).netloc

            # Track visited URLs
            visited_urls: Set[str] = set()
            pages_content: List[Dict] = []

            # Start crawling
            await self._crawl_page(
                url=website_url,
                base_domain=base_domain,
                visited=visited_urls,
                pages=pages_content,
                depth=0,
                company_name=company_name,
                products=products or []
            )

            logger.info(f"📄 Crawled {len(pages_content)} pages from {company_name}")

            if not pages_content:
                return {
                    "success": False,
                    "error": "No content could be extracted from website",
                    "pages_crawled": 0
                }

            # Extract knowledge chunks from crawled content
            knowledge_chunks = await self._extract_knowledge_chunks(
                pages_content=pages_content,
                company_name=company_name,
                products=products or []
            )

            logger.info(f"📦 Extracted {len(knowledge_chunks)} knowledge chunks")

            if not knowledge_chunks:
                return {
                    "success": False,
                    "error": "Could not extract product knowledge from pages",
                    "pages_crawled": len(pages_content)
                }

            # Store embeddings in database
            embeddings_created = await self._store_knowledge_chunks(
                client_id=client_id,
                company_name=company_name,
                chunks=knowledge_chunks
            )

            return {
                "success": True,
                "client_id": client_id,
                "company_name": company_name,
                "website_url": website_url,
                "pages_crawled": len(pages_content),
                "chunks_extracted": len(knowledge_chunks),
                "embeddings_created": embeddings_created,
                "crawled_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Crawl failed for {company_name}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "client_id": client_id
            }

    async def _crawl_page(
        self,
        url: str,
        base_domain: str,
        visited: Set[str],
        pages: List[Dict],
        depth: int,
        company_name: str,
        products: List[str]
    ):
        """
        Recursively crawl a page and its linked pages.
        """
        # Check limits
        if len(visited) >= self.max_pages:
            return
        if depth > self.max_depth:
            return
        if url in visited:
            return

        # Skip non-relevant URLs
        if any(re.search(pattern, url, re.I) for pattern in self.skip_patterns):
            return

        # Mark as visited
        visited.add(url)

        try:
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                response = await client.get(url, headers=self.headers)

                if response.status_code != 200:
                    logger.warning(f"⚠️ Skipping {url} (status: {response.status_code})")
                    return

                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type:
                    return

                html_content = response.text

                # Extract text content (simple extraction without BeautifulSoup)
                text_content = self._extract_text_from_html(html_content)
                title = self._extract_title_from_html(html_content)

                # Check if page is relevant
                relevance_score = self._calculate_relevance(
                    text_content,
                    title,
                    url,
                    company_name,
                    products
                )

                if relevance_score > 0.3:  # Threshold for inclusion
                    pages.append({
                        "url": url,
                        "title": title,
                        "content": text_content[:15000],  # Limit content length
                        "relevance": relevance_score
                    })
                    logger.info(f"✅ Crawled: {title[:50]}... (relevance: {relevance_score:.2f})")

                # Extract and queue links for crawling
                if depth < self.max_depth:
                    links = self._extract_links(html_content, url, base_domain)

                    # Prioritize product-related links
                    priority_links = [l for l in links if any(
                        re.search(p, l, re.I) for p in self.priority_patterns
                    )]
                    other_links = [l for l in links if l not in priority_links]

                    # Crawl priority links first
                    for link in priority_links[:10]:
                        await self._crawl_page(
                            url=link,
                            base_domain=base_domain,
                            visited=visited,
                            pages=pages,
                            depth=depth + 1,
                            company_name=company_name,
                            products=products
                        )

                    # Then some other links
                    for link in other_links[:5]:
                        await self._crawl_page(
                            url=link,
                            base_domain=base_domain,
                            visited=visited,
                            pages=pages,
                            depth=depth + 1,
                            company_name=company_name,
                            products=products
                        )

        except Exception as e:
            logger.warning(f"⚠️ Error crawling {url}: {str(e)}")

    def _extract_text_from_html(self, html: str) -> str:
        """
        Extract readable text from HTML (simple regex-based extraction).
        For production, consider using beautifulsoup4.
        """
        # Remove script and style elements
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.I)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.I)
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.I)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.I)

        # Remove HTML comments
        html = re.sub(r'<!--.*?-->', '', html, flags=re.DOTALL)

        # Remove all HTML tags
        text = re.sub(r'<[^>]+>', ' ', html)

        # Decode HTML entities
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&quot;', '"', text)
        text = re.sub(r'&#\d+;', '', text)

        # Clean whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        return text

    def _extract_title_from_html(self, html: str) -> str:
        """Extract page title from HTML."""
        match = re.search(r'<title[^>]*>([^<]+)</title>', html, re.I)
        if match:
            return match.group(1).strip()

        # Try h1 as fallback
        match = re.search(r'<h1[^>]*>([^<]+)</h1>', html, re.I)
        if match:
            return match.group(1).strip()

        return "Untitled Page"

    def _extract_links(self, html: str, base_url: str, base_domain: str) -> List[str]:
        """Extract internal links from HTML."""
        links = []

        # Find all href attributes
        href_pattern = r'href=["\']([^"\']+)["\']'
        matches = re.findall(href_pattern, html, re.I)

        for href in matches:
            # Skip anchors and javascript
            if href.startswith('#') or href.startswith('javascript:'):
                continue

            # Convert relative URLs to absolute
            full_url = urljoin(base_url, href)

            # Only include same-domain links
            parsed = urlparse(full_url)
            if parsed.netloc == base_domain:
                # Remove fragments and query strings for deduplication
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                if clean_url not in links:
                    links.append(clean_url)

        return links[:50]  # Limit links per page

    def _calculate_relevance(
        self,
        content: str,
        title: str,
        url: str,
        company_name: str,
        products: List[str]
    ) -> float:
        """
        Calculate relevance score for a page.
        """
        score = 0.0
        content_lower = content.lower()
        title_lower = title.lower()
        url_lower = url.lower()

        # Check for product keywords
        product_keywords = products + [
            "product", "specifications", "specs", "features",
            "model", "dimensions", "warranty", "price",
            "installation", "how to", "faq", "support"
        ]

        for keyword in product_keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in title_lower:
                score += 0.3
            if keyword_lower in content_lower:
                score += 0.1
            if keyword_lower in url_lower:
                score += 0.2

        # Check for company name
        if company_name.lower() in content_lower:
            score += 0.1

        # Penalize very short content
        if len(content) < 500:
            score *= 0.5

        # Cap at 1.0
        return min(score, 1.0)

    async def _extract_knowledge_chunks(
        self,
        pages_content: List[Dict],
        company_name: str,
        products: List[str]
    ) -> List[Dict]:
        """
        Use GPT-4 to extract structured knowledge chunks from crawled pages.
        """
        # Combine page content for analysis
        combined_content = "\n\n---PAGE BREAK---\n\n".join([
            f"Title: {page['title']}\nURL: {page['url']}\n\n{page['content'][:5000]}"
            for page in sorted(pages_content, key=lambda x: x['relevance'], reverse=True)[:15]
        ])

        prompt = f"""Analyze this website content from {company_name} and extract SPECIFIC product knowledge.

Create knowledge chunks that will help answer customer questions. Each chunk should be:
1. Self-contained (makes sense on its own)
2. Specific (includes actual numbers, specs, features)
3. Accurate (only include facts from the content)

Product keywords to focus on: {', '.join(products) if products else 'general products'}

Website Content:
{combined_content[:25000]}

Return a JSON array of knowledge chunks with this structure:
[
  {{"title": "Short descriptive title", "category": "product|spec|faq|brand", "content": "Detailed information extracted from the website..."}},
  ...
]

Extract at least 5 chunks if possible. Focus on:
- Product names and descriptions
- Technical specifications (dimensions, power, features)
- Installation requirements
- Comparison information
- FAQs and common questions
- Company/brand information

IMPORTANT: Only include factual information from the content. Do not make up specifications."""

        try:
            response = await self.openai.chat.completions.create(
                model="gpt-4o-mini",  # Cost-effective for extraction
                messages=[
                    {"role": "system", "content": "You are a product information extractor. Extract accurate, specific knowledge from website content. Return valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )

            content = response.choices[0].message.content

            # Parse JSON from response
            # Handle markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            import json
            chunks = json.loads(content.strip())

            # Validate chunks
            valid_chunks = []
            for chunk in chunks:
                if all(k in chunk for k in ['title', 'category', 'content']):
                    if len(chunk['content']) > 50:  # Minimum content length
                        valid_chunks.append(chunk)

            return valid_chunks

        except Exception as e:
            logger.error(f"Error extracting knowledge chunks: {str(e)}")
            return []

    async def _store_knowledge_chunks(
        self,
        client_id: str,
        company_name: str,
        chunks: List[Dict]
    ) -> int:
        """
        Store knowledge chunks as embeddings in document_embeddings.
        Uses the same pattern as /api/admin/ingest-knowledge.
        """
        embeddings_created = 0

        for idx, chunk in enumerate(chunks):
            try:
                # Combine title and content for embedding
                full_text = f"{chunk['title']}\n\n{chunk['content']}"

                # Generate embedding
                response = await self.openai.embeddings.create(
                    model="text-embedding-ada-002",
                    input=full_text[:8000]
                )
                embedding = response.data[0].embedding

                # Generate synthetic document_id for crawled content
                synthetic_doc_id = str(uuid.uuid4())

                # Store in document_embeddings
                embedding_record = {
                    'document_id': synthetic_doc_id,
                    'client_id': client_id,
                    'chunk_text': full_text,
                    'chunk_index': idx,
                    'embedding': embedding,
                    'metadata': {
                        'title': chunk['title'],
                        'category': chunk.get('category', 'product'),
                        'source': 'website_crawler',
                        'char_count': len(full_text),
                        'company_name': company_name,
                        'crawled_at': datetime.utcnow().isoformat()
                    },
                    'created_at': datetime.utcnow().isoformat()
                }

                self.supabase.table('document_embeddings').insert(embedding_record).execute()
                embeddings_created += 1
                logger.info(f"   Created embedding for: {chunk['title'][:50]}...")

            except Exception as e:
                logger.error(f"Error storing chunk '{chunk.get('title', 'unknown')}': {str(e)}")

        return embeddings_created


async def crawl_client_website(
    supabase_client,
    openai_api_key: str,
    client_id: str,
    website_url: str,
    company_name: str,
    products: List[str] = None
) -> Dict[str, Any]:
    """
    Convenience function to crawl a client's website.
    """
    crawler = WebsiteCrawlerService(supabase_client, openai_api_key)
    return await crawler.crawl_website(client_id, website_url, company_name, products)
