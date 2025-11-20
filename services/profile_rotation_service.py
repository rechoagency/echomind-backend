"""
Profile Rotation Service
Intelligently assigns which Reddit profile should post which content
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from supabase_client import supabase

logger = logging.getLogger(__name__)


class ProfileRotationService:
    """
    Manages intelligent rotation of Reddit profiles across opportunities
    """
    
    def __init__(self):
        self.supabase = supabase
        logger.info("Profile Rotation Service initialized")
    
    def assign_profiles_to_opportunities(
        self,
        client_id: str,
        opportunities: List[Dict]
    ) -> List[Dict]:
        """
        Assign Reddit profiles to opportunities with intelligent rotation
        
        Strategy:
        1. Same subreddit in same week = same profile (consistency)
        2. Balance load across profiles
        3. Prefer profiles with higher karma for high-priority opps
        4. Max 3-4 posts per profile per week
        
        Args:
            client_id: Client UUID
            opportunities: List of scored opportunities
            
        Returns:
            Opportunities with assigned_profile field added
        """
        logger.info(f"🔄 Assigning profiles for {len(opportunities)} opportunities")
        
        # Get client's Reddit profiles
        profiles = self._get_client_profiles(client_id)
        
        if not profiles or len(profiles) == 0:
            logger.warning(f"⚠️ No Reddit profiles found for client {client_id}")
            # Return opportunities with no profile assigned
            for opp in opportunities:
                opp['assigned_profile'] = None
                opp['profile_username'] = "NO_PROFILE_CONFIGURED"
            return opportunities
        
        logger.info(f"📋 Found {len(profiles)} profiles for rotation")
        
        # Get recent profile usage (last 7 days)
        recent_usage = self._get_recent_profile_usage(client_id, days=7)
        
        # Track subreddit assignments this batch
        subreddit_assignments = {}
        
        # Assign profiles
        assigned_opportunities = []
        for opp in opportunities:
            subreddit = opp.get('subreddit_name', '')
            priority = opp.get('priority', 'MEDIUM')
            
            # Check if this subreddit already assigned this week
            if subreddit in subreddit_assignments:
                profile = subreddit_assignments[subreddit]
                logger.debug(f"   Using consistent profile {profile['username']} for r/{subreddit}")
            else:
                # Select optimal profile
                profile = self._select_optimal_profile(
                    profiles,
                    subreddit,
                    priority,
                    recent_usage
                )
                subreddit_assignments[subreddit] = profile
                logger.debug(f"   Assigned {profile['username']} to r/{subreddit}")
            
            # Add profile info to opportunity
            opp['assigned_profile'] = profile['id']
            opp['profile_username'] = profile['username']
            opp['profile_karma'] = profile.get('current_karma', 0)
            opp['profile_last_posted'] = profile.get('last_post_timestamp')
            
            assigned_opportunities.append(opp)
            
            # Track usage for this batch
            recent_usage[profile['id']] = recent_usage.get(profile['id'], 0) + 1
        
        logger.info(f"✅ Assigned profiles to {len(assigned_opportunities)} opportunities")
        
        # Log distribution
        profile_counts = defaultdict(int)
        for opp in assigned_opportunities:
            profile_counts[opp['profile_username']] += 1
        
        logger.info("📊 Profile distribution:")
        for username, count in profile_counts.items():
            logger.info(f"   {username}: {count} posts")
        
        return assigned_opportunities
    
    def _get_client_profiles(self, client_id: str) -> List[Dict]:
        """Get all active Reddit profiles for client"""
        try:
            response = self.supabase.table('client_reddit_profiles') \
                .select('*') \
                .eq('client_id', client_id) \
                .eq('is_active', True) \
                .execute()
            
            return response.data or []
        
        except Exception as e:
            logger.error(f"Error fetching profiles: {e}")
            return []
    
    def _get_recent_profile_usage(self, client_id: str, days: int = 7) -> Dict[str, int]:
        """
        Get profile usage counts for recent period
        Returns: {profile_id: post_count}
        """
        try:
            # Check generated_content table for recent posts
            cutoff_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            response = self.supabase.table('generated_content') \
                .select('profile_id') \
                .eq('client_id', client_id) \
                .gte('created_at', cutoff_date) \
                .execute()
            
            # Count posts per profile
            usage = defaultdict(int)
            if response.data:
                for record in response.data:
                    profile_id = record.get('profile_id')
                    if profile_id:
                        usage[profile_id] += 1
            
            return dict(usage)
        
        except Exception as e:
            logger.warning(f"Could not fetch usage data: {e}")
            return {}
    
    def _select_optimal_profile(
        self,
        profiles: List[Dict],
        subreddit: str,
        priority: str,
        recent_usage: Dict[str, int]
    ) -> Dict:
        """
        Select optimal profile based on multiple factors
        
        Criteria:
        1. Lowest recent usage (balance load)
        2. Higher karma for high-priority posts
        3. Target subreddit match (if profile has specific subreddits)
        """
        
        # Score each profile
        scored_profiles = []
        
        for profile in profiles:
            score = 0
            
            # Factor 1: Prefer less-used profiles (40% weight)
            profile_id = profile.get('id')
            usage_count = recent_usage.get(profile_id, 0)
            usage_score = max(0, 100 - (usage_count * 10))  # -10 per recent post
            score += usage_score * 0.4
            
            # Factor 2: Prefer higher karma (30% weight) - especially for high-priority
            karma = profile.get('current_karma', 0)
            karma_score = min(100, karma)  # Cap at 100
            if priority in ['HIGH', 'URGENT']:
                score += karma_score * 0.4  # Boost karma importance
            else:
                score += karma_score * 0.3
            
            # Factor 3: Target subreddit match (30% weight)
            target_subs = profile.get('target_subreddits', [])
            if target_subs and subreddit:
                # Check if subreddit matches
                if subreddit in target_subs or f"r/{subreddit}" in target_subs:
                    score += 100 * 0.3
            
            scored_profiles.append({
                'profile': profile,
                'score': score,
                'usage_count': usage_count
            })
        
        # Sort by score (highest first)
        scored_profiles.sort(key=lambda x: x['score'], reverse=True)
        
        # Return best profile
        best = scored_profiles[0]
        logger.debug(
            f"   Selected {best['profile']['username']} "
            f"(score: {best['score']:.1f}, usage: {best['usage_count']})"
        )
        
        return best['profile']
    
    def update_profile_stats(self, profile_id: str, posted: bool = False):
        """
        Update profile statistics after posting
        
        Args:
            profile_id: Profile UUID
            posted: Whether content was actually posted
        """
        try:
            update_data = {}
            
            if posted:
                update_data['last_post_timestamp'] = datetime.utcnow().isoformat()
                # Note: Karma should be updated separately via Reddit API scraping
            
            if update_data:
                self.supabase.table('client_reddit_profiles') \
                    .update(update_data) \
                    .eq('id', profile_id) \
                    .execute()
                
                logger.info(f"✅ Updated stats for profile {profile_id}")
        
        except Exception as e:
            logger.error(f"Error updating profile stats: {e}")
