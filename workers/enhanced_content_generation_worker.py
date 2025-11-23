"""
Enhanced Content Generation Worker

Generates ultra-human Reddit content by:
1. Matching subreddit voice profiles
2. Enriching with vectorized client data
3. Using GPT-4 Turbo with anti-AI-pattern prompts
4. Respecting brand mention % controls
5. Including realistic typos, idioms, and natural language patterns

This replaces the basic content_generation_worker.py with voice-aware generation.
import numpy as np
"""

import os
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import random
import re
from openai import OpenAI

from database import get_supabase_client

logger = logging.getLogger(__name__)

class EnhancedContentGenerator:
    """Generates voice-matched, ultra-human content for Reddit"""
    
    # AI patterns to avoid
    AI_RED_FLAGS = [
        "I understand", "I appreciate", "Let me help", "Feel free",
        "I'd be happy to", "Here's the thing", "At the end of the day",
        "It's important to note", "Additionally", "Furthermore",
        "In conclusion", "To summarize", "Moving forward"
    ]
    
    def __init__(self):
        self.supabase = get_supabase_client()
        self.openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = "gpt-4-turbo"  # Best model for human-like writing
    
    async def generate_content(
        self,
        opportunity_id: str,
        thread_context: Dict[str, Any],
        client_data: Dict[str, Any],
        brand_mention_percentage: float = 0.0
    ) -> Dict[str, Any]:
        """
        Generate voice-matched content for an opportunity
        
        Args:
            opportunity_id: UUID of opportunity
            thread_context: Thread title, body, subreddit, user history
            client_data: Brand voice, products, vectorized knowledge
            brand_mention_percentage: 0-100, controls product mention frequency
            
        Returns:
            Generated content with metadata
        """
        try:
            # Step 1: Get subreddit voice profile
            voice_profile = await self._get_voice_profile(
                thread_context['subreddit'],
                client_data['client_id']
            )
            
            # Step 2: Get relevant client knowledge via vector search
            enrichment_data = await self._get_enrichment_data(
                thread_context,
                client_data
            )
            
            # Step 3: Determine if brand mention should be included
            include_brand = self._should_include_brand_mention(
                brand_mention_percentage,
                thread_context.get('commercial_intent', 0),
                enrichment_data
            )
            
            # Step 4: Build ultra-human prompt
            system_prompt = self._build_system_prompt(
                voice_profile,
                client_data['brand_voice'],
                include_brand
            )
            
            user_prompt = self._build_user_prompt(
                thread_context,
                enrichment_data,
                include_brand
            )
            
            # Step 5: Generate with GPT-4 Turbo
            content = await self._generate_with_gpt4(
                system_prompt,
                user_prompt,
                voice_profile
            )
            
            # Step 6: Post-process for realism
            content = self._add_realistic_imperfections(content, voice_profile)
            
            # Step 7: Quality check
            quality_score = self._check_quality(content, voice_profile)
            
            return {
                "opportunity_id": opportunity_id,
                "content": content,
                "preview": content[:100] + "..." if len(content) > 100 else content,
                "brand_mentioned": include_brand,
                "quality_score": quality_score,
                "voice_profile_used": voice_profile['subreddit'],
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error generating content for {opportunity_id}: {e}")
            raise
    
    async def _get_voice_profile(self, subreddit: str, client_id: str) -> Dict[str, Any]:
        """Fetch voice profile from database"""
        try:
            response = self.supabase.table("voice_profiles")\
                .select("voice_profile")\
                .eq("client_id", client_id)\
                .eq("subreddit", subreddit)\
                .execute()
            
            if response.data:
                return response.data[0]['voice_profile']
            else:
                logger.warning(f"No voice profile found for r/{subreddit}, using default")
                return self._get_default_voice_profile(subreddit)
                
        except Exception as e:
            logger.error(f"Error fetching voice profile: {e}")
            return self._get_default_voice_profile(subreddit)
    
    async def _get_enrichment_data(self, thread_context: Dict, client_data: Dict) -> Dict[str, Any]:
        """Get relevant client knowledge via vector search"""
        # This would do actual vector search in production
        # For now, return structured data
        return {
            "relevant_products": client_data.get('products', []),
            "unique_knowledge": client_data.get('unique_knowledge', []),
            "scientific_data": client_data.get('scientific_data', []),
            "customer_insights": client_data.get('customer_insights', [])
        }
    
    def _should_include_brand_mention(
        self,
        brand_percentage: float,
        commercial_intent: float,
        enrichment_data: Dict
    ) -> bool:
        """Determine if this specific opportunity should mention brand"""
        
        # Never mention if brand_percentage is 0
        if brand_percentage == 0:
            return False
        
        # Only mention if commercial intent is high enough
        if commercial_intent < 0.6:
            return False
        
        # Use brand_percentage as probability
        # But boost if commercial intent is very high
        adjusted_probability = brand_percentage / 100.0
        if commercial_intent > 0.8:
            adjusted_probability = min(adjusted_probability * 1.2, 1.0)
        
        return random.random() < adjusted_probability
    
    def _build_system_prompt(
        self,
        voice_profile: Dict,
        brand_voice: Dict,
        include_brand: bool
    ) -> str:
        """Build GPT-4 system prompt for ultra-human writing"""
        
        typo_count = max(1, int(voice_profile.get('typo_frequency', 0.02) * 300))
        
        prompt = f"""You are writing as a REAL PERSON in r/{voice_profile['subreddit']}.

=== VOICE PROFILE ===
Tone: {voice_profile.get('tone', 'casual, supportive')}
Grammar: {voice_profile.get('grammar_style', 'conversational')}
Average sentence length: {voice_profile.get('avg_sentence_length', 12)} words
Formality: {voice_profile.get('formality_level', 'LOW')}
Common phrases this community uses: {', '.join(voice_profile.get('signature_idioms', ['honestly', 'literally'])[:5])}

=== CRITICAL RULES - NO AI PATTERNS ===
❌ NEVER use these AI phrases:
{', '.join(self.AI_RED_FLAGS)}

❌ NEVER write in listicle format with dashes unless it feels natural
❌ NEVER use em-dashes (—) for emphasis
❌ NO corporate speak or customer service language
❌ NO perfect grammar - write like a real tired human

✅ DO include {typo_count} realistic typos/casual mistakes:
- Missing apostrophes (dont, cant, youre)
- Lowercase "i" occasionally
- Double spaces or missing spaces
- Casual abbreviations (bc, tho, def)

✅ DO write like you're texting a friend at 2am
✅ DO use fragments and run-on sentences sometimes
✅ DO include personal anecdotes that sound real
✅ DO show emotion (frustration, hope, exhaustion)

=== PARAGRAPH STRUCTURE ===
- Start with immediate empathy or direct answer
- Share personal experience (2-3 sentences)
- Give practical advice (keep it real)
- End with encouragement BUT not toxic positivity

"""

        if include_brand:
            prompt += f"""
=== BRAND MENTION (Natural Only) ===
Brand: {brand_voice.get('company_name', 'The Waite')}
Voice: {brand_voice.get('tone', 'girlfriend-approved, supportive')}

ONLY mention the brand if:
1. The thread is DIRECTLY related to products
2. It fits naturally in your personal story
3. You frame it as "I found this..." NOT "You should buy..."

Brand disclaimer: {brand_voice.get('medical_disclaimer', 'Always talk to your provider about...')}

Example good mention: "I ended up getting these ice packs from The Waite after someone here recommended them"
Example bad mention: "The Waite has great products for this!"
"""
        else:
            prompt += f"""
=== NO BRAND MENTION ===
Focus purely on being helpful. Build authority and trust.
Share real experience and practical advice only.
"""
        
        return prompt
    
    def _build_user_prompt(
        self,
        thread_context: Dict,
        enrichment_data: Dict,
        include_brand: bool
    ) -> str:
        """Build user prompt with thread context"""
        
        prompt = f"""Thread Title: {thread_context['title']}
Subreddit: r/{thread_context['subreddit']}
Target User: u/{thread_context['target_user']}

Thread Content:
{thread_context.get('body', '[No body text]')}

User's Situation (based on post history):
{thread_context.get('user_context', 'New parent seeking advice')}

"""
        
        if include_brand and enrichment_data.get('relevant_products'):
            prompt += f"""
Relevant Products (mention naturally if appropriate):
{chr(10).join([f"- {p['name']}: {p.get('description', '')}" for p in enrichment_data['relevant_products'][:2]])}
"""
        
        if enrichment_data.get('unique_knowledge'):
            prompt += f"""
Unique Insights (use to show expertise):
{chr(10).join([f"- {k}" for k in enrichment_data['unique_knowledge'][:3]])}
"""
        
        prompt += """
Write a response that:
1. Sounds like a real person who's been through this
2. Is genuinely helpful without being preachy
3. Includes the realistic typos specified
4. Matches the subreddit's voice perfectly
5. Feels like a 2am text to a friend, not a blog post

Length: 100-300 words (natural paragraph breaks)
"""
        
        return prompt
    
    async def _generate_with_gpt4(
        self,
        system_prompt: str,
        user_prompt: str,
        voice_profile: Dict
    ) -> str:
        """Generate content using GPT-4 Turbo"""
        
        try:
            response = self.openai.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.9,  # High creativity for human-like variation
                top_p=0.95,
                frequency_penalty=0.3,  # Reduce repetitive patterns
                presence_penalty=0.3,   # Encourage topic diversity
                max_tokens=600
            )
            
            content = response.choices[0].message.content.strip()
            return content
            
        except Exception as e:
            logger.error(f"GPT-4 generation failed: {e}")
            raise
    
    def _add_realistic_imperfections(self, content: str, voice_profile: Dict) -> str:
        """Add realistic typos and imperfections"""
        
        # Occasionally lowercase "i"
        if random.random() < 0.3:
            content = re.sub(r'\bi\b', 'i', content, count=1)
        
        # Add double space occasionally
        if random.random() < 0.2:
            sentences = content.split('. ')
            if len(sentences) > 1:
                idx = random.randint(0, len(sentences)-2)
                sentences[idx] += '.  '  # Double space
                content = ''.join(sentences)
        
        # Ensure at least one casual contraction
        contractions = {
            "do not": "dont",
            "cannot": "cant",
            "you are": "youre",
            "that is": "thats"
        }
        
        for formal, casual in contractions.items():
            if formal in content.lower() and random.random() < 0.5:
                content = re.sub(formal, casual, content, count=1, flags=re.IGNORECASE)
                break
        
        return content
    
    def _check_quality(self, content: str, voice_profile: Dict) -> float:
        """Check content quality and flag AI patterns"""
        
        score = 1.0
        
        # Check for AI red flags
        for phrase in self.AI_RED_FLAGS:
            if phrase.lower() in content.lower():
                score -= 0.2
                logger.warning(f"AI pattern detected: {phrase}")
        
        # Check for em-dashes
        if '—' in content:
            score -= 0.1
        
        # Check sentence length variance (humans vary a lot)
        sentences = [s.strip() for s in re.split(r'[.!?]+', content) if s.strip()]
        if sentences:
            lengths = [len(s.split()) for s in sentences]
            variance = np.var(lengths) if len(lengths) > 1 else 0
            if variance < 10:  # Too uniform
                score -= 0.1
        
        return max(score, 0.0)
    
    def _get_default_voice_profile(self, subreddit: str) -> Dict:
        """Default voice profile if none exists"""
        return {
            "subreddit": subreddit,
            "tone": "casual, supportive, real",
            "grammar_style": "conversational with fragments",
            "avg_sentence_length": 12,
            "formality_level": "LOW",
            "signature_idioms": ["honestly", "literally", "same here"],
            "typo_frequency": 0.02
        }


# Helper function to generate content for opportunity
async def generate_enhanced_content(
    opportunity_id: str,
    client_id: str,
    brand_mention_percentage: float = 0.0
) -> Dict[str, Any]:
    """
    Generate enhanced content for a specific opportunity
    
    Args:
        opportunity_id: UUID of opportunity
        client_id: UUID of client
        brand_mention_percentage: 0-100
        
    Returns:
        Generated content with metadata
    """
    generator = EnhancedContentGenerator()
    supabase = get_supabase_client()
    
    # Fetch opportunity
    opp_response = supabase.table("opportunities").select("*").eq("id", opportunity_id).execute()
    if not opp_response.data:
        raise ValueError(f"Opportunity {opportunity_id} not found")
    
    opportunity = opp_response.data[0]
    
    # Fetch client data
    client_response = supabase.table("clients").select("*").eq("client_id", client_id).execute()
    client_data = client_response.data[0] if client_response.data else {}
    
    # Build thread context
    thread_context = {
        "title": opportunity.get("thread_title"),
        "subreddit": opportunity.get("subreddit"),
        "target_user": opportunity.get("target_user"),
        "body": opportunity.get("thread_body", ""),
        "commercial_intent": opportunity.get("commercial_intent_score", 0),
        "user_context": opportunity.get("user_context", "")
    }
    
    # Generate content
    return await generator.generate_content(
        opportunity_id,
        thread_context,
        client_data,
        brand_mention_percentage
    )
