"""
Opportunity Scoring Worker
Analyzes discovered opportunities with THREE separate scores:
1. relevance_score - Brand relevance (keyword/embedding match)
2. commercial_intent_score - Buying/decision intent
3. engagement_score - Thread activity potential

Plus configurable weighted composite_score.
"""

import os
import logging
import re
from typing import Dict, List, Optional, Tuple
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
    Worker that analyzes opportunities with THREE separate scores.
    Scores are stored individually for transparency and configurable weighting.
    """

    # Default scoring weights (can be overridden per brand)
    DEFAULT_WEIGHTS = {
        'relevance': 0.35,
        'commercial_intent': 0.40,
        'engagement': 0.25
    }

    # High commercial intent phrases (user is ready to buy/decide)
    HIGH_INTENT_PHRASES = [
        "looking to buy", "want to purchase", "ready to buy",
        "what should i get", "what should i buy", "which should i get",
        "best for", "recommend", "recommendation", "suggestions",
        "help me choose", "help me decide", "narrowed down to",
        "worth it", "should i get", "thinking of buying",
        "where to buy", "need to buy", "planning to buy"
    ]

    # Medium intent phrases (research/comparison phase)
    MEDIUM_INTENT_PHRASES = [
        "vs", "versus", "compared to", "or should i",
        "anyone tried", "anyone use", "experience with",
        "thoughts on", "opinions on", "reviews",
        "how does", "what do you think", "is it good"
    ]

    # Low/no intent phrases (already bought, showing off)
    LOW_INTENT_PHRASES = [
        "just bought", "i got", "picked up", "finally got",
        "showing off", "my setup", "my collection",
        "just installed", "here's my", "check out my"
    ]

    # Pain point indicators (problem = opportunity)
    PAIN_POINTS = [
        "struggling", "problem", "issue", "frustrat", "annoying", "difficult",
        "terrible", "awful", "hate", "can't stand", "tired of", "fed up",
        "doesn't work", "failed", "disappointing", "worst", "horrible",
        "broken", "stopped working", "gave up", "nightmare"
    ]

    # Urgency indicators
    URGENCY_WORDS = [
        "urgent", "asap", "immediately", "now", "today", "soon",
        "emergency", "desperate", "quickly", "fast", "right now",
        "need help", "please help", "anyone available"
    ]

    def __init__(self):
        """Initialize the scoring worker"""
        self.supabase = supabase
        logger.info("Opportunity Scoring Worker initialized (THREE-SCORE SYSTEM)")

    def calculate_relevance_score(
        self,
        opportunity: Dict,
        brand_config: Optional[Dict] = None
    ) -> Tuple[float, Dict]:
        """
        Calculate brand relevance score (0-100)

        Factors:
        - Keyword matches (product names, categories, brand terms)
        - Topic alignment with brand's expertise
        - Subreddit match (is this a target subreddit?)

        Future: Add embedding similarity for semantic matching

        Returns:
            tuple of (score, debug_info)
        """
        debug = {
            'keywords_matched': [],
            'topic_alignment': 0,
            'subreddit_bonus': 0
        }
        score = 0

        thread_title = opportunity.get("thread_title", "")
        thread_content = opportunity.get("original_post_text") or opportunity.get("thread_content", "")
        full_text = f"{thread_title} {thread_content}".lower()
        subreddit = opportunity.get("subreddit", "").lower()

        # Get brand keywords from config or client data
        brand_keywords = []
        target_subreddits = []

        if brand_config:
            brand_keywords = brand_config.get('target_keywords', []) or []
            target_subreddits = [s.lower() for s in (brand_config.get('target_subreddits', []) or [])]
            # Add product names, categories, etc.
            brand_keywords.extend(brand_config.get('product_keywords', []) or [])
            brand_keywords.extend(brand_config.get('industry_keywords', []) or [])

        # Keyword matching (each match = 15 points, max 60)
        for keyword in brand_keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in full_text:
                score += 15
                debug['keywords_matched'].append(keyword)
                if len(debug['keywords_matched']) >= 4:
                    break

        # Cap keyword score at 60
        score = min(score, 60)
        debug['keyword_score'] = score

        # Subreddit match bonus (25 points if in target subreddit)
        if subreddit in target_subreddits:
            score += 25
            debug['subreddit_bonus'] = 25

        # Topic alignment (basic - check for industry-related terms)
        # This is a simplified version - could be enhanced with embeddings
        industry_terms = {
            'home_improvement': ['install', 'diy', 'project', 'renovation', 'remodel', 'fix', 'repair'],
            'fireplace': ['fireplace', 'heating', 'warm', 'flames', 'mantel', 'insert', 'electric'],
            'furniture': ['mount', 'stand', 'lift', 'cabinet', 'entertainment', 'media'],
            'general': ['help', 'advice', 'recommend', 'suggest', 'looking for']
        }

        topic_score = 0
        for category, terms in industry_terms.items():
            matches = sum(1 for term in terms if term in full_text)
            if matches >= 2:
                topic_score = max(topic_score, 15)

        score += topic_score
        debug['topic_alignment'] = topic_score

        final_score = min(score, 100)
        debug['final_relevance_score'] = final_score

        return (final_score, debug)

    def calculate_commercial_intent_score(self, opportunity: Dict) -> Tuple[float, Dict]:
        """
        Calculate buying/commercial intent score (0-100)

        Factors:
        - Buying phrases: "looking to buy", "what should I get", "best X for Y"
        - Comparison language: "X vs Y", "which is better", "recommendations"
        - Decision stage: "help me decide", "narrowed down to", "ready to purchase"
        - Question indicators: asking for advice vs sharing experience
        - Pain points: problems that products can solve

        Returns:
            tuple of (score, debug_info)
        """
        debug = {
            'high_intent_matches': [],
            'medium_intent_matches': [],
            'low_intent_matches': [],
            'pain_points': [],
            'question_bonus': 0,
            'urgency_bonus': 0
        }
        score = 0

        thread_title = opportunity.get("thread_title", "")
        thread_content = opportunity.get("original_post_text") or opportunity.get("thread_content", "")
        full_text = f"{thread_title} {thread_content}".lower()

        # High intent phrases (+20 each, max 60)
        for phrase in self.HIGH_INTENT_PHRASES:
            if phrase in full_text:
                score += 20
                debug['high_intent_matches'].append(phrase)
                if len(debug['high_intent_matches']) >= 3:
                    break

        high_intent_score = min(score, 60)
        score = high_intent_score

        # Medium intent phrases (+10 each, max 30)
        medium_score = 0
        for phrase in self.MEDIUM_INTENT_PHRASES:
            if phrase in full_text:
                medium_score += 10
                debug['medium_intent_matches'].append(phrase)
                if len(debug['medium_intent_matches']) >= 3:
                    break

        score += min(medium_score, 30)

        # Low/no intent phrases (DEDUCT points)
        for phrase in self.LOW_INTENT_PHRASES:
            if phrase in full_text:
                score -= 25
                debug['low_intent_matches'].append(phrase)

        # Pain point bonus (+8 each, max 24)
        pain_score = 0
        for pain in self.PAIN_POINTS:
            if pain in full_text:
                pain_score += 8
                debug['pain_points'].append(pain)
                if len(debug['pain_points']) >= 3:
                    break

        score += min(pain_score, 24)

        # Question bonus (questions = seeking advice)
        question_marks = full_text.count("?")
        if question_marks >= 1:
            score += 10
            debug['question_bonus'] = 10
        if question_marks >= 3:
            score += 10
            debug['question_bonus'] = 20

        # Urgency bonus
        for word in self.URGENCY_WORDS:
            if word in full_text:
                score += 10
                debug['urgency_bonus'] += 10
                if debug['urgency_bonus'] >= 20:
                    break

        final_score = max(0, min(score, 100))
        debug['final_commercial_intent_score'] = final_score

        return (final_score, debug)

    def calculate_engagement_score(self, opportunity: Dict) -> Tuple[float, Dict]:
        """
        Calculate engagement potential score (0-100)

        Factors:
        - Comment count and activity
        - Upvote count/score
        - Thread age (prefer 2-48 hours - not too old, not too new)
        - Author karma (if available)

        Returns:
            tuple of (score, debug_info)
        """
        debug = {
            'comment_score': 0,
            'upvote_score': 0,
            'age_score': 0,
            'activity_indicator': 'unknown'
        }
        score = 0

        # Comment count scoring (0-40 points)
        num_comments = opportunity.get('comment_count') or opportunity.get('num_comments', 0)
        if num_comments >= 50:
            comment_score = 40
            debug['activity_indicator'] = 'high'
        elif num_comments >= 20:
            comment_score = 30
            debug['activity_indicator'] = 'medium-high'
        elif num_comments >= 10:
            comment_score = 20
            debug['activity_indicator'] = 'medium'
        elif num_comments >= 5:
            comment_score = 15
            debug['activity_indicator'] = 'low-medium'
        elif num_comments >= 1:
            comment_score = 10
            debug['activity_indicator'] = 'low'
        else:
            comment_score = 5  # New threads still have potential
            debug['activity_indicator'] = 'new'

        score += comment_score
        debug['comment_score'] = comment_score
        debug['num_comments'] = num_comments

        # Upvote scoring (0-35 points)
        upvotes = opportunity.get('score', 0) or opportunity.get('upvotes', 0) or opportunity.get('thread_score', 0)
        if upvotes >= 100:
            upvote_score = 35
        elif upvotes >= 50:
            upvote_score = 25
        elif upvotes >= 20:
            upvote_score = 15
        elif upvotes >= 5:
            upvote_score = 10
        else:
            upvote_score = 5

        score += upvote_score
        debug['upvote_score'] = upvote_score
        debug['upvotes'] = upvotes

        # Thread age scoring (0-25 points)
        # Prefer threads 2-48 hours old (active but not stale)
        date_found = opportunity.get('date_found') or opportunity.get('created_at')
        thread_created = opportunity.get('thread_created_utc')

        age_score = 15  # Default middle value
        if thread_created:
            try:
                if isinstance(thread_created, str):
                    created_dt = datetime.fromisoformat(thread_created.replace('Z', '+00:00'))
                else:
                    created_dt = datetime.fromtimestamp(thread_created)

                age_hours = (datetime.utcnow() - created_dt.replace(tzinfo=None)).total_seconds() / 3600

                if 2 <= age_hours <= 12:
                    age_score = 25  # Sweet spot - fresh and active
                elif 12 < age_hours <= 48:
                    age_score = 20  # Still good
                elif 48 < age_hours <= 168:  # 2-7 days
                    age_score = 10  # Older but might still be active
                else:
                    age_score = 5  # Old thread

                debug['thread_age_hours'] = round(age_hours, 1)
            except Exception:
                pass

        score += age_score
        debug['age_score'] = age_score

        final_score = min(score, 100)
        debug['final_engagement_score'] = final_score

        return (final_score, debug)

    def calculate_composite_score(
        self,
        relevance: float,
        commercial_intent: float,
        engagement: float,
        weights: Optional[Dict] = None
    ) -> float:
        """
        Calculate weighted composite score from the three component scores.

        Default weights (can be customized per brand):
        - relevance: 35%
        - commercial_intent: 40%
        - engagement: 25%

        Returns:
            Composite score (0-100)
        """
        if weights is None:
            weights = self.DEFAULT_WEIGHTS

        composite = (
            relevance * weights.get('relevance', 0.35) +
            commercial_intent * weights.get('commercial_intent', 0.40) +
            engagement * weights.get('engagement', 0.25)
        )

        return min(round(composite, 2), 100)

    def determine_priority(self, composite_score: float) -> str:
        """Determine priority tier from composite score"""
        if composite_score >= 85:
            return "URGENT"
        elif composite_score >= 70:
            return "HIGH"
        elif composite_score >= 50:
            return "MEDIUM"
        else:
            return "LOW"

    def score_opportunity(self, opportunity: Dict, brand_config: Optional[Dict] = None) -> Dict:
        """
        Score a single opportunity with ALL THREE scores.

        Args:
            opportunity: Dictionary containing opportunity data
            brand_config: Optional brand configuration for relevance scoring

        Returns:
            Dictionary with all scores, debug info, and priority
        """
        # Calculate all three scores
        relevance, relevance_debug = self.calculate_relevance_score(opportunity, brand_config)
        commercial_intent, intent_debug = self.calculate_commercial_intent_score(opportunity)
        engagement, engagement_debug = self.calculate_engagement_score(opportunity)

        # Calculate composite
        composite = self.calculate_composite_score(relevance, commercial_intent, engagement)
        priority = self.determine_priority(composite)

        # Compile debug info
        scoring_debug = {
            'relevance': relevance_debug,
            'commercial_intent': intent_debug,
            'engagement': engagement_debug,
            'weights_used': self.DEFAULT_WEIGHTS,
            'scored_at': datetime.utcnow().isoformat()
        }

        return {
            # Individual scores
            "relevance_score": relevance,
            "commercial_intent_score": commercial_intent,
            "engagement_score": engagement,

            # Composite and priority
            "composite_score": composite,
            "opportunity_score": composite,  # Backward compatibility
            "priority": priority,
            "priority_tier": priority,

            # Debug info
            "scoring_debug": scoring_debug,
            "analysis_timestamp": datetime.utcnow().isoformat()
        }

    def get_brand_config(self, client_id: str) -> Optional[Dict]:
        """Get brand configuration for relevance scoring"""
        try:
            # Get from clients table
            client = self.supabase.table("clients")\
                .select("target_keywords, target_subreddits, company_name, industry")\
                .eq("client_id", client_id)\
                .execute()

            if client.data:
                client_data = client.data[0]

                # Also get keywords from client_keyword_config
                keywords = []
                try:
                    keyword_config = self.supabase.table("client_keyword_config")\
                        .select("keyword")\
                        .eq("client_id", client_id)\
                        .eq("is_active", True)\
                        .execute()
                    if keyword_config.data:
                        keywords = [k['keyword'] for k in keyword_config.data]
                except Exception:
                    pass

                # Get subreddits from client_subreddit_config
                subreddits = []
                try:
                    sub_config = self.supabase.table("client_subreddit_config")\
                        .select("subreddit_name")\
                        .eq("client_id", client_id)\
                        .eq("is_active", True)\
                        .execute()
                    if sub_config.data:
                        subreddits = [s['subreddit_name'] for s in sub_config.data]
                except Exception:
                    pass

                return {
                    'company_name': client_data.get('company_name'),
                    'industry': client_data.get('industry'),
                    'target_keywords': keywords or client_data.get('target_keywords', []),
                    'target_subreddits': subreddits or client_data.get('target_subreddits', [])
                }

            return None

        except Exception as e:
            logger.error(f"Error getting brand config: {e}")
            return None

    def process_all_opportunities(self, client_id: Optional[str] = None, batch_size: int = 500) -> Dict:
        """
        Process opportunities without scores (with batch limits to prevent timeouts)

        Args:
            client_id: Optional client ID to filter by
            batch_size: Maximum opportunities to process per run (default 500)

        Returns:
            Dictionary with processing results
        """
        try:
            logger.info(f"Starting THREE-SCORE opportunity scoring (batch_size={batch_size})...")

            # Get brand config if client specified
            brand_config = None
            if client_id:
                brand_config = self.get_brand_config(client_id)
                if brand_config:
                    logger.info(f"Loaded brand config for {brand_config.get('company_name')}")

            # Get opportunities without composite scores - prioritize recent
            query = self.supabase.table("opportunities")\
                .select("*")\
                .is_("composite_score", "null")\
                .order("created_at", desc=True)\
                .limit(batch_size)

            if client_id:
                query = query.eq("client_id", client_id)

            opportunities = query.execute()

            if not opportunities.data:
                # Try falling back to opportunity_score being null (backward compat)
                query = self.supabase.table("opportunities")\
                    .select("*")\
                    .is_("opportunity_score", "null")\
                    .order("created_at", desc=True)\
                    .limit(batch_size)

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
                    # Get brand config for this opportunity's client if not already loaded
                    opp_client_id = opp.get("client_id")
                    if opp_client_id and opp_client_id != client_id:
                        brand_config = self.get_brand_config(opp_client_id)

                    # Calculate all scores
                    scores = self.score_opportunity(opp, brand_config)

                    # Get opportunity ID (handle both column names)
                    opp_id = opp.get("opportunity_id") or opp.get("id")

                    # Update database with ALL scores
                    update_data = {
                        "relevance_score": scores['relevance_score'],
                        "commercial_intent_score": scores['commercial_intent_score'],
                        "engagement_score": scores['engagement_score'],
                        "composite_score": scores['composite_score'],
                        "opportunity_score": scores['opportunity_score'],  # Backward compat
                        "priority_tier": scores['priority_tier'],
                        "scoring_debug": scores['scoring_debug'],
                        "updated_at": datetime.utcnow().isoformat()
                    }

                    # Use opportunity_id if available, otherwise id
                    if opp.get("opportunity_id"):
                        self.supabase.table("opportunities").update(update_data)\
                            .eq("opportunity_id", opp_id).execute()
                    else:
                        self.supabase.table("opportunities").update(update_data)\
                            .eq("id", opp_id).execute()

                    processed += 1

                    if processed % 50 == 0:
                        logger.info(f"Processed {processed}/{len(opportunities.data)} opportunities")

                except Exception as e:
                    logger.error(f"Error scoring opportunity {opp.get('id')}: {str(e)}")
                    errors += 1

            logger.info(f"Scoring complete: {processed} processed, {errors} errors")

            # Check if there's more to process
            more_to_process = len(opportunities.data) >= batch_size

            return {
                "success": True,
                "processed": processed,
                "errors": errors,
                "batch_size": batch_size,
                "total_in_batch": len(opportunities.data),
                "more_to_process": more_to_process,
                "scoring_type": "THREE_SCORE_SYSTEM",
                "message": f"Processed {processed} opportunities with relevance/intent/engagement scores"
            }

        except Exception as e:
            logger.error(f"Error in opportunity scoring process: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def rescore_opportunity(self, opportunity_id: str) -> Dict:
        """
        Rescore a specific opportunity with all three scores

        Args:
            opportunity_id: ID of opportunity to rescore

        Returns:
            Dictionary with results
        """
        try:
            # Get opportunity
            opp = self.supabase.table("opportunities")\
                .select("*")\
                .eq("opportunity_id", opportunity_id)\
                .execute()

            if not opp.data:
                # Try 'id' column
                opp = self.supabase.table("opportunities")\
                    .select("*")\
                    .eq("id", opportunity_id)\
                    .execute()

            if not opp.data:
                return {
                    "success": False,
                    "error": f"Opportunity {opportunity_id} not found"
                }

            opportunity = opp.data[0]
            client_id = opportunity.get("client_id")
            brand_config = self.get_brand_config(client_id) if client_id else None

            # Calculate all scores
            scores = self.score_opportunity(opportunity, brand_config)

            # Update database
            update_data = {
                "relevance_score": scores['relevance_score'],
                "commercial_intent_score": scores['commercial_intent_score'],
                "engagement_score": scores['engagement_score'],
                "composite_score": scores['composite_score'],
                "opportunity_score": scores['opportunity_score'],
                "priority_tier": scores['priority_tier'],
                "scoring_debug": scores['scoring_debug'],
                "updated_at": datetime.utcnow().isoformat()
            }

            if opportunity.get("opportunity_id"):
                self.supabase.table("opportunities").update(update_data)\
                    .eq("opportunity_id", opportunity_id).execute()
            else:
                self.supabase.table("opportunities").update(update_data)\
                    .eq("id", opportunity_id).execute()

            logger.info(f"Rescored opportunity {opportunity_id}: composite={scores['composite_score']} ({scores['priority_tier']})")

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
    logger.info("Running Opportunity Scoring Worker (THREE-SCORE SYSTEM)...")
    result = score_all_opportunities()
    logger.info(f"Results: {result}")
