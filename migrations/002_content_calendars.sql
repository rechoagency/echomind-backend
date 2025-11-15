-- ==========================================
-- Migration 002: Content Calendars Table
-- ==========================================
-- Purpose: Store generated content calendars for clients
-- Run this in Supabase SQL Editor
-- ==========================================

-- Create content_calendars table
CREATE TABLE IF NOT EXISTS content_calendars (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    
    -- Calendar metadata
    calendar_name VARCHAR(255) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    frequency VARCHAR(50) NOT NULL, -- 'daily', 'weekly', 'bi-weekly', 'monthly'
    
    -- Generated content
    calendar_data JSONB NOT NULL, -- Array of calendar entries
    -- Structure: [
    --   {
    --     "date": "2024-01-15",
    --     "opportunity_id": "uuid",
    --     "subreddit": "r/technology",
    --     "post_title": "How to solve X problem",
    --     "suggested_response": "Based on your experience...",
    --     "product_match": "Product Name",
    --     "priority": "HIGH",
    --     "estimated_engagement": 150
    --   }
    -- ]
    
    -- Status tracking
    status VARCHAR(50) DEFAULT 'draft', -- 'draft', 'approved', 'in_progress', 'completed'
    approval_date TIMESTAMP WITH TIME ZONE,
    approved_by VARCHAR(255),
    
    -- Statistics
    total_entries INTEGER DEFAULT 0,
    completed_entries INTEGER DEFAULT 0,
    
    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Constraints
    CONSTRAINT valid_frequency CHECK (frequency IN ('daily', 'weekly', 'bi-weekly', 'monthly')),
    CONSTRAINT valid_status CHECK (status IN ('draft', 'approved', 'in_progress', 'completed')),
    CONSTRAINT valid_date_range CHECK (end_date >= start_date)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_content_calendars_client_id ON content_calendars(client_id);
CREATE INDEX IF NOT EXISTS idx_content_calendars_status ON content_calendars(status);
CREATE INDEX IF NOT EXISTS idx_content_calendars_date_range ON content_calendars(start_date, end_date);
CREATE INDEX IF NOT EXISTS idx_content_calendars_created_at ON content_calendars(created_at DESC);

-- Create GIN index for JSONB queries
CREATE INDEX IF NOT EXISTS idx_content_calendars_data ON content_calendars USING GIN(calendar_data);

-- Add updated_at trigger
CREATE OR REPLACE FUNCTION update_content_calendars_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER content_calendars_updated_at_trigger
    BEFORE UPDATE ON content_calendars
    FOR EACH ROW
    EXECUTE FUNCTION update_content_calendars_updated_at();

-- Grant permissions (adjust role name as needed)
-- GRANT ALL ON content_calendars TO authenticated;
-- GRANT ALL ON content_calendars TO service_role;

COMMENT ON TABLE content_calendars IS 'Stores generated content calendars for client posting schedules';
COMMENT ON COLUMN content_calendars.calendar_data IS 'JSONB array of calendar entries with dates, opportunities, and suggested content';
COMMENT ON COLUMN content_calendars.frequency IS 'Posting frequency: daily, weekly, bi-weekly, or monthly';
COMMENT ON COLUMN content_calendars.status IS 'Calendar workflow status: draft, approved, in_progress, or completed';
