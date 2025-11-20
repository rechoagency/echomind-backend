-- PostgreSQL function for knowledge base vector similarity search
-- This function matches Reddit opportunities with client's proprietary knowledge base
-- Used by KnowledgeMatchbackService for RAG (Retrieval Augmented Generation)

CREATE OR REPLACE FUNCTION match_knowledge_embeddings(
  query_embedding vector(1536),
  client_id uuid,
  similarity_threshold float DEFAULT 0.70,
  match_count int DEFAULT 3
)
RETURNS TABLE (
  document_id uuid,
  chunk_text text,
  chunk_index int,
  metadata jsonb,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    de.document_id,
    de.chunk_text,
    de.chunk_index,
    de.metadata,
    1 - (de.embedding <=> query_embedding) as similarity
  FROM document_embeddings de
  WHERE 
    de.client_id = match_knowledge_embeddings.client_id
    AND 1 - (de.embedding <=> query_embedding) >= similarity_threshold
  ORDER BY de.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Add index for faster vector similarity searches if not exists
CREATE INDEX IF NOT EXISTS document_embeddings_embedding_idx 
ON document_embeddings 
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Add index on client_id for faster filtering
CREATE INDEX IF NOT EXISTS document_embeddings_client_id_idx 
ON document_embeddings (client_id);

-- Grant execute permissions to authenticated users
GRANT EXECUTE ON FUNCTION match_knowledge_embeddings TO authenticated;

COMMENT ON FUNCTION match_knowledge_embeddings IS 
'Vector similarity search for knowledge base RAG. Finds most relevant document chunks for a given query embedding, filtered by client_id.';
