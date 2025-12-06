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

# Traffic attribution for business ROI (import with fallback)
try:
    from utils.utm_builder import inject_link_naturally
except ImportError:
    inject_link_naturally = None  # Will log warning after logger is configured

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
    
    # Fallback voice profile for when subreddit-specific profile is missing
    FALLBACK_VOICE_PROFILE = {
        # Length patterns
        "avg_word_count": 75,
        "word_count_range": {"min": 30, "max": 200},
        "short_reply_probability": 0.4,
        "avg_sentence_length": 12,

        # Grammar patterns
        "capitalization_style": "mixed",
        "lowercase_start_pct": 25,

        # Lexical patterns
        "common_phrases": ["honestly", "in my experience", "typically", "depends on"],
        "slang_examples": [],
        "signature_idioms": [],

        # Emoji patterns
        "emoji_frequency": "rare",
        "common_emojis": [],

        # Tone patterns
        "dominant_tone": "helpful, direct",
        "tone": "supportive, conversational",
        "grammar_style": "casual with informal patterns",
        "formality_score": 0.35,
        "formality_level": "LOW",

        # Content patterns
        "example_openers": [],
        "example_closers": [],
        "question_frequency": 0.1,
        "exclamation_usage_pct": 5,
        "hedging_frequency": 0.02,

        # Metadata
        "voice_description": "Default Reddit community voice. Friendly and authentic.",
        "sample_comments": [],
        "users_analyzed": 0,
        "comments_analyzed": 0,
        "is_fallback": True
    }

    def get_voice_profile(self, subreddit_name: str, client_id: str) -> Optional[Dict]:
        """
        Get voice profile for a subreddit.
        Returns fallback profile if none found (ensures content always sounds human).
        Note: voice_database_worker saves to 'subreddit' column, not 'subreddit_name'
        """
        try:
            # Try 'subreddit' column first (what voice_database_worker uses)
            profile = self.supabase.table("voice_profiles")\
                .select("*")\
                .eq("subreddit", subreddit_name.lower())\
                .eq("client_id", client_id)\
                .execute()

            if profile.data:
                return profile.data[0]

            # Return fallback profile instead of None
            logger.warning(f"No voice profile found for r/{subreddit_name} - using fallback voice")
            return self.FALLBACK_VOICE_PROFILE

        except Exception as e:
            logger.error(f"Error fetching voice profile: {str(e)} - using fallback")
            return self.FALLBACK_VOICE_PROFILE
    
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
        Build the complete prompt for GPT-4 content generation.

        This prompt has FIVE layers:
        1. GLOBAL RULES - Same for all content (authenticity, no fake experience)
        2. DYNAMIC VOICE - From learned subreddit patterns (changes per subreddit)
        3. DYNAMIC KNOWLEDGE - From brand's RAG (changes per client)
        4. THREAD CONTEXT - The specific post being replied to
        5. BRAND MENTION - Instructions for brand/product mentions

        Returns:
            Complete prompt string for GPT-4
        """
        thread_title = opportunity.get("thread_title", "")
        thread_content = opportunity.get("original_post_text", "")
        subreddit = opportunity.get("subreddit", "")

        # Check if brand owns this subreddit
        owned_subreddits = []
        if client_data:
            owned_subreddits = client_data.get('owned_subreddits', []) or client_data.get('brand_owned_subreddits', [])
        is_owned = subreddit in owned_subreddits or f"r/{subreddit}" in owned_subreddits

        # ═══════════════════════════════════════════════════════════════════════
        # LAYER 1: GLOBAL AUTHENTICITY RULES (same for ALL content)
        # ═══════════════════════════════════════════════════════════════════════

        global_rules = f"""
══════════════════════════════════════════════════════════════════════════════
AUTHENTICITY RULES (MANDATORY - APPLY TO ALL CONTENT)
══════════════════════════════════════════════════════════════════════════════

You are writing a Reddit response on behalf of {brand_name}, posting from a brand-affiliated account.

CRITICAL - WHAT YOU ARE:
- An industry professional who works in this space
- Someone with genuine expertise who participates in Reddit communities
- A helpful community member who happens to have brand knowledge

CRITICAL - WHAT YOU ARE NOT:
- A fake customer pretending to have bought the product
- A shill writing fake testimonials
- A corporate PR bot

MANDATORY RULES:

1. NEVER FAKE PERSONAL PRODUCT EXPERIENCE
   ❌ FORBIDDEN: "I bought this and loved it!", "When I got mine...", "I've been using this for months"
   ❌ FORBIDDEN: "I had the same problem!", "This happened to me too!", "I dealt with this"
   ✅ CORRECT: "You'll find that...", "Most people report...", "The typical experience is..."
   ✅ CORRECT: "Based on what we see...", "Customers typically...", "In this situation..."

2. USE SECOND PERSON, NOT FIRST PERSON
   ❌ FORBIDDEN: "I recommend...", "I would suggest...", "I think you should..."
   ✅ CORRECT: "You'll want to...", "Consider...", "The best approach is..."
   ✅ ACCEPTABLE: "We make [product]" or "Our [product]" - this is honest, not deceptive

3. NO CORPORATE MARKETING PHRASES
   ❌ FORBIDDEN: "That's a great question!", "Thanks for reaching out!"
   ❌ FORBIDDEN: "Hope this helps!", "We're happy to help!", "Feel free to ask!"
   ❌ FORBIDDEN: "We pride ourselves on...", "Our commitment to quality..."
   ✅ CORRECT: Just provide the helpful information directly, no preamble or sign-off

4. BE HONEST ABOUT LIMITATIONS
   ✅ CORRECT: "This won't work for every situation - specifically..."
   ✅ CORRECT: "The main downside is...", "One thing to be aware of..."
   This builds credibility and trust.

5. EXPERTISE WITHOUT ARROGANCE
   ✅ CORRECT: "The main thing with [topic] is..." (sharing knowledge)
   ✅ CORRECT: "What most people don't realize is..." (insider info)
   ❌ FORBIDDEN: "Actually, you're wrong about..." (condescending)
"""

        # ═══════════════════════════════════════════════════════════════════════
        # LAYER 2: DYNAMIC VOICE (learned from subreddit users)
        # ═══════════════════════════════════════════════════════════════════════

        if voice_profile and not voice_profile.get('is_fallback'):
            # Use ACTUAL learned patterns from the voice_profile JSONB column
            vp = voice_profile.get('voice_profile', voice_profile)

            # Length patterns
            avg_words = vp.get('avg_word_count') or 75
            word_range = vp.get('word_count_range') or {"min": 30, "max": 200}
            short_reply_prob = vp.get('short_reply_probability') or 0.4

            # Grammar patterns
            cap_style = vp.get('capitalization_style') or 'mixed'
            lowercase_pct = vp.get('lowercase_start_pct') or 25
            formality = vp.get('formality_score') or 0.35
            formality_level = vp.get('formality_level') or 'LOW'

            # Lexical patterns
            common_phrases = vp.get('common_phrases') or []
            slang = vp.get('slang_examples') or []
            idioms = vp.get('signature_idioms') or []

            # Emoji patterns
            emoji_freq = vp.get('emoji_frequency') or 'rare'
            common_emojis = vp.get('common_emojis') or []

            # Tone patterns
            tone = vp.get('tone') or vp.get('dominant_tone') or 'helpful'
            grammar_style = vp.get('grammar_style') or 'conversational'

            # Content patterns
            openers = vp.get('example_openers') or []
            closers = vp.get('example_closers') or []
            exclamation_pct = vp.get('exclamation_usage_pct') or 5
            question_freq = vp.get('question_frequency') or 0.1

            # Metadata
            comments_analyzed = vp.get('comments_analyzed') or 0
            users_analyzed = vp.get('users_analyzed') or 0
            sample_comments = vp.get('sample_comments') or []
            voice_description = vp.get('voice_description') or ''

            # Format lists
            phrases_str = ', '.join(f'"{p}"' for p in common_phrases[:8]) if common_phrases else 'none identified'
            slang_str = ', '.join(slang[:6]) if slang else 'minimal slang'
            idioms_str = ', '.join(f'"{i}"' for i in idioms[:5]) if idioms else 'none identified'
            openers_str = ', '.join(f'"{o}"' for o in openers[:5]) if openers else 'no specific patterns'
            emojis_str = ', '.join(common_emojis[:5]) if common_emojis else 'none'

            voice_section = f"""
══════════════════════════════════════════════════════════════════════════════
SUBREDDIT VOICE PROFILE (LEARNED FROM r/{subreddit} USERS)
══════════════════════════════════════════════════════════════════════════════

These patterns were extracted from analyzing {comments_analyzed} real comments
by {users_analyzed} users in r/{subreddit}. MATCH THEM.

LENGTH:
- Average reply length: {avg_words} words
- Typical range: {word_range.get('min', 30)} to {word_range.get('max', 200)} words
- Short replies (<50 words): {round(short_reply_prob * 100)}% of posts
- Keep your response within this range unless the topic requires more detail

GRAMMAR & CAPITALIZATION:
- Style: {cap_style}
- {lowercase_pct}% of sentences start lowercase (match this roughly)
- {"Use sentence fragments freely - users here don't always write complete sentences" if formality < 0.3 else "Write in complete sentences"}

FORMALITY: {formality} (0=very casual, 1=very formal)
- {"Very casual - contractions, relaxed grammar, conversational" if formality < 0.3 else "Moderately formal - clear but not stiff" if formality < 0.6 else "More formal - proper grammar, professional tone"}

COMMON PHRASES IN THIS COMMUNITY:
{phrases_str}
→ Use 1-2 of these naturally if they fit

SLANG USED HERE:
{slang_str}
→ Use if natural, don't force it

SUBREDDIT-SPECIFIC IDIOMS:
{idioms_str}

EMOJI USAGE: {emoji_freq}
{f"Common emojis: {emojis_str}" if common_emojis else ""}
→ {"Use emojis occasionally" if emoji_freq in ['occasional', 'frequent'] else "Avoid emojis or use very sparingly"}

TONE: {tone}
- Grammar style: {grammar_style}
→ Match this tone in your response

EXAMPLE OPENERS USED IN THIS SUB:
{openers_str}
→ Consider starting similarly (but don't copy exactly)

EXCLAMATION MARKS: {exclamation_pct}% of sentences
→ {"Use exclamations freely" if exclamation_pct > 15 else "Use exclamations sparingly" if exclamation_pct > 5 else "Avoid exclamation marks mostly"}

{f'VOICE SUMMARY: {voice_description}' if voice_description else ''}
"""

            # Add sample comments for reference
            if sample_comments:
                voice_section += f"""

EXAMPLE REAL COMMENTS FROM r/{subreddit} (for style reference only):
"""
                for i, sample in enumerate(sample_comments[:3], 1):
                    sample_text = sample.get('text', '')[:250]
                    voice_section += f'\n{i}. "{sample_text}..."'

        else:
            # Fallback for when no profile exists
            voice_section = f"""
══════════════════════════════════════════════════════════════════════════════
SUBREDDIT VOICE (r/{subreddit} - DEFAULT REDDIT STYLE)
══════════════════════════════════════════════════════════════════════════════

No specific voice profile available. Use general Reddit casual style:
- Conversational, helpful tone
- 50-150 words typical
- Contractions OK
- Minimal emojis
- Get to the point quickly
"""

        # ═══════════════════════════════════════════════════════════════════════
        # LAYER 3: DYNAMIC KNOWLEDGE (from brand's RAG)
        # ═══════════════════════════════════════════════════════════════════════

        if knowledge_insights and len(knowledge_insights) > 0:
            knowledge_text = "\n\n".join([
                f"• {insight.get('excerpt', insight.get('chunk_text', ''))[:500]}"
                for insight in knowledge_insights[:5]
            ])
            knowledge_section = f"""
══════════════════════════════════════════════════════════════════════════════
BRAND KNOWLEDGE (USE WHEN RELEVANT)
══════════════════════════════════════════════════════════════════════════════

The following information is from {brand_name}'s knowledge base. Use it when relevant,
but don't force it if it doesn't fit the question.

{knowledge_text}

RULES FOR USING THIS KNOWLEDGE:
- Incorporate naturally, don't dump facts
- Prefer specific details over vague claims
- Frame as "research shows..." or "data indicates..." (not "our research")
- If the thread isn't about these topics, don't mention them
- This positions you as knowledgeable, not as a marketer
"""
        else:
            knowledge_section = f"""
══════════════════════════════════════════════════════════════════════════════
BRAND KNOWLEDGE
══════════════════════════════════════════════════════════════════════════════

No specific product knowledge retrieved for this thread.
Provide helpful general expertise based on the topic.
"""

        # ═══════════════════════════════════════════════════════════════════════
        # LAYER 4: THREAD CONTEXT
        # ═══════════════════════════════════════════════════════════════════════

        thread_section = f"""
══════════════════════════════════════════════════════════════════════════════
THREAD TO RESPOND TO
══════════════════════════════════════════════════════════════════════════════

Subreddit: r/{subreddit}
Title: {thread_title}

Post Content:
{thread_content[:2000] if thread_content else '[No post content]'}
"""

        # ═══════════════════════════════════════════════════════════════════════
        # LAYER 5: BRAND MENTION INSTRUCTIONS
        # ═══════════════════════════════════════════════════════════════════════

        if is_owned:
            # Brand-owned subreddit - promotional allowed
            brand_section = f"""
══════════════════════════════════════════════════════════════════════════════
BRAND MENTION (OWNED SUBREDDIT)
══════════════════════════════════════════════════════════════════════════════

This is a {brand_name}-owned community. You may be promotional:
- Highlight {brand_name} products and services
- Use official brand voice
- Include calls-to-action
- Share brand news and updates
"""
        elif mention_brand or mention_product:
            brand_section = f"""
══════════════════════════════════════════════════════════════════════════════
BRAND MENTION GUIDANCE
══════════════════════════════════════════════════════════════════════════════

{"You MAY mention " + brand_name + " in this response." if mention_brand else ""}
{"You MAY mention specific products if relevant." if mention_product else ""}

RULES:
- Mention as ONE option, not the only solution
- Be honest about pros AND cons
- Frame as "we make" or "our product" - NOT as fake customer testimonial
- Don't oversell - let the helpfulness speak for itself

Example good mention:
"For that room size, you'd want something in the 5000 BTU range. We make the Sideline series
for exactly this use case, but honestly any unit in that range will work similarly."
"""
        else:
            brand_section = """
══════════════════════════════════════════════════════════════════════════════
BRAND MENTION
══════════════════════════════════════════════════════════════════════════════

Do NOT mention the brand or specific products in this response.
Focus purely on being helpful with general expertise.
"""

        # Add explicit instructions if present
        explicit_instructions = client_settings.get('explicit_instructions', '')
        if explicit_instructions:
            brand_section += f"""

CRITICAL COMPLIANCE GUIDELINES (MUST FOLLOW):
{explicit_instructions}

These guidelines take precedence over all other instructions.
"""

        # Add product context if should mention
        if mention_product and product_matches:
            matches = product_matches.get("matches", [])
            if matches:
                brand_section += "\n\n**Relevant Product Information (mention naturally if appropriate):**\n"
                for i, match in enumerate(matches[:2], 1):
                    product_info = match.get("product_info", "")
                    relevance = match.get("relevance_score", 0)
                    brand_section += f"{i}. {product_info[:300]}... (relevance: {relevance})\n"

        # ═══════════════════════════════════════════════════════════════════════
        # FINAL INSTRUCTION
        # ═══════════════════════════════════════════════════════════════════════

        final_instruction = f"""
══════════════════════════════════════════════════════════════════════════════
YOUR TASK
══════════════════════════════════════════════════════════════════════════════

Write a single Reddit reply that:
1. Answers the user's question/addresses their situation helpfully
2. Sounds like a real r/{subreddit} community member (use the voice patterns above)
3. Incorporates brand knowledge naturally IF relevant
4. Follows ALL authenticity rules (no fake experience, no marketing speak)
5. Stays within the typical word count for this subreddit

Output ONLY the reply text. No explanations, no meta-commentary.
"""

        # Combine all sections
        full_prompt = f"""
{global_rules}

{voice_section}

{knowledge_section}

{thread_section}

{brand_section}

{final_instruction}
"""

        return full_prompt
    
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
                # Use correct column names from opportunities table
                opportunity_text = f"{opportunity.get('thread_title', '')}\n\n{opportunity.get('original_post_text', '')}"
                knowledge_insights = self.knowledge_matchback.match_opportunity_to_knowledge(
                    opportunity_text=opportunity_text,
                    client_id=client_id,
                    similarity_threshold=0.50,  # Lowered from 0.70 to capture more knowledge matches
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
                    'knowledge_insights_used': len(knowledge_insights),
                    'knowledge_excerpts': [k.get('excerpt', '')[:100] for k in knowledge_insights[:2]] if knowledge_insights else [],
                    'assigned_profile': opportunity.get('profile_username', 'NO_PROFILE'),
                    'profile_karma': opportunity.get('profile_karma', 0),
                    'opportunity_id': opportunity.get('opportunity_id'),
                    'thread_title': opportunity.get('thread_title', ''),
                    'db_insert_error': db_error  # Will be None if successful
                })
                
            except Exception as e:
                import traceback
                error_tb = traceback.format_exc()
                logger.error(f"❌ Error generating content #{i+1}: {e}")
                logger.error(f"Traceback: {error_tb}")
                generated_content.append({
                    'type': 'error',
                    'error': str(e),
                    'traceback': error_tb,
                    'opportunity_id': opportunity.get('opportunity_id'),
                    'thread_title': opportunity.get('thread_title', '')
                })
                continue

        logger.info(f"\n✅ Generated {len(generated_content)} pieces of content")
        logger.info(f"{'='*70}\n")

        # Separate successful and error items
        successes = [c for c in generated_content if c.get('type') != 'error']
        errors = [c for c in generated_content if c.get('type') == 'error']

        return {
            "success": True,
            "generated": len(successes),
            "errors": len(errors),
            "content": successes,
            "error_details": errors[:3] if errors else []  # Include first 3 errors for debugging
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
