"""
Excel Weekly Report Generator

Replaces HTML email reports with Excel workbooks.
Generates 25-piece content queues every Monday & Thursday at 7am EST.

Format matches client expectations:
- 26 columns (Opportunity ID through Notes)
- Urgency color coding
- Content Preview + Full Copy/Paste Ready text
- Product matchback in Notes column
"""

import os
import asyncio
import logging
from typing import Dict, List, Any
from datetime import datetime, timedelta
import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side

from database import get_supabase_client
from workers.enhanced_content_generation_worker import generate_enhanced_content

logger = logging.getLogger(__name__)

class ExcelReportGenerator:
    """Generates Excel weekly content reports"""
    
    def __init__(self):
        self.supabase = get_supabase_client()
    
    async def generate_weekly_report(
        self,
        client_id: str,
        brand_mention_percentage: float = 0.0,
        num_opportunities: int = 25
    ) -> str:
        """
        Generate Excel report with content queue
        
        Args:
            client_id: UUID of client
            brand_mention_percentage: 0-100 control
            num_opportunities: Number of opportunities to include (default 25)
            
        Returns:
            File path to generated Excel report
        """
        try:
            logger.info(f"Generating Excel report for client {client_id}")
            
            # Fetch client info
            client_response = self.supabase.table("clients").select("*").eq("client_id", client_id).execute()
            if not client_response.data:
                raise ValueError(f"Client {client_id} not found")
            
            client = client_response.data[0]
            company_name = client.get('company_name', 'Client')
            
            # Fetch top opportunities from last 3 days
            three_days_ago = (datetime.utcnow() - timedelta(days=3)).isoformat()
            opportunities_response = self.supabase.table("opportunities")\
                .select("*")\
                .eq("client_id", client_id)\
                .gte("created_at", three_days_ago)\
                .order("combined_score", desc=True)\
                .limit(num_opportunities)\
                .execute()
            
            opportunities = opportunities_response.data
            
            if not opportunities:
                logger.warning(f"No opportunities found for client {client_id}")
                return None
            
            logger.info(f"Found {len(opportunities)} opportunities for report")
            
            # Generate content for each opportunity
            content_queue = []
            for rank, opp in enumerate(opportunities, 1):
                try:
                    content_data = await generate_enhanced_content(
                        opp['id'],
                        client_id,
                        brand_mention_percentage
                    )
                    
                    content_queue.append({
                        "opportunity": opp,
                        "content": content_data,
                        "rank": rank
                    })
                    
                except Exception as e:
                    logger.error(f"Failed to generate content for opportunity {opp['id']}: {e}")
                    continue
            
            # Create Excel workbook
            filepath = await self._create_excel_report(
                client,
                content_queue,
                brand_mention_percentage
            )
            
            logger.info(f"Excel report generated: {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error generating Excel report: {e}")
            raise
    
    async def _create_excel_report(
        self,
        client: Dict,
        content_queue: List[Dict],
        brand_mention_percentage: float
    ) -> str:
        """Create Excel workbook with content queue"""
        
        # Create workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Weekly Content Queue"
        
        # Define styling
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF", size=11)
        border = Border(
            left=Side(style='thin', color='D3D3D3'),
            right=Side(style='thin', color='D3D3D3'),
            top=Side(style='thin', color='D3D3D3'),
            bottom=Side(style='thin', color='D3D3D3')
        )
        
        # Define headers (26 columns)
        headers = [
            "Opportunity ID", "Rank", "Priority Tier", "Timing", "Urgency",
            "Content Type", "Subreddit", "Thread Title", "Thread URL", "Target User",
            "User Commercial Score", "User Authority Score", "Thread Score", "User Score",
            "Combined Opportunity Score", "Approach Strategy", "Content Preview",
            "Full Content (Copy/Paste Ready)", "Content Status", "Post Window Start",
            "Post Window End", "Thread Upvotes", "Thread Comments",
            "Engagement Probability", "Conversion Potential", "Notes"
        ]
        
        # Add headers
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.value = header
            cell.fill = header_fill
            cell.font = header_font
            cell.border = border
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
        
        # Set column widths
        column_widths = [15, 6, 16, 14, 10, 16, 14, 40, 50, 18, 12, 12, 11, 10, 15, 25, 80, 120, 14, 18, 18, 12, 12, 14, 14, 60]
        for idx, width in enumerate(column_widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(idx)].width = width
        
        # Add content rows
        for row_idx, item in enumerate(content_queue, 2):
            opp = item['opportunity']
            content = item['content']
            rank = item['rank']
            
            # Determine tier and urgency
            tier = self._get_priority_tier(opp.get('combined_score', 0))
            timing = self._get_timing_category(opp.get('created_at'))
            urgency = self._get_urgency_emoji(opp.get('combined_score', 0), timing)
            
            # Build row data
            row_data = [
                opp.get('id', '')[:15],  # Opportunity ID (truncated)
                rank,
                tier,
                timing,
                urgency,
                "COMMENT/REPLY",
                opp.get('subreddit', ''),
                opp.get('thread_title', ''),
                opp.get('thread_url', ''),
                opp.get('target_user', ''),
                round(opp.get('commercial_intent_score', 0), 2),
                round(opp.get('authority_score', 0), 2),
                round(opp.get('thread_score', 0), 2),
                round(opp.get('user_score', 0), 2),
                round(opp.get('combined_score', 0), 2),
                content.get('approach_strategy', 'EDUCATIONAL_WITH_PRODUCT'),
                content.get('preview', ''),
                content.get('content', ''),
                "Ready to Post",
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                (datetime.utcnow() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
                opp.get('thread_upvotes', 0),
                opp.get('thread_comments', 0),
                round(opp.get('engagement_probability', 0), 2),
                round(opp.get('conversion_potential', 0), 2),
                self._build_notes(opp, content, brand_mention_percentage)
            ]
            
            # Write row
            for col_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.value = value
                cell.border = border
                
                # Special formatting
                if col_idx in [17, 18, 26]:  # Wrap text columns
                    cell.alignment = Alignment(wrap_text=True, vertical='top')
                elif col_idx == 5:  # Urgency colors
                    cell.alignment = Alignment(horizontal='center', vertical='center')
                    if "🔴" in str(value):
                        cell.font = Font(color="FF0000", bold=True)
                    elif "🟡" in str(value):
                        cell.font = Font(color="FFA500", bold=True)
                    elif "🟢" in str(value):
                        cell.font = Font(color="008000", bold=True)
                else:
                    cell.alignment = Alignment(vertical='center')
        
        # Save file
        company_name_clean = client.get('company_name', 'Client').replace(' ', '_')
        timestamp = datetime.utcnow().strftime("%Y%m%d")
        filename = f"{company_name_clean}_Weekly_Content_{timestamp}.xlsx"
        filepath = f"/tmp/{filename}"
        
        wb.save(filepath)
        return filepath
    
    def _get_priority_tier(self, score: float) -> str:
        """Determine priority tier from score"""
        if score >= 0.8:
            return "TIER_1 (HIGHEST)"
        elif score >= 0.65:
            return "TIER_2 (HIGH)"
        elif score >= 0.5:
            return "TIER_3 (MEDIUM)"
        else:
            return "TIER_4 (LOW)"
    
    def _get_timing_category(self, created_at: str) -> str:
        """Determine timing urgency"""
        if not created_at:
            return "UNKNOWN"
        
        created = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        age_hours = (datetime.utcnow() - created.replace(tzinfo=None)).total_seconds() / 3600
        
        if age_hours <= 4:
            return "IMMEDIATE"
        elif age_hours <= 48:
            return "WITHIN_48H"
        elif age_hours <= 96:
            return "WITHIN_4DAYS"
        else:
            return "EXPIRED"
    
    def _get_urgency_emoji(self, score: float, timing: str) -> str:
        """Get urgency emoji based on score and timing"""
        if score >= 0.8 and timing in ["IMMEDIATE", "WITHIN_48H"]:
            return "🔴 URGENT"
        elif score >= 0.65:
            return "🟡 HIGH"
        else:
            return "🟢 MEDIUM"
    
    def _build_notes(self, opp: Dict, content: Dict, brand_percentage: float) -> str:
        """Build notes column with metadata"""
        notes = []
        
        # Priority indicator
        if opp.get('combined_score', 0) >= 0.8:
            notes.append("PLATINUM OPPORTUNITY")
        elif opp.get('combined_score', 0) >= 0.7:
            notes.append("HIGH-VALUE")
        
        # Brand mention status
        if content.get('brand_mentioned'):
            notes.append(f"Brand mentioned (Current setting: {brand_percentage}%)")
        else:
            notes.append(f"No brand mention (Current setting: {brand_percentage}%)")
        
        # Product match if applicable
        if content.get('product_matched'):
            notes.append(f"Product: {content['product_matched']}")
        
        # Voice profile
        if content.get('voice_profile_used'):
            notes.append(f"Voice: r/{content['voice_profile_used']}")
        
        # Quality score
        if content.get('quality_score'):
            quality = content['quality_score']
            if quality >= 0.9:
                notes.append("✅ Quality: Excellent")
            elif quality >= 0.7:
                notes.append("⚠️ Quality: Good")
            else:
                notes.append("❌ Quality: Review needed")
        
        return " | ".join(notes)


async def generate_weekly_excel_report(
    client_id: str,
    brand_mention_percentage: float = 0.0
) -> str:
    """
    Generate weekly Excel report for client
    
    Args:
        client_id: UUID of client
        brand_mention_percentage: 0-100
        
    Returns:
        Filepath to generated Excel report
    """
    generator = ExcelReportGenerator()
    return await generator.generate_weekly_report(client_id, brand_mention_percentage)
