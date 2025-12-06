-- Fix document_embeddings foreign key constraint
-- The table has a FK to client_documents but documents are stored in document_uploads

-- Option 1: Drop the foreign key constraint entirely
ALTER TABLE document_embeddings
DROP CONSTRAINT IF EXISTS document_embeddings_document_id_fkey;

-- Option 2: Add an index on document_id for performance (without FK constraint)
CREATE INDEX IF NOT EXISTS document_embeddings_document_id_idx
ON document_embeddings (document_id);

-- Verify the constraint is gone
-- SELECT conname FROM pg_constraint WHERE conrelid = 'document_embeddings'::regclass;
