-- Add metadata column to content_delivered table for knowledge insights tracking
-- This column stores JSON data about which knowledge base insights were used in content generation

-- Add metadata column if it doesn't exist
ALTER TABLE content_delivered 
ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb;

-- Add index for faster metadata queries
CREATE INDEX IF NOT EXISTS content_delivered_metadata_idx 
ON content_delivered USING gin (metadata);

-- Add comment
COMMENT ON COLUMN content_delivered.metadata IS 
'JSON metadata about content generation: knowledge_insights_count, thought_leadership_enabled, etc.';
