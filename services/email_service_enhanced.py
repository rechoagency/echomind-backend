"""
Enhanced Email Service with Retry Logic
Robust email delivery with automatic retries and detailed logging
"""
import os
import logging
import asyncio
from typing import List, Optional, Dict
from datetime import datetime

logger = logging.getLogger(__name__)

class EmailServiceEnhanced:
    """Enhanced email service with retry logic and validation"""
    
    def __init__(self):
        self.api_key = os.getenv("RESEND_API_KEY")
        self.from_email = os.getenv("RESEND_FROM_EMAIL", "onboarding@echomind.ai")
        self.from_name = os.getenv("RESEND_FROM_NAME", "EchoMind")
        self.enabled = bool(self.api_key)
        self.initialization_error = None
        self.resend_module = None
        
        if not self.enabled:
            logger.error("❌ CRITICAL: RESEND_API_KEY not configured")
            logger.error("👉 Add RESEND_API_KEY to Railway environment variables")
            logger.error("👉 Get your API key from https://resend.com/api-keys")
        else:
            try:
                # Import resend only when needed (lazy import)
                import resend
                self.resend_module = resend
                resend.api_key = self.api_key
                logger.info("✅ Email service initialized")
                logger.info(f"   From: {self.from_name} <{self.from_email}>")
            except ImportError:
                self.initialization_error = "resend library not installed (pip install resend)"
                self.enabled = False
                logger.warning("⚠️ Email service: resend library not installed")
                logger.info("   Will install on next deployment")
            except Exception as e:
                self.initialization_error = str(e)
                self.enabled = False
                logger.error(f"❌ Email service initialization failed: {str(e)}")
                logger.error("   Check RESEND_API_KEY is valid")
    
    async def send_with_retry(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        attachments: Optional[List[Dict]] = None,
        max_retries: int = 3,
        retry_delay: int = 5
    ) -> Dict:
        """
        Send email with automatic retry logic
        
        Args:
            to_email: Recipient email
            subject: Email subject
            html_content: HTML email content
            attachments: List of attachments (optional)
            max_retries: Maximum retry attempts
            retry_delay: Delay between retries (seconds)
        
        Returns:
            Dict with send results
        """
        if not self.enabled:
            error_msg = "Email service not configured - RESEND_API_KEY missing or resend not installed"
            logger.error(f"❌ {error_msg}")
            return {
                "success": False,
                "error": error_msg,
                "fix": "Add RESEND_API_KEY to Railway environment variables and ensure resend is in requirements.txt"
            }
        
        if not self.resend_module:
            return {
                "success": False,
                "error": "Resend module not initialized",
                "fix": "Install resend library: pip install resend"
            }
        
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"📧 Attempting to send email (attempt {attempt}/{max_retries})")
                logger.info(f"   To: {to_email}")
                logger.info(f"   Subject: {subject}")
                
                params = {
                    "from": self.from_email,
                    "to": to_email,
                    "subject": subject,
                    "html": html_content
                }
                
                if attachments:
                    params["attachments"] = attachments
                    logger.info(f"   Attachments: {len(attachments)} files")
                
                # Send email using resend module
                response = self.resend_module.Emails.send(params)
                
                if response.get("id"):
                    logger.info(f"✅ Email sent successfully!")
                    logger.info(f"   Email ID: {response['id']}")
                    logger.info(f"   Attempt: {attempt}/{max_retries}")
                    
                    return {
                        "success": True,
                        "email_id": response["id"],
                        "to": to_email,
                        "subject": subject,
                        "attempts": attempt,
                        "sent_at": datetime.now().isoformat()
                    }
                else:
                    raise Exception(f"Resend API returned no ID: {response}")
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Email send failed (attempt {attempt}/{max_retries}): {error_msg}")
                
                if attempt < max_retries:
                    logger.info(f"⏳ Retrying in {retry_delay} seconds...")
                    await asyncio.sleep(retry_delay)
                else:
                    logger.error(f"❌ Email send failed after {max_retries} attempts")
                    return {
                        "success": False,
                        "error": error_msg,
                        "to": to_email,
                        "subject": subject,
                        "attempts": max_retries,
                        "fix": "Check RESEND_API_KEY is valid and domain is verified"
                    }
        
        return {
            "success": False,
            "error": "Max retries exceeded",
            "attempts": max_retries
        }
    
    def validate_configuration(self) -> Dict:
        """Validate email service configuration"""
        issues = []
        
        if not self.api_key:
            issues.append({
                "severity": "CRITICAL",
                "issue": "RESEND_API_KEY not set",
                "fix": "Add RESEND_API_KEY to Railway environment variables",
                "url": "https://resend.com/api-keys"
            })
        elif not self.api_key.startswith("re_"):
            issues.append({
                "severity": "WARNING",
                "issue": "RESEND_API_KEY format looks incorrect",
                "fix": "Resend API keys should start with 're_'",
                "url": "https://resend.com/api-keys"
            })
        
        if self.initialization_error:
            issues.append({
                "severity": "CRITICAL" if "not installed" not in self.initialization_error else "WARNING",
                "issue": f"Email service failed to initialize: {self.initialization_error}",
                "fix": "Check RESEND_API_KEY is valid and resend library is installed",
                "url": "https://resend.com/api-keys"
            })
        
        if not os.getenv("RESEND_FROM_EMAIL"):
            issues.append({
                "severity": "WARNING",
                "issue": "RESEND_FROM_EMAIL not set (using default: onboarding@echomind.ai)",
                "fix": "Set RESEND_FROM_EMAIL to your verified domain email",
                "url": "https://resend.com/domains"
            })
        
        return {
            "enabled": self.enabled,
            "configured": len([i for i in issues if i["severity"] == "CRITICAL"]) == 0,
            "issues": issues,
            "from_email": self.from_email,
            "from_name": self.from_name
        }
    
    def get_setup_instructions(self) -> Dict:
        """Get setup instructions for email service"""
        return {
            "enabled": self.enabled,
            "steps": [
                "1. Visit https://resend.com and sign up/login",
                "2. Go to API Keys section",
                "3. Create a new API key",
                "4. Copy the API key (starts with 're_')",
                "5. Add to Railway: RESEND_API_KEY=<your_key>",
                "6. Ensure resend is in requirements.txt",
                "7. (Optional) Add custom domain in Resend",
                "8. (Optional) Set RESEND_FROM_EMAIL=noreply@yourdomain.com",
                "9. Redeploy backend",
                "10. Test email delivery with dummy client"
            ],
            "free_tier": "100 emails/day (sufficient for testing)",
            "paid_tier": "$0.001 per email (very affordable)"
        }

# Singleton instance
email_service = EmailServiceEnhanced()

# Export for easy import
__all__ = ["email_service", "EmailServiceEnhanced"]
