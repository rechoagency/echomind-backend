"""
Opportunity Scoring Worker
Analyzes discovered opportunities for commercial intent and assigns scores
"""

import os
import logging
import re
from typing import Dict, List, Optional
from datetime import datetime
from supabase import create_client, Client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


class OpportunityScoringWorker:
    """
    Worker that analyzes opportunities for commercial intent
    """
    
    # Buying intent keywords (weighted by strength)
    BUYING_SIGNALS = {
        "high": ["buy", "purchase", "order", "looking for", "need to buy", "where to buy", 
                 "best place", "recommend", "worth it", "price", "cost", "budget", "afford"],
        "medium": ["help", "advice", "suggest", "opinion", "experience", "tried", "used",
                   "anyone know", "suggestions", "tips", "how to"],
        "low": ["thinking about", "considering", "maybe", "eventually", "someday"]
    }
    
    # Pain point indicators
    PAIN_POINTS = [
        "struggling", "problem", "issue", "frustrat", "annoying", "difficult", 
        "terrible", "awful", "hate", "can't stand", "tired of", "fed up",
        "doesn't work", "failed", "disappointing", "worst", "horrible"
    ]
    
    # Question indicators (questions = high intent)
    QUESTION_PATTERNS = [
        r"\?",  # Contains question mark
        r"^(what|where|when|why|how|which|who|can|should|would|could|does|is|are)",  # Question starters
        r"(help|advice|recommend|suggest)"  # Implicit questions
    ]
    
    def __init__(self):
        """Initialize the scoring worker"""
        self.supabase = supabase
        logger.info("Opportunity Scoring Worker initialized")
    
    def score_opportunity(self, opportunity: Dict) -> Dict:
        """
        Score a single opportunity for commercial intent
        
        Args:
            opportunity: Dictionary containing opportunity data
            
        Returns:
            Dictionary with scores and analysis
        """
        thread_title = opportunity.get("thread_title", "")
        # Use original_post_text (not thread_content) to match schema
        thread_content = opportunity.get("original_post_text") or opportunity.get("thread_content", "")
        comment_count = opportunity.get("comment_count", 0)
        
        # Combine title and content for analysis
        full_text = f"{thread_title} {thread_content}".lower()
        
        # Calculate component scores
        buying_intent_score = self._calculate_buying_intent(full_text)
        pain_point_score = self._calculate_pain_point_score(full_text)
        question_score = self._calculate_question_score(full_text)
        engagement_score = self._calculate_engagement_score(comment_count)
        urgency_score = self._calculate_urgency_score(full_text)
        
        # Calculate weighted opportunity score
        opportunity_score = (
            buying_intent_score * 0.35 +
            pain_point_score * 0.25 +
            question_score * 0.20 +
            engagement_score * 0.10 +
            urgency_score * 0.10
        )
        
        # Determine priority tier
        if opportunity_score >= 90:
            priority = "URGENT"
        elif opportunity_score >= 75:
            priority = "HIGH"
        elif opportunity_score >= 60:
            priority = "MEDIUM"
        else:
            priority = "LOW"
        
        return {
            "opportunity_score": round(opportunity_score, 2),
            "priority": priority,
            "buying_intent_score": round(buying_intent_score, 2),
            "pain_point_score": round(pain_point_score, 2),
            "question_score": round(question_score, 2),
            "engagement_score": round(engagement_score, 2),
            "urgency_score": round(urgency_score, 2),
            "analysis_timestamp": datetime.utcnow().isoformat()
        }
    
    def _calculate_buying_intent(self, text: str) -> float:
        """
        Calculate buying intent score based on keywords
        
        Args:
            text: Text to analyze
            
        Returns:
            Score from 0-100
        """
        score = 0
        matches = []
        
        # Check high-intent keywords (worth 10 points each, max 50)
        for keyword in self.BUYING_SIGNALS["high"]:
            if keyword in text:
                score += 10
                matches.append(keyword)
        
        # Check medium-intent keywords (worth 5 points each, max 30)
        for keyword in self.BUYING_SIGNALS["medium"]:
            if keyword in text:
                score += 5
                matches.append(keyword)
        
        # Check low-intent keywords (worth 2 points each, max 10)
        for keyword in self.BUYING_SIGNALS["low"]:
            if keyword in text:
                score += 2
                matches.append(keyword)
        
        # Cap at 100
        final_score = min(score, 100)
        
        if matches:
            logger.debug(f"Buying intent matches: {matches[:5]} | Score: {final_score}")
        
        return final_score
    
    def _calculate_pain_point_score(self, text: str) -> float:
        """
        Calculate pain point intensity score
        
        Args:
            text: Text to analyze
            
        Returns:
            Score from 0-100
        """
        score = 0
        matches = []
        
        for pain_word in self.PAIN_POINTS:
            if pain_word in text:
                score += 8
                matches.append(pain_word)
        
        # Bonus for multiple pain points (desperation signal)
        if len(matches) > 3:
            score += 20
        
        # Cap at 100
        final_score = min(score, 100)
        
        if matches:
            logger.debug(f"Pain point matches: {matches[:5]} | Score: {final_score}")
        
        return final_score
    
    def _calculate_question_score(self, text: str) -> float:
        """
        Calculate question score (questions = seeking advice = high intent)
        
        Args:
            text: Text to analyze
            
        Returns:
            Score from 0-100
        """
        score = 0
        
        # Check for question patterns
        for pattern in self.QUESTION_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                score += 30
        
        # Bonus for multiple questions
        question_marks = text.count("?")
        if question_marks > 1:
            score += 20
        
        # Cap at 100
        return min(score, 100)
    
    def _calculate_engagement_score(self, comment_count: int) -> float:
        """
        Calculate engagement score based on comment count
        
        Args:
            comment_count: Number of comments on thread
            
        Returns:
            Score from 0-100
        """
        # Logarithmic scale - high engagement = community validation
        if comment_count == 0:
            return 0
        elif comment_count < 5:
            return 30
        elif comment_count < 15:
            return 50
        elif comment_count < 30:
            return 70
        elif comment_count < 50:
            return 85
        else:
            return 100
    
    def _calculate_urgency_score(self, text: str) -> float:
        """
        Calculate urgency score
        
        Args:
            text: Text to analyze
            
        Returns:
            Score from 0-100
        """
        urgency_words = [
            "urgent", "asap", "immediately", "now", "today", "soon",
            "emergency", "desperate", "quickly", "fast", "right now"
        ]
        
        score = 0
        for word in urgency_words:
            if word in text:
                score += 25
        
        # Bonus for exclamation marks (emotion = urgency)
        exclamations = text.count("!")
        score += min(exclamations * 10, 30)
        
        return min(score, 100)
    
    def process_all_opportunities(self, client_id: Optional[str] = None) -> Dict:
        """
        Process all opportunities without scores
        
        Args:
            client_id: Optional client ID to filter by
            
        Returns:
            Dictionary with processing results
        """
        try:
            logger.info("Starting opportunity scoring process...")
            
            # Get opportunities without scores
            query = self.supabase.table("opportunities")\
                .select("*")\
                .is_("opportunity_score", "null")
            
            if client_id:
                query = query.eq("client_id", client_id)
            
            opportunities = query.execute()
            
            if not opportunities.data:
                logger.info("No opportunities to score")
                return {
                    "success": True,
                    "processed": 0,
                    "message": "No opportunities need scoring"
                }
            
            logger.info(f"Found {len(opportunities.data)} opportunities to score")
            
            processed = 0
            errors = 0
            
            for opp in opportunities.data:
                try:
                    # Calculate scores
                    scores = self.score_opportunity(opp)

                    # Get opportunity ID (handle both column names)
                    opp_id = opp.get("opportunity_id") or opp.get("id")

                    # Update database with scores
                    update_data = {
                        "opportunity_score": scores['opportunity_score'],
                        "priority_tier": scores['priority'],
                        "updated_at": datetime.utcnow().isoformat()
                    }

                    # Use opportunity_id if available, otherwise id
                    if opp.get("opportunity_id"):
                        self.supabase.table("opportunities").update(update_data).eq("opportunity_id", opp_id).execute()
                    else:
                        self.supabase.table("opportunities").update(update_data).eq("id", opp_id).execute()

                    processed += 1

                    if processed % 100 == 0:
                        logger.info(f"Processed {processed}/{len(opportunities.data)} opportunities")

                except Exception as e:
                    logger.error(f"Error scoring opportunity {opp.get('id')}: {str(e)}")
                    errors += 1

            logger.info(f"Scoring complete: {processed} processed, {errors} errors")
            
            return {
                "success": True,
                "processed": processed,
                "errors": errors,
                "total": len(opportunities.data)
            }
        
        except Exception as e:
            logger.error(f"Error in opportunity scoring process: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def rescore_opportunity(self, opportunity_id: str) -> Dict:
        """
        Rescore a specific opportunity
        
        Args:
            opportunity_id: ID of opportunity to rescore
            
        Returns:
            Dictionary with results
        """
        try:
            # Get opportunity
            opp = self.supabase.table("opportunities")\
                .select("*")\
                .eq("id", opportunity_id)\
                .execute()
            
            if not opp.data:
                return {
                    "success": False,
                    "error": f"Opportunity {opportunity_id} not found"
                }
            
            # Calculate scores
            scores = self.score_opportunity(opp.data[0])

            # Update database with scores
            update_data = {
                "opportunity_score": scores['opportunity_score'],
                "priority_tier": scores['priority'],
                "updated_at": datetime.utcnow().isoformat()
            }
            self.supabase.table("opportunities").update(update_data).eq("id", opportunity_id).execute()

            logger.info(f"Rescored opportunity {opportunity_id}: {scores['opportunity_score']} ({scores['priority']})")

            return {
                "success": True,
                "opportunity_id": opportunity_id,
                "scores": scores
            }

        except Exception as e:
            logger.error(f"Error rescoring opportunity: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }


# Utility functions for direct execution
def score_all_opportunities(client_id: Optional[str] = None):
    """
    Score all opportunities (can be called from scheduler)
    """
    worker = OpportunityScoringWorker()
    return worker.process_all_opportunities(client_id)


def score_opportunity_by_id(opportunity_id: str):
    """
    Score a specific opportunity
    """
    worker = OpportunityScoringWorker()
    return worker.rescore_opportunity(opportunity_id)


if __name__ == "__main__":
    # Test execution
    logger.info("Running Opportunity Scoring Worker...")
    result = score_all_opportunities()
    logger.info(f"Results: {result}")
