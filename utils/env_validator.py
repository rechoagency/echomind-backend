"""
Environment Variable Validator
Validates all required API keys and configuration at startup
"""
import os
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

class EnvironmentValidator:
    """Validates environment variables and API keys at startup"""
    
    REQUIRED_VARS = {
        "SUPABASE_URL": {
            "description": "Supabase project URL",
            "critical": True,
            "example": "https://xxxxxxxxxxxx.supabase.co"
        },
        "SUPABASE_SERVICE_ROLE_KEY": {
            "description": "Supabase service role key",
            "critical": True,
            "example": "eyJ..."
        },
        "OPENAI_API_KEY": {
            "description": "OpenAI API key for content generation",
            "critical": True,
            "example": "sk-..."
        },
        "RESEND_API_KEY": {
            "description": "Resend API key for email delivery",
            "critical": True,
            "example": "re_..."
        },
        "REDDIT_CLIENT_ID": {
            "description": "Reddit app client ID",
            "critical": True,
            "example": "xxxxxxxxxxxxx"
        },
        "REDDIT_CLIENT_SECRET": {
            "description": "Reddit app client secret",
            "critical": True,
            "example": "xxxxxxxxxxxxx"
        },
        "REDDIT_USER_AGENT": {
            "description": "Reddit API user agent",
            "critical": True,
            "example": "platform:app_name:v1.0 (by /u/username)"
        }
    }
    
    OPTIONAL_VARS = {
        "REDDIT_PRO_API_KEY": {
            "description": "Reddit Pro API key (optional)",
            "critical": False,
            "example": "rp_..."
        },
        "SLACK_WEBHOOK_URL": {
            "description": "Slack webhook for notifications (optional)",
            "critical": False,
            "example": "https://hooks.slack.com/services/..."
        }
    }
    
    @classmethod
    def validate_all(cls) -> Tuple[bool, Dict[str, List[str]]]:
        """
        Validate all environment variables
        
        Returns:
            Tuple of (is_valid, results_dict)
            results_dict contains 'missing', 'present', 'warnings'
        """
        results = {
            "missing": [],
            "present": [],
            "warnings": [],
            "optional_missing": []
        }
        
        # Check required variables
        for var_name, var_info in cls.REQUIRED_VARS.items():
            value = os.getenv(var_name)
            
            if not value:
                results["missing"].append({
                    "name": var_name,
                    "description": var_info["description"],
                    "example": var_info["example"],
                    "critical": var_info["critical"]
                })
                logger.error(f"❌ MISSING CRITICAL: {var_name} - {var_info['description']}")
            else:
                results["present"].append(var_name)
                logger.info(f"✅ Found: {var_name}")
                
                # Basic format validation
                if var_name == "OPENAI_API_KEY" and not value.startswith("sk-"):
                    results["warnings"].append(f"{var_name} should start with 'sk-'")
                    
                if var_name == "RESEND_API_KEY" and not value.startswith("re_"):
                    results["warnings"].append(f"{var_name} should start with 're_'")
                    
                if var_name == "SUPABASE_URL" and not value.startswith("https://"):
                    results["warnings"].append(f"{var_name} should start with 'https://'")
        
        # Check optional variables
        for var_name, var_info in cls.OPTIONAL_VARS.items():
            value = os.getenv(var_name)
            
            if not value:
                results["optional_missing"].append({
                    "name": var_name,
                    "description": var_info["description"],
                    "example": var_info["example"]
                })
                logger.warning(f"⚠️ OPTIONAL MISSING: {var_name} - {var_info['description']}")
            else:
                results["present"].append(var_name)
                logger.info(f"✅ Found (optional): {var_name}")
        
        is_valid = len(results["missing"]) == 0
        
        return is_valid, results
    
    @classmethod
    def get_validation_report(cls) -> str:
        """Get a formatted validation report"""
        is_valid, results = cls.validate_all()
        
        report = ["=" * 80]
        report.append("🔍 ENVIRONMENT VARIABLE VALIDATION REPORT")
        report.append("=" * 80)
        
        # Present variables
        if results["present"]:
            report.append(f"\n✅ PRESENT ({len(results['present'])} variables):")
            for var in results["present"]:
                report.append(f"   • {var}")
        
        # Missing critical variables
        if results["missing"]:
            report.append(f"\n❌ MISSING CRITICAL ({len(results['missing'])} variables):")
            for var in results["missing"]:
                report.append(f"   • {var['name']}")
                report.append(f"     Description: {var['description']}")
                report.append(f"     Example: {var['example']}")
        
        # Missing optional variables
        if results["optional_missing"]:
            report.append(f"\n⚠️ MISSING OPTIONAL ({len(results['optional_missing'])} variables):")
            for var in results["optional_missing"]:
                report.append(f"   • {var['name']}")
                report.append(f"     Description: {var['description']}")
        
        # Warnings
        if results["warnings"]:
            report.append(f"\n⚠️ WARNINGS ({len(results['warnings'])} issues):")
            for warning in results["warnings"]:
                report.append(f"   • {warning}")
        
        # Overall status
        report.append("\n" + "=" * 80)
        if is_valid:
            report.append("✅ VALIDATION PASSED - All critical variables present")
        else:
            report.append("❌ VALIDATION FAILED - Missing critical variables")
            report.append("   Add missing variables to Railway and redeploy")
        report.append("=" * 80)
        
        return "\n".join(report)
    
    @classmethod
    def validate_or_exit(cls):
        """Validate environment variables and exit if critical ones are missing"""
        is_valid, results = cls.validate_all()
        
        print(cls.get_validation_report())
        
        if not is_valid:
            logger.critical("❌ CRITICAL: Cannot start application - missing required environment variables")
            logger.critical("👉 Add missing variables to Railway environment and redeploy")
            raise SystemExit(1)
        
        return True

# Quick validation function
def validate_env() -> bool:
    """Quick validation - returns True if all required vars present"""
    validator = EnvironmentValidator()
    is_valid, _ = validator.validate_all()
    return is_valid

if __name__ == "__main__":
    # Test validation
    EnvironmentValidator.validate_or_exit()
