"""
Weekly Report Generator Worker
Sends comprehensive Monday/Thursday 7am EST reports to all active clients
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from supabase import create_client, Client
import openai

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WeeklyReportGenerator:
    """Generates and sends weekly opportunity reports to clients"""
    
    def __init__(self):
        """Initialize with Supabase and OpenAI clients"""
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_ROLE_KEY")  # Fixed: use SERVICE_ROLE_KEY
        )
        self.openai = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        logger.info("Weekly Report Generator initialized")
    
    async def send_reports_to_all_clients(self) -> Dict[str, Any]:
        """
        Send weekly reports to all active clients
        
        Returns:
            Summary of reports sent
        """
        logger.info("=" * 70)
        logger.info("WEEKLY REPORT GENERATION STARTED")
        logger.info("=" * 70)
        
        start_time = datetime.utcnow()
        
        # Fetch all active clients
        clients_response = self.supabase.table("clients").select("*").execute()
        clients = clients_response.data
        
        results = {
            "started_at": start_time.isoformat(),
            "total_clients": len(clients),
            "reports_sent": 0,
            "reports_failed": 0,
            "clients_processed": []
        }
        
        for client in clients:
            try:
                client_id = client.get("client_id")
                company_name = client.get("company_name", "Unknown")
                
                logger.info(f"\n📊 Processing report for: {company_name}")
                
                # Generate and send report
                report_result = await self._generate_and_send_report(client)
                
                if report_result.get("success"):
                    results["reports_sent"] += 1
                    logger.info(f"✅ Report sent to {company_name}")
                else:
                    results["reports_failed"] += 1
                    logger.error(f"❌ Report failed for {company_name}: {report_result.get('error')}")
                
                results["clients_processed"].append({
                    "client_id": client_id,
                    "company_name": company_name,
                    "success": report_result.get("success"),
                    "error": report_result.get("error")
                })
                
            except Exception as e:
                logger.error(f"❌ Error processing {client.get('company_name')}: {str(e)}")
                results["reports_failed"] += 1
        
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        results["completed_at"] = end_time.isoformat()
        results["duration_seconds"] = duration
        
        logger.info("\n" + "=" * 70)
        logger.info("WEEKLY REPORT GENERATION COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Total clients: {results['total_clients']}")
        logger.info(f"Reports sent: {results['reports_sent']}")
        logger.info(f"Reports failed: {results['reports_failed']}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info("=" * 70)
        
        return results
    
    async def _generate_and_send_report(self, client: Dict) -> Dict[str, Any]:
        """
        Generate and send weekly report for a single client
        
        Args:
            client: Client data dictionary
            
        Returns:
            Result of report generation and sending
        """
        try:
            client_id = client.get("client_id")
            
            # Fetch opportunities from past week
            week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()
            opportunities = self._fetch_weekly_opportunities(client_id, week_ago)
            
            # If no opportunities, send "no activity" report
            if not opportunities:
                return await self._send_no_activity_report(client)
            
            # Generate weekly analysis
            analysis = await self._generate_weekly_analysis(client, opportunities)
            
            # Get top opportunities by tier
            top_opportunities = self._get_top_opportunities_by_tier(opportunities)
            
            # Send report via email/Slack
            send_result = await self._send_report(client, opportunities, analysis, top_opportunities)
            
            return {
                "success": True,
                "client_id": client_id,
                "opportunities_count": len(opportunities),
                "send_result": send_result
            }
            
        except Exception as e:
            logger.error(f"Error generating report for {client.get('company_name')}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _fetch_weekly_opportunities(self, client_id: str, since: str) -> List[Dict]:
        """Fetch opportunities discovered in the past week"""
        try:
            response = self.supabase.table("opportunities")\
                .select("*")\
                .eq("client_id", client_id)\
                .gte("created_at", since)\
                .order("combined_score", desc=True)\
                .execute()
            
            return response.data
        except Exception as e:
            logger.error(f"Error fetching opportunities: {str(e)}")
            return []
    
    async def _generate_weekly_analysis(self, client: Dict, opportunities: List[Dict]) -> str:
        """Generate AI analysis of the week's opportunities"""
        try:
            # Calculate stats
            total_opps = len(opportunities)
            avg_score = sum([o.get("combined_score", 0) for o in opportunities]) / max(total_opps, 1)
            
            platinum = [o for o in opportunities if o.get("priority_tier") == "Platinum"]
            gold = [o for o in opportunities if o.get("priority_tier") == "Gold"]
            silver = [o for o in opportunities if o.get("priority_tier") == "Silver"]
            
            # Get subreddit distribution
            subreddit_counts = {}
            for opp in opportunities:
                sub = opp.get("subreddit")
                subreddit_counts[sub] = subreddit_counts.get(sub, 0) + 1
            
            top_subreddits = sorted(subreddit_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            
            prompt = f"""Generate a concise weekly analysis for {client.get('company_name')}'s Reddit opportunities.

WEEK SUMMARY:
- Total opportunities discovered: {total_opps}
- Average opportunity score: {avg_score:.1f}/100
- Platinum tier: {len(platinum)} (urgent action required)
- Gold tier: {len(gold)} (high priority)
- Silver tier: {len(silver)} (monitor)

TOP SUBREDDITS THIS WEEK:
{chr(10).join([f"- r/{sub}: {count} opportunities" for sub, count in top_subreddits])}

SAMPLE OPPORTUNITIES:
{chr(10).join([f"- r/{o.get('subreddit')}: {o.get('post_title', '')[:100]}... (Score: {o.get('combined_score', 0)}/100)" for o in opportunities[:3]])}

Generate a 2-3 paragraph analysis covering:
1. Key trends this week (what types of discussions are happening)
2. Strategic recommendations (which opportunities to prioritize)
3. Expected impact (engagement potential, brand building)

Keep it actionable and business-focused. Use markdown formatting."""

            response = self.openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=500
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error generating analysis: {str(e)}")
            return f"Analysis unavailable. {total_opps} opportunities discovered this week."
    
    def _get_top_opportunities_by_tier(self, opportunities: List[Dict]) -> Dict[str, List[Dict]]:
        """Organize opportunities by priority tier"""
        result = {
            "Platinum": [],
            "Gold": [],
            "Silver": []
        }
        
        for opp in opportunities:
            tier = opp.get("priority_tier", "Silver")
            if tier in result:
                result[tier].append(opp)
        
        # Limit to top 5 per tier
        for tier in result:
            result[tier] = result[tier][:5]
        
        return result
    
    async def _send_report(
        self,
        client: Dict,
        opportunities: List[Dict],
        analysis: str,
        top_opportunities: Dict[str, List[Dict]]
    ) -> Dict[str, Any]:
        """Send the weekly report via email/Slack"""
        try:
            # Import notification service
            from services.notification_service import NotificationService
            
            notification_service = NotificationService(
                supabase_client=self.supabase,
                openai_api_key=os.getenv("OPENAI_API_KEY")
            )
            
            # Build email HTML
            email_html = self._build_report_email(client, opportunities, analysis, top_opportunities)
            
            # Send via Resend
            import httpx
            
            email = client.get("email")
            if not email:
                logger.warning(f"No email for {client.get('company_name')}")
                return {"success": False, "error": "No email address"}
            
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {os.getenv('RESEND_API_KEY')}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": "EchoMind Reports <reports@echomind.ai>",
                    "to": [email],
                    "subject": f"📊 Weekly Reddit Report: {len(opportunities)} Opportunities - {client.get('company_name')}",
                    "html": email_html
                }
            )
            
            if response.status_code == 200:
                logger.info(f"✅ Email sent to {email}")
                return {"success": True, "email": email}
            else:
                logger.error(f"Resend error: {response.status_code} - {response.text}")
                return {"success": False, "error": f"Resend error: {response.status_code}"}
                
        except Exception as e:
            logger.error(f"Error sending report: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def _send_no_activity_report(self, client: Dict) -> Dict[str, Any]:
        """Send report when no opportunities were found this week"""
        try:
            import httpx
            
            email = client.get("email")
            if not email:
                return {"success": False, "error": "No email address"}
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #667eea;">📊 Weekly Report: {client.get('company_name')}</h1>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p style="font-size: 18px; margin: 0;"><strong>No new opportunities this week</strong></p>
                    <p style="margin: 10px 0 0 0; color: #666;">Our workers are continuously monitoring {len(client.get('subreddits', []))} subreddits. We'll notify you as soon as relevant discussions appear.</p>
                </div>
                
                <p>This happens occasionally when:</p>
                <ul>
                    <li>Reddit activity is low in your target subreddits</li>
                    <li>No posts matched your keyword criteria</li>
                    <li>Discussions didn't reach our relevance threshold</li>
                </ul>
                
                <p><strong>What we're still doing:</strong></p>
                <ul>
                    <li>✅ Monitoring 24/7 for new opportunities</li>
                    <li>✅ Analyzing posts in real-time</li>
                    <li>✅ Building your opportunity pipeline</li>
                </ul>
                
                <a href="https://echomind-dashboard.netlify.app/dashboard.html?client_id={client.get('client_id')}" style="display: inline-block; background: #667eea; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 20px 0;">View Dashboard</a>
                
                <p style="color: #666; font-size: 14px; margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee;">
                    <strong>EchoMind</strong><br>
                    Next report: {(datetime.utcnow() + timedelta(days=3)).strftime('%A, %B %d')} at 7am EST
                </p>
            </body>
            </html>
            """
            
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {os.getenv('RESEND_API_KEY')}",
                    "Content-Type": "application/json"
                },
                json={
                    "from": "EchoMind Reports <reports@echomind.ai>",
                    "to": [email],
                    "subject": f"📊 Weekly Report: No New Opportunities - {client.get('company_name')}",
                    "html": html
                }
            )
            
            return {"success": response.status_code == 200}
            
        except Exception as e:
            logger.error(f"Error sending no-activity report: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def _build_report_email(
        self,
        client: Dict,
        opportunities: List[Dict],
        analysis: str,
        top_opportunities: Dict[str, List[Dict]]
    ) -> str:
        """Build HTML email for weekly report"""
        
        # Convert analysis markdown to HTML
        analysis_html = analysis.replace('\n\n', '</p><p>').replace('\n', '<br>')
        analysis_html = f"<p>{analysis_html}</p>"
        
        # Build opportunity cards by tier
        opp_cards_html = ""
        
        for tier, color in [("Platinum", "#e74c3c"), ("Gold", "#f39c12"), ("Silver", "#95a5a6")]:
            tier_opps = top_opportunities.get(tier, [])
            if tier_opps:
                opp_cards_html += f"""
                <div style="margin: 30px 0;">
                    <h3 style="color: {color};">● {tier} Priority ({len(tier_opps)} opportunities)</h3>
                """
                
                for opp in tier_opps:
                    opp_cards_html += f"""
                    <div style="background: white; border-left: 4px solid {color}; padding: 15px; margin: 10px 0; border-radius: 6px;">
                        <p style="margin: 0; font-weight: bold;">{opp.get('post_title', '')[:100]}...</p>
                        <p style="margin: 5px 0; font-size: 14px; color: #666;">
                            r/{opp.get('subreddit')} • Score: {opp.get('combined_score', 0)}/100
                        </p>
                        <p style="margin: 10px 0; font-size: 14px;">
                            {opp.get('suggested_response', '')[:200] if opp.get('suggested_response') else 'AI-generated response pending...'}...
                        </p>
                        <a href="https://reddit.com{opp.get('post_url', '')}" style="font-size: 14px; color: #667eea;">View on Reddit →</a>
                    </div>
                    """
                
                opp_cards_html += "</div>"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                h1 {{ color: #667eea; }}
                h2 {{ color: #764ba2; margin-top: 30px; }}
                .stats {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
                .btn {{ display: inline-block; background: #667eea; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📊 Weekly Reddit Report</h1>
                <h2 style="color: #764ba2; font-size: 24px;">{client.get('company_name')}</h2>
                
                <div class="stats">
                    <p style="font-size: 18px; margin: 0;"><strong>{len(opportunities)} Opportunities Discovered This Week</strong></p>
                    <p style="margin: 10px 0 0 0;">
                        {len(top_opportunities.get('Platinum', []))} Platinum • 
                        {len(top_opportunities.get('Gold', []))} Gold • 
                        {len(top_opportunities.get('Silver', []))} Silver
                    </p>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="margin-top: 0; color: #667eea;">📈 Weekly Analysis</h3>
                    {analysis_html}
                </div>
                
                <h2>🎯 Top Opportunities</h2>
                {opp_cards_html}
                
                <a href="https://echomind-dashboard.netlify.app/dashboard.html?client_id={client.get('client_id')}" class="btn">
                    View Full Dashboard →
                </a>
                
                <div style="margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee; font-size: 14px; color: #666;">
                    <p>Questions? Reply to this email or visit your dashboard.</p>
                    <p style="margin-top: 20px;">
                        <strong>EchoMind</strong><br>
                        Next report: {(datetime.utcnow() + timedelta(days=3 if datetime.utcnow().weekday() == 0 else 4)).strftime('%A, %B %d')} at 7am EST
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html


# Utility function for direct execution
async def generate_all_weekly_reports():
    """Send weekly reports to all clients - Called by scheduler"""
    generator = WeeklyReportGenerator()
    return await generator.send_reports_to_all_clients()

# Backward compatibility
async def send_weekly_reports():
    """Send weekly reports to all clients"""
    return await generate_all_weekly_reports()


if __name__ == "__main__":
    import asyncio
    
    logger.info("Running Weekly Report Generator...")
    result = asyncio.run(send_weekly_reports())
    
    if result["reports_sent"] > 0:
        logger.info(f"\n🎉 Successfully sent {result['reports_sent']} reports!")
    else:
        logger.error(f"\n❌ No reports sent. {result['reports_failed']} failures.")
