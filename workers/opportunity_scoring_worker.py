"""
Opportunity Scoring Worker v3.0 - Reddit Timing Optimized

REDDIT REALITY: Old threads are dead. Timing is EVERYTHING.

SCORING FORMULA (4 components):
1. TIMING SCORE (30%) - Freshness is king on Reddit
   - 2-12 hours: 100 points (PEAK - rising, max visibility)
   - 12-24 hours: 80 points
   - 24-48 hours: 50 points
   - 48-72 hours: 20 points
   - 72+ hours: 0 points
   - 7+ days: EXCLUDED entirely

2. VELOCITY SCORE (25%) - Activity rate matters more than totals
   - comments_per_hour and upvotes_per_hour
   - High velocity = rising thread = more visibility

3. COMMERCIAL INTENT (25%) - Buying signals
   - "looking for", "recommend", "budget", "best", "purchase"
   - Price mentions, comparison requests

4. RELEVANCE (20%) - Brand fit
   - Keyword matches
   - Target subreddit match

MINIMUM FILTERS (exclude if ANY fail):
- thread_age < 7 days (archived = invisible)
- comment_count >= 3 (shows actual engagement)
- thread not locked/removed
"""

import os
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
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
    Reddit-optimized opportunity scoring.
    Timing and velocity are weighted heavily because Reddit is real-time.
    """

    # ========================================
    # MINIMUM FILTERS - Exclude if ANY fail
    # ========================================
    MIN_COMMENTS = 3              # At least 3 comments shows engagement
    MAX_THREAD_AGE_DAYS = 7       # 7+ days = archived/invisible on Reddit

    # ========================================
    # SCORING WEIGHTS - Reddit optimized
    # ========================================
    DEFAULT_WEIGHTS = {
        'timing': 0.30,           # Freshness is CRITICAL on Reddit
        'velocity': 0.25,         # Activity rate > total count
        'commercial_intent': 0.25,
        'relevance': 0.20
    }

    # Commercial intent indicators
    HIGH_INTENT_PHRASES = [
        "looking to buy", "want to purchase", "ready to buy",
        "what should i get", "what should i buy", "which should i get",
        "best for", "recommend", "recommendation", "suggestions",
        "help me choose", "help me decide", "narrowed down to",
        "worth it", "should i get", "thinking of buying",
        "where to buy", "need to buy", "planning to buy",
        "looking for", "in the market for", "shopping for"
    ]

    COMPARISON_PHRASES = [
        "vs", "versus", "compared to", "or should i",
        "which one", "better option", "alternative to",
        "x or y", "a or b"
    ]

    PRICE_INDICATORS = [
        "budget", "price", "cost", "afford", "expensive", "cheap",
        "worth the money", "bang for buck", "value for money",
        "$", "dollars", "under $", "around $", "up to $",
        "price range", "how much", "investment"
    ]

    # Negative indicators (already bought, not buying)
    LOW_INTENT_PHRASES = [
        "just bought", "i got", "picked up", "finally got",
        "showing off", "my setup", "my collection",
        "just installed", "here's my", "check out my"
    ]

    def __init__(self):
        """Initialize the scoring worker"""
        self.supabase = supabase
        logger.info("Opportunity Scoring Worker v3.0 initialized (REDDIT TIMING OPTIMIZED)")

    def get_thread_age_hours(self, opportunity: Dict) -> Optional[float]:
        """Calculate thread age in hours"""
        thread_created = (
            opportunity.get('thread_created_utc') or
            opportunity.get('thread_created_at') or
            opportunity.get('date_posted')
        )

        if not thread_created:
            return None

        try:
            if isinstance(thread_created, str):
                created_dt = datetime.fromisoformat(thread_created.replace('Z', '+00:00'))
            else:
                created_dt = datetime.fromtimestamp(thread_created)

            age_hours = (datetime.utcnow() - created_dt.replace(tzinfo=None)).total_seconds() / 3600
            return max(0, age_hours)
        except Exception:
            return None

    def should_exclude(self, opportunity: Dict) -> Tuple[bool, str]:
        """
        Check if opportunity should be EXCLUDED entirely.

        Exclusion criteria:
        - Thread older than 7 days (archived/invisible)
        - Less than 3 comments (dead thread)
        - Thread is locked/removed

        Returns:
            (should_exclude, reason)
        """
        # Check thread age - 7+ days = EXCLUDE
        age_hours = self.get_thread_age_hours(opportunity)
        if age_hours is not None and age_hours > (self.MAX_THREAD_AGE_DAYS * 24):
            return (True, f"Thread is {round(age_hours/24, 1)} days old (max {self.MAX_THREAD_AGE_DAYS} days)")

        # Check minimum comments
        num_comments = (
            opportunity.get('comment_count') or
            opportunity.get('num_comments') or
            opportunity.get('thread_num_comments', 0)
        )
        if num_comments < self.MIN_COMMENTS:
            return (True, f"Only {num_comments} comments (min {self.MIN_COMMENTS})")

        # Check if locked/removed (if we have that data)
        if opportunity.get('is_locked') or opportunity.get('removed'):
            return (True, "Thread is locked or removed")

        return (False, "")

    def calculate_timing_score(self, opportunity: Dict) -> Tuple[float, Dict]:
        """
        Calculate timing score (0-100).

        Reddit timing reality:
        - 2-12 hours: 100 (PEAK - rising, max visibility)
        - 12-24 hours: 80 (still good)
        - 24-48 hours: 50 (okay)
        - 48-72 hours: 20 (getting stale)
        - 72+ hours: 0 (dead)

        Returns:
            (score, debug_info)
        """
        debug = {
            'thread_age_hours': None,
            'thread_age_category': 'unknown',
            'timing_score': 0
        }

        age_hours = self.get_thread_age_hours(opportunity)

        if age_hours is None:
            # No age data - give middle score
            debug['timing_score'] = 50
            debug['thread_age_category'] = 'unknown'
            return (50, debug)

        debug['thread_age_hours'] = round(age_hours, 1)

        # Reddit timing scoring
        if age_hours < 2:
            # Too new - not enough traction yet
            score = 70
            debug['thread_age_category'] = 'very_fresh'
        elif 2 <= age_hours <= 12:
            # PEAK - Rising thread, maximum visibility
            score = 100
            debug['thread_age_category'] = 'PEAK_RISING'
        elif 12 < age_hours <= 24:
            # Still good
            score = 80
            debug['thread_age_category'] = 'fresh'
        elif 24 < age_hours <= 48:
            # Okay
            score = 50
            debug['thread_age_category'] = 'moderate'
        elif 48 < age_hours <= 72:
            # Getting stale
            score = 20
            debug['thread_age_category'] = 'stale'
        else:
            # Dead - but still within 7 day limit
            score = 0
            debug['thread_age_category'] = 'old'

        debug['timing_score'] = score
        return (score, debug)

    def calculate_velocity_score(self, opportunity: Dict) -> Tuple[float, Dict]:
        """
        Calculate velocity score (0-100) based on activity RATE.

        Velocity = activity per hour, not totals.
        A 4-hour old thread with 20 comments is HOT.
        A 3-day old thread with 20 comments is COLD.

        Returns:
            (score, debug_info)
        """
        debug = {
            'comments': 0,
            'upvotes': 0,
            'age_hours': None,
            'comments_per_hour': 0,
            'upvotes_per_hour': 0,
            'velocity_category': 'unknown'
        }

        # Get metrics
        num_comments = (
            opportunity.get('comment_count') or
            opportunity.get('num_comments') or
            opportunity.get('thread_num_comments', 0)
        )
        upvotes = (
            opportunity.get('score', 0) or
            opportunity.get('upvotes', 0) or
            opportunity.get('thread_score', 0)
        )

        debug['comments'] = num_comments
        debug['upvotes'] = upvotes

        age_hours = self.get_thread_age_hours(opportunity)
        if age_hours is None or age_hours < 0.5:
            age_hours = 1  # Minimum 1 hour to avoid division issues

        debug['age_hours'] = round(age_hours, 1)

        # Calculate velocity
        comments_per_hour = num_comments / age_hours
        upvotes_per_hour = upvotes / age_hours

        debug['comments_per_hour'] = round(comments_per_hour, 2)
        debug['upvotes_per_hour'] = round(upvotes_per_hour, 2)

        # Score based on comment velocity (more important than upvotes for engagement)
        # These thresholds are calibrated for Reddit activity
        if comments_per_hour >= 10:
            comment_velocity_score = 60  # Viral thread
            debug['velocity_category'] = 'VIRAL'
        elif comments_per_hour >= 5:
            comment_velocity_score = 50  # Hot thread
            debug['velocity_category'] = 'hot'
        elif comments_per_hour >= 2:
            comment_velocity_score = 40  # Active thread
            debug['velocity_category'] = 'active'
        elif comments_per_hour >= 1:
            comment_velocity_score = 30  # Decent activity
            debug['velocity_category'] = 'decent'
        elif comments_per_hour >= 0.5:
            comment_velocity_score = 20  # Slow but alive
            debug['velocity_category'] = 'slow'
        elif comments_per_hour >= 0.2:
            comment_velocity_score = 10
            debug['velocity_category'] = 'very_slow'
        else:
            comment_velocity_score = 0
            debug['velocity_category'] = 'dead'

        # Score based on upvote velocity
        if upvotes_per_hour >= 20:
            upvote_velocity_score = 40
        elif upvotes_per_hour >= 10:
            upvote_velocity_score = 30
        elif upvotes_per_hour >= 5:
            upvote_velocity_score = 20
        elif upvotes_per_hour >= 2:
            upvote_velocity_score = 15
        elif upvotes_per_hour >= 1:
            upvote_velocity_score = 10
        else:
            upvote_velocity_score = 5

        # Combined velocity score (comments weighted higher)
        score = min(100, comment_velocity_score + upvote_velocity_score)
        debug['velocity_score'] = score

        return (score, debug)

    def calculate_commercial_intent_score(self, opportunity: Dict) -> Tuple[float, Dict]:
        """
        Calculate commercial/buying intent score (0-100).

        Signals:
        - Buying phrases ("looking for", "recommend", "best")
        - Price mentions ("budget", "$", "how much")
        - Comparison requests ("X vs Y", "which should I")
        - Questions (? marks)

        Returns:
            (score, debug_info)
        """
        debug = {
            'high_intent_matches': [],
            'comparison_matches': [],
            'price_matches': [],
            'low_intent_matches': [],
            'question_count': 0
        }
        score = 0

        thread_title = opportunity.get("thread_title", "")
        thread_content = opportunity.get("original_post_text") or opportunity.get("thread_content") or opportunity.get("thread_body", "")
        full_text = f"{thread_title} {thread_content}".lower()

        # High intent phrases (+20 each, max 60)
        for phrase in self.HIGH_INTENT_PHRASES:
            if phrase in full_text:
                score += 20
                debug['high_intent_matches'].append(phrase)
                if len(debug['high_intent_matches']) >= 3:
                    break
        score = min(score, 60)

        # Comparison phrases (+15 each, max 30)
        comparison_score = 0
        for phrase in self.COMPARISON_PHRASES:
            if phrase in full_text:
                comparison_score += 15
                debug['comparison_matches'].append(phrase)
                if len(debug['comparison_matches']) >= 2:
                    break
        score += min(comparison_score, 30)

        # Price indicators (+15 each, max 30)
        price_score = 0
        for indicator in self.PRICE_INDICATORS:
            if indicator in full_text:
                price_score += 15
                debug['price_matches'].append(indicator)
                if len(debug['price_matches']) >= 2:
                    break
        score += min(price_score, 30)

        # Question bonus (+10 for questions)
        question_count = full_text.count("?")
        debug['question_count'] = question_count
        if question_count >= 1:
            score += 10
        if question_count >= 3:
            score += 10

        # Low intent penalty (-30 each)
        for phrase in self.LOW_INTENT_PHRASES:
            if phrase in full_text:
                score -= 30
                debug['low_intent_matches'].append(phrase)

        final_score = max(0, min(score, 100))
        debug['commercial_intent_score'] = final_score

        return (final_score, debug)

    def calculate_relevance_score(
        self,
        opportunity: Dict,
        brand_config: Optional[Dict] = None
    ) -> Tuple[float, Dict]:
        """
        Calculate brand relevance score (0-100).

        Factors:
        - Keyword matches to client products
        - Subreddit is in client's target list

        Returns:
            (score, debug_info)
        """
        debug = {
            'keywords_matched': [],
            'subreddit_match': False,
            'subreddit': ''
        }
        score = 0

        thread_title = opportunity.get("thread_title", "")
        thread_content = opportunity.get("original_post_text") or opportunity.get("thread_content") or opportunity.get("thread_body", "")
        full_text = f"{thread_title} {thread_content}".lower()
        subreddit = opportunity.get("subreddit", "").lower().replace("r/", "")
        debug['subreddit'] = subreddit

        brand_keywords = []
        target_subreddits = []

        if brand_config:
            brand_keywords = brand_config.get('target_keywords', []) or []
            target_subreddits = [s.lower().replace("r/", "") for s in (brand_config.get('target_subreddits', []) or [])]
            brand_keywords.extend(brand_config.get('product_keywords', []) or [])

        # Keyword matching (+15 each, max 60)
        for keyword in brand_keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in full_text:
                score += 15
                debug['keywords_matched'].append(keyword)
                if len(debug['keywords_matched']) >= 4:
                    break
        score = min(score, 60)

        # Subreddit match bonus (+40 points)
        if subreddit in target_subreddits:
            score += 40
            debug['subreddit_match'] = True

        final_score = min(score, 100)
        debug['relevance_score'] = final_score

        return (final_score, debug)

    def calculate_composite_score(
        self,
        timing: float,
        velocity: float,
        commercial_intent: float,
        relevance: float,
        weights: Optional[Dict] = None
    ) -> float:
        """
        Calculate weighted composite score.

        Weights:
        - timing: 30%
        - velocity: 25%
        - commercial_intent: 25%
        - relevance: 20%
        """
        if weights is None:
            weights = self.DEFAULT_WEIGHTS

        composite = (
            timing * weights.get('timing', 0.30) +
            velocity * weights.get('velocity', 0.25) +
            commercial_intent * weights.get('commercial_intent', 0.25) +
            relevance * weights.get('relevance', 0.20)
        )

        return min(round(composite, 2), 100)

    def determine_priority(self, composite_score: float) -> str:
        """Determine priority tier from composite score"""
        if composite_score >= 80:
            return "URGENT"
        elif composite_score >= 60:
            return "HIGH"
        elif composite_score >= 40:
            return "MEDIUM"
        else:
            return "LOW"

    def score_opportunity(self, opportunity: Dict, brand_config: Optional[Dict] = None) -> Optional[Dict]:
        """
        Score a single opportunity with Reddit-optimized scoring.

        Returns None if opportunity should be EXCLUDED.

        Returns:
            Dictionary with all scores, or None if excluded
        """
        # Check exclusion first
        should_exclude, exclude_reason = self.should_exclude(opportunity)
        if should_exclude:
            return {
                "excluded": True,
                "exclude_reason": exclude_reason,
                "composite_score": 0,
                "priority_tier": "EXCLUDED"
            }

        # Calculate all four scores
        timing, timing_debug = self.calculate_timing_score(opportunity)
        velocity, velocity_debug = self.calculate_velocity_score(opportunity)
        commercial_intent, intent_debug = self.calculate_commercial_intent_score(opportunity)
        relevance, relevance_debug = self.calculate_relevance_score(opportunity, brand_config)

        # Calculate composite
        composite = self.calculate_composite_score(timing, velocity, commercial_intent, relevance)
        priority = self.determine_priority(composite)

        # Compile debug info
        scoring_debug = {
            'version': 'v3.0_reddit_optimized',
            'timing': timing_debug,
            'velocity': velocity_debug,
            'commercial_intent': intent_debug,
            'relevance': relevance_debug,
            'weights_used': self.DEFAULT_WEIGHTS,
            'scored_at': datetime.utcnow().isoformat()
        }

        return {
            # Individual scores
            "timing_score": timing,
            "velocity_score": velocity,
            "commercial_intent_score": commercial_intent,
            "relevance_score": relevance,

            # For backward compatibility - map to old column names
            "engagement_score": velocity,  # velocity replaces engagement

            # Composite and priority
            "composite_score": composite,
            "opportunity_score": composite,
            "priority": priority,
            "priority_tier": priority,

            # Debug info
            "scoring_debug": scoring_debug,
            "analysis_timestamp": datetime.utcnow().isoformat(),
            "excluded": False
        }

    def get_brand_config(self, client_id: str) -> Optional[Dict]:
        """Get brand configuration for relevance scoring"""
        try:
            client = self.supabase.table("clients")\
                .select("target_keywords, target_subreddits, company_name, industry")\
                .eq("client_id", client_id)\
                .execute()

            if client.data:
                client_data = client.data[0]

                # Get keywords from client_keyword_config
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

    def process_all_opportunities(self, client_id: Optional[str] = None, batch_size: int = 500, force_rescore: bool = False) -> Dict:
        """
        Process opportunities with Reddit-optimized scoring.

        Args:
            client_id: Optional client ID to filter by
            batch_size: Maximum opportunities to process per run
            force_rescore: If True, rescore ALL opportunities regardless of existing scores

        Returns:
            Dictionary with processing results
        """
        try:
            logger.info(f"Starting Reddit-optimized scoring v3.0 (batch_size={batch_size}, force_rescore={force_rescore})...")

            # Get brand config if client specified
            brand_config = None
            if client_id:
                brand_config = self.get_brand_config(client_id)
                if brand_config:
                    logger.info(f"Loaded brand config for {brand_config.get('company_name')}")

            # Build query
            if force_rescore:
                # Rescore all opportunities for this client
                query = self.supabase.table("opportunities")\
                    .select("*")\
                    .order("created_at", desc=True)\
                    .limit(batch_size)
            else:
                # Only score opportunities without composite scores
                query = self.supabase.table("opportunities")\
                    .select("*")\
                    .is_("composite_score", "null")\
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
                    "excluded": 0,
                    "message": "No opportunities need scoring"
                }

            logger.info(f"Found {len(opportunities.data)} opportunities to score")

            processed = 0
            excluded = 0
            errors = 0

            for opp in opportunities.data:
                try:
                    opp_client_id = opp.get("client_id")
                    if opp_client_id and opp_client_id != client_id and not brand_config:
                        brand_config = self.get_brand_config(opp_client_id)

                    # Calculate all scores
                    scores = self.score_opportunity(opp, brand_config)

                    if scores is None:
                        excluded += 1
                        continue

                    # Get opportunity ID
                    opp_id = opp.get("opportunity_id") or opp.get("id")

                    # Update database
                    update_data = {
                        "timing_score": scores.get('timing_score'),
                        "relevance_score": scores['relevance_score'],
                        "commercial_intent_score": scores['commercial_intent_score'],
                        "engagement_score": scores['engagement_score'],
                        "composite_score": scores['composite_score'],
                        "opportunity_score": scores['opportunity_score'],
                        "priority_tier": scores['priority_tier'],
                        "scoring_debug": scores['scoring_debug'],
                        "updated_at": datetime.utcnow().isoformat()
                    }

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
                    logger.error(f"Error scoring opportunity {opp.get('opportunity_id', opp.get('id'))}: {str(e)}")
                    errors += 1

            logger.info(f"Scoring complete: {processed} processed, {excluded} excluded, {errors} errors")

            return {
                "success": True,
                "processed": processed,
                "excluded": excluded,
                "errors": errors,
                "batch_size": batch_size,
                "total_in_batch": len(opportunities.data),
                "more_to_process": len(opportunities.data) >= batch_size,
                "scoring_version": "v3.0_reddit_optimized",
                "message": f"Processed {processed} opportunities with timing/velocity/intent/relevance scores"
            }

        except Exception as e:
            logger.error(f"Error in opportunity scoring process: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

    def rescore_opportunity(self, opportunity_id: str) -> Dict:
        """Rescore a specific opportunity"""
        try:
            opp = self.supabase.table("opportunities")\
                .select("*")\
                .eq("opportunity_id", opportunity_id)\
                .execute()

            if not opp.data:
                opp = self.supabase.table("opportunities")\
                    .select("*")\
                    .eq("id", opportunity_id)\
                    .execute()

            if not opp.data:
                return {"success": False, "error": f"Opportunity {opportunity_id} not found"}

            opportunity = opp.data[0]
            client_id = opportunity.get("client_id")
            brand_config = self.get_brand_config(client_id) if client_id else None

            scores = self.score_opportunity(opportunity, brand_config)

            if scores.get('excluded'):
                return {
                    "success": True,
                    "opportunity_id": opportunity_id,
                    "excluded": True,
                    "reason": scores.get('exclude_reason')
                }

            update_data = {
                "timing_score": scores.get('timing_score'),
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
            return {"success": False, "error": str(e)}


# Utility functions
def score_all_opportunities(client_id: Optional[str] = None, force_rescore: bool = False):
    """Score all opportunities (can be called from scheduler)"""
    worker = OpportunityScoringWorker()
    return worker.process_all_opportunities(client_id, force_rescore=force_rescore)


def score_opportunity_by_id(opportunity_id: str):
    """Score a specific opportunity"""
    worker = OpportunityScoringWorker()
    return worker.rescore_opportunity(opportunity_id)


if __name__ == "__main__":
    logger.info("Running Opportunity Scoring Worker v3.0 (Reddit Timing Optimized)...")
    result = score_all_opportunities()
    logger.info(f"Results: {result}")
