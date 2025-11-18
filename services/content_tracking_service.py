"""
EchoMind - Content Tracking Service
Logs all content delivered to clients for analytics and strategy compliance
"""

import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from supabase import create_client, Client
import logging
from uuid import UUID

logger = logging.getLogger(__name__)


class ContentTrackingService:
    """Service for tracking content delivery and usage"""
    
    def __init__(self):
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY")
        )
    
    async def log_content_delivery(
        self,
        client_id: str,
        opportunities: List[Dict[str, Any]],
        delivery_batch: str,  # e.g., 'MON-2025-W47'
        client_settings: Dict[str, Any]
    ) -> int:
        """
        Log a batch of content pieces delivered to a client
        
        Args:
            client_id: Client UUID
            opportunities: List of content opportunities delivered
            delivery_batch: Batch identifier (e.g., 'MON-2025-W47')
            client_settings: Current slider settings at delivery time
            
        Returns:
            Number of pieces logged
        """
        
        try:
            records = []
            
            for opp in opportunities:
                record = {
                    'client_id': client_id,
                    'delivery_date': datetime.utcnow().isoformat(),
                    'delivery_batch': delivery_batch,
                    'opportunity_id': opp.get('opportunity_id', f"OPP-{opp.get('id', 'unknown')}"),
                    
                    # Content classification
                    'content_type': opp.get('content_type', 'reply').lower(),
                    'subreddit': opp.get('subreddit', 'unknown'),
                    'thread_title': opp.get('thread_title', 'Untitled'),
                    'thread_url': opp.get('thread_url'),
                    
                    # Content details
                    'suggested_content': opp.get('suggested_content', ''),
                    'original_post_context': opp.get('original_post', ''),
                    
                    # Strategy tracking
                    'brand_mentioned': self._check_brand_mention(
                        opp.get('suggested_content', ''),
                        opp.get('brand_name', 'The Waite')
                    ),
                    'product_mentioned': bool(opp.get('product_mentioned')),
                    'product_name': opp.get('product_name'),
                    'product_url': opp.get('product_url'),
                    
                    # Scoring
                    'relevance_score': opp.get('relevance_score'),
                    'commercial_intent_score': opp.get('commercial_intent_score'),
                    'overall_priority': opp.get('overall_priority'),
                    'urgency_level': opp.get('urgency_level'),
                    
                    # Snapshot of settings at delivery
                    'settings_snapshot': {
                        'reply_percentage': client_settings.get('reply_percentage'),
                        'brand_mention_percentage': client_settings.get('brand_mention_percentage'),
                        'product_mention_percentage': client_settings.get('product_mention_percentage'),
                        'current_phase': client_settings.get('current_phase')
                    },
                    
                    # Initial status
                    'status': 'delivered'
                }
                
                records.append(record)
            
            # Batch insert
            result = self.supabase.table('content_delivered').insert(records).execute()
            
            logger.info(f"Logged {len(records)} content pieces for client {client_id} (batch: {delivery_batch})")
            
            return len(records)
            
        except Exception as e:
            logger.error(f"Failed to log content delivery: {e}")
            raise
    
    def _check_brand_mention(self, content: str, brand_name: str) -> bool:
        """Check if content mentions the brand"""
        if not content or not brand_name:
            return False
        
        content_lower = content.lower()
        brand_lower = brand_name.lower()
        
        # Check for exact match or possessive
        return brand_lower in content_lower or f"{brand_lower}'s" in content_lower
    
    async def mark_content_used(
        self,
        content_id: str,
        reddit_post_url: Optional[str] = None,
        marked_by: Optional[str] = None
    ) -> bool:
        """
        Mark a content piece as used (actually posted to Reddit)
        
        Args:
            content_id: UUID of content_delivered record
            reddit_post_url: URL of the actual Reddit post
            marked_by: Who marked it (user email/name)
            
        Returns:
            Success status
        """
        
        try:
            update_data = {
                'status': 'used',
                'marked_used_at': datetime.utcnow().isoformat(),
                'reddit_post_url': reddit_post_url
            }
            
            if marked_by:
                update_data['marked_by'] = marked_by
            
            self.supabase.table('content_delivered')\
                .update(update_data)\
                .eq('id', content_id)\
                .execute()
            
            logger.info(f"Marked content {content_id} as used")
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark content as used: {e}")
            return False
    
    async def mark_content_skipped(self, content_id: str, marked_by: Optional[str] = None) -> bool:
        """Mark a content piece as skipped"""
        
        try:
            update_data = {
                'status': 'skipped',
                'marked_used_at': datetime.utcnow().isoformat()
            }
            
            if marked_by:
                update_data['marked_by'] = marked_by
            
            self.supabase.table('content_delivered')\
                .update(update_data)\
                .eq('id', content_id)\
                .execute()
            
            logger.info(f"Marked content {content_id} as skipped")
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark content as skipped: {e}")
            return False
    
    async def get_delivery_summary(
        self,
        client_id: str,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get delivery summary for a client and time period
        
        Args:
            client_id: Client UUID
            period_start: Start of period (default: 7 days ago)
            period_end: End of period (default: now)
            
        Returns:
            Summary dictionary with metrics
        """
        
        try:
            if not period_start:
                period_start = datetime.utcnow() - timedelta(days=7)
            if not period_end:
                period_end = datetime.utcnow()
            
            # Fetch delivered content
            result = self.supabase.table('content_delivered')\
                .select('*')\
                .eq('client_id', client_id)\
                .gte('delivery_date', period_start.isoformat())\
                .lte('delivery_date', period_end.isoformat())\
                .execute()
            
            content = result.data
            
            if not content:
                return self._empty_summary()
            
            # Calculate metrics
            total = len(content)
            replies = sum(1 for c in content if c['content_type'] == 'reply')
            posts = sum(1 for c in content if c['content_type'] == 'post')
            brand_mentions = sum(1 for c in content if c['brand_mentioned'])
            product_mentions = sum(1 for c in content if c['product_mentioned'])
            used = sum(1 for c in content if c['status'] == 'used')
            skipped = sum(1 for c in content if c['status'] == 'skipped')
            
            # Get latest settings snapshot
            latest_settings = content[-1].get('settings_snapshot', {})
            
            return {
                'period_start': period_start.isoformat(),
                'period_end': period_end.isoformat(),
                'total_delivered': total,
                'monday_deliveries': sum(1 for c in content if datetime.fromisoformat(c['delivery_date'].replace('Z', '+00:00')).weekday() == 0),
                'thursday_deliveries': sum(1 for c in content if datetime.fromisoformat(c['delivery_date'].replace('Z', '+00:00')).weekday() == 3),
                
                # Content type breakdown
                'replies': replies,
                'posts': posts,
                'reply_percentage': round((replies / total * 100) if total > 0 else 0, 1),
                'post_percentage': round((posts / total * 100) if total > 0 else 0, 1),
                
                # Brand mention metrics
                'brand_mentions': brand_mentions,
                'brand_mention_percentage': round((brand_mentions / total * 100) if total > 0 else 0, 1),
                
                # Product mention metrics
                'product_mentions': product_mentions,
                'product_mention_percentage': round((product_mentions / total * 100) if total > 0 else 0, 1),
                
                # Usage metrics
                'used': used,
                'skipped': skipped,
                'pending': total - used - skipped,
                'usage_rate': round((used / total * 100) if total > 0 else 0, 1),
                
                # Target settings (from snapshot)
                'target_reply_percentage': latest_settings.get('reply_percentage'),
                'target_brand_percentage': latest_settings.get('brand_mention_percentage'),
                'target_product_percentage': latest_settings.get('product_mention_percentage'),
                
                # Variance (actual vs target)
                'reply_variance': round((replies / total * 100) - latest_settings.get('reply_percentage', 0), 1) if total > 0 and latest_settings.get('reply_percentage') else None,
                'brand_variance': round((brand_mentions / total * 100) - latest_settings.get('brand_mention_percentage', 0), 1) if total > 0 and latest_settings.get('brand_mention_percentage') else None,
                'product_variance': round((product_mentions / total * 100) - latest_settings.get('product_mention_percentage', 0), 1) if total > 0 and latest_settings.get('product_mention_percentage') else None,
                
                # Scoring averages
                'avg_relevance_score': round(sum(c.get('relevance_score', 0) or 0 for c in content) / total, 1) if total > 0 else 0,
                'avg_priority': round(sum(c.get('overall_priority', 0) or 0 for c in content) / total, 1) if total > 0 else 0,
                
                # Top performers
                'top_subreddits': self._get_top_subreddits(content),
                'top_products': self._get_top_products(content)
            }
            
        except Exception as e:
            logger.error(f"Failed to get delivery summary: {e}")
            raise
    
    def _empty_summary(self) -> Dict[str, Any]:
        """Return empty summary structure"""
        return {
            'total_delivered': 0,
            'monday_deliveries': 0,
            'thursday_deliveries': 0,
            'replies': 0,
            'posts': 0,
            'reply_percentage': 0,
            'post_percentage': 0,
            'brand_mentions': 0,
            'brand_mention_percentage': 0,
            'product_mentions': 0,
            'product_mention_percentage': 0,
            'used': 0,
            'skipped': 0,
            'pending': 0,
            'usage_rate': 0,
            'top_subreddits': [],
            'top_products': []
        }
    
    def _get_top_subreddits(self, content: List[Dict]) -> List[Dict]:
        """Get top performing subreddits"""
        subreddit_stats = {}
        
        for c in content:
            sub = c['subreddit']
            if sub not in subreddit_stats:
                subreddit_stats[sub] = {'count': 0, 'used': 0}
            subreddit_stats[sub]['count'] += 1
            if c['status'] == 'used':
                subreddit_stats[sub]['used'] += 1
        
        # Sort by count
        sorted_subs = sorted(
            [{'subreddit': k, **v} for k, v in subreddit_stats.items()],
            key=lambda x: x['count'],
            reverse=True
        )
        
        return sorted_subs[:5]
    
    def _get_top_products(self, content: List[Dict]) -> List[Dict]:
        """Get top mentioned products"""
        product_stats = {}
        
        for c in content:
            if c.get('product_mentioned') and c.get('product_name'):
                prod = c['product_name']
                if prod not in product_stats:
                    product_stats[prod] = {'count': 0, 'used': 0}
                product_stats[prod]['count'] += 1
                if c['status'] == 'used':
                    product_stats[prod]['used'] += 1
        
        # Sort by count
        sorted_prods = sorted(
            [{'product': k, **v} for k, v in product_stats.items()],
            key=lambda x: x['count'],
            reverse=True
        )
        
        return sorted_prods[:5]
    
    async def compute_and_store_summary(
        self,
        client_id: str,
        period_type: str = 'week'
    ) -> bool:
        """
        Compute and store analytics summary using database function
        
        Args:
            client_id: Client UUID
            period_type: 'week', 'month', or 'all-time'
            
        Returns:
            Success status
        """
        
        try:
            # Determine period dates
            now = datetime.utcnow().date()
            
            if period_type == 'week':
                period_start = now - timedelta(days=7)
                period_end = now
            elif period_type == 'month':
                period_start = now - timedelta(days=30)
                period_end = now
            else:  # all-time
                period_start = datetime(2025, 1, 1).date()
                period_end = now
            
            # Call database function
            self.supabase.rpc(
                'compute_analytics_summary',
                {
                    'p_client_id': client_id,
                    'p_period_start': period_start.isoformat(),
                    'p_period_end': period_end.isoformat(),
                    'p_period_type': period_type
                }
            ).execute()
            
            logger.info(f"Computed analytics summary for client {client_id} ({period_type})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to compute analytics summary: {e}")
            return False


# Integration function for Monday/Thursday delivery
async def log_weekly_delivery(
    client_id: str,
    opportunities: List[Dict[str, Any]],
    is_monday: bool = True
) -> int:
    """
    Log weekly content delivery (called by Mon/Thu scheduler)
    
    Args:
        client_id: Client UUID
        opportunities: List of opportunities delivered
        is_monday: True for Monday delivery, False for Thursday
        
    Returns:
        Number of pieces logged
    """
    
    service = ContentTrackingService()
    
    # Get current client settings
    supabase = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_KEY")
    )
    
    settings_result = supabase.table('client_settings')\
        .select('*')\
        .eq('client_id', client_id)\
        .execute()
    
    client_settings = settings_result.data[0] if settings_result.data else {}
    
    # Generate batch identifier
    now = datetime.utcnow()
    week_num = now.isocalendar()[1]
    day_code = 'MON' if is_monday else 'THU'
    delivery_batch = f"{day_code}-{now.year}-W{week_num:02d}"
    
    # Log delivery
    count = await service.log_content_delivery(
        client_id=client_id,
        opportunities=opportunities,
        delivery_batch=delivery_batch,
        client_settings=client_settings
    )
    
    # Compute weekly summary
    await service.compute_and_store_summary(client_id, 'week')
    
    return count
