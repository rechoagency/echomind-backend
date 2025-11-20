"""
Strategy Progression Service
Automatically adjusts strategy based on client onboarding phase
"""

import logging
from typing import Dict
from datetime import datetime
from supabase_client import supabase

logger = logging.getLogger(__name__)


class StrategyProgressionService:
    """
    Manages time-based strategy progression for Reddit compliance
    
    Phases:
    - Month 1-2 (Days 1-60): Karma Building (100% replies, 0% mentions)
    - Month 3-4 (Days 61-120): Gradual Introduction (80% replies, 30-40% mentions)
    - Month 5+ (Days 121+): Full Strategy (use client's custom settings)
    """
    
    # Phase definitions
    KARMA_BUILDING_DAYS = 60
    GRADUAL_INTRO_DAYS = 120
    
    PHASE_SETTINGS = {
        'karma_building': {
            'reply_percentage': 100,
            'post_percentage': 0,
            'brand_mention_percentage': 0,
            'product_mention_percentage': 0,
            'phase_name': 'Karma Building (Months 1-2)',
            'description': 'Building credibility through helpful replies only'
        },
        'gradual_introduction': {
            'reply_percentage': 80,
            'post_percentage': 20,
            'brand_mention_percentage': 30,
            'product_mention_percentage': 20,
            'phase_name': 'Gradual Introduction (Months 3-4)',
            'description': 'Introducing brand mentions gradually'
        },
        'full_strategy': {
            'phase_name': 'Full Strategy (Month 5+)',
            'description': 'Using custom strategy settings'
        }
    }
    
    def __init__(self):
        self.supabase = supabase
        logger.info("Strategy Progression Service initialized")
    
    def get_effective_strategy(self, client_id: str) -> Dict:
        """
        Get effective strategy settings with phase-based overrides
        
        Args:
            client_id: Client UUID
            
        Returns:
            Strategy settings with phase info
        """
        try:
            # Get client data
            client_response = self.supabase.table('clients') \
                .select('created_at') \
                .eq('client_id', client_id) \
                .single() \
                .execute()
            
            if not client_response.data:
                logger.error(f"Client {client_id} not found")
                return self._get_default_settings()
            
            # Get client_settings (custom strategy)
            settings_response = self.supabase.table('client_settings') \
                .select('*') \
                .eq('client_id', client_id) \
                .single() \
                .execute()
            
            custom_settings = settings_response.data if settings_response.data else {}
            
            # Calculate days since onboarding
            created_at = client_response.data.get('created_at')
            if not created_at:
                logger.warning(f"No created_at for client {client_id}, using defaults")
                return self._apply_defaults(custom_settings)
            
            days_active = self._calculate_days_since_onboarding(created_at)
            
            # Determine current phase
            if days_active < self.KARMA_BUILDING_DAYS:
                phase = 'karma_building'
                effective_settings = self.PHASE_SETTINGS['karma_building'].copy()
                logger.info(
                    f"📅 Client {client_id}: Day {days_active} - KARMA BUILDING phase "
                    f"(0% brand mentions enforced)"
                )
            
            elif days_active < self.GRADUAL_INTRO_DAYS:
                phase = 'gradual_introduction'
                effective_settings = self.PHASE_SETTINGS['gradual_introduction'].copy()
                logger.info(
                    f"📅 Client {client_id}: Day {days_active} - GRADUAL INTRO phase "
                    f"(30% brand mentions, 20% product mentions)"
                )
            
            else:
                phase = 'full_strategy'
                # Use custom settings from client_settings table
                effective_settings = {
                    'reply_percentage': custom_settings.get('reply_percentage', 70),
                    'post_percentage': custom_settings.get('post_percentage', 30),
                    'brand_mention_percentage': custom_settings.get('brand_mention_percentage', 40),
                    'product_mention_percentage': custom_settings.get('product_mention_percentage', 30),
                    'phase_name': self.PHASE_SETTINGS['full_strategy']['phase_name'],
                    'description': self.PHASE_SETTINGS['full_strategy']['description']
                }
                logger.info(
                    f"📅 Client {client_id}: Day {days_active} - FULL STRATEGY phase "
                    f"(using custom settings)"
                )
            
            # Add metadata
            effective_settings.update({
                'current_phase': phase,
                'days_since_onboarding': days_active,
                'explicit_instructions': custom_settings.get('explicit_instructions'),
                'phase_override_active': phase != 'full_strategy'
            })
            
            return effective_settings
        
        except Exception as e:
            logger.error(f"Error getting effective strategy: {e}")
            return self._get_default_settings()
    
    def _calculate_days_since_onboarding(self, created_at: str) -> int:
        """Calculate number of days since client was created"""
        try:
            # Parse ISO timestamp
            if isinstance(created_at, str):
                created_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            else:
                created_date = created_at
            
            now = datetime.utcnow()
            delta = now - created_date.replace(tzinfo=None)
            
            return delta.days
        
        except Exception as e:
            logger.error(f"Error calculating days: {e}")
            return 0
    
    def _get_default_settings(self) -> Dict:
        """Return safe default settings"""
        return {
            'reply_percentage': 100,
            'post_percentage': 0,
            'brand_mention_percentage': 0,
            'product_mention_percentage': 0,
            'current_phase': 'karma_building',
            'days_since_onboarding': 0,
            'phase_name': 'Karma Building (Default)',
            'description': 'Default safe settings',
            'phase_override_active': True
        }
    
    def _apply_defaults(self, settings: Dict) -> Dict:
        """Apply defaults to incomplete settings"""
        return {
            'reply_percentage': settings.get('reply_percentage', 100),
            'post_percentage': settings.get('post_percentage', 0),
            'brand_mention_percentage': settings.get('brand_mention_percentage', 0),
            'product_mention_percentage': settings.get('product_mention_percentage', 0),
            'current_phase': 'unknown',
            'days_since_onboarding': 0,
            'phase_name': 'Unknown Phase',
            'description': 'Using available settings',
            'explicit_instructions': settings.get('explicit_instructions'),
            'phase_override_active': False
        }
    
    def get_phase_info(self, client_id: str) -> Dict:
        """
        Get detailed phase information for dashboard display
        
        Returns:
            Phase info including progress, next milestone, recommendations
        """
        try:
            effective_settings = self.get_effective_strategy(client_id)
            
            days_active = effective_settings['days_since_onboarding']
            current_phase = effective_settings['current_phase']
            
            # Calculate progress and next milestone
            if current_phase == 'karma_building':
                days_remaining = self.KARMA_BUILDING_DAYS - days_active
                next_phase = 'Gradual Introduction'
                progress_percent = (days_active / self.KARMA_BUILDING_DAYS) * 100
                recommendation = "Focus on building karma through helpful replies. NO brand mentions yet."
            
            elif current_phase == 'gradual_introduction':
                days_remaining = self.GRADUAL_INTRO_DAYS - days_active
                next_phase = 'Full Strategy'
                days_in_phase = days_active - self.KARMA_BUILDING_DAYS
                phase_duration = self.GRADUAL_INTRO_DAYS - self.KARMA_BUILDING_DAYS
                progress_percent = (days_in_phase / phase_duration) * 100
                recommendation = "Gradually introducing brand mentions. Keep ratio subtle."
            
            else:
                days_remaining = 0
                next_phase = None
                progress_percent = 100
                recommendation = "Using full custom strategy. Monitor engagement and adjust sliders."
            
            return {
                'current_phase': current_phase,
                'phase_name': effective_settings['phase_name'],
                'days_active': days_active,
                'days_remaining_in_phase': max(0, days_remaining),
                'next_phase': next_phase,
                'progress_percent': round(progress_percent, 1),
                'recommendation': recommendation,
                'strategy_settings': {
                    'reply_percentage': effective_settings['reply_percentage'],
                    'brand_mention_percentage': effective_settings['brand_mention_percentage'],
                    'product_mention_percentage': effective_settings['product_mention_percentage']
                }
            }
        
        except Exception as e:
            logger.error(f"Error getting phase info: {e}")
            return {
                'current_phase': 'unknown',
                'phase_name': 'Unknown',
                'days_active': 0,
                'recommendation': 'Error loading phase information'
            }
