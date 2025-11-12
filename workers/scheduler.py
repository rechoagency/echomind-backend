"""
Worker Scheduler
Orchestrates execution of all workers in correct order with dependency management
"""

import os
import logging
from typing import Dict, Optional
from datetime import datetime

# Import all workers
from workers.opportunity_scoring_worker import OpportunityScoringWorker
from workers.product_matchback_worker import ProductMatchbackWorker
from workers.content_generation_worker import ContentGenerationWorker
from workers.voice_application_worker import VoiceApplicationWorker

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkerScheduler:
    """
    Orchestrates execution of all intelligence workers
    """
    
    def __init__(self):
        """Initialize the scheduler with all workers"""
        self.opportunity_scorer = OpportunityScoringWorker()
        self.product_matchback = ProductMatchbackWorker()
        self.content_generator = ContentGenerationWorker()
        self.voice_application = VoiceApplicationWorker()
        logger.info("Worker Scheduler initialized with all workers")
    
    def run_full_pipeline(
        self,
        client_id: Optional[str] = None,
        force_regenerate: bool = False
    ) -> Dict:
        """
        Run complete intelligence pipeline for all opportunities
        
        Execution order:
        1. Score opportunities (commercial intent)
        2. Match products (vector search)
        3. Generate content (GPT with products)
        4. Apply voice profiles (formatting)
        
        Args:
            client_id: Optional client filter
            force_regenerate: Force regeneration even if already processed
            
        Returns:
            Complete pipeline results
        """
        pipeline_start = datetime.utcnow()
        logger.info("=" * 70)
        logger.info("STARTING FULL INTELLIGENCE PIPELINE")
        logger.info("=" * 70)
        
        results = {
            "pipeline_started_at": pipeline_start.isoformat(),
            "client_id": client_id,
            "steps": {}
        }
        
        try:
            # STEP 1: Score opportunities
            logger.info("\n[STEP 1/4] Running Opportunity Scoring...")
            logger.info("-" * 70)
            scoring_result = self.opportunity_scorer.process_all_opportunities(client_id)
            results["steps"]["opportunity_scoring"] = scoring_result
            
            if scoring_result["success"]:
                logger.info(f"✅ Scored {scoring_result['processed']} opportunities")
            else:
                logger.error(f"❌ Opportunity scoring failed: {scoring_result.get('error')}")
                # Continue anyway - some might already be scored
            
            # STEP 2: Product matchback
            logger.info("\n[STEP 2/4] Running Product Matchback...")
            logger.info("-" * 70)
            matchback_result = self.product_matchback.process_all_opportunities(
                client_id=client_id,
                force_rematch=force_regenerate
            )
            results["steps"]["product_matchback"] = matchback_result
            
            if matchback_result["success"]:
                logger.info(f"✅ Matched {matchback_result['matched']} opportunities with products")
                logger.info(f"   {matchback_result['no_match']} had no matching products")
            else:
                logger.error(f"❌ Product matchback failed: {matchback_result.get('error')}")
                # This is more critical - might want to stop here
                if not force_regenerate:
                    results["pipeline_status"] = "PARTIAL_FAILURE"
                    results["pipeline_completed_at"] = datetime.utcnow().isoformat()
                    return results
            
            # STEP 3: Generate content
            logger.info("\n[STEP 3/4] Running Content Generation...")
            logger.info("-" * 70)
            content_result = self.content_generator.process_all_opportunities(
                client_id=client_id,
                regenerate=force_regenerate,
                only_with_products=True  # Only generate for opportunities with product matches
            )
            results["steps"]["content_generation"] = content_result
            
            if content_result["success"]:
                logger.info(f"✅ Generated {content_result['processed']} content pieces")
                logger.info(f"   {content_result['with_product_mentions']} include product mentions")
                logger.info(f"   {content_result['without_product_mentions']} are advice-only")
            else:
                logger.error(f"❌ Content generation failed: {content_result.get('error')}")
            
            # STEP 4: Apply voice profiles
            logger.info("\n[STEP 4/4] Running Voice Application...")
            logger.info("-" * 70)
            voice_result = self.voice_application.process_all_content(
                client_id=client_id,
                reapply=force_regenerate
            )
            results["steps"]["voice_application"] = voice_result
            
            if voice_result["success"]:
                logger.info(f"✅ Applied voice profiles to {voice_result['processed']} content pieces")
                logger.info(f"   {voice_result['modified']} required modifications")
                logger.info(f"   {voice_result['no_changes']} already matched style")
            else:
                logger.error(f"❌ Voice application failed: {voice_result.get('error')}")
            
            # Calculate totals
            pipeline_end = datetime.utcnow()
            duration = (pipeline_end - pipeline_start).total_seconds()
            
            results["pipeline_status"] = "SUCCESS"
            results["pipeline_completed_at"] = pipeline_end.isoformat()
            results["total_duration_seconds"] = duration
            
            # Summary stats
            results["summary"] = {
                "opportunities_scored": scoring_result.get("processed", 0),
                "products_matched": matchback_result.get("matched", 0),
                "content_generated": content_result.get("processed", 0),
                "voice_applied": voice_result.get("processed", 0),
                "content_with_products": content_result.get("with_product_mentions", 0)
            }
            
            logger.info("\n" + "=" * 70)
            logger.info("PIPELINE COMPLETE")
            logger.info("=" * 70)
            logger.info(f"Duration: {duration:.2f} seconds")
            logger.info(f"Opportunities processed: {results['summary']['opportunities_scored']}")
            logger.info(f"Products matched: {results['summary']['products_matched']}")
            logger.info(f"Content generated: {results['summary']['content_generated']}")
            logger.info(f"Content with product mentions: {results['summary']['content_with_products']}")
            logger.info("=" * 70)
            
            return results
        
        except Exception as e:
            logger.error(f"PIPELINE FAILED: {str(e)}")
            results["pipeline_status"] = "FAILED"
            results["pipeline_error"] = str(e)
            results["pipeline_completed_at"] = datetime.utcnow().isoformat()
            return results
    
    def run_scoring_only(self, client_id: Optional[str] = None) -> Dict:
        """Run only opportunity scoring"""
        logger.info("Running opportunity scoring only...")
        return self.opportunity_scorer.process_all_opportunities(client_id)
    
    def run_matchback_only(self, client_id: Optional[str] = None, force: bool = False) -> Dict:
        """Run only product matchback"""
        logger.info("Running product matchback only...")
        return self.product_matchback.process_all_opportunities(client_id, force)
    
    def run_content_generation_only(
        self,
        client_id: Optional[str] = None,
        regenerate: bool = False,
        only_with_products: bool = True
    ) -> Dict:
        """Run only content generation"""
        logger.info("Running content generation only...")
        return self.content_generator.process_all_opportunities(client_id, regenerate, only_with_products)
    
    def run_voice_application_only(self, client_id: Optional[str] = None, reapply: bool = False) -> Dict:
        """Run only voice application"""
        logger.info("Running voice application only...")
        return self.voice_application.process_all_content(client_id, reapply)
    
    def process_new_opportunities_incremental(self, client_id: Optional[str] = None) -> Dict:
        """
        Process only new opportunities that haven't been through the pipeline
        More efficient than full pipeline when adding new opportunities
        
        Returns:
            Processing results
        """
        logger.info("Running incremental processing for new opportunities...")
        
        results = {
            "mode": "incremental",
            "started_at": datetime.utcnow().isoformat()
        }
        
        # Score new opportunities (those without opportunity_score)
        scoring_result = self.opportunity_scorer.process_all_opportunities(client_id)
        results["scoring"] = scoring_result
        
        # Match products for newly scored opportunities
        matchback_result = self.product_matchback.process_all_opportunities(client_id, force_rematch=False)
        results["matchback"] = matchback_result
        
        # Generate content for opportunities with new product matches
        content_result = self.content_generator.process_all_opportunities(
            client_id,
            regenerate=False,
            only_with_products=True
        )
        results["content_generation"] = content_result
        
        # Apply voice to newly generated content
        voice_result = self.voice_application.process_all_content(client_id, reapply=False)
        results["voice_application"] = voice_result
        
        results["completed_at"] = datetime.utcnow().isoformat()
        
        logger.info(f"Incremental processing complete: {content_result.get('processed', 0)} new opportunities processed")
        
        return results
    
    def regenerate_content_for_client(self, client_id: str) -> Dict:
        """
        Regenerate all content for a specific client
        Useful after updating brand documents or voice profiles
        
        Args:
            client_id: Client UUID
            
        Returns:
            Processing results
        """
        logger.info(f"Regenerating all content for client {client_id}...")
        
        # Rematch products (in case documents changed)
        matchback_result = self.product_matchback.process_all_opportunities(
            client_id=client_id,
            force_rematch=True
        )
        
        # Regenerate content
        content_result = self.content_generator.process_all_opportunities(
            client_id=client_id,
            regenerate=True,
            only_with_products=True
        )
        
        # Reapply voice
        voice_result = self.voice_application.process_all_content(
            client_id=client_id,
            reapply=True
        )
        
        return {
            "client_id": client_id,
            "matchback": matchback_result,
            "content_generation": content_result,
            "voice_application": voice_result,
            "completed_at": datetime.utcnow().isoformat()
        }


# Utility functions for direct execution
def run_full_pipeline(client_id: Optional[str] = None, force_regenerate: bool = False):
    """Run complete pipeline"""
    scheduler = WorkerScheduler()
    return scheduler.run_full_pipeline(client_id, force_regenerate)


def run_incremental_update(client_id: Optional[str] = None):
    """Process only new opportunities"""
    scheduler = WorkerScheduler()
    return scheduler.process_new_opportunities_incremental(client_id)


def regenerate_all_for_client(client_id: str):
    """Regenerate everything for a client"""
    scheduler = WorkerScheduler()
    return scheduler.regenerate_content_for_client(client_id)


if __name__ == "__main__":
    # Test execution
    logger.info("Running Full Intelligence Pipeline...")
    result = run_full_pipeline()
    
    if result["pipeline_status"] == "SUCCESS":
        logger.info("\n🎉 PIPELINE SUCCESSFUL!")
        logger.info(f"Summary: {result['summary']}")
    else:
        logger.error(f"\n❌ PIPELINE FAILED: {result.get('pipeline_error')}")
