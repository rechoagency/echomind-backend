"""
Product Matchback Worker
Matches discovered opportunities with relevant client products using vector similarity
"""

import os
import logging
import json
from typing import Dict, List, Optional
from datetime import datetime
from supabase import create_client, Client
from openai import OpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize clients
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_API_KEY)


class ProductMatchbackWorker:
    """
    Worker that finds relevant products for opportunities using semantic search
    """
    
    def __init__(self):
        """Initialize the matchback worker"""
        self.supabase = supabase
        self.openai = openai_client
        logger.info("Product Matchback Worker initialized")
    
    def generate_embedding(self, text: str) -> List[float]:
        """
        Generate OpenAI embedding for text

        IMPORTANT: Must use text-embedding-ada-002 to match the embeddings stored
        in document_embeddings table. Using a different model would cause
        similarity searches to fail or return incorrect results.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (1536 dimensions)
        """
        try:
            response = self.openai.embeddings.create(
                model="text-embedding-ada-002",  # Must match document_ingestion_service
                input=text[:8000]  # Truncate to avoid token limits
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            raise
    
    def find_matching_products(
        self,
        client_id: str,
        query_text: str,
        limit: int = 3,
        similarity_threshold: float = 0.65
    ) -> List[Dict]:
        """
        Find products matching the query using vector similarity

        Uses document_embeddings table (the unified storage for all embeddings)
        with match_knowledge_embeddings RPC for efficient vector search.

        Args:
            client_id: Client UUID
            query_text: User's question/problem description
            limit: Maximum number of products to return
            similarity_threshold: Minimum similarity score (0-1)

        Returns:
            List of matching products with metadata
        """
        try:
            # Generate embedding for query (using text-embedding-ada-002 for consistency)
            query_embedding = self.generate_embedding(query_text)

            # Use match_knowledge_embeddings RPC for efficient vector search
            # This queries the document_embeddings table
            try:
                results = self.supabase.rpc(
                    "match_knowledge_embeddings",
                    {
                        "query_embedding": query_embedding,
                        "client_id": client_id,
                        "similarity_threshold": similarity_threshold,
                        "match_count": limit
                    }
                ).execute()

                if results.data:
                    matches = []
                    for result in results.data:
                        metadata = result.get("metadata") or {}
                        matches.append({
                            "chunk_text": result.get("chunk_text", ""),
                            "similarity_score": round(result.get("similarity", 0), 4),
                            "document_id": result.get("document_id"),
                            "document_filename": metadata.get("filename"),
                            "document_type": metadata.get("document_type"),
                            "chunk_id": result.get("id")
                        })
                    logger.info(f"Found {len(matches)} product matches via RPC (threshold: {similarity_threshold})")
                    return matches

            except Exception as rpc_error:
                logger.warning(f"RPC search failed, falling back to direct query: {rpc_error}")

            # Fallback: Direct query to document_embeddings table
            embeddings = self.supabase.table("document_embeddings")\
                .select("id, document_id, chunk_text, embedding, metadata")\
                .eq("client_id", client_id)\
                .limit(100)\
                .execute()

            if not embeddings.data:
                logger.warning(f"No embeddings found for client {client_id}")
                return []

            # Calculate cosine similarity for each embedding
            matches = []
            for emb in embeddings.data:
                try:
                    stored_embedding = emb.get("embedding")
                    if not stored_embedding:
                        continue

                    # Cosine similarity calculation
                    similarity = self._cosine_similarity(query_embedding, stored_embedding)

                    if similarity >= similarity_threshold:
                        metadata = emb.get("metadata") or {}
                        matches.append({
                            "chunk_text": emb.get("chunk_text", ""),
                            "similarity_score": round(similarity, 4),
                            "document_id": emb.get("document_id"),
                            "document_filename": metadata.get("filename"),
                            "document_type": metadata.get("document_type"),
                            "chunk_id": emb.get("id")
                        })
                except Exception as e:
                    logger.error(f"Error calculating similarity: {str(e)}")
                    continue

            # Sort by similarity score (descending) and take top N
            matches.sort(key=lambda x: x["similarity_score"], reverse=True)
            top_matches = matches[:limit]

            logger.info(f"Found {len(top_matches)} product matches for query (threshold: {similarity_threshold})")

            return top_matches

        except Exception as e:
            logger.error(f"Error finding matching products: {str(e)}")
            return []
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """
        Calculate cosine similarity between two vectors
        
        Args:
            vec1: First vector
            vec2: Second vector
            
        Returns:
            Similarity score (0-1)
        """
        import math
        
        # Dot product
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        
        # Magnitudes
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(b * b for b in vec2))
        
        # Avoid division by zero
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    def process_opportunity(self, opportunity: Dict) -> Dict:
        """
        Process a single opportunity to find product matches
        
        Args:
            opportunity: Opportunity data from database
            
        Returns:
            Dictionary with match results
        """
        try:
            opportunity_id = opportunity.get("id")
            client_id = opportunity.get("client_id")
            thread_title = opportunity.get("thread_title", "")
            thread_content = opportunity.get("thread_content", "")
            
            # Combine title and content for matching
            query_text = f"{thread_title}\n\n{thread_content}"
            
            logger.info(f"Processing opportunity {opportunity_id[:8]}... for product matchback")
            
            # Find matching products
            matches = self.find_matching_products(
                client_id=client_id,
                query_text=query_text,
                limit=3,
                similarity_threshold=0.65
            )
            
            if not matches:
                logger.info(f"No product matches found for opportunity {opportunity_id[:8]}...")
                return {
                    "success": True,
                    "opportunity_id": opportunity_id,
                    "matches_found": 0,
                    "product_matches": None
                }
            
            # Format matches for storage
            product_matches = {
                "matches": [
                    {
                        "product_info": match["chunk_text"][:500],  # First 500 chars
                        "relevance_score": match["similarity_score"],
                        "source_document": match["document_filename"],
                        "document_type": match["document_type"]
                    }
                    for match in matches
                ],
                "match_count": len(matches),
                "best_match_score": matches[0]["similarity_score"],
                "matched_at": datetime.utcnow().isoformat()
            }
            
            # Update opportunity with product matches
            self.supabase.table("opportunities").update({
                "product_matches": json.dumps(product_matches),
                "matchback_completed_at": datetime.utcnow().isoformat()
            }).eq("id", opportunity_id).execute()
            
            logger.info(f"Updated opportunity {opportunity_id[:8]}... with {len(matches)} product matches")
            
            return {
                "success": True,
                "opportunity_id": opportunity_id,
                "matches_found": len(matches),
                "product_matches": product_matches
            }
        
        except Exception as e:
            logger.error(f"Error processing opportunity for matchback: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "opportunity_id": opportunity.get("id")
            }
    
    def process_all_opportunities(self, client_id: Optional[str] = None, force_rematch: bool = False) -> Dict:
        """
        Process all opportunities without product matches

        Args:
            client_id: Optional client ID to filter by
            force_rematch: If True, rematch even if matches already exist

        Returns:
            Dictionary with processing results
        """
        try:
            logger.info("=" * 70)
            logger.info("🔍 PRODUCT MATCHBACK WORKER STARTED")
            logger.info("=" * 70)
            logger.info(f"Client ID: {client_id}, Force rematch: {force_rematch}")

            # CRITICAL: Check if any products/embeddings exist before processing
            # This prevents the entire pipeline from crashing when no products are configured
            try:
                products_check = self.supabase.table("products").select("id", count="exact").limit(1).execute()
                products_count = products_check.count if products_check.count else 0
                logger.info(f"📦 Products in database: {products_count}")

                embeddings_check = self.supabase.table("vector_embeddings").select("id", count="exact").limit(1).execute()
                embeddings_count = embeddings_check.count if embeddings_check.count else 0
                logger.info(f"📦 Vector embeddings in database: {embeddings_count}")

                if products_count == 0 and embeddings_count == 0:
                    logger.info("⚠️ No products or embeddings found - skipping matchback (this is OK)")
                    logger.info("   Products can be added later via document uploads")
                    return {
                        "success": True,
                        "processed": 0,
                        "matched": 0,
                        "no_match": 0,
                        "errors": 0,
                        "message": "No products configured - matchback skipped (OK to continue)"
                    }
            except Exception as check_error:
                logger.warning(f"⚠️ Could not check products/embeddings: {check_error}")
                logger.info("   Continuing anyway - matchback will handle missing data gracefully")

            logger.info("Starting product matchback process...")
            
            # Get opportunities without product matches (or all if force_rematch)
            query = self.supabase.table("opportunities").select("*")
            
            if not force_rematch:
                query = query.is_("product_matches", "null")
            
            if client_id:
                query = query.eq("client_id", client_id)
            
            opportunities = query.execute()
            
            if not opportunities.data:
                logger.info("No opportunities to process for matchback")
                return {
                    "success": True,
                    "processed": 0,
                    "message": "No opportunities need product matchback"
                }
            
            logger.info(f"Found {len(opportunities.data)} opportunities for product matchback")
            
            processed = 0
            matched = 0
            no_match = 0
            errors = 0
            
            for opp in opportunities.data:
                try:
                    result = self.process_opportunity(opp)
                    
                    if result["success"]:
                        processed += 1
                        if result["matches_found"] > 0:
                            matched += 1
                        else:
                            no_match += 1
                    else:
                        errors += 1
                    
                    if processed % 10 == 0:
                        logger.info(f"Processed {processed}/{len(opportunities.data)} opportunities")
                
                except Exception as e:
                    logger.error(f"Error processing opportunity {opp.get('id')}: {str(e)}")
                    errors += 1
            
            logger.info(f"Matchback complete: {processed} processed, {matched} with matches, {no_match} no matches, {errors} errors")
            
            return {
                "success": True,
                "processed": processed,
                "matched": matched,
                "no_match": no_match,
                "errors": errors,
                "total": len(opportunities.data)
            }
        
        except Exception as e:
            logger.error(f"Error in product matchback process: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def rematch_opportunity(self, opportunity_id: str) -> Dict:
        """
        Rematch a specific opportunity
        
        Args:
            opportunity_id: ID of opportunity to rematch
            
        Returns:
            Dictionary with results
        """
        try:
            # Get opportunity
            opp = self.supabase.table("opportunities")\
                .select("*")\
                .eq("id", opportunity_id)\
                .execute()
            
            if not opp.data:
                return {
                    "success": False,
                    "error": f"Opportunity {opportunity_id} not found"
                }
            
            # Process matchback
            result = self.process_opportunity(opp.data[0])
            
            return result
        
        except Exception as e:
            logger.error(f"Error rematching opportunity: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }


# Utility functions for direct execution
def matchback_all_opportunities(client_id: Optional[str] = None, force_rematch: bool = False):
    """
    Run product matchback for all opportunities
    """
    worker = ProductMatchbackWorker()
    return worker.process_all_opportunities(client_id, force_rematch)


def matchback_opportunity_by_id(opportunity_id: str):
    """
    Run product matchback for specific opportunity
    """
    worker = ProductMatchbackWorker()
    return worker.rematch_opportunity(opportunity_id)


if __name__ == "__main__":
    # Test execution
    logger.info("Running Product Matchback Worker...")
    result = matchback_all_opportunities()
    logger.info(f"Results: {result}")
