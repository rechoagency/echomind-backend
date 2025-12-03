"""
Onboarding Orchestrator - COMPLETE SYSTEM
Coordinates all post-onboarding processing:
1. File upload & vectorization
2. AUTO_IDENTIFY subreddits & keywords
3. Opportunity scoring
4. Product matchback
5. Voice analysis
6. Content calendar generation
7. Email notifications
"""

import os
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json
from openai import OpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class OnboardingOrchestrator:
    """Complete post-onboarding orchestration"""
    
    def __init__(self, supabase_client, openai_api_key: str):
        self.supabase = supabase_client
        self.openai_api_key = openai_api_key
        self.openai = OpenAI(api_key=openai_api_key)
        
        # Initialize services
        from services.auto_identify_service import AutoIdentifyService
        from services.notification_service import NotificationService
        self.auto_identify = AutoIdentifyService(supabase_client, openai_api_key)
        self.notification_service = NotificationService(openai_api_key)
    
    async def process_client_onboarding(self, client_id: str) -> Dict[str, Any]:
        """
        Execute complete onboarding workflow
        
        Args:
            client_id: UUID of newly onboarded client
            
        Returns:
            Complete processing results
        """
        results = {
            "client_id": client_id,
            "tasks_completed": [],
            "tasks_failed": [],
            "started_at": datetime.utcnow().isoformat()
        }
        
        try:
            # Get client data
            client_data = self.supabase.table("clients").select("*").eq("client_id", client_id).execute()
            if not client_data.data:
                raise ValueError(f"Client {client_id} not found")
            
            client = client_data.data[0]
            logger.info(f"🚀 Starting orchestration for {client.get('company_name')}")
            
            # TASK 1: AUTO_IDENTIFY Subreddits
            if client.get("target_subreddits") == ["AUTO_IDENTIFY"]:
                logger.info("🔍 AUTO_IDENTIFY: Discovering subreddits...")
                subreddit_results = await self.auto_identify.discover_subreddits(client)
                results["subreddit_discovery"] = subreddit_results
                if subreddit_results.get("success"):
                    results["tasks_completed"].append("subreddit_discovery")
                    logger.info(f"✅ Discovered {subreddit_results.get('count')} subreddits")
                else:
                    results["tasks_failed"].append("subreddit_discovery")
            
            # TASK 2: AUTO_IDENTIFY Keywords
            if client.get("target_keywords") == ["AUTO_IDENTIFY"]:
                logger.info("🔍 AUTO_IDENTIFY: Extracting keywords...")
                keyword_results = await self.auto_identify.extract_keywords(client)
                results["keyword_extraction"] = keyword_results
                if keyword_results.get("success"):
                    results["tasks_completed"].append("keyword_extraction")
                    logger.info(f"✅ Extracted {keyword_results.get('count')} keywords")
                else:
                    results["tasks_failed"].append("keyword_extraction")

            # TASK 3: Build voice database for subreddits
            logger.info("🎤 Building voice database...")
            voice_results = await self._build_voice_database(client_id)
            results["voice_database"] = voice_results
            if voice_results.get("success"):
                results["tasks_completed"].append("voice_database")
                logger.info(f"✅ Built voice profiles for {voice_results.get('successful', 0)} subreddits")
            else:
                results["tasks_failed"].append("voice_database")
                logger.warning(f"⚠️ Voice database partially failed: {voice_results.get('error', 'Unknown')}")

            # TASK 4: Score existing opportunities
            logger.info("📊 Scoring opportunities...")
            scoring_results = await self._score_opportunities(client_id)
            results["opportunity_scoring"] = scoring_results
            if scoring_results.get("success"):
                results["tasks_completed"].append("opportunity_scoring")
                logger.info(f"✅ Scored {scoring_results.get('count', 0)} opportunities")

            # TASK 5: Generate content calendar
            logger.info("📅 Generating content calendar...")
            calendar_results = await self._generate_content_calendar(client)
            results["content_calendar"] = calendar_results
            if calendar_results.get("success"):
                results["tasks_completed"].append("content_calendar")
                logger.info(f"✅ Calendar generated with {calendar_results.get('items', 0)} items")
            
            # TASK 6: Send welcome email
            logger.info("📧 Sending welcome email...")
            email_results = await self._send_welcome_email(client, calendar_results)
            results["email_notification"] = email_results
            if email_results.get("success"):
                results["tasks_completed"].append("email_notification")
                logger.info(f"✅ Email sent to {client.get('notification_email')}")
            else:
                results["tasks_failed"].append("email_notification")
                logger.error(f"❌ Email failed: {email_results.get('error', 'Unknown error')}")
                logger.error(f"   Target: {client.get('notification_email')}")
                logger.error(f"   Details: {email_results.get('details', 'No details')}")
            
            # Update client status
            self.supabase.table("clients").update({
                "onboarding_status": "completed",
                "updated_at": datetime.utcnow().isoformat()
            }).eq("client_id", client_id).execute()
            
            results["completed_at"] = datetime.utcnow().isoformat()
            results["success"] = len(results["tasks_failed"]) == 0
            
            logger.info(f"🎉 Orchestration complete for {client.get('company_name')}")
            logger.info(f"   ✅ Completed: {len(results['tasks_completed'])}")
            logger.info(f"   ❌ Failed: {len(results['tasks_failed'])}")
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Orchestration error: {str(e)}")
            results["error"] = str(e)
            results["success"] = False
            
            # Update client status to error
            try:
                self.supabase.table("clients").update({
                    "onboarding_status": "error",
                    "updated_at": datetime.utcnow().isoformat()
                }).eq("client_id", client_id).execute()
            except:
                pass
            
            return results

    async def _build_voice_database(self, client_id: str) -> Dict:
        """Build voice profiles for client's configured subreddits"""
        try:
            from workers.voice_database_worker import build_client_voice_database
            result = await build_client_voice_database(client_id)
            return {
                "success": result.get("failed", 0) < result.get("total_subreddits", 1),
                "total_subreddits": result.get("total_subreddits", 0),
                "successful": result.get("successful", 0),
                "failed": result.get("failed", 0)
            }
        except Exception as e:
            logger.error(f"Voice database build error: {str(e)}")
            return {"success": False, "error": str(e)}

    async def _score_opportunities(self, client_id: str) -> Dict:
        """Score top 100 opportunities for client"""
        try:
            # Get top 100 recent opportunities
            opportunities = self.supabase.table("opportunities")\
                .select("*")\
                .eq("client_id", client_id)\
                .order("created_at", desc=True)\
                .limit(100)\
                .execute()
            
            if not opportunities.data:
                return {"success": True, "count": 0, "message": "No opportunities to score"}
            
            scored_count = 0
            
            for opp in opportunities.data:
                try:
                    # Calculate scores using AI
                    scores = await self._calculate_opportunity_scores(opp)
                    
                    # Update opportunity
                    self.supabase.table("opportunities").update({
                        "subreddit_score": scores.get("subreddit", 50),
                        "thread_score": scores.get("thread", 50),
                        "user_score": scores.get("user", 50),
                        "combined_score": scores["composite"],
                        "priority_tier": scores["priority"],
                        "updated_at": datetime.utcnow().isoformat()
                    }).eq("opportunity_id", opp["opportunity_id"]).execute()
                    
                    scored_count += 1
                    
                except Exception as e:
                    logger.error(f"Error scoring opportunity {opp['id']}: {str(e)}")
                    continue
            
            return {
                "success": True,
                "count": scored_count,
                "total": len(opportunities.data)
            }
            
        except Exception as e:
            logger.error(f"Opportunity scoring error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def _calculate_opportunity_scores(self, opportunity: Dict) -> Dict:
        """Calculate all scores for an opportunity"""
        title = opportunity.get("thread_title", "")
        content = opportunity.get("thread_content", "")
        full_text = f"{title}\n\n{content}"
        
        prompt = f"""Analyze this Reddit post for marketing opportunity scoring:

{full_text[:1000]}

Rate 0-100 for each:
1. Buying Intent: Commercial intent, ready to purchase
2. Pain Point: Expresses frustration, seeks solution
3. Organic Lift: Question quality, engagement potential, urgency

Return JSON:
{{"buying_intent": 75, "pain_point": 85, "organic_lift": 90, "reasoning": "..."}}"""
        
        try:
            response = self.openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            
            result_text = response.choices[0].message.content.strip()
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            scores = json.loads(result_text)
            
            # Calculate composite score
            buying_intent = scores.get("buying_intent", 50)
            pain_point = scores.get("pain_point", 50)
            organic_lift = scores.get("organic_lift", 50)
            
            composite = (buying_intent * 0.35 + pain_point * 0.25 + organic_lift * 0.40)
            
            # Determine priority
            if composite >= 80:
                priority = "URGENT"
            elif composite >= 65:
                priority = "HIGH"
            elif composite >= 50:
                priority = "MEDIUM"
            else:
                priority = "LOW"
            
            return {
                "buying_intent": buying_intent,
                "pain_point": pain_point,
                "organic_lift": organic_lift,
                "composite": round(composite, 1),
                "priority": priority
            }
            
        except Exception as e:
            logger.error(f"AI scoring error: {str(e)}")
            # Return default scores
            return {
                "buying_intent": 50,
                "pain_point": 50,
                "organic_lift": 50,
                "composite": 50.0,
                "priority": "MEDIUM"
            }
    
    async def _generate_content_calendar(self, client: Dict) -> Dict:
        """Generate 2-week content calendar"""
        try:
            client_id = client.get("client_id")
            posting_freq = client.get("posting_frequency", 10)
            
            # Get top opportunities
            opportunities = self.supabase.table("opportunities")\
                .select("*")\
                .eq("client_id", client_id)\
                .order("combined_score", desc=True)\
                .limit(posting_freq * 2)\
                .execute()
            
            if not opportunities.data:
                return {
                    "success": True,
                    "items": 0,
                    "message": "No opportunities available yet"
                }
            
            # Generate calendar using AI
            opp_summary = "\n".join([
                f"- [{opp.get('priority_tier')}] r/{opp.get('subreddit')}: {opp.get('thread_title')[:100]}"
                for opp in opportunities.data[:10]
            ])
            
            prompt = f"""Create a 2-week Reddit posting calendar for {client.get('company_name')}.

Posting Frequency: {posting_freq} posts/week
Industry: {client.get('industry')}
Tone: {client.get('content_tone')}

Top Opportunities:
{opp_summary}

Generate a schedule with:
- Dates (next 14 days, Mon/Thu priority)
- Which opportunity to respond to
- Brief response strategy

Return JSON:
[{{"date": "2024-01-15", "day": "Monday", "subreddit": "Entrepreneur", "thread": "...", "strategy": "..."}}]"""
            
            response = self.openai.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5
            )
            
            calendar_text = response.choices[0].message.content.strip()
            if "```json" in calendar_text:
                calendar_text = calendar_text.split("```json")[1].split("```")[0].strip()
            elif "```" in calendar_text:
                calendar_text = calendar_text.split("```")[1].split("```")[0].strip()
            
            calendar_items = json.loads(calendar_text)
            
            # Store calendar in database
            calendar_record = {
                "client_id": client_id,
                "calendar_data": calendar_items,
                "period_start": datetime.utcnow().isoformat(),
                "period_end": (datetime.utcnow() + timedelta(days=14)).isoformat(),
                "created_at": datetime.utcnow().isoformat()
            }
            
            self.supabase.table("content_calendars").insert(calendar_record).execute()
            
            return {
                "success": True,
                "items": len(calendar_items),
                "calendar": calendar_items
            }
            
        except Exception as e:
            logger.error(f"Calendar generation error: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def _send_welcome_email(self, client: Dict, calendar: Dict) -> Dict:
        """Send comprehensive welcome notification with analysis + sample content"""
        try:
            # Get all data for notification
            client_id = client.get("client_id") or client.get("id")
            
            # Fetch AUTO_IDENTIFY results
            client_record = self.supabase.table("clients").select("*").eq("client_id", client_id).single().execute()
            auto_identify_results = {
                "subreddits": client_record.data.get("subreddits", []),
                "keywords": client_record.data.get("keywords", [])
            }
            
            # Fetch top opportunities
            opportunities_response = self.supabase.table("opportunities")\
                .select("*")\
                .eq("client_id", client_id)\
                .order("combined_score", desc=True)\
                .limit(10)\
                .execute()
            opportunities = opportunities_response.data if opportunities_response.data else []
            
            # Get calendar items
            calendar_items = calendar.get("calendar", [])
            
            # Fetch product matches (if any)
            product_matches = []
            for opp in opportunities[:3]:
                if opp.get("product_matches"):
                    product_matches.extend(opp.get("product_matches", []))
            
            # Send comprehensive notification using NEW email service with Excel attachments
            from services.email_service_with_excel import WelcomeEmailService
            email_service = WelcomeEmailService()
            notification_result = await email_service.send_welcome_email_with_reports(
                client=client_record.data,
                opportunities=opportunities
            )
            
            # Also send original notification (for Slack, etc.)
            # await self.notification_service.send_onboarding_complete_notification(
            #     client=client_record.data,
            #     auto_identify_results=auto_identify_results,
            #     opportunities=opportunities,
            #     calendar_items=calendar_items,
            #     product_matches=product_matches
            # )
            
            return notification_result
            
        except Exception as e:
            logger.error(f"❌ Email sending error: {str(e)}")
            import traceback
            logger.error(f"   Traceback: {traceback.format_exc()}")
            return {"success": False, "error": str(e), "traceback": traceback.format_exc()}
