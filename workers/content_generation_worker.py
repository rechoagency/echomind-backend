"""
Content Generation Worker - UPDATED with Slider Integration
Generates natural Reddit responses with slider-based strategy controls
"""

import os
import logging
import json
import random
from typing import Dict, List, Optional
from datetime import datetime, date
from supabase import create_client, Client
from openai import OpenAI
import sys
import os

# Traffic attribution for business ROI
try:
    from utils.utm_builder import inject_link_naturally
except ImportError:
    logger.warning("utm_builder not found - traffic attribution disabled")
    inject_link_naturally = None

# Add parent directory to path for service imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.profile_rotation_service import ProfileRotationService
from services.strategy_progression_service import StrategyProgressionService
from services.knowledge_matchback_service import KnowledgeMatchbackService
from utils.retry_decorator import retry_on_openai_error

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize clients
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
# OpenAI client with timeout (30 seconds)
openai_client = OpenAI(api_key=OPENAI_API_KEY, timeout=30.0)


class ContentGenerationWorker:
    """
    Worker that generates Reddit responses with slider-based strategy controls
    """
    
    def __init__(self):
        """Initialize the content generation worker"""
        self.supabase = supabase
        self.openai = openai_client
        self.profile_rotation = ProfileRotationService()
        self.strategy_progression = StrategyProgressionService()
        self.knowledge_matchback = KnowledgeMatchbackService(supabase)
        logger.info("Content Generation Worker initialized (WITH PROFILE ROTATION, TIME-BASED STRATEGY & KNOWLEDGE BASE RAG)")

    @retry_on_openai_error(max_attempts=3)
    def _call_openai_with_retry(self, prompt: str, max_tokens: int = 250) -> str:
        """Call OpenAI API with automatic retry and exponential backoff."""
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Please write the response now."}
                ],
                temperature=0.8,
                max_tokens=max_tokens
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise
    
    def get_client_settings(self, client_id: str) -> Dict:
        """
        Load client settings including slider values and special instructions.
        Returns defaults if no settings found.
        """
        try:
            response = self.supabase.table('client_settings') \
                .select('*') \
                .eq('client_id', client_id) \
                .single() \
                .execute()
            
            if response.data:
                logger.info(f"✅ Loaded settings for client {client_id}")
                return {
                    'reply_percentage': response.data.get('reply_percentage', 70),
                    'brand_mention_percentage': response.data.get('brand_mention_percentage', 30),
                    'product_mention_percentage': response.data.get('product_mention_percentage', 20),
                    'explicit_instructions': response.data.get('explicit_instructions', '')
                }
            else:
                logger.warning(f"⚠️ No settings found for client {client_id}, using defaults")
                return {
                    'reply_percentage': 70,
                    'brand_mention_percentage': 30,
                    'product_mention_percentage': 20,
                    'explicit_instructions': ''
                }
        except Exception as e:
            logger.error(f"❌ Error loading client settings: {e}")
            return {
                'reply_percentage': 70,
                'brand_mention_percentage': 30,
                'product_mention_percentage': 20,
                'explicit_instructions': ''
            }
    
    def should_mention_brand(self, brand_mention_percentage: int) -> bool:
        """Probabilistically decide if brand should be mentioned"""
        return random.randint(1, 100) <= brand_mention_percentage
    
    def should_mention_product(self, product_mention_percentage: int, similarity_score: float) -> bool:
        """
        Decide if product should be mentioned.
        ONLY applies when vector similarity >= 0.75 (75%)
        """
        if similarity_score < 0.75:
            return False
        return random.randint(1, 100) <= product_mention_percentage
    
    def get_voice_profile(self, subreddit_name: str, client_id: str) -> Optional[Dict]:
        """
        Get voice profile for a subreddit
        """
        try:
            profile = self.supabase.table("voice_profiles")\
                .select("*")\
                .eq("subreddit_name", subreddit_name.lower())\
                .eq("client_id", client_id)\
                .execute()
            
            if profile.data:
                return profile.data[0]
            
            logger.warning(f"No voice profile found for r/{subreddit_name}")
            return None
        
        except Exception as e:
            logger.error(f"Error fetching voice profile: {str(e)}")
            return None
    
    def build_generation_prompt(
        self,
        opportunity: Dict,
        voice_profile: Optional[Dict],
        product_matches: Optional[Dict],
        knowledge_insights: Optional[List[Dict]],
        client_settings: Dict,
        mention_brand: bool,
        mention_product: bool,
        brand_name: str,
        client_data: Optional[Dict] = None
    ) -> str:
        """
        Build prompt for GPT content generation WITH slider controls AND subreddit ownership logic
        """
        thread_title = opportunity.get("thread_title", "")
        thread_content = opportunity.get("original_post_text", "")  # Use correct column name
        subreddit = opportunity.get("subreddit", "")  # Use correct column name
        
        # Check if brand owns this subreddit
        owned_subreddits = []
        if client_data:
            owned_subreddits = client_data.get('owned_subreddits', []) or client_data.get('brand_owned_subreddits', [])
        
        is_owned = subreddit in owned_subreddits or f"r/{subreddit}" in owned_subreddits
        
        # Base prompt with ownership-specific strategy
        if is_owned:
            # OWNED SUBREDDIT: Promotional seed content strategy
            prompt = f"""You are the moderator/community manager of r/{subreddit}, a brand-owned community.

**Your Goal:** Create engaging seed content to draw users and spark conversation.

**Thread Title:** {thread_title}

**Thread Content:** {thread_content}

**Your Task:** Write promotional seed content that:
1. Highlights {brand_name} products/services naturally
2. Asks engaging questions to encourage community discussion
3. Shares helpful tips, guides, or resources related to your brand
4. Promotes upcoming sales, new products, or brand initiatives
5. Builds excitement and community engagement

**Tone:** Friendly brand voice, community-building, promotional but authentic
"""
        else:
            # NOT OWNED: Careful, objective community reply strategy
            prompt = f"""You are a helpful Reddit community member responding in r/{subreddit}.

**Thread Title:** {thread_title}

**Thread Content:** {thread_content}

**Your Task:** Write a natural, empathetic response that:
1. Shows genuine understanding of their situation
2. Provides helpful advice or shares personal experience
3. {'Subtly mentions ' + brand_name + ' in a natural way' if mention_brand else 'Provides helpful advice WITHOUT mentioning ' + brand_name}

"""
        
        # Add voice profile guidelines
        if voice_profile:
            formality = voice_profile.get("formality_score", 0.5)
            lowercase_pct = voice_profile.get("lowercase_start_pct", 0)
            exclamation_pct = voice_profile.get("exclamation_usage_pct", 0)
            dominant_tone = voice_profile.get("dominant_tone", "supportive")
            
            prompt += f"""**Community Voice Style (r/{subreddit}):**
- Formality: {"Casual and conversational" if formality < 0.4 else "Moderately formal" if formality < 0.7 else "Professional"}
- Tone: {dominant_tone}
- Writing style: {"Often starts lowercase, relaxed" if lowercase_pct > 60 else "Standard capitalization"}
- Enthusiasm: {"High energy, uses exclamation marks" if exclamation_pct > 10 else "Moderate, occasional excitement" if exclamation_pct > 5 else "Calm and measured"}

"""
        
        # CRITICAL: Add knowledge base insights for ALL posts (thought leadership)
        if knowledge_insights and len(knowledge_insights) > 0:
            prompt += """\n**UNIQUE DATA & RESEARCH (from your company's knowledge base):**

You have access to proprietary research, case studies, and data that most people don't have. Use these insights to add credibility and unique value to your response:

"""
            for i, insight in enumerate(knowledge_insights[:3], 1):
                excerpt = insight.get('excerpt', '')
                source = insight.get('source_filename', 'Internal Research')
                relevance = insight.get('relevance_percentage', 0)
                
                prompt += f"{i}. **Insight from {source}** (relevance: {relevance}%):\n"
                prompt += f"   {excerpt}\n\n"
            
            prompt += """**HOW TO USE THESE INSIGHTS:**
- Naturally weave this data into your response when contextually relevant
- DO NOT explicitly mention the company name or say "our research" during karma building phase
- Frame it as "research shows..." or "data indicates..." or "studies have found..."
- This positions you as a knowledgeable expert, not a marketer
- Reddit, Google, and LLMs value unique information that can't be found elsewhere
- This is KEY for building karma and trust before any brand mentions

"""
        
        # Add product context if should mention
        if mention_product and product_matches:
            matches = product_matches.get("matches", [])
            if matches:
                prompt += "**Relevant Product Information (mention naturally if appropriate):**\n\n"
                for i, match in enumerate(matches[:2], 1):
                    product_info = match.get("product_info", "")
                    relevance = match.get("relevance_score", 0)
                    prompt += f"{i}. {product_info[:300]}... (relevance: {relevance})\n\n"
        
        # CRITICAL: Add special instructions
        explicit_instructions = client_settings.get('explicit_instructions', '')
        if explicit_instructions:
            prompt += f"""
**CRITICAL COMPLIANCE GUIDELINES (MUST FOLLOW):**
{explicit_instructions}

These guidelines take precedence over all other instructions.

"""
        
        # Final instructions (different for owned vs not-owned)
        if is_owned:
            # Owned subreddit: More promotional, community-building
            prompt += """**Posting Guidelines for Brand-Owned Community:**
- COMMUNITY FIRST: Build genuine value and engagement
- PROMOTIONAL ENCOURAGED: Highlight brand benefits, products, sales
- CALL-TO-ACTION OK: "Check out our...", "Visit our store...", "Join our newsletter..."
- BRAND VOICE: Use official brand tone and messaging
- ENGAGE: Ask questions, request feedback, encourage discussion
- SHOWCASE: Share product highlights, customer stories, brand news

Write the engaging seed content now:"""
        else:
            # Not owned: Subtle, community-friendly, no hard selling
            prompt += """**Important Guidelines (Community Subreddit):**
- BE AUTHENTIC: Sound like a real person sharing experience, not an ad
- BE HELPFUL FIRST: Address their problem genuinely before any product/brand mention
- BE SUBTLE: If mentioning a product or brand, do it naturally ("I've had good results with...", "something that helped me was...")
- BE HONEST: Add disclaimers like "not sponsored" or "just my experience"
- MATCH THE TONE: Use the community's voice style
- BE BRIEF: 2-4 sentences max, Reddit users prefer concise responses
- NO HARD SELLING: Never use sales language or call-to-actions
- COMMUNITY RULES: Respect the community, don't spam or over-promote

Write the response now:"""
        
        return prompt
    
    def generate_content_for_client(
        self,
        client_id: str,
        opportunities: List[Dict],
        delivery_batch: str = None
    ) -> Dict:
        """
        Generate content for Mon/Thu delivery with slider-based strategy
        
        Args:
            client_id: Client UUID
            opportunities: List of scored opportunities
            delivery_batch: e.g. 'MON-2025-W47'
            
        Returns:
            Generated content and stats
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"🚀 Generating content for client: {client_id}")
        logger.info(f"{'='*70}\n")
        
        # STEP 1: Load client data
        client_response = self.supabase.table('clients').select('*').eq('client_id', client_id).single().execute()
        if not client_response.data:
            logger.error(f"❌ Client {client_id} not found")
            return {"success": False, "error": "Client not found"}
        
        client = client_response.data
        brand_name = client['company_name']
        
        # STEP 2: Load client settings WITH TIME-BASED PROGRESSION
        settings = self.strategy_progression.get_effective_strategy(client_id)
        
        logger.info(f"📊 Effective Strategy (Phase: {settings.get('phase_name', 'Unknown')}):")
        logger.info(f"   Days Active: {settings.get('days_since_onboarding', 0)}")
        logger.info(f"   Reply Percentage: {settings['reply_percentage']}%")
        logger.info(f"   Brand Mention: {settings['brand_mention_percentage']}%")
        logger.info(f"   Product Mention: {settings['product_mention_percentage']}%")
        if settings.get('phase_override_active'):
            logger.info(f"   ⚠️ PHASE OVERRIDE ACTIVE: Using {settings['current_phase']} settings")
        logger.info(f"   Special Instructions: {'✅ Present' if settings.get('explicit_instructions') else '❌ None'}\n")
        
        # STEP 3: Apply reply vs post ratio
        total_content = len(opportunities)
        reply_pct = settings['reply_percentage']
        num_replies = int(total_content * (reply_pct / 100))
        num_posts = total_content - num_replies
        
        logger.info(f"📝 Content Plan:")
        logger.info(f"   Total: {total_content} pieces")
        logger.info(f"   Replies: {num_replies}")
        logger.info(f"   Posts: {num_posts}\n")
        
        # STEP 3.5: Assign Reddit profiles to opportunities
        logger.info(f"🔄 Assigning Reddit profiles...")
        opportunities = self.profile_rotation.assign_profiles_to_opportunities(
            client_id,
            opportunities
        )
        logger.info(f"✅ Profile assignments complete\n")
        
        generated_content = []
        
        # STEP 4: Generate each piece of content
        for i, opportunity in enumerate(opportunities):
            try:
                # Determine content type
                content_type = 'reply' if i < num_replies else 'post'
                
                # STEP 5: Decide brand mention (applies to ALL content)
                mention_brand = self.should_mention_brand(settings['brand_mention_percentage'])
                
                # STEP 6: Decide product mention (only when similarity >= 75%)
                product_similarity = opportunity.get('product_similarity', 0)
                mention_product = self.should_mention_product(
                    settings['product_mention_percentage'],
                    product_similarity
                )
                
                logger.info(f"   Generating {content_type} #{i+1}:")
                logger.info(f"      Brand mention: {'✅ Yes' if mention_brand else '❌ No'}")
                logger.info(f"      Product mention: {'✅ Yes' if mention_product else '❌ No'} (similarity: {product_similarity:.2f})")
                
                # Get voice profile
                subreddit = opportunity.get('subreddit', '')  # Use correct column name
                voice_profile = self.get_voice_profile(subreddit, client_id)
                
                # Get product matches
                product_matches = opportunity.get('product_matchback')
                
                # CRITICAL: Get knowledge base insights for ALL posts (not just when products mentioned)
                opportunity_text = f"{opportunity.get('reddit_item_title', '')}\n\n{opportunity.get('reddit_item_content', '')}"
                knowledge_insights = self.knowledge_matchback.match_opportunity_to_knowledge(
                    opportunity_text=opportunity_text,
                    client_id=client_id,
                    similarity_threshold=0.70,  # Lower than products (0.75) for broader matching
                    max_insights=3
                )
                scores = [f"{k['relevance_percentage']}%" for k in knowledge_insights]
                logger.info(f"      Knowledge insights found: {len(knowledge_insights)} (scores: {scores})")
                
                # STEP 7: Build prompt with special instructions AND ownership logic
                prompt = self.build_generation_prompt(
                    opportunity=opportunity,
                    voice_profile=voice_profile,
                    product_matches=product_matches,
                    knowledge_insights=knowledge_insights,
                    client_settings=settings,
                    mention_brand=mention_brand,
                    mention_product=mention_product,
                    brand_name=brand_name,
                    client_data=client  # Pass client data for ownership check
                )
                
                # STEP 8: Generate with AI (with automatic retry)
                content_text = self._call_openai_with_retry(prompt, max_tokens=250)
                
                # STEP 8.5: Inject trackable link for traffic attribution (ROI TRACKING!)
                if inject_link_naturally:
                    website_url = client.get('website_url')
                    if website_url and len(content_text) > 100:
                        content_text = inject_link_naturally(
                            content=content_text,
                            website_url=website_url,
                            client_id=client_id,
                            subreddit=subreddit
                        )
                        logger.info(f"      💰 Traffic attribution: {website_url}")
                
                # STEP 9: Log delivery to database WITH PROFILE INFO & KNOWLEDGE INSIGHTS
                db_error = self.log_content_delivery(
                    client_id=client_id,
                    content_type=content_type,
                    subreddit=subreddit,
                    content_text=content_text,
                    opportunity_id=opportunity.get('opportunity_id'),
                    reddit_item_id=opportunity.get('reddit_id'),
                    brand_mentioned=mention_brand,
                    product_mentioned=opportunity.get('matched_product') if mention_product else None,
                    delivery_batch=delivery_batch,
                    profile_id=opportunity.get('assigned_profile'),
                    profile_username=opportunity.get('profile_username'),
                    knowledge_insights_count=len(knowledge_insights)
                )

                generated_content.append({
                    'type': content_type,
                    'text': content_text,
                    'subreddit': subreddit,
                    'brand_mentioned': mention_brand,
                    'product_mentioned': mention_product,
                    'assigned_profile': opportunity.get('profile_username', 'NO_PROFILE'),
                    'profile_karma': opportunity.get('profile_karma', 0),
                    'opportunity_id': opportunity.get('opportunity_id'),
                    'thread_title': opportunity.get('thread_title', ''),
                    'db_insert_error': db_error  # Will be None if successful
                })
                
            except Exception as e:
                logger.error(f"❌ Error generating content #{i+1}: {e}")
                continue
        
        logger.info(f"\n✅ Generated {len(generated_content)} pieces of content")
        logger.info(f"{'='*70}\n")
        
        return {
            "success": True,
            "generated": len(generated_content),
            "content": generated_content
        }
    
    def log_content_delivery(
        self,
        client_id: str,
        content_type: str,
        subreddit: str,
        content_text: str,
        opportunity_id: Optional[str],
        reddit_item_id: str,
        brand_mentioned: bool,
        product_mentioned: Optional[str],
        delivery_batch: Optional[str],
        profile_id: Optional[str] = None,
        profile_username: Optional[str] = None,
        knowledge_insights_count: int = 0
    ) -> Optional[str]:
        """Log content delivery to database for analytics WITH PROFILE INFO & KNOWLEDGE BASE USAGE

        Returns:
            None on success, error message string on failure
        """
        try:
            # Use column names that match actual Supabase schema
            # From reports_router.py: subreddit_name, delivered_at
            insert_data = {
                'client_id': client_id,
                'content_type': content_type,
                'subreddit_name': subreddit or 'unknown',
                'delivered_at': datetime.utcnow().isoformat(),
                'body': content_text,  # Body for the content
            }
            logger.info(f"      📝 Inserting to content_delivered: {list(insert_data.keys())}")
            result = self.supabase.table('content_delivered').insert(insert_data).execute()
            logger.info(f"      ✅ Logged {content_type} to content_delivered (result: {result.data})")
            return None
        except Exception as e:
            error_msg = str(e)
            logger.error(f"      ❌ Error logging delivery: {error_msg}")
            return error_msg

    def process_all_opportunities(
        self,
        client_id: Optional[str] = None,
        regenerate: bool = False,
        only_with_products: bool = False
    ) -> Dict:
        """
        Process all opportunities and generate content.
        Called by the scheduler pipeline.

        Args:
            client_id: Optional client ID to filter by
            regenerate: If True, regenerate existing content
            only_with_products: If True, only process opportunities with product matches

        Returns:
            Dictionary with processing results
        """
        try:
            logger.info("=" * 70)
            logger.info("🔥 PROCESS_ALL_OPPORTUNITIES CALLED")
            logger.info("=" * 70)
            logger.info(f"Client ID: {client_id}")
            logger.info(f"Regenerate: {regenerate}")
            logger.info(f"Only with products: {only_with_products}")

            # Build query for opportunities - get recent ones (simple query to avoid timeout)
            # The complex scoring filter was causing Supabase statement timeout
            logger.info("📊 Querying for recent opportunities (simple query)...")
            # Use correct column names: opportunity_id, thread_title, original_post_text, subreddit
            query = self.supabase.table("opportunities").select("opportunity_id, client_id, thread_title, original_post_text, subreddit, thread_url, date_found")
            if client_id:
                query = query.eq("client_id", client_id)
            query = query.order("date_found", desc=True)
            query = query.limit(10)  # Start with 10 to avoid timeout

            opportunities_response = query.execute()
            logger.info(f"📊 Query result: {len(opportunities_response.data or [])} opportunities found")

            if not opportunities_response.data:
                logger.info("No scored opportunities found to generate content for")
                return {
                    "success": True,
                    "processed": 0,
                    "with_product_mentions": 0,
                    "without_product_mentions": 0,
                    "message": "No opportunities to process"
                }

            opportunities = opportunities_response.data
            logger.info(f"Found {len(opportunities)} opportunities to generate content for")

            # Filter by product if required
            if only_with_products:
                opportunities = [o for o in opportunities if o.get('matched_product_id')]
                logger.info(f"Filtered to {len(opportunities)} opportunities with product matches")

                if not opportunities:
                    return {
                        "success": True,
                        "processed": 0,
                        "with_product_mentions": 0,
                        "without_product_mentions": 0,
                        "message": "No opportunities with product matches"
                    }

            # Check for existing content if not regenerating
            if not regenerate:
                existing_content = self.supabase.table("content_delivered")\
                    .select("opportunity_id")\
                    .in_("opportunity_id", [o["opportunity_id"] for o in opportunities])\
                    .execute()

                existing_ids = {c["opportunity_id"] for c in (existing_content.data or [])}
                opportunities = [o for o in opportunities if o["opportunity_id"] not in existing_ids]

                if not opportunities:
                    logger.info("All opportunities already have generated content")
                    return {
                        "success": True,
                        "processed": 0,
                        "with_product_mentions": 0,
                        "without_product_mentions": 0,
                        "message": "All opportunities already processed"
                    }

            # Group by client
            from collections import defaultdict
            by_client = defaultdict(list)
            for opp in opportunities:
                by_client[opp["client_id"]].append(opp)

            total_processed = 0
            with_products = 0
            without_products = 0

            # Generate content for each client's opportunities
            logger.info(f"🎯 Processing {len(by_client)} client(s) with opportunities")
            for cid, client_opps in by_client.items():
                logger.info("=" * 50)
                logger.info(f"🚀 CALLING generate_content_for_client")
                logger.info(f"   Client ID: {cid}")
                logger.info(f"   Opportunities: {len(client_opps)}")
                if client_opps:
                    sample = client_opps[0]
                    logger.info(f"   Sample opportunity keys: {list(sample.keys())[:10]}")
                    logger.info(f"   Sample opportunity ID: {sample.get('opportunity_id')}")

                try:
                    result = self.generate_content_for_client(
                        client_id=cid,
                        opportunities=client_opps,
                        delivery_batch=f"PIPELINE-{datetime.now().strftime('%Y-%m-%d')}"
                    )
                    logger.info(f"✅ generate_content_for_client returned: {result}")
                except Exception as gen_error:
                    logger.error(f"❌ generate_content_for_client FAILED: {gen_error}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    result = {"success": False, "error": str(gen_error)}

                if result.get("success"):
                    generated = result.get("generated", 0)
                    total_processed += generated

                    # Count product mentions
                    for content in result.get("content", []):
                        if content.get("product_mentioned"):
                            with_products += 1
                        else:
                            without_products += 1

            logger.info("=" * 70)
            logger.info(f"🏁 Content generation complete: {total_processed} pieces generated")
            logger.info("=" * 70)

            return {
                "success": True,
                "processed": total_processed,
                "with_product_mentions": with_products,
                "without_product_mentions": without_products
            }

        except Exception as e:
            import traceback
            logger.error("=" * 70)
            logger.error(f"❌ FATAL ERROR in process_all_opportunities: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            logger.error("=" * 70)
            return {
                "success": False,
                "error": str(e),
                "processed": 0,
                "with_product_mentions": 0,
                "without_product_mentions": 0
            }


# Standalone test function
def test_with_the_waite():
    """Test with The Waite client"""
    import asyncio
    
    THE_WAITE_CLIENT_ID = "466046c9-9e68-4957-8445-9a4fcf92def6"
    
    worker = ContentGenerationWorker()
    
    # Get some test opportunities
    opportunities_response = supabase.table('opportunities') \
        .select('*') \
        .eq('client_id', THE_WAITE_CLIENT_ID) \
        .limit(10) \
        .execute()
    
    if opportunities_response.data:
        result = worker.generate_content_for_client(
            client_id=THE_WAITE_CLIENT_ID,
            opportunities=opportunities_response.data,
            delivery_batch='TEST-2025-W47'
        )
        print(json.dumps(result, indent=2))
    else:
        print("No opportunities found for The Waite")


if __name__ == "__main__":
    test_with_the_waite()
