-- =====================================================
-- MIGRATION: Fix opportunities table - Add missing columns
-- Created: 2025-11-26
-- Purpose: Fix column mismatch between code and database
-- =====================================================

-- PART 1: Add missing columns (already done)
-- These were added in the first migration run

-- PART 2: Fix NOT NULL constraints that prevent inserts
-- The brand_mention_monitor.py doesn't set all fields that have NOT NULL constraints
-- Make these columns nullable or set default values

-- Fix thread_created_at - set default to current timestamp
ALTER TABLE opportunities ALTER COLUMN thread_created_at DROP NOT NULL;
ALTER TABLE opportunities ALTER COLUMN thread_created_at SET DEFAULT NOW();

-- Fix subreddit_score - set default to 0
ALTER TABLE opportunities ALTER COLUMN subreddit_score DROP NOT NULL;
ALTER TABLE opportunities ALTER COLUMN subreddit_score SET DEFAULT 0;

-- Fix thread_score - set default to 0
ALTER TABLE opportunities ALTER COLUMN thread_score DROP NOT NULL;
ALTER TABLE opportunities ALTER COLUMN thread_score SET DEFAULT 0;

-- Fix user_score - set default to 0
ALTER TABLE opportunities ALTER COLUMN user_score DROP NOT NULL;
ALTER TABLE opportunities ALTER COLUMN user_score SET DEFAULT 0;

-- Fix combined_score - set default to 0
ALTER TABLE opportunities ALTER COLUMN combined_score DROP NOT NULL;
ALTER TABLE opportunities ALTER COLUMN combined_score SET DEFAULT 0;

-- Fix priority_tier - set default to 'PENDING'
ALTER TABLE opportunities ALTER COLUMN priority_tier DROP NOT NULL;
ALTER TABLE opportunities ALTER COLUMN priority_tier SET DEFAULT 'PENDING';

-- Reload PostgREST schema cache
NOTIFY pgrst, 'reload schema';

-- =====================================================
-- VERIFICATION: Run this to check NOT NULL columns
-- =====================================================
-- SELECT column_name, is_nullable, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'opportunities'
-- AND is_nullable = 'NO'
-- ORDER BY column_name;
