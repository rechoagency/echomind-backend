-- =====================================================
-- MIGRATION: Add opportunity_score column to opportunities table
-- Created: 2025-12-03
-- Purpose: Enable opportunity scoring worker to save scores
-- =====================================================

-- Add opportunity_score column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'opportunities'
                   AND column_name = 'opportunity_score') THEN
        ALTER TABLE opportunities ADD COLUMN opportunity_score DECIMAL(5,2);
    END IF;
END $$;

-- Set default for new opportunities
ALTER TABLE opportunities ALTER COLUMN opportunity_score SET DEFAULT NULL;

-- Create index for filtering by score
CREATE INDEX IF NOT EXISTS idx_opportunities_score ON opportunities (opportunity_score);

-- Reload PostgREST schema cache
NOTIFY pgrst, 'reload schema';

-- =====================================================
-- VERIFICATION: Check the column was added
-- =====================================================
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'opportunities'
-- AND column_name = 'opportunity_score';
