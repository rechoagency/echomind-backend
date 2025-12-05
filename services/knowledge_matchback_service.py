"""
Knowledge Base Matchback Service
Matches Reddit opportunities with client's proprietary knowledge base using vector similarity
Enables thought leadership content by citing unique research, case studies, and data
"""

import logging
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
from openai import OpenAI

logger = logging.getLogger(__name__)

class KnowledgeMatchbackService:
    """Match opportunities with client knowledge base using RAG"""
    
    def __init__(self, supabase_client):
        """
        Initialize knowledge matchback service
        
        Args:
            supabase_client: Supabase client instance
        """
        self.supabase = supabase_client
        
        # Initialize OpenAI client
        openai_key = os.getenv('OPENAI_API_KEY')
        if openai_key:
            self.openai_client = OpenAI(api_key=openai_key)
            logger.info("OpenAI client initialized for knowledge matchback")
        else:
            self.openai_client = None
            logger.warning("OpenAI API key not found - knowledge matchback disabled")
    
    def match_opportunity_to_knowledge(
        self,
        opportunity_text: str,
        client_id: str,
        similarity_threshold: float = 0.70,
        max_insights: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Find relevant knowledge base insights for an opportunity
        
        Args:
            opportunity_text: Combined title + content from Reddit opportunity
            client_id: Client UUID
            similarity_threshold: Minimum similarity score (0.70 = 70%)
            max_insights: Maximum number of insights to return
            
        Returns:
            List of relevant insights with excerpts and metadata
        """
        try:
            if not self.openai_client:
                logger.warning("OpenAI not configured - skipping knowledge matchback")
                return []
            
            # Generate embedding for opportunity text
            logger.info(f"Generating embedding for opportunity text (length: {len(opportunity_text)})")
            embedding = self._generate_embedding(opportunity_text)
            
            if not embedding:
                logger.error("Failed to generate embedding for opportunity")
                return []
            
            # Vector search against client's knowledge base
            logger.info(f"Searching knowledge base for client {client_id} with threshold {similarity_threshold}")
            
            # Use Supabase RPC for vector similarity search
            # Note: This assumes you have a PostgreSQL function `match_knowledge_embeddings`
            # Similar to the product matchback function
            response = self.supabase.rpc(
                'match_knowledge_embeddings',
                {
                    'query_embedding': embedding,
                    'client_id': client_id,
                    'similarity_threshold': similarity_threshold,
                    'match_count': max_insights
                }
            ).execute()
            
            if not response.data:
                logger.info(f"No knowledge base matches found above {similarity_threshold} threshold")
                return []
            
            # Format results
            insights = []
            for match in response.data:
                insights.append({
                    'document_id': match.get('document_id'),
                    'chunk_text': match.get('chunk_text', ''),
                    'excerpt': self._create_excerpt(match.get('chunk_text', '')),
                    'similarity_score': match.get('similarity', 0.0),
                    'relevance_percentage': round(match.get('similarity', 0.0) * 100, 1),
                    'metadata': match.get('metadata', {}),
                    'source_filename': match.get('metadata', {}).get('filename', 'Unknown'),
                    'document_type': match.get('metadata', {}).get('document_type', 'research')
                })
            
            logger.info(f"Found {len(insights)} relevant knowledge base insights for opportunity")
            return insights
            
        except Exception as e:
            logger.error(f"Error in knowledge matchback: {str(e)}", exc_info=True)
            return []
    
    def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate OpenAI embedding for text
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector or None if failed
        """
        try:
            # Use same model as product matchback for consistency
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=text[:8000]  # Truncate to avoid token limits
            )
            
            embedding = response.data[0].embedding
            logger.info(f"Generated embedding with {len(embedding)} dimensions")
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            return None
    
    def _create_excerpt(self, text: str, max_length: int = 300) -> str:
        """
        Create a concise excerpt from chunk text
        
        Args:
            text: Full chunk text
            max_length: Maximum excerpt length
            
        Returns:
            Excerpt string
        """
        if len(text) <= max_length:
            return text
        
        # Try to break at sentence boundary
        excerpt = text[:max_length]
        last_period = excerpt.rfind('.')
        
        if last_period > max_length * 0.7:  # If period is reasonably close to end
            return excerpt[:last_period + 1]
        else:
            return excerpt + "..."
    
    def get_knowledge_base_stats(self, client_id: str) -> Dict[str, Any]:
        """
        Get statistics about client's knowledge base

        Args:
            client_id: Client UUID

        Returns:
            Stats (document count, chunk count, coverage)
        """
        try:
            # Count documents (using document_uploads table)
            docs_response = self.supabase.table('document_uploads') \
                .select('id', count='exact') \
                .eq('client_id', client_id) \
                .eq('processing_status', 'completed') \
                .execute()

            document_count = docs_response.count if docs_response.count else 0

            # Count chunks from document_chunks table
            chunk_count = 0
            try:
                chunks_response = self.supabase.table('document_chunks') \
                    .select('id', count='exact') \
                    .eq('client_id', client_id) \
                    .execute()
                chunk_count = chunks_response.count if chunks_response.count else 0
            except Exception:
                pass  # Table might not exist

            # Count embeddings from vector_embeddings table
            vector_count = 0
            try:
                vector_response = self.supabase.table('vector_embeddings') \
                    .select('id', count='exact') \
                    .eq('client_id', client_id) \
                    .execute()
                vector_count = vector_response.count if vector_response.count else 0
            except Exception:
                pass  # Table might not exist

            # Also count embeddings from document_embeddings table (legacy/alternate)
            doc_emb_count = 0
            try:
                doc_emb_response = self.supabase.table('document_embeddings') \
                    .select('id', count='exact') \
                    .eq('client_id', client_id) \
                    .execute()
                doc_emb_count = doc_emb_response.count if doc_emb_response.count else 0
            except Exception:
                pass  # Table might not exist

            # Use whichever has data
            embedding_count = max(vector_count, doc_emb_count)
            total_chunks = max(chunk_count, embedding_count)

            # If no chunks in tables but documents report chunk_count, get from document_uploads
            if total_chunks == 0 and document_count > 0:
                try:
                    docs_with_chunks = self.supabase.table('document_uploads') \
                        .select('chunk_count') \
                        .eq('client_id', client_id) \
                        .eq('processing_status', 'completed') \
                        .execute()
                    if docs_with_chunks.data:
                        total_chunks = sum(d.get('chunk_count', 0) or 0 for d in docs_with_chunks.data)
                except Exception:
                    pass

            return {
                'documents_uploaded': document_count,
                'knowledge_chunks': total_chunks,
                'vector_embeddings': embedding_count,
                'avg_chunks_per_document': round(total_chunks / document_count, 1) if document_count > 0 else 0,
                'estimated_coverage_kb': total_chunks * 1  # ~1KB per chunk
            }

        except Exception as e:
            logger.error(f"Error getting knowledge base stats: {str(e)}")
            return {
                'documents_uploaded': 0,
                'knowledge_chunks': 0,
                'vector_embeddings': 0,
                'avg_chunks_per_document': 0,
                'estimated_coverage_kb': 0
            }
    
    def update_document_metadata(
        self,
        document_id: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """
        Update metadata for a document (useful for categorization)

        Args:
            document_id: Document UUID
            metadata: Metadata to add/update

        Returns:
            True if successful
        """
        try:
            # Update document metadata (using document_uploads table)
            self.supabase.table('document_uploads') \
                .update({'metadata': metadata}) \
                .eq('id', document_id) \
                .execute()

            logger.info(f"Updated metadata for document {document_id}")
            return True

        except Exception as e:
            logger.error(f"Error updating document metadata: {str(e)}")
            return False
