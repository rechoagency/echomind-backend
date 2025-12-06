"""
Compliance Service
Handles brand-specific compliance requirements (medical, financial, legal disclaimers)
"""

import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class ComplianceService:
    """Handle brand-specific compliance requirements"""

    # Disclaimer templates by industry type
    DISCLAIMER_TEMPLATES = {
        "medical": (
            "*This is general information, not medical advice. "
            "Please consult a healthcare professional for personal medical questions.*"
        ),
        "financial": (
            "*This is general information, not financial advice. "
            "Please consult a qualified financial advisor for personal financial decisions.*"
        ),
        "legal": (
            "*This is general information, not legal advice. "
            "Please consult a qualified attorney for legal matters.*"
        ),
        "supplement": (
            "*These statements have not been evaluated by the FDA. "
            "This product is not intended to diagnose, treat, cure, or prevent any disease.*"
        ),
        "weight_loss": (
            "*Individual results may vary. Always consult with a healthcare professional "
            "before starting any weight loss program.*"
        ),
        "investment": (
            "*Past performance does not guarantee future results. "
            "Investing involves risk, including the potential loss of principal.*"
        )
    }

    # Industry keywords that trigger compliance flags
    INDUSTRY_COMPLIANCE_TRIGGERS = {
        'requires_medical_disclaimer': [
            'health', 'medical', 'wellness', 'supplement', 'vitamin',
            'therapy', 'treatment', 'pharmaceutical', 'drug', 'medicine',
            'clinical', 'healthcare', 'nursing', 'doctor', 'patient'
        ],
        'requires_financial_disclaimer': [
            'finance', 'investment', 'banking', 'trading', 'crypto',
            'cryptocurrency', 'stocks', 'bonds', 'wealth', 'money',
            'insurance', 'mortgage', 'loan', 'credit', 'retirement'
        ],
        'requires_legal_disclaimer': [
            'legal', 'law', 'attorney', 'lawyer', 'litigation',
            'contract', 'estate planning', 'compliance'
        ],
        'requires_supplement_disclaimer': [
            'supplement', 'vitamin', 'mineral', 'herbal', 'nutraceutical',
            'probiotic', 'protein powder', 'amino acid', 'dietary'
        ],
        'requires_weight_loss_disclaimer': [
            'weight loss', 'diet', 'slimming', 'fat burn', 'metabolism',
            'keto', 'fitness', 'body transformation'
        ]
    }

    def __init__(self, supabase_client=None):
        """
        Initialize compliance service

        Args:
            supabase_client: Optional Supabase client for fetching client data
        """
        self.supabase = supabase_client

    def get_brand_compliance_flags(self, client_id: str) -> Dict[str, bool]:
        """
        Get compliance requirements for a brand based on industry and explicit flags.

        Args:
            client_id: Client UUID

        Returns:
            Dictionary of compliance flags
        """
        flags = {
            'requires_medical_disclaimer': False,
            'requires_financial_disclaimer': False,
            'requires_legal_disclaimer': False,
            'requires_supplement_disclaimer': False,
            'requires_weight_loss_disclaimer': False
        }

        if not self.supabase:
            return flags

        try:
            # Get client data
            result = self.supabase.table("clients")\
                .select("industry, compliance_flags, company_name")\
                .eq("client_id", client_id)\
                .execute()

            if not result.data:
                logger.warning(f"Client {client_id} not found for compliance check")
                return flags

            client = result.data[0]
            industry = (client.get('industry') or '').lower()
            explicit_flags = client.get('compliance_flags') or {}

            # Apply explicit flags first (they take precedence)
            for flag_name in flags:
                if flag_name in explicit_flags:
                    flags[flag_name] = explicit_flags[flag_name]

            # Auto-detect based on industry keywords
            for flag_name, keywords in self.INDUSTRY_COMPLIANCE_TRIGGERS.items():
                if not flags[flag_name]:  # Don't override explicit settings
                    for keyword in keywords:
                        if keyword in industry:
                            flags[flag_name] = True
                            logger.info(
                                f"Auto-detected {flag_name} for {client.get('company_name')} "
                                f"(industry contains '{keyword}')"
                            )
                            break

            return flags

        except Exception as e:
            logger.error(f"Error getting compliance flags for {client_id}: {e}")
            return flags

    def apply_disclaimers(
        self,
        content: str,
        compliance_flags: Dict[str, bool],
        position: str = "end"
    ) -> Tuple[str, List[str]]:
        """
        Apply required disclaimers to content.

        Args:
            content: Original content text
            compliance_flags: Dictionary of compliance flags
            position: Where to add disclaimers ("end", "start", or "both")

        Returns:
            Tuple of (modified content, list of disclaimers added)
        """
        disclaimers_to_add = []
        disclaimers_added = []

        # Check each flag and collect required disclaimers
        if compliance_flags.get('requires_medical_disclaimer'):
            disclaimers_to_add.append(self.DISCLAIMER_TEMPLATES['medical'])
            disclaimers_added.append('medical')

        if compliance_flags.get('requires_financial_disclaimer'):
            disclaimers_to_add.append(self.DISCLAIMER_TEMPLATES['financial'])
            disclaimers_added.append('financial')

        if compliance_flags.get('requires_legal_disclaimer'):
            disclaimers_to_add.append(self.DISCLAIMER_TEMPLATES['legal'])
            disclaimers_added.append('legal')

        if compliance_flags.get('requires_supplement_disclaimer'):
            disclaimers_to_add.append(self.DISCLAIMER_TEMPLATES['supplement'])
            disclaimers_added.append('supplement')

        if compliance_flags.get('requires_weight_loss_disclaimer'):
            disclaimers_to_add.append(self.DISCLAIMER_TEMPLATES['weight_loss'])
            disclaimers_added.append('weight_loss')

        # If no disclaimers needed, return original content
        if not disclaimers_to_add:
            return content, []

        # Combine disclaimers
        disclaimer_text = "\n\n".join(disclaimers_to_add)

        # Apply based on position
        if position == "start":
            modified_content = f"{disclaimer_text}\n\n{content}"
        elif position == "both":
            modified_content = f"{disclaimer_text}\n\n{content}\n\n{disclaimer_text}"
        else:  # Default: end
            modified_content = f"{content}\n\n{disclaimer_text}"

        logger.info(f"Applied disclaimers: {disclaimers_added}")
        return modified_content, disclaimers_added

    def check_content_compliance(self, content: str, compliance_flags: Dict[str, bool]) -> Dict:
        """
        Check if content already contains required disclaimers.

        Args:
            content: Content to check
            compliance_flags: Required compliance flags

        Returns:
            Dictionary with compliance status
        """
        content_lower = content.lower()
        issues = []
        warnings = []

        # Check for medical disclaimer
        if compliance_flags.get('requires_medical_disclaimer'):
            if 'not medical advice' not in content_lower and 'consult a healthcare' not in content_lower:
                issues.append("Missing medical disclaimer")

        # Check for financial disclaimer
        if compliance_flags.get('requires_financial_disclaimer'):
            if 'not financial advice' not in content_lower and 'consult a' not in content_lower:
                issues.append("Missing financial disclaimer")

        # Check for problematic claims
        problematic_phrases = [
            'guaranteed', 'proven to cure', '100% effective', 'miracle',
            'get rich quick', 'risk-free', 'no side effects'
        ]
        for phrase in problematic_phrases:
            if phrase in content_lower:
                warnings.append(f"Potentially problematic claim: '{phrase}'")

        return {
            'compliant': len(issues) == 0,
            'issues': issues,
            'warnings': warnings
        }

    def get_industry_guidelines(self, industry: str) -> Dict:
        """
        Get content guidelines for a specific industry.

        Args:
            industry: Industry name or category

        Returns:
            Dictionary with guidelines
        """
        industry_lower = industry.lower()

        guidelines = {
            'general': {
                'avoid_phrases': ['guaranteed', 'miracle', '100%'],
                'required_qualifiers': [],
                'tone_guidance': 'Be helpful and informative'
            }
        }

        # Health/Medical
        if any(kw in industry_lower for kw in ['health', 'medical', 'supplement', 'wellness']):
            return {
                'avoid_phrases': [
                    'cure', 'treat', 'prevent disease', 'miracle',
                    'clinically proven', 'doctor recommended'
                ],
                'required_qualifiers': [
                    'consult your doctor', 'individual results may vary',
                    'not medical advice'
                ],
                'tone_guidance': (
                    'Share information helpfully but avoid making health claims. '
                    'Encourage consulting healthcare professionals.'
                ),
                'disclaimer_type': 'medical'
            }

        # Finance/Investment
        if any(kw in industry_lower for kw in ['finance', 'investment', 'trading', 'crypto']):
            return {
                'avoid_phrases': [
                    'guaranteed returns', 'risk-free', 'get rich',
                    'insider', 'sure thing', 'can\'t lose'
                ],
                'required_qualifiers': [
                    'not financial advice', 'past performance',
                    'consult a financial advisor'
                ],
                'tone_guidance': (
                    'Share information factually. Never make predictions or guarantees. '
                    'Always recommend professional financial advice.'
                ),
                'disclaimer_type': 'financial'
            }

        return guidelines['general']


# Factory function for easy initialization
def get_compliance_service(supabase_client=None) -> ComplianceService:
    """
    Get a compliance service instance.

    Args:
        supabase_client: Optional Supabase client

    Returns:
        ComplianceService instance
    """
    return ComplianceService(supabase_client)
