"""
Document Ingestion Service
Handles file uploads, chunking, and vectorization for client documents
Supports: PDF, Word (.docx), Excel (.xlsx, .xls), CSV, JSON, TXT
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib

# File processing libraries
import PyPDF2
from docx import Document as DocxDocument
import pandas as pd

# OpenAI for embeddings
from openai import OpenAI

# Supabase client (assumed to be passed in or initialized)
from supabase import create_client, Client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DocumentIngestionService:
    """
    Service for ingesting, chunking, and vectorizing client documents
    """
    
    def __init__(self, supabase_client: Client, openai_api_key: str):
        """
        Initialize the document ingestion service
        
        Args:
            supabase_client: Initialized Supabase client
            openai_api_key: OpenAI API key for embeddings
        """
        self.supabase = supabase_client
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.chunk_size = 1000  # characters per chunk
        self.chunk_overlap = 200  # overlap between chunks
        
    def process_document(
        self, 
        client_id: str,
        file_content: bytes,
        filename: str,
        file_type: str,
        document_type: str = "brand_document"
    ) -> Dict[str, Any]:
        """
        Main entry point for document processing
        
        Args:
            client_id: UUID of the client
            file_content: Raw file bytes
            filename: Original filename
            file_type: MIME type or extension
            document_type: Type of document (brand_document, product_feed, support_ticket, etc.)
            
        Returns:
            Dictionary with processing results
        """
        try:
            logger.info(f"Processing document: {filename} for client: {client_id}")
            
            # Extract text based on file type
            extracted_text = self._extract_text(file_content, file_type, filename)
            
            if not extracted_text or len(extracted_text.strip()) == 0:
                raise ValueError(f"No text could be extracted from {filename}")
            
            # Calculate file hash for deduplication
            file_hash = hashlib.sha256(file_content).hexdigest()
            
            # Check if document already exists
            existing = self.supabase.table("document_uploads").select("id").eq("file_hash", file_hash).eq("client_id", client_id).execute()
            
            if existing.data and len(existing.data) > 0:
                logger.warning(f"Document {filename} already exists (hash: {file_hash})")
                return {
                    "success": False,
                    "message": "Document already uploaded",
                    "document_id": existing.data[0]["id"]
                }
            
            # Store document metadata
            document_record = {
                "client_id": client_id,
                "filename": filename,
                "file_type": file_type,
                "file_size": len(file_content),
                "file_hash": file_hash,
                "document_type": document_type,
                "processing_status": "processing",
                "uploaded_at": datetime.utcnow().isoformat()
            }
            
            doc_result = self.supabase.table("document_uploads").insert(document_record).execute()
            document_id = doc_result.data[0]["id"]
            
            # Chunk the text
            chunks = self._chunk_text(extracted_text)
            logger.info(f"Created {len(chunks)} chunks from {filename}")
            
            # Process each chunk
            chunk_ids = []
            for idx, chunk_text in enumerate(chunks):
                chunk_id = self._process_chunk(
                    document_id=document_id,
                    client_id=client_id,
                    chunk_text=chunk_text,
                    chunk_index=idx,
                    document_type=document_type
                )
                chunk_ids.append(chunk_id)
            
            # Update document status
            self.supabase.table("document_uploads").update({
                "processing_status": "completed",
                "processed_at": datetime.utcnow().isoformat(),
                "chunk_count": len(chunks)
            }).eq("id", document_id).execute()
            
            logger.info(f"Successfully processed document {filename}: {len(chunks)} chunks, {len(chunk_ids)} vectors")
            
            return {
                "success": True,
                "document_id": document_id,
                "filename": filename,
                "chunks_created": len(chunks),
                "vectors_created": len(chunk_ids)
            }
            
        except Exception as e:
            logger.error(f"Error processing document {filename}: {str(e)}")
            
            # Update document status to failed if we have a document_id
            if 'document_id' in locals():
                self.supabase.table("document_uploads").update({
                    "processing_status": "failed",
                    "error_message": str(e)
                }).eq("id", document_id).execute()
            
            return {
                "success": False,
                "error": str(e),
                "filename": filename
            }
    
    def _extract_text(self, file_content: bytes, file_type: str, filename: str) -> str:
        """
        Extract text from various file types
        
        Args:
            file_content: Raw file bytes
            file_type: MIME type or extension
            filename: Original filename (used for extension detection)
            
        Returns:
            Extracted text content
        """
        # Normalize file type
        file_type_lower = file_type.lower()
        filename_lower = filename.lower()
        
        try:
            # PDF files
            if "pdf" in file_type_lower or filename_lower.endswith(".pdf"):
                return self._extract_from_pdf(file_content)
            
            # Word documents (.docx)
            elif "word" in file_type_lower or "officedocument" in file_type_lower or filename_lower.endswith(".docx"):
                return self._extract_from_docx(file_content)
            
            # Excel files (.xlsx, .xls)
            elif "excel" in file_type_lower or "spreadsheet" in file_type_lower or filename_lower.endswith((".xlsx", ".xls")):
                return self._extract_from_excel(file_content, filename)
            
            # CSV files
            elif "csv" in file_type_lower or filename_lower.endswith(".csv"):
                return self._extract_from_csv(file_content)
            
            # JSON files
            elif "json" in file_type_lower or filename_lower.endswith(".json"):
                return self._extract_from_json(file_content)
            
            # Plain text files
            elif "text" in file_type_lower or filename_lower.endswith(".txt"):
                return file_content.decode("utf-8")
            
            else:
                # Try as plain text as fallback
                try:
                    return file_content.decode("utf-8")
                except Exception as e:
                    raise ValueError(f"Unsupported file type: {file_type}")
                    
        except Exception as e:
            logger.error(f"Error extracting text from {filename}: {str(e)}")
            raise
    
    def _extract_from_pdf(self, file_content: bytes) -> str:
        """Extract text from PDF files"""
        import io
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text_parts = []
        for page in pdf_reader.pages:
            text_parts.append(page.extract_text())
        
        return "\n\n".join(text_parts)
    
    def _extract_from_docx(self, file_content: bytes) -> str:
        """Extract text from Word documents (.docx)"""
        import io
        docx_file = io.BytesIO(file_content)
        doc = DocxDocument(docx_file)
        
        text_parts = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text_parts.append(paragraph.text)
        
        return "\n\n".join(text_parts)
    
    def _extract_from_excel(self, file_content: bytes, filename: str) -> str:
        """
        Extract text from Excel files (.xlsx, .xls)
        Smart detection for product feeds vs general data
        """
        import io
        
        # Determine engine based on file extension
        engine = "openpyxl" if filename.lower().endswith(".xlsx") else "xlrd"
        
        excel_file = io.BytesIO(file_content)
        
        # Read all sheets
        excel_data = pd.read_excel(excel_file, sheet_name=None, engine=engine)
        
        text_parts = []
        
        for sheet_name, df in excel_data.items():
            text_parts.append(f"Sheet: {sheet_name}")
            text_parts.append("=" * 50)
            
            # Check if this looks like a product feed
            columns_lower = [col.lower() for col in df.columns]
            is_product_feed = any(keyword in " ".join(columns_lower) for keyword in 
                                 ["product", "sku", "price", "description", "item"])
            
            if is_product_feed:
                # Format as product entries
                for idx, row in df.iterrows():
                    row_text = " | ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
                    text_parts.append(row_text)
            else:
                # Format as general data table
                text_parts.append(df.to_string(index=False))
            
            text_parts.append("")  # Blank line between sheets
        
        return "\n".join(text_parts)
    
    def _extract_from_csv(self, file_content: bytes) -> str:
        """Extract text from CSV files"""
        import io
        csv_file = io.StringIO(file_content.decode("utf-8"))
        df = pd.read_csv(csv_file)
        
        # Check if this looks like a product feed
        columns_lower = [col.lower() for col in df.columns]
        is_product_feed = any(keyword in " ".join(columns_lower) for keyword in 
                             ["product", "sku", "price", "description", "item"])
        
        if is_product_feed:
            # Format as product entries
            text_parts = []
            for idx, row in df.iterrows():
                row_text = " | ".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
                text_parts.append(row_text)
            return "\n".join(text_parts)
        else:
            # Format as table
            return df.to_string(index=False)
    
    def _extract_from_json(self, file_content: bytes) -> str:
        """Extract text from JSON files"""
        json_data = json.loads(file_content.decode("utf-8"))
        
        # Pretty print JSON for better chunking
        return json.dumps(json_data, indent=2)
    
    def _chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks
        
        Args:
            text: Full text to chunk
            
        Returns:
            List of text chunks
        """
        chunks = []
        start = 0
        text_length = len(text)
        
        while start < text_length:
            # Calculate end position
            end = start + self.chunk_size
            
            # If this isn't the last chunk, try to break at a sentence or paragraph
            if end < text_length:
                # Look for paragraph break first
                paragraph_break = text.rfind("\n\n", start, end)
                if paragraph_break != -1 and paragraph_break > start:
                    end = paragraph_break
                else:
                    # Look for sentence break
                    sentence_break = max(
                        text.rfind(". ", start, end),
                        text.rfind("! ", start, end),
                        text.rfind("? ", start, end)
                    )
                    if sentence_break != -1 and sentence_break > start:
                        end = sentence_break + 1
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move start position with overlap
            start = end - self.chunk_overlap if end < text_length else text_length
        
        return chunks
    
    def _process_chunk(
        self,
        document_id: str,
        client_id: str,
        chunk_text: str,
        chunk_index: int,
        document_type: str
    ) -> str:
        """
        Process a single chunk: store it and create embedding
        
        Args:
            document_id: Parent document ID
            client_id: Client UUID
            chunk_text: Text content of chunk
            chunk_index: Index of chunk in document
            document_type: Type of document
            
        Returns:
            Chunk ID
        """
        # Store chunk
        chunk_record = {
            "document_id": document_id,
            "client_id": client_id,
            "chunk_index": chunk_index,
            "chunk_text": chunk_text,
            "char_count": len(chunk_text),
            "created_at": datetime.utcnow().isoformat()
        }
        
        chunk_result = self.supabase.table("document_chunks").insert(chunk_record).execute()
        chunk_id = chunk_result.data[0]["id"]
        
        # Generate embedding
        try:
            embedding = self._generate_embedding(chunk_text)
            
            # Store embedding
            embedding_record = {
                "chunk_id": chunk_id,
                "client_id": client_id,
                "embedding": embedding,
                "model": "text-embedding-3-small",
                "document_type": document_type,
                "created_at": datetime.utcnow().isoformat()
            }
            
            self.supabase.table("vector_embeddings").insert(embedding_record).execute()
            
        except Exception as e:
            logger.error(f"Error generating embedding for chunk {chunk_id}: {str(e)}")
            # Continue processing even if embedding fails
        
        return chunk_id
    
    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate OpenAI embedding for text
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector
        """
        response = self.openai_client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        
        return response.data[0].embedding
    
    def search_similar_content(
        self,
        client_id: str,
        query_text: str,
        limit: int = 5,
        similarity_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Search for similar content using vector similarity
        
        Args:
            client_id: Client UUID
            query_text: Search query
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score (0-1)
            
        Returns:
            List of matching chunks with similarity scores
        """
        try:
            # Generate embedding for query
            query_embedding = self._generate_embedding(query_text)
            
            # Use Supabase RPC function for vector similarity search
            # This requires a database function to be created (see migration SQL)
            results = self.supabase.rpc(
                "search_similar_chunks",
                {
                    "query_embedding": query_embedding,
                    "query_client_id": client_id,
                    "match_threshold": similarity_threshold,
                    "match_count": limit
                }
            ).execute()
            
            return results.data
            
        except Exception as e:
            logger.error(f"Error searching similar content: {str(e)}")
            return []
    
    def get_product_matches(
        self,
        client_id: str,
        user_query: str,
        limit: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Find relevant products for a user query
        
        Args:
            client_id: Client UUID
            user_query: User's question or pain point
            limit: Maximum number of products to return
            
        Returns:
            List of matching products with relevance scores
        """
        # Search for similar content
        matches = self.search_similar_content(
            client_id=client_id,
            query_text=user_query,
            limit=limit,
            similarity_threshold=0.6
        )
        
        # Format results
        products = []
        for match in matches:
            products.append({
                "chunk_text": match.get("chunk_text"),
                "similarity_score": match.get("similarity"),
                "document_id": match.get("document_id"),
                "document_type": match.get("document_type")
            })
        
        return products


# Utility function for easy initialization
def create_document_service(supabase_url: str, supabase_key: str, openai_api_key: str) -> DocumentIngestionService:
    """
    Factory function to create document service
    
    Args:
        supabase_url: Supabase project URL
        supabase_key: Supabase API key
        openai_api_key: OpenAI API key
        
    Returns:
        Initialized DocumentIngestionService
    """
    supabase_client = create_client(supabase_url, supabase_key)
    return DocumentIngestionService(supabase_client, openai_api_key)
