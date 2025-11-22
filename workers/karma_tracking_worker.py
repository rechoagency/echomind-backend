"""
Karma Tracking Worker
Tracks Reddit profile karma growth to measure EchoMind's impact

BUSINESS VALUE:
- Proves "makes brands karma grow" claim
- Provides weekly/monthly growth metrics
- Enables before/after comparisons
- Shows ROI through engagement metrics
"""

import logging
import os
from datetime import datetime, timedelta
import praw
from supabase_client import get_supabase_client

logger = logging.getLogger(__name__)

class KarmaTrackingWorker:
    """
    Tracks karma for client Reddit profiles
    Stores historical data to show growth over time
    """
    
    def __init__(self):
        """Initialize Reddit API and Supabase clients"""
        self.supabase = get_supabase_client()
        
        # Initialize Reddit API client
        self.reddit = praw.Reddit(
            client_id=os.getenv("REDDIT_CLIENT_ID"),
            client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
            user_agent=os.getenv("REDDIT_USER_AGENT", "EchoMind Karma Tracker")
        )
        
        logger.info("✅ KarmaTrackingWorker initialized")
    
    def fetch_profile_karma(self, username: str) -> dict:
        """
        Fetch current karma for a Reddit profile
        
        Args:
            username: Reddit username
            
        Returns:
            dict with karma data: {
                'username': str,
                'total_karma': int,
                'comment_karma': int, 
                'link_karma': int,
                'fetched_at': datetime
            }
        """
        try:
            redditor = self.reddit.redditor(username)
            
            karma_data = {
                'username': username,
                'total_karma': redditor.total_karma if hasattr(redditor, 'total_karma') else 
                              (redditor.comment_karma + redditor.link_karma),
                'comment_karma': redditor.comment_karma,
                'link_karma': redditor.link_karma,
                'fetched_at': datetime.utcnow().isoformat()
            }
            
            logger.info(f"✅ Fetched karma for u/{username}: {karma_data['total_karma']} total")
            return karma_data
            
        except Exception as e:
            logger.error(f"❌ Error fetching karma for u/{username}: {e}")
            return None
    
    def log_karma_snapshot(self, profile_id: str, client_id: str, username: str):
        """
        Log current karma snapshot to database
        
        Args:
            profile_id: UUID of client Reddit profile
            client_id: UUID of client
            username: Reddit username
        """
        try:
            # Fetch current karma
            karma_data = self.fetch_profile_karma(username)
            if not karma_data:
                return
            
            # Store in database
            snapshot = {
                'profile_id': profile_id,
                'client_id': client_id,
                'username': username,
                'total_karma': karma_data['total_karma'],
                'comment_karma': karma_data['comment_karma'],
                'link_karma': karma_data['link_karma'],
                'snapshot_date': karma_data['fetched_at']
            }
            
            response = self.supabase.table('karma_snapshots').insert(snapshot).execute()
            
            if response.data:
                logger.info(f"✅ Logged karma snapshot for u/{username}")
            else:
                logger.error(f"❌ Failed to log karma snapshot for u/{username}")
                
        except Exception as e:
            logger.error(f"❌ Error logging karma snapshot: {e}")
    
    def track_all_client_profiles(self):
        """
        Track karma for all active client Reddit profiles
        Run this daily via cron/scheduler
        """
        try:
            # Get all active profiles
            response = self.supabase.table('client_reddit_profiles')\
                .select('id, client_id, username')\
                .eq('is_active', True)\
                .execute()
            
            if not response.data:
                logger.warning("⚠️  No active profiles to track")
                return
            
            profiles = response.data
            logger.info(f"📊 Tracking karma for {len(profiles)} profiles...")
            
            success_count = 0
            for profile in profiles:
                self.log_karma_snapshot(
                    profile_id=profile['id'],
                    client_id=profile['client_id'],
                    username=profile['username']
                )
                success_count += 1
            
            logger.info(f"✅ Completed karma tracking: {success_count}/{len(profiles)} profiles")
            
        except Exception as e:
            logger.error(f"❌ Error in track_all_client_profiles: {e}")
    
    def get_karma_growth(self, profile_id: str, days: int = 7) -> dict:
        """
        Calculate karma growth for a profile over time period
        
        Args:
            profile_id: UUID of client Reddit profile
            days: Number of days to look back (default: 7)
            
        Returns:
            dict with growth metrics: {
                'start_karma': int,
                'end_karma': int,
                'growth': int,
                'growth_percentage': float,
                'period_days': int
            }
        """
        try:
            start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
            
            # Get earliest and latest snapshots in period
            response = self.supabase.table('karma_snapshots')\
                .select('*')\
                .eq('profile_id', profile_id)\
                .gte('snapshot_date', start_date)\
                .order('snapshot_date', desc=False)\
                .execute()
            
            if not response.data or len(response.data) < 2:
                logger.warning(f"⚠️  Not enough data to calculate growth for profile {profile_id}")
                return None
            
            snapshots = response.data
            start_karma = snapshots[0]['total_karma']
            end_karma = snapshots[-1]['total_karma']
            growth = end_karma - start_karma
            growth_percentage = (growth / start_karma * 100) if start_karma > 0 else 0
            
            result = {
                'start_karma': start_karma,
                'end_karma': end_karma,
                'growth': growth,
                'growth_percentage': round(growth_percentage, 2),
                'period_days': days
            }
            
            logger.info(f"📈 Karma growth: {growth} (+{growth_percentage:.1f}%) over {days} days")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error calculating karma growth: {e}")
            return None

# CLI for testing and manual runs
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    worker = KarmaTrackingWorker()
    
    # Track all profiles
    worker.track_all_client_profiles()
    
    print("\n✅ Karma tracking complete")
