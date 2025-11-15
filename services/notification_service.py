"""
Notification Service - Email & Slack Integration
Sends rich onboarding completion notifications with analysis + sample content
"""

import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json
import requests
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class NotificationService:
    """Handles email and Slack notifications for client onboarding completion"""
    
    def __init__(self, openai_api_key: str):
        self.openai = OpenAI(api_key=openai_api_key)
        self.resend_api_key = os.getenv("RESEND_API_KEY")
    
    async def send_onboarding_complete_notification(
        self,
        client: Dict,
        auto_identify_results: Dict,
        opportunities: List[Dict],
        calendar_items: List[Dict],
        product_matches: List[Dict]
    ) -> Dict[str, Any]:
        """
        Send comprehensive onboarding completion notification via Email + Slack
        
        Includes:
        1. Initial analysis summary (subreddits, keywords, opportunity overview)
        2. Sample content output (what they'll receive Monday/Thursday)
        3. Next steps and dashboard link
        
        Args:
            client: Client record from database
            auto_identify_results: Subreddits/keywords discovered
            opportunities: Top scored opportunities
            calendar_items: Generated calendar entries
            product_matches: Product matchback results
            
        Returns:
            Success status for email and Slack
        """
        try:
            # Generate comprehensive analysis
            analysis = await self._generate_initial_analysis(
                client,
                auto_identify_results,
                opportunities,
                calendar_items,
                product_matches
            )
            
            # Generate sample content preview
            sample_content = await self._generate_sample_content(
                client,
                opportunities[:5],
                calendar_items[:5]
            )
            
            # Send email
            email_result = await self._send_email_notification(
                client,
                analysis,
                sample_content
            )
            
            # Send Slack
            slack_result = await self._send_slack_notification(
                client,
                analysis,
                sample_content
            )
            
            return {
                "success": True,
                "email": email_result,
                "slack": slack_result,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Notification error for {client.get('company_name')}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _generate_initial_analysis(
        self,
        client: Dict,
        auto_identify: Dict,
        opportunities: List[Dict],
        calendar: List[Dict],
        products: List[Dict]
    ) -> Dict[str, str]:
        """
        Generate comprehensive initial analysis using AI
        
        Returns formatted sections for email/Slack
        """
        try:
            # Prepare data for AI analysis
            subreddits = auto_identify.get("subreddits", [])
            keywords = auto_identify.get("keywords", [])
            
            # Create analysis prompt
            # Build subreddit and keyword lists
            subreddit_list = "\n".join([f"- r/{s}" for s in subreddits[:10]])
            keyword_list = "\n".join([f"- {k}" for k in keywords[:15]])
            
            prompt = f"""Generate a comprehensive initial analysis report for {client.get('company_name')}.

COMPANY INFO:
- Industry: {client.get('industry')}
- Product: {client.get('primary_product_service')}
- Target Audience: {client.get('target_audience')}
- Pain Points Addressed: {client.get('pain_points_addressed')}

AUTO-DISCOVERED DATA:
Subreddits ({len(subreddits)}):
{subreddit_list}

Keywords ({len(keywords)}):
{keyword_list}

OPPORTUNITY OVERVIEW:
- Total opportunities found: {len(opportunities)}
- Average opportunity score: {sum([o.get('opportunity_score', 0) for o in opportunities]) / max(len(opportunities), 1):.1f}/100
- Urgent priorities: {len([o for o in opportunities if o.get('priority') == 'URGENT'])}
- High priorities: {len([o for o in opportunities if o.get('priority') == 'HIGH'])}

CONTENT CALENDAR:
- Posting frequency: {client.get('posting_frequency', 'weekly')}
- Calendar entries generated: {len(calendar)}
- Next post scheduled: {calendar[0].get('date') if calendar else 'TBD'}

Create a professional analysis report with these sections:

1. EXECUTIVE SUMMARY (3-4 sentences)
   - What we discovered about their market presence
   - Key opportunities identified
   - Expected impact

2. SUBREDDIT STRATEGY (bullet points)
   - Top 5 subreddits and why they matter
   - Community engagement potential
   - Strategic positioning recommendations

3. KEYWORD INTELLIGENCE (bullet points)
   - Top 5 keywords with highest opportunity potential
   - Search intent analysis
   - Content strategy recommendations

4. OPPORTUNITY BREAKDOWN (structured)
   - Urgent priorities requiring immediate attention
   - High-value opportunities for this week
   - Long-term engagement potential

5. NEXT STEPS (actionable items)
   - What to expect Monday/Thursday mornings
   - How to review and approve content
   - Dashboard usage tips

Format in clean, professional business language. Use markdown formatting.
"""
            
            response = self.openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1500
            )
            
            analysis_text = response.choices[0].message.content.strip()
            
            # Parse into sections
            sections = {
                "executive_summary": self._extract_section(analysis_text, "EXECUTIVE SUMMARY"),
                "subreddit_strategy": self._extract_section(analysis_text, "SUBREDDIT STRATEGY"),
                "keyword_intelligence": self._extract_section(analysis_text, "KEYWORD INTELLIGENCE"),
                "opportunity_breakdown": self._extract_section(analysis_text, "OPPORTUNITY BREAKDOWN"),
                "next_steps": self._extract_section(analysis_text, "NEXT STEPS"),
                "full_text": analysis_text
            }
            
            return sections
            
        except Exception as e:
            logger.error(f"Analysis generation error: {str(e)}")
            return {
                "executive_summary": "Analysis in progress...",
                "full_text": "Detailed analysis will be available shortly."
            }
    
    async def _generate_sample_content(
        self,
        client: Dict,
        opportunities: List[Dict],
        calendar: List[Dict]
    ) -> Dict[str, Any]:
        """
        Generate sample content output (what they'll receive Mon/Thu)
        
        Returns formatted sample report
        """
        try:
            # Select best opportunity for sample
            top_opp = opportunities[0] if opportunities else None
            
            if not top_opp:
                return {
                    "sample_available": False,
                    "message": "Sample content will be generated once opportunities are detected."
                }
            
            # Generate sample response using AI
            prompt = f"""Generate a sample Reddit response for this opportunity:

COMPANY: {client.get('company_name')}
PRODUCT: {client.get('primary_product_service')}
BRAND VOICE: {client.get('brand_voice_guidelines', 'Professional and helpful')}

REDDIT POST:
Subreddit: r/{top_opp.get('subreddit')}
Title: {top_opp.get('thread_title')}
Preview: {top_opp.get('content_preview', '')[:300]}

OPPORTUNITY SCORE: {top_opp.get('opportunity_score', 0)}/100
Priority: {top_opp.get('priority')}

Generate a natural, helpful Reddit comment that:
1. Addresses the user's pain point directly
2. Provides genuine value (not just promotion)
3. Naturally mentions the product as a solution
4. Maintains brand voice
5. Encourages engagement

Format as a ready-to-post Reddit comment (2-3 paragraphs).
"""
            
            response = self.openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500
            )
            
            sample_response = response.choices[0].message.content.strip()
            
            return {
                "sample_available": True,
                "opportunity": {
                    "subreddit": top_opp.get('subreddit'),
                    "title": top_opp.get('thread_title'),
                    "score": top_opp.get('opportunity_score'),
                    "priority": top_opp.get('priority'),
                    "url": f"https://reddit.com/r/{top_opp.get('subreddit')}/comments/{top_opp.get('post_id')}"
                },
                "suggested_response": sample_response,
                "estimated_engagement": top_opp.get('estimated_engagement', 'Medium'),
                "product_match": top_opp.get('product_matches', [{}])[0].get('product_name') if top_opp.get('product_matches') else None,
                "posting_time": calendar[0].get('date') if calendar else 'TBD'
            }
            
        except Exception as e:
            logger.error(f"Sample content generation error: {str(e)}")
            return {
                "sample_available": False,
                "error": str(e)
            }
    
    async def _send_email_notification(
        self,
        client: Dict,
        analysis: Dict,
        sample: Dict
    ) -> Dict:
        """Send formatted email via Resend (easiest, most reliable)"""
        try:
            email = client.get("notification_email") or client.get("primary_contact_email")
            
            if not email:
                logger.warning(f"No email provided for {client.get('company_name')}")
                return {"success": False, "reason": "No email address"}
            
            # Build HTML email
            html_content = self._build_email_html(client, analysis, sample)
            
            # If Resend configured, send email
            if self.resend_api_key:
                headers = {
                    "Authorization": f"Bearer {self.resend_api_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "from": "EchoMind <onboarding@resend.dev>",
                    "to": [email],
                    "subject": f"🎉 EchoMind Setup Complete for {client.get('company_name')}",
                    "html": html_content
                }
                
                response = requests.post(
                    "https://api.resend.com/emails",
                    headers=headers,
                    json=payload,
                    timeout=10
                )
                
                if response.status_code in [200, 201]:
                    logger.info(f"✅ Email sent to {email} via Resend")
                    return {"success": True, "email": email, "provider": "resend"}
                else:
                    logger.error(f"Resend error: {response.status_code} - {response.text}")
                    return {"success": False, "error": response.text}
            
            else:
                # Log email content (for testing without Resend)
                logger.info(f"""
================================================================================
📧 EMAIL NOTIFICATION (Resend not configured - logging only)
================================================================================
TO: {email}
SUBJECT: 🎉 EchoMind Setup Complete for {client.get('company_name')}

{analysis.get('full_text', 'Analysis in progress...')}

--- SAMPLE CONTENT ---
{json.dumps(sample, indent=2)}

Dashboard: https://echomind-dashboard.netlify.app/dashboard.html?client_id={client.get('id')}
================================================================================
                """)
                return {"success": True, "mode": "logged", "email": email}
            
        except Exception as e:
            logger.error(f"Email send error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def _send_slack_notification(
        self,
        client: Dict,
        analysis: Dict,
        sample: Dict
    ) -> Dict:
        """Send formatted message to Slack webhook"""
        try:
            webhook_url = client.get("slack_webhook_url")
            
            if not webhook_url:
                logger.info(f"No Slack webhook for {client.get('company_name')}")
                return {"success": False, "reason": "No webhook URL"}
            
            # Build Slack blocks
            blocks = self._build_slack_blocks(client, analysis, sample)
            
            payload = {
                "text": f"🎉 EchoMind Setup Complete: {client.get('company_name')}",
                "blocks": blocks
            }
            
            response = requests.post(
                webhook_url,
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Slack notification sent for {client.get('company_name')}")
                return {"success": True}
            else:
                logger.error(f"Slack error: {response.status_code} - {response.text}")
                return {"success": False, "error": response.text}
            
        except Exception as e:
            logger.error(f"Slack send error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _build_email_html(self, client: Dict, analysis: Dict, sample: Dict) -> str:
        """Build rich HTML email"""
        
        # Prepare analysis HTML (avoid backslash in f-string)
        analysis_html = analysis.get('full_text', '').replace('\n', '<br>')
        
        sample_html = ""
        if sample.get("sample_available"):
            opp = sample.get("opportunity", {})
            sample_html = f"""
            <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="color: #667eea; margin-top: 0;">📝 Sample Content Preview</h3>
                
                <div style="background: white; padding: 15px; border-radius: 6px; margin: 15px 0;">
                    <p style="margin: 5px 0;"><strong>Opportunity:</strong> <span style="color: #e74c3c;">●</span> {opp.get('priority')} Priority</p>
                    <p style="margin: 5px 0;"><strong>Subreddit:</strong> r/{opp.get('subreddit')}</p>
                    <p style="margin: 5px 0;"><strong>Post:</strong> {opp.get('title', '')[:100]}...</p>
                    <p style="margin: 5px 0;"><strong>Score:</strong> {opp.get('score')}/100</p>
                    <p style="margin: 5px 0;"><strong>Scheduled:</strong> {sample.get('posting_time')}</p>
                </div>
                
                <div style="background: white; padding: 15px; border-radius: 6px; border-left: 4px solid #667eea;">
                    <p style="font-weight: bold; margin-top: 0;">Suggested Response:</p>
                    <p style="line-height: 1.6; white-space: pre-wrap;">{sample.get('suggested_response', '')}</p>
                </div>
                
                <p style="margin-top: 15px; font-size: 14px; color: #666;">
                    <strong>💡 This is what you'll receive every Monday & Thursday morning</strong><br>
                    Review → Approve → We post on your behalf
                </p>
            </div>
            """
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                h1 {{ color: #667eea; }}
                h2 {{ color: #764ba2; margin-top: 30px; }}
                .stats {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; }}
                .section {{ margin: 20px 0; }}
                .btn {{ display: inline-block; background: #667eea; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🎉 Welcome to EchoMind, {client.get('company_name')}!</h1>
                
                <div class="stats">
                    <p style="font-size: 18px; margin: 0;"><strong>Your Reddit Intelligence System is Live</strong></p>
                    <p style="margin: 10px 0 0 0;">Automatic monitoring started • AI analysis complete • Content calendar generated</p>
                </div>
                
                <div class="section">
                    <h2>📊 Initial Analysis Summary</h2>
                    {analysis_html}
                </div>
                
                {sample_html}
                
                <div class="section">
                    <h2>🚀 What Happens Next</h2>
                    <ul>
                        <li><strong>Every Monday & Thursday at 8am:</strong> You'll receive an email like this with top opportunities and suggested responses</li>
                        <li><strong>Review in dashboard:</strong> Click the link below to see all opportunities, approve content, and track performance</li>
                        <li><strong>We handle posting:</strong> Once you approve, our system posts on your behalf at optimal times</li>
                        <li><strong>Continuous monitoring:</strong> EchoMind scans Reddit 24/7 for new opportunities</li>
                    </ul>
                </div>
                
                <a href="https://echomind-dashboard.netlify.app/dashboard.html?client_id={client.get('id')}" class="btn">
                    View Dashboard →
                </a>
                
                <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; font-size: 14px; color: #666;">
                    <p>Questions? Reply to this email or visit your dashboard.</p>
                    <p style="margin-top: 20px;">
                        <strong>EchoMind</strong><br>
                        Maximize your organic visibility on Reddit
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _build_slack_blocks(self, client: Dict, analysis: Dict, sample: Dict) -> List[Dict]:
        """Build Slack message blocks"""
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🎉 EchoMind Setup Complete: {client.get('company_name')}"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Your Reddit intelligence system is now live and monitoring {len(client.get('subreddits', []))} subreddits for opportunities.*"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Executive Summary*\n" + str(analysis.get('executive_summary', 'Analysis in progress...'))
                }
            }
        ]
        
        # Add sample content if available
        if sample.get("sample_available"):
            opp = sample.get("opportunity", {})
            blocks.extend([
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": ("*📝 Sample Content Preview*\n\n" +
                                 f"*Opportunity:* {opp.get('priority')} Priority ({opp.get('score')}/100)" + "\n" +
                                 f"*Subreddit:* r/{opp.get('subreddit')}" + "\n" +
                                 f"*Post:* {opp.get('title', '')[:100]}..." + "\n" +
                                 f"*Scheduled:* {sample.get('posting_time')}")
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Suggested Response:*" + "\n```" + str(sample.get('suggested_response', '')[:500]) + "```"
                    }
                }
            ])
        
        # Add dashboard link
        blocks.extend([
            {
                "type": "divider"
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "View Dashboard"
                        },
                        "url": f"https://echomind-dashboard.netlify.app/dashboard.html?client_id={client.get('id')}",
                        "style": "primary"
                    }
                ]
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "💡 *You'll receive reports like this every Monday & Thursday at 8am*"
                    }
                ]
            }
        ])
        
        return blocks
    
    def _extract_section(self, text: str, section_name: str) -> str:
        """Extract a specific section from markdown text"""
        try:
            # Find section by heading
            lines = text.split('\n')
            section_lines = []
            capturing = False
            
            for line in lines:
                if section_name.upper() in line.upper():
                    capturing = True
                    continue
                elif capturing and line.startswith('#'):
                    # Next section started
                    break
                elif capturing:
                    section_lines.append(line)
            
            return '\n'.join(section_lines).strip()
        except:
            return text[:500]  # Fallback to first 500 chars
