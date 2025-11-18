"""
Document Processor Service
Handles text extraction, chunking, and vectorization for uploaded documents
Supports: PDF, Word (.docx), Excel (.xlsx, .xls), CSV, JSON, TXT, MD
"""

import logging
import io
import os
from typing import List, Dict, Any
from datetime import datetime

# File processing libraries
try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

try:
    import pandas as pd
except ImportError:
    pd = None

# OpenAI for embeddings
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Process documents: extract text, chunk, and create embeddings"""
    
    def __init__(self, supabase_client, chunk_size: int = 1000, chunk_overlap: int = 200):
        """
        Initialize document processor
        
        Args:
            supabase_client: Supabase client instance
            chunk_size: Characters per chunk (default 1000)
            chunk_overlap: Overlap between chunks (default 200)
        """
        self.supabase = supabase_client
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        
        # Initialize OpenAI client
        openai_key = os.getenv('OPENAI_API_KEY')
        if openai_key and OpenAI:
            self.openai_client = OpenAI(api_key=openai_key)
        else:
            self.openai_client = None
            logger.warning("OpenAI API key not found - embeddings will be skipped")
    
    async def process_document(
        self,
        document_id: str,
        client_id: str,
        file_content: bytes,
        filename: str,
        file_type: str
    ) -> Dict[str, Any]:
        """
        Process a document: extract text, chunk, and create embeddings
        
        Args:
            document_id: UUID of document record
            client_id: UUID of client
            file_content: Raw file bytes
            filename: Original filename
            file_type: MIME type
            
        Returns:
            Processing results (chunks created, embeddings created)
        """
        try:
            # Extract text from file
            text = self._extract_text(file_content, filename, file_type)
            
            if not text or len(text.strip()) < 10:
                logger.warning(f"No meaningful text extracted from {filename}")
                return {
                    'success': False,
                    'error': 'No text content found in document',
                    'chunks_created': 0,
                    'embeddings_created': 0
                }
            
            # Chunk the text
            chunks = self._chunk_text(text)
            logger.info(f"Created {len(chunks)} chunks from {filename}")
            
            # Create embeddings for each chunk
            # TODO: Re-enable embeddings once OpenAI API key is configured in Railway
            # For now, skip embedding generation to speed up uploads
            embeddings_created = 0
            logger.info(f"Skipping embedding generation (OpenAI not configured) - file uploaded successfully")
            
            logger.info(f"Successfully processed {filename}: {len(chunks)} chunks, {embeddings_created} embeddings")
            
            return {
                'success': True,
                'chunks_created': len(chunks),
                'embeddings_created': embeddings_created
            }
            
        except Exception as e:
            logger.error(f"Error processing document {filename}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'chunks_created': 0,
                'embeddings_created': 0
            }
    
    def _extract_text(self, file_content: bytes, filename: str, file_type: str) -> str:
        """
        Extract text from various file types
        
        Args:
            file_content: Raw file bytes
            filename: Original filename
            file_type: MIME type
            
        Returns:
            Extracted text
        """
        filename_lower = filename.lower()
        
        try:
            # PDF
            if filename_lower.endswith('.pdf') and PyPDF2:
                return self._extract_from_pdf(file_content)
            
            # Word (.docx)
            elif filename_lower.endswith('.docx') and DocxDocument:
                return self._extract_from_docx(file_content)
            
            # Excel (.xlsx, .xls)
            elif filename_lower.endswith(('.xlsx', '.xls')) and pd:
                return self._extract_from_excel(file_content, filename)
            
            # CSV
            elif filename_lower.endswith('.csv') and pd:
                return self._extract_from_csv(file_content)
            
            # JSON
            elif filename_lower.endswith('.json'):
                return self._extract_from_json(file_content)
            
            # Plain text (.txt, .md)
            elif filename_lower.endswith(('.txt', '.md')):
                return file_content.decode('utf-8', errors='ignore')
            
            else:
                # Try as plain text
                return file_content.decode('utf-8', errors='ignore')
                
        except Exception as e:
            logger.error(f"Error extracting text from {filename}: {str(e)}")
            # Try as plain text fallback
            try:
                return file_content.decode('utf-8', errors='ignore')
            except:
                raise ValueError(f"Could not extract text from {filename}")
    
    def _extract_from_pdf(self, file_content: bytes) -> str:
        """Extract text from PDF"""
        if not PyPDF2:
            raise ValueError("PyPDF2 not installed")
        
        pdf_file = io.BytesIO(file_content)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        
        text_parts = []
        for page in pdf_reader.pages:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        
        return "\n\n".join(text_parts)
    
    def _extract_from_docx(self, file_content: bytes) -> str:
        """Extract text from Word document"""
        if not DocxDocument:
            raise ValueError("python-docx not installed")
        
        docx_file = io.BytesIO(file_content)
        doc = DocxDocument(docx_file)
        
        text_parts = []
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                text_parts.append(paragraph.text)
        
        return "\n\n".join(text_parts)
    
    def _extract_from_excel(self, file_content: bytes, filename: str) -> str:
        """Extract text from Excel file"""
        if not pd:
            raise ValueError("pandas not installed")
        
        engine = "openpyxl" if filename.lower().endswith('.xlsx') else "xlrd"
        excel_file = io.BytesIO(file_content)
        
        # Read all sheets
        excel_data = pd.read_excel(excel_file, sheet_name=None, engine=engine)
        
        text_parts = []
        for sheet_name, df in excel_data.items():
            text_parts.append(f"Sheet: {sheet_name}")
            text_parts.append("=" * 50)
            
            # Convert to string representation
            text_parts.append(df.to_string(index=False))
            text_parts.append("")  # Blank line
        
        return "\n".join(text_parts)
    
    def _extract_from_csv(self, file_content: bytes) -> str:
        """Extract text from CSV"""
        if not pd:
            raise ValueError("pandas not installed")
        
        csv_file = io.StringIO(file_content.decode('utf-8', errors='ignore'))
        df = pd.read_csv(csv_file)
        
        return df.to_string(index=False)
    
    def _extract_from_json(self, file_content: bytes) -> str:
        """Extract text from JSON"""
        import json
        json_data = json.loads(file_content.decode('utf-8'))
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
            end = start + self.chunk_size
            
            # Try to break at sentence boundary
            if end < text_length:
                # Look for paragraph break
                para_break = text.rfind("\n\n", start, end)
                if para_break != -1 and para_break > start:
                    end = para_break
                else:
                    # Look for sentence break
                    sent_break = max(
                        text.rfind(". ", start, end),
                        text.rfind("! ", start, end),
                        text.rfind("? ", start, end)
                    )
                    if sent_break != -1 and sent_break > start:
                        end = sent_break + 1
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move with overlap
            start = end - self.chunk_overlap if end < text_length else text_length
        
        return chunks
    
    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate embedding using OpenAI
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector (1536 dimensions)
        """
        if not self.openai_client:
            return None
        
        try:
            response = self.openai_client.embeddings.create(
                model="text-embedding-ada-002",
                input=text[:8000]  # Limit to 8000 chars
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {str(e)}")
            return None
