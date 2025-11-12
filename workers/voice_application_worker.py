"""
Voice Application Worker
Post-processes generated content to match subreddit voice patterns precisely
"""

import os
import logging
import re
from typing import Dict, Optional
from datetime import datetime
from supabase import create_client, Client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


class VoiceApplicationWorker:
    """
    Worker that applies voice profile formatting to generated content
    """
    
    def __init__(self):
        """Initialize the voice application worker"""
        self.supabase = supabase
        logger.info("Voice Application Worker initialized")
    
    def get_voice_profile(self, subreddit_name: str, client_id: str) -> Optional[Dict]:
        """
        Get voice profile for subreddit
        
        Args:
            subreddit_name: Subreddit name
            client_id: Client UUID
            
        Returns:
            Voice profile or None
        """
        try:
            profile = self.supabase.table("subreddit_voice_profiles")\
                .select("*")\
                .eq("subreddit_name", subreddit_name.lower())\
                .eq("client_id", client_id)\
                .execute()
            
            if profile.data:
                return profile.data[0]
            return None
        
        except Exception as e:
            logger.error(f"Error fetching voice profile: {str(e)}")
            return None
    
    def apply_lowercase_style(self, text: str, lowercase_pct: float) -> str:
        """
        Apply lowercase sentence start style based on percentage
        
        Args:
            text: Original text
            lowercase_pct: Percentage of sentences that start lowercase (0-100)
            
        Returns:
            Modified text
        """
        if lowercase_pct < 60:
            return text  # Don't apply if not dominant style
        
        # Split into sentences
        sentences = re.split(r'([.!?]\s+)', text)
        
        result = []
        for i, part in enumerate(sentences):
            # Every other part is a sentence (odd indices are delimiters)
            if i % 2 == 0 and part:
                # Lowercase the first letter if it's a letter
                if part[0].isupper():
                    part = part[0].lower() + part[1:]
            result.append(part)
        
        return ''.join(result)
    
    def adjust_exclamation_usage(self, text: str, exclamation_pct: float) -> str:
        """
        Adjust exclamation mark usage based on community style
        
        Args:
            text: Original text
            exclamation_pct: Percentage of posts with exclamations (0-100)
            
        Returns:
            Modified text
        """
        current_exclamations = text.count('!')
        
        # High exclamation community (>10%)
        if exclamation_pct > 10:
            # If no exclamations, add one or two
            if current_exclamations == 0:
                # Replace last period with exclamation
                text = re.sub(r'\.$', '!', text)
            # If only one, maybe add another for emphasis
            elif current_exclamations == 1 and exclamation_pct > 15:
                text = text.replace('!', '!!')
        
        # Low exclamation community (<5%)
        elif exclamation_pct < 5:
            # Remove excessive exclamations
            if current_exclamations > 1:
                text = text.replace('!!', '!')
                text = text.replace('!!!', '!')
        
        return text
    
    def adjust_formality(self, text: str, formality_score: float) -> str:
        """
        Adjust formality level of text
        
        Args:
            text: Original text
            formality_score: Formality score (0-1, where 0=casual, 1=formal)
            
        Returns:
            Modified text
        """
        # Very casual (< 0.4)
        if formality_score < 0.4:
            # Add casual contractions if not present
            text = text.replace("I am ", "i'm ")
            text = text.replace("I have ", "i've ")
            text = text.replace("You are ", "you're ")
            text = text.replace("That is ", "that's ")
            text = text.replace("It is ", "it's ")
            text = text.replace("cannot ", "can't ")
            text = text.replace("do not ", "don't ")
            
            # Add casual intensifiers
            text = text.replace("very ", "really ")
            text = text.replace("extremely ", "super ")
        
        # Formal (> 0.7)
        elif formality_score > 0.7:
            # Expand contractions
            text = text.replace("i'm ", "I am ")
            text = text.replace("i've ", "I have ")
            text = text.replace("you're ", "you are ")
            text = text.replace("that's ", "that is ")
            text = text.replace("it's ", "it is ")
            text = text.replace("can't ", "cannot ")
            text = text.replace("don't ", "do not ")
        
        return text
    
    def apply_tone(self, text: str, dominant_tone: str) -> str:
        """
        Ensure text matches dominant tone of subreddit
        
        Args:
            text: Original text
            dominant_tone: Dominant tone (supportive, encouraging, etc.)
            
        Returns:
            Modified text
        """
        # Add tone-appropriate phrases if missing
        tone_markers = {
            "supportive": ["you've got this", "hang in there", "you're not alone"],
            "encouraging": ["keep going", "you can do it", "don't give up"],
            "empathetic": ["i understand", "i feel you", "that's tough"],
            "advice-giving": ["here's what worked for me", "i'd suggest", "try"],
            "hopeful": ["things will get better", "stay positive", "good luck"]
        }
        
        # Check if tone is already present
        if dominant_tone.lower() in tone_markers:
            markers = tone_markers[dominant_tone.lower()]
            has_tone = any(marker in text.lower() for marker in markers)
            
            # If missing tone and text is short, might need adjustment
            # (but don't force it - GPT usually handles this)
        
        return text
    
    def apply_voice_profile(self, text: str, voice_profile: Dict) -> Dict:
        """
        Apply complete voice profile to text
        
        Args:
            text: Original generated text
            voice_profile: Voice profile data
            
        Returns:
            Dict with modified text and metrics
        """
        try:
            modified_text = text
            
            # Extract metrics
            lowercase_pct = voice_profile.get("lowercase_start_pct", 0)
            exclamation_pct = voice_profile.get("exclamation_usage_pct", 0)
            formality_score = voice_profile.get("formality_score", 0.5)
            dominant_tone = voice_profile.get("dominant_tone", "supportive")
            
            # Apply transformations in order
            modified_text = self.apply_formality(modified_text, formality_score)
            modified_text = self.adjust_exclamation_usage(modified_text, exclamation_pct)
            modified_text = self.apply_lowercase_style(modified_text, lowercase_pct)
            modified_text = self.apply_tone(modified_text, dominant_tone)
            
            return {
                "success": True,
                "original_text": text,
                "modified_text": modified_text,
                "changes_made": text != modified_text,
                "applied_metrics": {
                    "lowercase_pct": lowercase_pct,
                    "exclamation_pct": exclamation_pct,
                    "formality_score": formality_score,
                    "dominant_tone": dominant_tone
                }
            }
        
        except Exception as e:
            logger.error(f"Error applying voice profile: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "original_text": text,
                "modified_text": text
            }
    
    def process_content(self, content_id: str) -> Dict:
        """
        Process a single content piece to apply voice
        
        Args:
            content_id: Generated content ID
            
        Returns:
            Processing result
        """
        try:
            # Get content
            content = self.supabase.table("generated_content")\
                .select("*")\
                .eq("id", content_id)\
                .execute()
            
            if not content.data:
                return {
                    "success": False,
                    "error": f"Content {content_id} not found"
                }
            
            content_record = content.data[0]
            client_id = content_record.get("client_id")
            subreddit_name = content_record.get("subreddit_name")
            generated_text = content_record.get("generated_text")
            
            # Get voice profile
            voice_profile = self.get_voice_profile(subreddit_name, client_id)
            
            if not voice_profile:
                logger.warning(f"No voice profile for r/{subreddit_name}, skipping voice application")
                return {
                    "success": False,
                    "error": "No voice profile available",
                    "content_id": content_id
                }
            
            # Apply voice
            result = self.apply_voice_profile(generated_text, voice_profile)
            
            if not result["success"]:
                return result
            
            # Update content record if changes were made
            if result["changes_made"]:
                self.supabase.table("generated_content").update({
                    "generated_text": result["modified_text"],
                    "voice_applied": True,
                    "voice_applied_at": datetime.utcnow().isoformat()
                }).eq("id", content_id).execute()
                
                logger.info(f"Applied voice profile to content {content_id[:8]}... (text modified)")
            else:
                # Still mark as processed even if no changes
                self.supabase.table("generated_content").update({
                    "voice_applied": True,
                    "voice_applied_at": datetime.utcnow().isoformat()
                }).eq("id", content_id).execute()
                
                logger.info(f"Voice profile checked for content {content_id[:8]}... (no changes needed)")
            
            return {
                "success": True,
                "content_id": content_id,
                "changes_made": result["changes_made"],
                "original_length": len(result["original_text"]),
                "modified_length": len(result["modified_text"])
            }
        
        except Exception as e:
            logger.error(f"Error processing content: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "content_id": content_id
            }
    
    def process_all_content(self, client_id: Optional[str] = None, reapply: bool = False) -> Dict:
        """
        Process all generated content without voice application
        
        Args:
            client_id: Optional client filter
            reapply: If True, reapply even if already applied
            
        Returns:
            Processing results
        """
        try:
            logger.info("Starting voice application process...")
            
            # Build query
            query = self.supabase.table("generated_content").select("*")
            
            if not reapply:
                query = query.or_("voice_applied.is.null,voice_applied.eq.false")
            
            if client_id:
                query = query.eq("client_id", client_id)
            
            content_records = query.execute()
            
            if not content_records.data:
                logger.info("No content needs voice application")
                return {
                    "success": True,
                    "processed": 0,
                    "message": "No content needs voice application"
                }
            
            logger.info(f"Found {len(content_records.data)} content pieces for voice application")
            
            processed = 0
            modified = 0
            no_changes = 0
            errors = 0
            
            for content in content_records.data:
                try:
                    result = self.process_content(content["id"])
                    
                    if result["success"]:
                        processed += 1
                        if result.get("changes_made"):
                            modified += 1
                        else:
                            no_changes += 1
                    else:
                        errors += 1
                    
                    if processed % 10 == 0:
                        logger.info(f"Processed {processed}/{len(content_records.data)} content pieces")
                
                except Exception as e:
                    logger.error(f"Error processing content {content.get('id')}: {str(e)}")
                    errors += 1
            
            logger.info(f"Voice application complete: {processed} processed, {modified} modified, {no_changes} no changes, {errors} errors")
            
            return {
                "success": True,
                "processed": processed,
                "modified": modified,
                "no_changes": no_changes,
                "errors": errors,
                "total": len(content_records.data)
            }
        
        except Exception as e:
            logger.error(f"Error in voice application process: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }


# Utility functions
def apply_voice_to_all_content(client_id: Optional[str] = None, reapply: bool = False):
    """Apply voice profiles to all content"""
    worker = VoiceApplicationWorker()
    return worker.process_all_content(client_id, reapply)


def apply_voice_to_content(content_id: str):
    """Apply voice profile to specific content"""
    worker = VoiceApplicationWorker()
    return worker.process_content(content_id)


if __name__ == "__main__":
    logger.info("Running Voice Application Worker...")
    result = apply_voice_to_all_content()
    logger.info(f"Results: {result}")
