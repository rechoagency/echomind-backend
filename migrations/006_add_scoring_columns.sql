-- =====================================================
-- MIGRATION: Add scoring columns to opportunities table
-- Created: 2025-12-07
-- Purpose: Enable full opportunity scoring with all score types
-- =====================================================

-- Add composite_score column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'opportunities'
                   AND column_name = 'composite_score') THEN
        ALTER TABLE opportunities ADD COLUMN composite_score DECIMAL(5,2);
    END IF;
END $$;

-- Add commercial_intent_score if doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'opportunities'
                   AND column_name = 'commercial_intent_score') THEN
        ALTER TABLE opportunities ADD COLUMN commercial_intent_score DECIMAL(5,2);
    END IF;
END $$;

-- Add relevance_score if doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'opportunities'
                   AND column_name = 'relevance_score') THEN
        ALTER TABLE opportunities ADD COLUMN relevance_score DECIMAL(5,2);
    END IF;
END $$;

-- Add engagement_score if doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'opportunities'
                   AND column_name = 'engagement_score') THEN
        ALTER TABLE opportunities ADD COLUMN engagement_score DECIMAL(5,2);
    END IF;
END $$;

-- Add timing_score if doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'opportunities'
                   AND column_name = 'timing_score') THEN
        ALTER TABLE opportunities ADD COLUMN timing_score DECIMAL(5,2);
    END IF;
END $$;

-- Add priority_tier if doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'opportunities'
                   AND column_name = 'priority_tier') THEN
        ALTER TABLE opportunities ADD COLUMN priority_tier VARCHAR(20);
    END IF;
END $$;

-- Add scoring_debug for debugging
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name = 'opportunities'
                   AND column_name = 'scoring_debug') THEN
        ALTER TABLE opportunities ADD COLUMN scoring_debug JSONB;
    END IF;
END $$;

-- Create indexes for filtering
CREATE INDEX IF NOT EXISTS idx_opportunities_composite_score ON opportunities (composite_score);
CREATE INDEX IF NOT EXISTS idx_opportunities_priority_tier ON opportunities (priority_tier);

-- Reload PostgREST schema cache
NOTIFY pgrst, 'reload schema';

-- =====================================================
-- VERIFICATION QUERY (run manually to check):
-- =====================================================
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'opportunities'
-- AND column_name IN ('composite_score', 'commercial_intent_score',
--                     'relevance_score', 'engagement_score',
--                     'timing_score', 'priority_tier', 'scoring_debug');
