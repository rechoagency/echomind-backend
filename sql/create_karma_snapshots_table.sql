-- Create karma_snapshots table for tracking Reddit profile karma over time

CREATE TABLE IF NOT EXISTS karma_snapshots (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    profile_id UUID NOT NULL REFERENCES client_reddit_profiles(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
    username VARCHAR(255) NOT NULL,
    total_karma INTEGER NOT NULL,
    comment_karma INTEGER NOT NULL,
    link_karma INTEGER NOT NULL,
    snapshot_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS karma_snapshots_profile_id_idx ON karma_snapshots (profile_id);
CREATE INDEX IF NOT EXISTS karma_snapshots_client_id_idx ON karma_snapshots (client_id);
CREATE INDEX IF NOT EXISTS karma_snapshots_date_idx ON karma_snapshots (snapshot_date DESC);

-- Composite index for growth queries
CREATE INDEX IF NOT EXISTS karma_snapshots_profile_date_idx ON karma_snapshots (profile_id, snapshot_date DESC);

COMMENT ON TABLE karma_snapshots IS 'Daily snapshots of Reddit profile karma for tracking growth over time';
