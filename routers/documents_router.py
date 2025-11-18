"""
Documents Router - Handles client document operations
Provides endpoints for listing and deleting uploaded documents
"""
from fastapi import APIRouter, HTTPException, status
from typing import List, Dict, Any
import logging
from datetime import datetime

# Import shared Supabase client
from supabase_client import get_supabase_client

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
                'filename': doc.get('file_name'),
                'file_size': doc.get('file_size', 0),
                'file_type': doc.get('file_type', 'Unknown'),
                'uploaded_at': doc.get('uploaded_at'),
                'storage_path': doc.get('storage_path'),
                'chunk_count': doc.get('chunk_count', 0)
            })
        
        logger.info(f"Retrieved {len(documents)} documents for client {client_id}")
        return documents
        
    except Exception as e:
        logger.error(f"Error retrieving documents for client {client_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve documents: {str(e)}"
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
            'message': f"Document '{document['file_name']}' deleted successfully",
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
            'filename': document['file_name'],
            'uploaded_at': document['uploaded_at'],
            'embedding_count': embedding_count,
            'chunk_count': document.get('chunk_count', 0)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting embeddings for document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve embeddings: {str(e)}"
        )
