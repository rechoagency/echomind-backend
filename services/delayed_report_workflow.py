"""
Delayed Report Generation Workflow
Waits for opportunities to be collected, then generates and sends reports
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional
import os

logger = logging.getLogger(__name__)


class DelayedReportWorkflow:
    """Handles delayed report generation after opportunity collection"""
    
    def __init__(self, supabase_client, openai_client, email_service):
        self.supabase = supabase_client
        self.openai = openai_client
        self.email_service = email_service
    
    async def execute_workflow(
        self,
        client_id: str,
        notification_email: str,
        slack_webhook: Optional[str] = None,
        min_opportunities: int = 10,
        timeout_seconds: int = 600
    ):
        """
        Execute complete delayed report workflow
        
        Args:
            client_id: Client UUID
            notification_email: Email to send reports to
            slack_webhook: Optional Slack webhook for notifications
            min_opportunities: Minimum opportunities needed (default 50)
            timeout_seconds: Maximum wait time (default 600s = 10 minutes)
        """
        logger.info(f"🚀 Starting delayed report workflow for client {client_id}")
        start_time = datetime.now()
        
        try:
            # STEP 1: Wait for opportunities
            logger.info(f"⏳ Waiting for {min_opportunities} opportunities (timeout: {timeout_seconds}s)...")
            opportunities = await self._wait_for_opportunities(
                client_id,
                min_opportunities,
                timeout_seconds
            )
            
            if not opportunities:
                logger.error(f"❌ No opportunities found after {timeout_seconds}s")
                await self._send_failure_notification(client_id, notification_email, slack_webhook)
                return
            
            logger.info(f"✅ Found {len(opportunities)} opportunities after {(datetime.now() - start_time).total_seconds():.1f}s")
            
            # STEP 2: Generate Intelligence Report
            logger.info(f"📊 Generating Intelligence Report...")
            from services.intelligence_report_generator_v2 import IntelligenceReportGeneratorV2
            
            intelligence_generator = IntelligenceReportGeneratorV2(self.supabase, self.openai)
            intelligence_report = intelligence_generator.generate_report(client_id, opportunities)
            
            # STEP 3: Generate Sample Content
            logger.info(f"📝 Generating Sample Content Report...")
            from services.sample_content_generator_v2 import SampleContentGeneratorV2
            
            sample_generator = SampleContentGeneratorV2(self.supabase, self.openai)
            sample_content = sample_generator.generate_report(client_id, opportunities)
            
            # STEP 4: Send welcome email with reports
            logger.info(f"📧 Sending welcome email to {notification_email}...")
            
            client = self.supabase.table("clients").select("*").eq("client_id", client_id).single().execute().data
            company_name = client.get('company_name', 'Client')
            
            result = await self._send_welcome_email_with_reports(
                client_id=client_id,
                company_name=company_name,
                to_email=notification_email,
                intelligence_report=intelligence_report,
                sample_content=sample_content
            )
            
            if result['success']:
                elapsed = (datetime.now() - start_time).total_seconds() / 60
                logger.info(f"✅ Workflow completed successfully in {elapsed:.1f} minutes")
                
                # STEP 5: Slack notification (optional)
                if slack_webhook:
                    await self._send_slack_notification(
                        webhook_url=slack_webhook,
                        company_name=company_name,
                        email=notification_email,
                        opportunity_count=len(opportunities)
                    )
            else:
                logger.error(f"❌ Email sending failed: {result.get('error')}")
                await self._send_failure_notification(client_id, notification_email, slack_webhook)
        
        except Exception as e:
            logger.error(f"❌ Workflow error: {str(e)}", exc_info=True)
            await self._send_failure_notification(client_id, notification_email, slack_webhook)
    
    async def _wait_for_opportunities(
        self,
        client_id: str,
        min_count: int,
        timeout_seconds: int
    ) -> list:
        """
        Wait for opportunities to be collected
        
        Polls database every 30 seconds until min_count is reached or timeout
        """
        start_time = datetime.now()
        check_interval = 30  # Check every 30 seconds
        
        while True:
            # Check current time
            elapsed = (datetime.now() - start_time).total_seconds()
            
            if elapsed >= timeout_seconds:
                logger.warning(f"⏰ Timeout reached ({timeout_seconds}s)")
                break
            
            # Query opportunities
            try:
                response = self.supabase.table("opportunities")\
                    .select("*")\
                    .eq("client_id", client_id)\
                    .order("overall_priority", desc=True)\
                    .limit(100)\
                    .execute()
                
                opportunities = response.data
                count = len(opportunities)
                
                logger.info(f"📊 Found {count}/{min_count} opportunities (elapsed: {elapsed:.0f}s)")
                
                if count >= min_count:
                    logger.info(f"✅ Minimum threshold reached: {count} opportunities")
                    return opportunities
                
                # Wait before next check
                await asyncio.sleep(check_interval)
            
            except Exception as e:
                logger.error(f"Error checking opportunities: {e}")
                await asyncio.sleep(check_interval)
        
        # Timeout reached - return what we have
        try:
            response = self.supabase.table("opportunities")\
                .select("*")\
                .eq("client_id", client_id)\
                .order("overall_priority", desc=True)\
                .limit(100)\
                .execute()
            
            return response.data
        except Exception as e:
            logger.error(f"Error fetching opportunities after timeout: {e}")
            return []
    
    async def _send_welcome_email_with_reports(
        self,
        client_id: str,
        company_name: str,
        to_email: str,
        intelligence_report,
        sample_content
    ) -> Dict:
        """Send welcome email with Excel attachments"""
        
        # Get RESEND_API_KEY
        resend_api_key = os.getenv("RESEND_API_KEY")
        
        if not resend_api_key:
            logger.error("❌ RESEND_API_KEY not configured")
            return {"success": False, "error": "RESEND_API_KEY not configured"}
        
        # Prepare attachments
        import base64
        
        intelligence_b64 = base64.b64encode(intelligence_report.read()).decode('utf-8')
        sample_b64 = base64.b64encode(sample_content.read()).decode('utf-8')
        
        # Email HTML
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #1F4788 0%, #4472C4 100%); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0; }}
                .content {{ background: #ffffff; padding: 30px; border: 1px solid #e0e0e0; }}
                .highlight {{ background: #f0f7ff; padding: 15px; border-left: 4px solid #1F4788; margin: 20px 0; }}
                .button {{ display: inline-block; padding: 12px 24px; background: #1F4788; color: white; text-decoration: none; border-radius: 5px; margin: 10px 0; }}
                .footer {{ text-align: center; padding: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🎉 Welcome to EchoMind!</h1>
                    <p style="font-size: 18px; margin: 10px 0 0 0;">Your Reddit Marketing Automation is Live</p>
                </div>
                
                <div class="content">
                    <p>Hi {company_name} team,</p>
                    
                    <p>Your EchoMind intelligence system has completed its initial Reddit scan and analysis. We've identified high-value opportunities and generated your first content queue.</p>
                    
                    <div class="highlight">
                        <strong>📊 Initial Intelligence Report (attached)</strong><br>
                        Complete market analysis with subreddit intelligence, moderator profiles, key influencers, and strategic recommendations.
                    </div>
                    
                    <div class="highlight">
                        <strong>📝 Sample Content Queue (attached)</strong><br>
                        25 pieces of ready-to-post content matched to high-priority opportunities, complete with voice analysis and engagement predictions.
                    </div>
                    
                    <p><strong>What happens next?</strong></p>
                    <ul>
                        <li>Your dashboard is live and tracking opportunities in real-time</li>
                        <li>Our AI will generate and queue content based on your strategy settings</li>
                        <li>You'll receive notifications for high-priority opportunities</li>
                        <li>Weekly reports will be delivered automatically</li>
                    </ul>
                    
                    <p style="text-align: center; margin: 30px 0;">
                        <a href="https://echomind-dashboard.netlify.app/client-dashboard.html?client_id={client_id}" class="button">
                            View Your Dashboard →
                        </a>
                    </p>
                    
                    <p>Questions? Reply to this email or reach out to your account manager.</p>
                    
                    <p>Here's to making Reddit work for your business! 🚀</p>
                    
                    <p style="margin-top: 30px;">
                        Best regards,<br>
                        <strong>The EchoMind Team</strong>
                    </p>
                </div>
                
                <div class="footer">
                    <p>EchoMind - Reddit Marketing Automation</p>
                    <p>This is an automated message. Please do not reply to this email.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Send via Resend API
        import requests
        
        try:
            response = requests.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": "EchoMind <noreply@echomind.ai>",
                    "to": [to_email],
                    "subject": f"🎉 Welcome to EchoMind - Your Reports Are Ready!",
                    "html": html_content,
                    "attachments": [
                        {
                            "filename": f"{company_name}_Intelligence_Report.xlsx",
                            "content": intelligence_b64
                        },
                        {
                            "filename": f"{company_name}_Sample_Content_Queue.xlsx",
                            "content": sample_b64
                        }
                    ]
                }
            )
            
            if response.status_code == 200:
                email_id = response.json().get('id')
                logger.info(f"✅ Welcome email sent successfully: {email_id}")
                return {
                    "success": True,
                    "email_id": email_id,
                    "recipient": to_email
                }
            else:
                logger.error(f"❌ Resend API error {response.status_code}: {response.text}")
                return {
                    "success": False,
                    "error": f"Resend API error: {response.status_code}"
                }
        
        except Exception as e:
            logger.error(f"❌ Email sending exception: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def _send_slack_notification(
        self,
        webhook_url: str,
        company_name: str,
        email: str,
        opportunity_count: int
    ):
        """Send Slack notification"""
        import requests
        
        try:
            message = {
                "text": f"✅ *Welcome Reports Delivered*",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*{company_name}* onboarding complete!"
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Email:*\n{email}"},
                            {"type": "mrkdwn", "text": f"*Opportunities:*\n{opportunity_count}"}
                        ]
                    }
                ]
            }
            
            response = requests.post(webhook_url, json=message)
            
            if response.status_code == 200:
                logger.info(f"✅ Slack notification sent")
            else:
                logger.warning(f"⚠️ Slack notification failed: {response.status_code}")
        
        except Exception as e:
            logger.warning(f"⚠️ Slack notification error: {e}")
    
    async def _send_failure_notification(
        self,
        client_id: str,
        email: str,
        slack_webhook: Optional[str]
    ):
        """Notify about workflow failure"""
        logger.error(f"❌ Sending failure notification for client {client_id}")
        
        # TODO: Implement failure notification email
        # For now, just log it
        logger.error(f"Failed to generate reports for {email}")
        
        if slack_webhook:
            try:
                import requests
                requests.post(slack_webhook, json={
                    "text": f"⚠️ Report generation failed for client {client_id}"
                })
            except:
                pass
