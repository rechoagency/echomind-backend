"""
Content Generation Worker
Generates natural Reddit responses with product mentions based on voice profiles and matchback
"""

import os
import logging
import json
import random
from typing import Dict, List, Optional
from datetime import datetime
from supabase import create_client, Client
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize clients
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)


class ContentGenerationWorker:
    """
    Worker that generates Reddit responses with natural product mentions
    """
    
    def __init__(self):
        """Initialize the content generation worker"""
        self.supabase = supabase
        self.openai = openai_client
        logger.info("Content Generation Worker initialized")
    
    def get_voice_profile(self, subreddit_name: str, client_id: str) -> Optional[Dict]:
        """
        Get voice profile for a subreddit
        
        Args:
            subreddit_name: Name of subreddit
            client_id: Client UUID
            
        Returns:
            Voice profile data or None
        """
        try:
            profile = self.supabase.table("subreddit_voice_profiles")\
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
        product_matches: Optional[Dict]
    ) -> str:
        """
        Build prompt for GPT content generation
        
        Args:
            opportunity: Opportunity data
            voice_profile: Voice profile for subreddit
            product_matches: Product matchback data
            
        Returns:
            System prompt for GPT
        """
        thread_title = opportunity.get("thread_title", "")
        thread_content = opportunity.get("thread_content", "")
        subreddit = opportunity.get("subreddit_name", "")
        
        # Base prompt
        prompt = f"""You are a helpful Reddit community member responding in r/{subreddit}.

**Thread Title:** {thread_title}

**Thread Content:** {thread_content}

**Your Task:** Write a natural, empathetic response that:
1. Shows genuine understanding of their situation
2. Provides helpful advice or shares personal experience
3. Naturally mentions a relevant product IF it genuinely helps

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
        
        # Add product context
        if product_matches:
            matches = product_matches.get("matches", [])
            if matches:
                prompt += "**Relevant Product Information (mention naturally if appropriate):**\n\n"
                for i, match in enumerate(matches[:2], 1):  # Top 2 matches
                    product_info = match.get("product_info", "")
                    relevance = match.get("relevance_score", 0)
                    prompt += f"{i}. {product_info[:300]}... (relevance: {relevance})\n\n"
        
        # Final instructions
        prompt += """**Important Guidelines:**
- BE AUTHENTIC: Sound like a real person sharing experience, not an ad
- BE HELPFUL FIRST: Address their problem genuinely before any product mention
- BE SUBTLE: If mentioning a product, do it naturally ("I've had good results with...", "something that helped me was...")
- BE HONEST: Add disclaimers like "not sponsored" or "just my experience"
- MATCH THE TONE: Use the community's voice style
- BE BRIEF: 2-4 sentences max, Reddit users prefer concise responses
- NO HARD SELLING: Never use sales language or call-to-actions

If the product genuinely doesn't fit, DON'T force it. Just give helpful advice.

Write the response now:"""
        
        return prompt
    
    def generate_content(
        self,
        opportunity: Dict,
        voice_profile: Optional[Dict] = None,
        product_matches: Optional[Dict] = None
    ) -> Dict:
        """
        Generate content for an opportunity
        
        Args:
            opportunity: Opportunity data
            voice_profile: Voice profile for subreddit
            product_matches: Product matchback data
            
        Returns:
            Generated content and metadata
        """
        try:
            # Build prompt
            prompt = self.build_generation_prompt(opportunity, voice_profile, product_matches)
            
            # Generate with GPT
            response = self.openai.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Please write the response now."}
                ],
                temperature=0.8,  # Higher temperature for natural variation
                max_tokens=250
            )
            
            generated_text = response.choices[0].message.content.strip()
            
            # Extract voice metrics from profile
            voice_metrics = {}
            if voice_profile:
                voice_metrics = {
                    "formality_level": voice_profile.get("formality_score"),
                    "lowercase_enforced": voice_profile.get("lowercase_start_pct", 0) > 60,
                    "exclamation_enforced": voice_profile.get("exclamation_usage_pct", 0) > 10,
                    "dominant_tone": voice_profile.get("dominant_tone"),
                    "voice_confidence": voice_profile.get("confidence_score")
                }
            
            # Check if product was mentioned
            has_product_mention = False
            if product_matches and product_matches.get("matches"):
                # Simple check: see if any product keywords appear in generated text
                for match in product_matches["matches"]:
                    product_text = match.get("product_info", "").lower()
                    # Extract potential product names (first 5 words)
                    product_keywords = product_text.split()[:5]
                    if any(keyword in generated_text.lower() for keyword in product_keywords if len(keyword) > 3):
                        has_product_mention = True
                        break
            
            return {
                "success": True,
                "generated_text": generated_text,
                "has_product_mention": has_product_mention,
                "voice_metrics": voice_metrics,
                "generation_model": "gpt-4",
                "generated_at": datetime.utcnow().isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error generating content: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def process_opportunity(self, opportunity: Dict) -> Dict:
        """
        Process a single opportunity to generate content
        
        Args:
            opportunity: Opportunity data
            
        Returns:
            Processing result
        """
        try:
            opportunity_id = opportunity.get("id")
            client_id = opportunity.get("client_id")
            subreddit_name = opportunity.get("subreddit_name", "")
            
            logger.info(f"Generating content for opportunity {opportunity_id[:8]}...")
            
            # Get voice profile
            voice_profile = self.get_voice_profile(subreddit_name, client_id)
            
            # Parse product matches if they exist
            product_matches = None
            if opportunity.get("product_matches"):
                try:
                    product_matches = json.loads(opportunity["product_matches"])
                except:
                    logger.warning(f"Could not parse product_matches for opportunity {opportunity_id}")
            
            # Generate content
            result = self.generate_content(opportunity, voice_profile, product_matches)
            
            if not result["success"]:
                logger.error(f"Failed to generate content for {opportunity_id}: {result.get('error')}")
                return result
            
            # Store generated content
            content_record = {
                "opportunity_id": opportunity_id,
                "client_id": client_id,
                "subreddit_name": subreddit_name,
                "generated_text": result["generated_text"],
                "generation_model": result["generation_model"],
                "has_product_mention": result["has_product_mention"],
                "formality_level": result["voice_metrics"].get("formality_level"),
                "lowercase_enforced": result["voice_metrics"].get("lowercase_enforced"),
                "exclamation_enforced": result["voice_metrics"].get("exclamation_enforced"),
                "dominant_tone": result["voice_metrics"].get("dominant_tone"),
                "voice_confidence": result["voice_metrics"].get("voice_confidence"),
                "generated_at": result["generated_at"],
                "status": "pending_review"
            }
            
            # Check if content already exists
            existing = self.supabase.table("generated_content")\
                .select("id")\
                .eq("opportunity_id", opportunity_id)\
                .execute()
            
            if existing.data:
                # Update existing
                self.supabase.table("generated_content")\
                    .update(content_record)\
                    .eq("opportunity_id", opportunity_id)\
                    .execute()
                logger.info(f"Updated existing content for opportunity {opportunity_id[:8]}...")
            else:
                # Insert new
                self.supabase.table("generated_content")\
                    .insert(content_record)\
                    .execute()
                logger.info(f"Created new content for opportunity {opportunity_id[:8]}...")
            
            return {
                "success": True,
                "opportunity_id": opportunity_id,
                "has_product_mention": result["has_product_mention"],
                "content_length": len(result["generated_text"])
            }
        
        except Exception as e:
            logger.error(f"Error processing opportunity for content generation: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "opportunity_id": opportunity.get("id")
            }
    
    def process_all_opportunities(
        self,
        client_id: Optional[str] = None,
        regenerate: bool = False,
        only_with_products: bool = True
    ) -> Dict:
        """
        Generate content for all opportunities
        
        Args:
            client_id: Optional client ID filter
            regenerate: If True, regenerate even if content exists
            only_with_products: Only generate for opportunities with product matches
            
        Returns:
            Processing results
        """
        try:
            logger.info("Starting content generation process...")
            
            # Build query
            query = self.supabase.table("opportunities").select("*")
            
            if client_id:
                query = query.eq("client_id", client_id)
            
            if only_with_products:
                query = query.not_.is_("product_matches", "null")
            
            opportunities = query.execute()
            
            if not opportunities.data:
                logger.info("No opportunities to generate content for")
                return {
                    "success": True,
                    "processed": 0,
                    "message": "No opportunities need content generation"
                }
            
            logger.info(f"Found {len(opportunities.data)} opportunities for content generation")
            
            # If not regenerating, filter out those with existing content
            if not regenerate:
                to_process = []
                for opp in opportunities.data:
                    existing = self.supabase.table("generated_content")\
                        .select("id")\
                        .eq("opportunity_id", opp["id"])\
                        .execute()
                    if not existing.data:
                        to_process.append(opp)
                opportunities.data = to_process
                logger.info(f"Filtered to {len(opportunities.data)} without existing content")
            
            if not opportunities.data:
                return {
                    "success": True,
                    "processed": 0,
                    "message": "All opportunities already have content"
                }
            
            processed = 0
            with_products = 0
            without_products = 0
            errors = 0
            
            for opp in opportunities.data:
                try:
                    result = self.process_opportunity(opp)
                    
                    if result["success"]:
                        processed += 1
                        if result.get("has_product_mention"):
                            with_products += 1
                        else:
                            without_products += 1
                    else:
                        errors += 1
                    
                    if processed % 5 == 0:
                        logger.info(f"Processed {processed}/{len(opportunities.data)} opportunities")
                
                except Exception as e:
                    logger.error(f"Error processing opportunity {opp.get('id')}: {str(e)}")
                    errors += 1
            
            logger.info(f"Content generation complete: {processed} processed, {with_products} with product mentions, {without_products} without, {errors} errors")
            
            return {
                "success": True,
                "processed": processed,
                "with_product_mentions": with_products,
                "without_product_mentions": without_products,
                "errors": errors,
                "total": len(opportunities.data)
            }
        
        except Exception as e:
            logger.error(f"Error in content generation process: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def regenerate_content(self, opportunity_id: str) -> Dict:
        """
        Regenerate content for a specific opportunity
        
        Args:
            opportunity_id: Opportunity ID
            
        Returns:
            Processing result
        """
        try:
            opp = self.supabase.table("opportunities")\
                .select("*")\
                .eq("id", opportunity_id)\
                .execute()
            
            if not opp.data:
                return {
                    "success": False,
                    "error": f"Opportunity {opportunity_id} not found"
                }
            
            return self.process_opportunity(opp.data[0])
        
        except Exception as e:
            logger.error(f"Error regenerating content: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }


# Utility functions
def generate_all_content(client_id: Optional[str] = None, regenerate: bool = False, only_with_products: bool = True):
    """Generate content for all opportunities"""
    worker = ContentGenerationWorker()
    return worker.process_all_opportunities(client_id, regenerate, only_with_products)


def regenerate_content_by_id(opportunity_id: str):
    """Regenerate content for specific opportunity"""
    worker = ContentGenerationWorker()
    return worker.regenerate_content(opportunity_id)


if __name__ == "__main__":
    logger.info("Running Content Generation Worker...")
    result = generate_all_content()
    logger.info(f"Results: {result}")
