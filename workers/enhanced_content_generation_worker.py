"""
Enhanced Content Generation Worker

Generates ultra-human Reddit content by:
1. Matching subreddit voice profiles
2. Enriching with vectorized client data (RAG from document_embeddings)
3. Adding real-time web search facts (if SERPAPI_KEY configured)
4. Using GPT-4 Turbo with anti-AI-pattern prompts
5. Respecting brand mention % controls
6. Including realistic typos, idioms, and natural language patterns

This replaces the basic content_generation_worker.py with voice-aware generation.
"""

import os
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import random
import re
import numpy as np
from openai import OpenAI, AsyncOpenAI

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
        """
        Get relevant client knowledge via ACTUAL RAG vector search + web search.

        This is the critical function that feeds SPECIFIC facts into content generation.
        Without this working, content is fluffy/generic.
        """
        enrichment = {
            "relevant_products": [],
            "unique_knowledge": [],
            "scientific_data": [],
            "customer_insights": [],
            "web_search_facts": [],
            "specific_specs": []
        }

        client_id = client_data.get('client_id')
        company_name = client_data.get('company_name', '')

        # Build search query from thread context
        search_text = f"{thread_context.get('title', '')} {thread_context.get('body', '')[:500]}"

        # ========================================
        # STEP 1: RAG Vector Search
        # ========================================
        try:
            rag_results = await self._rag_vector_search(client_id, search_text)

            for chunk in rag_results:
                chunk_text = chunk.get('chunk_text', '')
                metadata = chunk.get('metadata', {})
                category = metadata.get('category', 'general')

                # Route to appropriate enrichment category
                if category == 'product':
                    enrichment["relevant_products"].append({
                        "name": metadata.get('title', 'Product'),
                        "description": chunk_text[:300]
                    })
                elif category == 'spec':
                    enrichment["specific_specs"].append(chunk_text[:200])
                elif category == 'faq':
                    enrichment["unique_knowledge"].append(chunk_text[:200])
                else:
                    enrichment["unique_knowledge"].append(chunk_text[:200])

            logger.info(f"RAG enrichment: Found {len(rag_results)} relevant chunks for {company_name}")

        except Exception as e:
            logger.error(f"RAG vector search failed: {e}")

        # ========================================
        # STEP 2: Web Search Enrichment (if configured)
        # ========================================
        try:
            from services.web_search_service import enrich_with_web_search

            products = client_data.get('products', [])
            if isinstance(products, list) and products:
                product_names = [p.get('name') if isinstance(p, dict) else str(p) for p in products[:3]]
            else:
                product_names = []

            web_results = await enrich_with_web_search(
                topic=thread_context.get('title', ''),
                company_name=company_name,
                products=product_names
            )

            if web_results.get('enabled') and not web_results.get('error'):
                enrichment["web_search_facts"] = web_results.get('topic_facts', [])[:3]

                for detail in web_results.get('product_details', [])[:2]:
                    if detail.get('detail'):
                        enrichment["specific_specs"].append(detail['detail'])

                logger.info(f"Web search enrichment: Found {len(enrichment['web_search_facts'])} facts")

        except Exception as e:
            logger.warning(f"Web search enrichment failed (optional): {e}")

        return enrichment

    async def _rag_vector_search(self, client_id: str, search_text: str, limit: int = 5) -> List[Dict]:
        """
        Perform actual vector similarity search against document_embeddings.
        Uses the match_knowledge_embeddings RPC function.
        """
        try:
            # Generate embedding for search text
            openai_async = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            embedding_response = await openai_async.embeddings.create(
                model="text-embedding-ada-002",
                input=search_text[:8000]
            )
            query_embedding = embedding_response.data[0].embedding

            # Call Supabase RPC for vector similarity search
            response = self.supabase.rpc(
                'match_knowledge_embeddings',
                {
                    'query_embedding': query_embedding,
                    'match_client_id': client_id,
                    'match_threshold': 0.7,
                    'match_count': limit
                }
            ).execute()

            if response.data:
                logger.info(f"RAG search returned {len(response.data)} chunks")
                return response.data
            else:
                logger.warning(f"RAG search returned no results for client {client_id}")
                return []

        except Exception as e:
            logger.error(f"RAG vector search error: {e}")
            return []
    
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
        """Build user prompt with thread context and SPECIFIC facts from RAG + web search"""

        prompt = f"""Thread Title: {thread_context['title']}
Subreddit: r/{thread_context['subreddit']}
Target User: u/{thread_context['target_user']}

Thread Content:
{thread_context.get('body', '[No body text]')}

User's Situation (based on post history):
{thread_context.get('user_context', 'New parent seeking advice')}

"""

        # Add specific specs from RAG (THIS IS KEY FOR NON-FLUFFY CONTENT)
        if enrichment_data.get('specific_specs'):
            prompt += f"""
=== SPECIFIC PRODUCT FACTS (use these exact details) ===
{chr(10).join([f"• {spec}" for spec in enrichment_data['specific_specs'][:5]])}
"""

        # Add products with descriptions from RAG
        if include_brand and enrichment_data.get('relevant_products'):
            prompt += f"""
=== RELEVANT PRODUCTS (mention naturally if appropriate) ===
{chr(10).join([f"• {p['name']}: {p.get('description', '')[:200]}" for p in enrichment_data['relevant_products'][:2]])}
"""

        # Add unique knowledge from RAG
        if enrichment_data.get('unique_knowledge'):
            prompt += f"""
=== EXPERT KNOWLEDGE (use to show expertise) ===
{chr(10).join([f"• {k}" for k in enrichment_data['unique_knowledge'][:3]])}
"""

        # Add web search facts (real-time enrichment)
        if enrichment_data.get('web_search_facts'):
            prompt += f"""
=== CURRENT FACTS FROM WEB (very recent info) ===
{chr(10).join([f"• {fact}" for fact in enrichment_data['web_search_facts'][:3]])}
"""

        prompt += """
=== CONTENT REQUIREMENTS ===
Write a response that:
1. Sounds like a real person who's been through this
2. Is genuinely helpful without being preachy
3. Includes the realistic typos specified
4. Matches the subreddit's voice perfectly
5. Feels like a 2am text to a friend, not a blog post
6. MUST include at least 2 SPECIFIC facts/numbers from above (dimensions, prices, specs, etc.)
7. AVOID generic advice - be SPECIFIC with actual product details

Length: 100-300 words (natural paragraph breaks)

IMPORTANT: Generic fluffy content is NOT acceptable. Include SPECIFIC details like:
- Exact dimensions (e.g., "50 inches wide")
- Specific features (e.g., "60+ flame color options")
- Real numbers (e.g., "5000 BTU heat output")
- Actual model names (e.g., "Sideline Elite 50")
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
