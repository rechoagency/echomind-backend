"""
Documents Router - Handles client document operations
Provides endpoints for listing, uploading, and deleting documents
"""
from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form
from typing import List, Dict, Any
import logging
from datetime import datetime
import hashlib
import io

# Import shared Supabase client
from supabase_client import get_supabase_client

# Import document processing
from services.document_processor import DocumentProcessor

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/clients/{client_id}/documents")
async def get_client_documents(client_id: str) -> List[Dict[str, Any]]:
    """
    Get all documents uploaded for a specific client
    
    Args:
        client_id: UUID of the client
        
    Returns:
        List of documents with metadata (filename, upload_date, file_size, etc.)
    """
    try:
        supabase = get_supabase_client()
        
        # Query client_documents table
        response = supabase.table('client_documents') \
            .select('*') \
            .eq('client_id', client_id) \
            .order('uploaded_at', desc=True) \
            .execute()
        
        if not response.data:
            return []
        
        # Format response for frontend
        documents = []
        for doc in response.data:
            documents.append({
                'id': doc.get('id'),
                'filename': doc.get('filename'),
                'file_size': doc.get('file_size', 0),
                'file_type': doc.get('file_type', 'Unknown'),
                'uploaded_at': doc.get('uploaded_at'),
                'file_url': doc.get('file_url'),
                'metadata': doc.get('metadata', {})
            })
        
        logger.info(f"Retrieved {len(documents)} documents for client {client_id}")
        return documents
        
    except Exception as e:
        logger.error(f"Error retrieving documents for client {client_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve documents: {str(e)}"
        )


@router.post("/clients/{client_id}/documents/upload")
async def upload_client_documents(
    client_id: str,
    files: List[UploadFile] = File(...)
) -> Dict[str, Any]:
    """
    Upload one or more documents for a client
    
    Args:
        client_id: UUID of the client
        files: List of files to upload
        
    Returns:
        Upload results with document IDs and processing status
    """
    try:
        supabase = get_supabase_client()
        processor = DocumentProcessor(supabase)
        
        results = []
        
        for file in files:
            try:
                # Read file content
                content = await file.read()
                
                # Validate file size (50MB max)
                if len(content) > 50 * 1024 * 1024:
                    results.append({
                        'filename': file.filename,
                        'success': False,
                        'error': 'File too large (max 50MB)'
                    })
                    continue
                
                # Validate file type
                allowed_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.csv', '.json', '.txt', '.md']
                if not any(file.filename.lower().endswith(ext) for ext in allowed_extensions):
                    results.append({
                        'filename': file.filename,
                        'success': False,
                        'error': f'Unsupported file type. Allowed: {", ".join(allowed_extensions)}'
                    })
                    continue
                
                # Calculate file hash
                file_hash = hashlib.sha256(content).hexdigest()
                
                # Check for duplicates
                existing = supabase.table('client_documents') \
                    .select('id, filename') \
                    .eq('client_id', client_id) \
                    .eq('metadata->>file_hash', file_hash) \
                    .execute()
                
                if existing.data:
                    results.append({
                        'filename': file.filename,
                        'success': False,
                        'error': f'Duplicate file (already uploaded as {existing.data[0]["filename"]})'
                    })
                    continue
                
                # Store file metadata (we'll store content as base64 in metadata for now)
                # In production, you'd upload to S3/storage
                import base64
                file_base64 = base64.b64encode(content).decode('utf-8')
                
                document_record = {
                    'client_id': client_id,
                    'filename': file.filename,
                    'file_type': file.content_type or 'application/octet-stream',
                    'file_size': len(content),
                    'file_url': f'data:{file.content_type};base64,{file_base64[:100]}...',  # Truncated for display
                    'uploaded_at': datetime.utcnow().isoformat(),
                    'metadata': {
                        'file_hash': file_hash,
                        'original_filename': file.filename,
                        'content_base64': file_base64  # Store full content here
                    }
                }
                
                # Insert document record
                doc_response = supabase.table('client_documents').insert(document_record).execute()
                
                if not doc_response.data:
                    raise Exception("Failed to insert document record")
                
                document_id = doc_response.data[0]['id']
                
                # Process document (extract text and create embeddings)
                processing_result = await processor.process_document(
                    document_id=document_id,
                    client_id=client_id,
                    file_content=content,
                    filename=file.filename,
                    file_type=file.content_type or 'application/octet-stream'
                )
                
                results.append({
                    'filename': file.filename,
                    'success': True,
                    'document_id': document_id,
                    'chunks_created': processing_result.get('chunks_created', 0),
                    'embeddings_created': processing_result.get('embeddings_created', 0)
                })
                
                logger.info(f"Successfully uploaded and processed {file.filename} for client {client_id}")
                
            except Exception as file_error:
                logger.error(f"Error processing file {file.filename}: {str(file_error)}")
                results.append({
                    'filename': file.filename,
                    'success': False,
                    'error': str(file_error)
                })
        
        # Summary
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        
        return {
            'success': successful > 0,
            'total_files': len(files),
            'successful': successful,
            'failed': failed,
            'results': results
        }
        
    except Exception as e:
        logger.error(f"Error uploading documents for client {client_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload documents: {str(e)}"
        )


@router.delete("/clients/{client_id}/documents/{document_id}")
async def delete_client_document(client_id: str, document_id: str) -> Dict[str, Any]:
    """
    Delete a specific document and its embeddings
    
    Args:
        client_id: UUID of the client
        document_id: UUID of the document to delete
        
    Returns:
        Success message with deleted document info
    """
    try:
        supabase = get_supabase_client()
        
        # First, verify document belongs to this client
        doc_response = supabase.table('client_documents') \
            .select('*') \
            .eq('id', document_id) \
            .eq('client_id', client_id) \
            .execute()
        
        if not doc_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found for client {client_id}"
            )
        
        document = doc_response.data[0]
        
        # Delete associated embeddings first (foreign key constraint)
        embeddings_response = supabase.table('document_embeddings') \
            .delete() \
            .eq('document_id', document_id) \
            .execute()
        
        embeddings_deleted = len(embeddings_response.data) if embeddings_response.data else 0
        
        # Delete the document record
        delete_response = supabase.table('client_documents') \
            .delete() \
            .eq('id', document_id) \
            .execute()
        
        logger.info(f"Deleted document {document_id} and {embeddings_deleted} embeddings for client {client_id}")
        
        return {
            'success': True,
            'message': f"Document '{document['filename']}' deleted successfully",
            'document_id': document_id,
            'embeddings_deleted': embeddings_deleted
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {str(e)}"
        )


@router.get("/clients/{client_id}/documents/{document_id}/embeddings")
async def get_document_embeddings_count(client_id: str, document_id: str) -> Dict[str, Any]:
    """
    Get embedding count for a specific document (for debugging)
    
    Args:
        client_id: UUID of the client
        document_id: UUID of the document
        
    Returns:
        Document info with embedding count
    """
    try:
        supabase = get_supabase_client()
        
        # Get document info
        doc_response = supabase.table('client_documents') \
            .select('*') \
            .eq('id', document_id) \
            .eq('client_id', client_id) \
            .execute()
        
        if not doc_response.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found"
            )
        
        document = doc_response.data[0]
        
        # Count embeddings
        embeddings_response = supabase.table('document_embeddings') \
            .select('id', count='exact') \
            .eq('document_id', document_id) \
            .execute()
        
        embedding_count = embeddings_response.count if embeddings_response.count else 0
        
        return {
            'document_id': document_id,
            'filename': document['filename'],
            'uploaded_at': document['uploaded_at'],
            'embedding_count': embedding_count,
            'file_size': document.get('file_size', 0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting embeddings for document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve embeddings: {str(e)}"
        )
