"""
EchoMind - Updated Onboarding Orchestrator
Integrates intelligence report + 25 sample pieces generation
"""

import os
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional
from supabase import create_client, Client
import logging

# Import new generators
from onboarding_intelligence_generator import generate_onboarding_intelligence_report
from onboarding_sample_generator import generate_onboarding_sample_batch

# Import existing services
from services.auto_identify_service import auto_identify_subreddits_and_keywords
from services.document_ingestion_service import process_uploaded_documents
from services.voice_database_service import crawl_and_store_voice_samples

logger = logging.getLogger(__name__)


class OnboardingOrchestrator:
    """Orchestrates complete client onboarding process"""
    
    def __init__(self):
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY")
        )
    
    async def execute_onboarding(self, client_id: str, onboarding_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute complete onboarding workflow:
        1. Store client profile
        2. Process uploaded documents (knowledge base)
        3. Auto-identify subreddits/keywords
        4. Crawl voice database
        5. Generate intelligence report
        6. Generate 25 sample pieces
        7. Send welcome email with attachments
        """
        
        try:
            logger.info(f"Starting onboarding for client {client_id}")
            
            # Step 1: Store client profile
            await self._store_client_profile(client_id, onboarding_data)
            
            # Step 2: Process uploaded documents (if any)
            document_stats = None
            if onboarding_data.get('uploaded_files'):
                logger.info(f"Processing {len(onboarding_data['uploaded_files'])} uploaded files")
                document_stats = await process_uploaded_documents(
                    client_id, 
                    onboarding_data['uploaded_files']
                )
            
            # Step 3: Auto-identify subreddits and keywords (if enabled)
            if onboarding_data.get('auto_identify', True):
                logger.info("Auto-identifying subreddits and keywords")
                await auto_identify_subreddits_and_keywords(client_id, onboarding_data)
            
            # Step 4: Store manual subreddits/keywords
            await self._store_target_subreddits(client_id, onboarding_data.get('target_subreddits', []))
            await self._store_keywords(client_id, onboarding_data.get('keywords', []))
            
            # Step 5: Store products
            await self._store_products(client_id, onboarding_data.get('products', []))
            
            # Step 6: Crawl voice database (async - don't wait)
            asyncio.create_task(self._crawl_voice_database_async(client_id, onboarding_data))
            
            # Step 7: Generate intelligence report (ONE-TIME)
            logger.info("Generating intelligence report...")
            intelligence_report_path = await generate_onboarding_intelligence_report(client_id)
            logger.info(f"Intelligence report generated: {intelligence_report_path}")
            
            # Step 8: Generate 25 sample pieces (ONE-TIME)
            logger.info("Generating 25 sample pieces...")
            sample_pieces_path = await generate_onboarding_sample_batch(client_id)
            logger.info(f"Sample pieces generated: {sample_pieces_path}")
            
            # Step 9: Upload files to storage
            intelligence_report_url = await self._upload_to_storage(
                intelligence_report_path,
                f"onboarding/{client_id}/intelligence_report.xlsx"
            )
            
            sample_pieces_url = await self._upload_to_storage(
                sample_pieces_path,
                f"onboarding/{client_id}/25_sample_pieces.xlsx"
            )
            
            # Step 10: Send welcome email with attachments
            await self._send_welcome_email(
                client_id,
                onboarding_data,
                intelligence_report_url,
                sample_pieces_url,
                document_stats
            )
            
            # Step 11: Mark onboarding complete
            self.supabase.table('clients').update({
                'onboarding_completed': True,
                'onboarding_completed_at': datetime.utcnow().isoformat()
            }).eq('client_id', client_id).execute()
            
            logger.info(f"Onboarding complete for client {client_id}")
            
            return {
                'success': True,
                'client_id': client_id,
                'intelligence_report_url': intelligence_report_url,
                'sample_pieces_url': sample_pieces_url,
                'document_stats': document_stats,
                'message': 'Onboarding completed successfully'
            }
            
        except Exception as e:
            logger.error(f"Onboarding failed for client {client_id}: {str(e)}")
            raise
    
    async def _store_client_profile(self, client_id: str, data: Dict[str, Any]):
        """Store client profile in database"""
        
        profile = {
            'client_id': client_id,
            'company_name': data.get('company_name'),
            'website_url': data.get('website_url'),
            'industry': data.get('industry'),
            'target_audience': data.get('target_audience'),
            'posting_frequency': data.get('posting_frequency', 10),  # Default 10/week
            'contact_email': data.get('contact_email'),
            'created_at': datetime.utcnow().isoformat(),
            'status': 'active'
        }
        
        self.supabase.table('clients').insert(profile).execute()
    
    async def _store_target_subreddits(self, client_id: str, subreddits: list):
        """Store target subreddits"""
        
        if not subreddits:
            return
        
        records = [
            {
                'client_id': client_id,
                'subreddit_name': sub if sub.startswith('r/') else f"r/{sub}",
                'added_at': datetime.utcnow().isoformat()
            }
            for sub in subreddits
        ]
        
        self.supabase.table('target_subreddits').insert(records).execute()
    
    async def _store_keywords(self, client_id: str, keywords: list):
        """Store tracking keywords"""
        
        if not keywords:
            return
        
        records = [
            {
                'client_id': client_id,
                'keyword': keyword,
                'added_at': datetime.utcnow().isoformat()
            }
            for keyword in keywords
        ]
        
        self.supabase.table('client_keywords').insert(records).execute()
    
    async def _store_products(self, client_id: str, products: list):
        """Store products with embeddings"""
        
        if not products:
            return
        
        # Import embedding service
        from services.embedding_service import generate_embedding
        
        records = []
        for product in products:
            # Generate embedding for product
            product_text = f"{product.get('name', '')} {product.get('description', '')}"
            embedding = await generate_embedding(product_text)
            
            records.append({
                'client_id': client_id,
                'product_name': product.get('name'),
                'product_description': product.get('description'),
                'product_url': product.get('url'),
                'product_embedding': embedding,
                'added_at': datetime.utcnow().isoformat()
            })
        
        self.supabase.table('client_products').insert(records).execute()
    
    async def _crawl_voice_database_async(self, client_id: str, data: Dict[str, Any]):
        """Crawl voice database asynchronously (don't block onboarding)"""
        
        try:
            logger.info(f"Starting voice database crawl for {client_id}")
            website_url = data.get('website_url')
            if website_url:
                await crawl_and_store_voice_samples(client_id, website_url)
            logger.info(f"Voice database crawl complete for {client_id}")
        except Exception as e:
            logger.error(f"Voice crawl failed for {client_id}: {str(e)}")
    
    async def _upload_to_storage(self, local_path: str, storage_path: str) -> str:
        """Upload file to Supabase storage and return public URL"""
        
        try:
            # Read file
            with open(local_path, 'rb') as f:
                file_data = f.read()
            
            # Upload to Supabase storage
            bucket_name = 'echomind-files'
            
            result = self.supabase.storage.from_(bucket_name).upload(
                storage_path,
                file_data,
                file_options={'content-type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}
            )
            
            # Get public URL
            public_url = self.supabase.storage.from_(bucket_name).get_public_url(storage_path)
            
            return public_url
            
        except Exception as e:
            logger.error(f"Failed to upload {local_path}: {str(e)}")
            raise
    
    async def _send_welcome_email(
        self,
        client_id: str,
        onboarding_data: Dict[str, Any],
        intelligence_report_url: str,
        sample_pieces_url: str,
        document_stats: Optional[Dict]
    ):
        """Send welcome email with intelligence report and 25 samples attached"""
        
        # Import email service
        from services.email_service import send_email
        
        company_name = onboarding_data.get('company_name', 'there')
        contact_email = onboarding_data.get('contact_email')
        posting_frequency = onboarding_data.get('posting_frequency', 10)
        
        # Calculate weekly split
        pieces_per_delivery = posting_frequency // 2  # Split Mon/Thu
        
        email_body = f"""
        <html>
        <body>
            <h1>Welcome to EchoMind, {company_name}! 🎉</h1>
            
            <p>Your Reddit marketing automation system is now live and ready to go.</p>
            
            <h2>What Happens Next</h2>
            
            <p><strong>Automated Delivery Schedule:</strong></p>
            <ul>
                <li><strong>Every Monday at 7am EST:</strong> You'll receive {pieces_per_delivery} content opportunities</li>
                <li><strong>Every Thursday at 7am EST:</strong> You'll receive {pieces_per_delivery} content opportunities</li>
            </ul>
            
            <p>Each delivery includes ready-to-post content matched to high-value Reddit conversations.</p>
            
            <h2>Your Onboarding Package</h2>
            
            <p>We've prepared two comprehensive documents to get you started:</p>
            
            <ol>
                <li>
                    <strong>Intelligence Report</strong> - Deep analysis of your target Reddit communities
                    <br>
                    <a href="{intelligence_report_url}">Download Intelligence Report</a>
                    <br>
                    <small>Includes: Subreddit analysis, moderator profiles, high-value threads, brand voice analysis, and strategic recommendations</small>
                </li>
                
                <li>
                    <strong>25 Sample Content Pieces</strong> - Example opportunities from your first batch
                    <br>
                    <a href="{sample_pieces_url}">Download 25 Sample Pieces</a>
                    <br>
                    <small>Shows exactly what your weekly deliveries will look like - formatted, ready to review and post</small>
                </li>
            </ol>
            
            {self._get_document_stats_html(document_stats)}
            
            <h2>Dashboard Access</h2>
            
            <p>Manage your strategy settings at: <a href="https://echomind-dashboard.netlify.app">EchoMind Dashboard</a></p>
            
            <p>Use the Strategy tab to adjust:</p>
            <ul>
                <li><strong>Brand Mention %</strong> - Control general brand awareness mentions</li>
                <li><strong>Product Mention %</strong> - Control direct product mentions (only on highly relevant opportunities)</li>
            </ul>
            
            <h2>Questions?</h2>
            
            <p>Reply to this email or visit our <a href="https://echomind.com/support">support center</a>.</p>
            
            <p>Excited to help you build authentic Reddit presence!</p>
            
            <p>
                <strong>The EchoMind Team</strong><br>
                <a href="https://echomind.com">echomind.com</a>
            </p>
        </body>
        </html>
        """
        
        await send_email(
            to_email=contact_email,
            subject=f"Welcome to EchoMind - Your Intelligence Report & Samples Are Ready",
            html_body=email_body,
            attachments=[
                {'url': intelligence_report_url, 'filename': 'Intelligence_Report.xlsx'},
                {'url': sample_pieces_url, 'filename': '25_Sample_Pieces.xlsx'}
            ]
        )
        
        logger.info(f"Welcome email sent to {contact_email}")
    
    def _get_document_stats_html(self, stats: Optional[Dict]) -> str:
        """Generate HTML for document processing stats"""
        
        if not stats:
            return ""
        
        return f"""
        <h2>Knowledge Base Processing</h2>
        
        <p>We've successfully processed your uploaded documents:</p>
        <ul>
            <li><strong>{stats.get('total_files', 0)} files</strong> uploaded</li>
            <li><strong>{stats.get('total_chunks', 0)} content chunks</strong> indexed</li>
            <li><strong>{stats.get('total_characters', 0):,} characters</strong> analyzed</li>
        </ul>
        
        <p>This content is now embedded in your voice database and will be used to inject real expertise into your Reddit responses.</p>
        """


# Main entry point for API
async def trigger_onboarding(client_id: str, onboarding_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main function called by API endpoint
    """
    orchestrator = OnboardingOrchestrator()
    result = await orchestrator.execute_onboarding(client_id, onboarding_data)
    return result
