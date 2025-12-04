-- =====================================================
-- MIGRATION: Fix document_uploads table schema
-- Created: 2025-12-03
-- Purpose: Add missing columns required by document_ingestion_service.py
--
-- Issue: The document upload endpoint fails with:
--   "column document_uploads.file_hash does not exist"
-- =====================================================

-- Add file_hash column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'document_uploads'
                   AND column_name = 'file_hash') THEN
        ALTER TABLE document_uploads ADD COLUMN file_hash VARCHAR(64);
    END IF;
END $$;

-- Add file_size column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'document_uploads'
                   AND column_name = 'file_size') THEN
        ALTER TABLE document_uploads ADD COLUMN file_size BIGINT;
    END IF;
END $$;

-- Add file_type column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'document_uploads'
                   AND column_name = 'file_type') THEN
        ALTER TABLE document_uploads ADD COLUMN file_type VARCHAR(100);
    END IF;
END $$;

-- Add uploaded_at column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'document_uploads'
                   AND column_name = 'uploaded_at') THEN
        ALTER TABLE document_uploads ADD COLUMN uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();
    END IF;
END $$;

-- Add filename column if it doesn't exist (code expects 'filename' not 'file_name')
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'document_uploads'
                   AND column_name = 'filename') THEN
        -- Check if file_name exists, if so rename it
        IF EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'document_uploads'
                   AND column_name = 'file_name') THEN
            ALTER TABLE document_uploads RENAME COLUMN file_name TO filename;
        ELSE
            ALTER TABLE document_uploads ADD COLUMN filename VARCHAR(255);
        END IF;
    END IF;
END $$;

-- Add document_type column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'document_uploads'
                   AND column_name = 'document_type') THEN
        ALTER TABLE document_uploads ADD COLUMN document_type VARCHAR(50) DEFAULT 'brand_document';
    END IF;
END $$;

-- Add processing_status column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'document_uploads'
                   AND column_name = 'processing_status') THEN
        ALTER TABLE document_uploads ADD COLUMN processing_status VARCHAR(20) DEFAULT 'pending';
    END IF;
END $$;

-- Add processed_at column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'document_uploads'
                   AND column_name = 'processed_at') THEN
        ALTER TABLE document_uploads ADD COLUMN processed_at TIMESTAMP WITH TIME ZONE;
    END IF;
END $$;

-- Add chunk_count column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'document_uploads'
                   AND column_name = 'chunk_count') THEN
        ALTER TABLE document_uploads ADD COLUMN chunk_count INTEGER DEFAULT 0;
    END IF;
END $$;

-- Add error_message column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'document_uploads'
                   AND column_name = 'error_message') THEN
        ALTER TABLE document_uploads ADD COLUMN error_message TEXT;
    END IF;
END $$;

-- Create index for file_hash lookups (deduplication)
CREATE INDEX IF NOT EXISTS idx_document_uploads_file_hash ON document_uploads (file_hash);

-- Create index for client_id lookups
CREATE INDEX IF NOT EXISTS idx_document_uploads_client_id ON document_uploads (client_id);

-- =====================================================
-- ALSO: Ensure document_chunks table exists
-- =====================================================
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES document_uploads(id) ON DELETE CASCADE,
    client_id UUID NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    char_count INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks (document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_client_id ON document_chunks (client_id);

-- =====================================================
-- ALSO: Ensure vector_embeddings table exists
-- =====================================================
CREATE TABLE IF NOT EXISTS vector_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chunk_id UUID REFERENCES document_chunks(id) ON DELETE CASCADE,
    client_id UUID NOT NULL,
    embedding vector(1536),  -- OpenAI text-embedding-3-small dimension
    model VARCHAR(50) DEFAULT 'text-embedding-3-small',
    document_type VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vector_embeddings_client_id ON vector_embeddings (client_id);

-- Reload PostgREST schema cache
NOTIFY pgrst, 'reload schema';

-- =====================================================
-- VERIFICATION: Check the columns were added
-- =====================================================
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'document_uploads'
-- ORDER BY ordinal_position;
