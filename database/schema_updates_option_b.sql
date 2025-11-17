-- Database Schema Updates for Option B Build
-- Run these in Supabase SQL Editor

-- =====================================================
-- 1. SUBREDDIT VOICE PROFILES TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS subreddit_voice_profiles (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    subreddit TEXT NOT NULL,
    voice_profile JSONB NOT NULL,
    sample_size INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(client_id, subreddit)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_voice_profiles_client_subreddit 
ON subreddit_voice_profiles(client_id, subreddit);

-- Voice profile structure example:
COMMENT ON TABLE subreddit_voice_profiles IS 'Stores voice patterns for each subreddit per client
Example voice_profile JSONB:
{
  "subreddit": "BeyondTheBump",
  "tone": "exhausted, supportive, real talk",
  "grammar_style": "conversational with fragments",
  "avg_sentence_length": 12.3,
  "avg_word_length": 4.8,
  "common_phrases": ["honestly", "literally", "I feel you"],
  "typo_frequency": 0.03,
  "uses_emojis": "occasional",
  "exclamation_frequency": 0.15,
  "question_frequency": 0.10,
  "sentiment_distribution": {"supportive": 40, "frustrated": 30, "hopeful": 20},
  "signature_idioms": ["solidarity", "same boat", "you got this"],
  "formality_level": "LOW",
  "voice_description": "Community writes like tired friends sharing real experiences"
}';

-- =====================================================
-- 2. CLIENT PRODUCTS TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS client_products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    product_name TEXT NOT NULL,
    description TEXT,
    price DECIMAL(10, 2),
    currency TEXT DEFAULT 'USD',
    product_url TEXT,
    pain_points TEXT[], -- Array of pain points this product addresses
    keywords TEXT[], -- Keywords for matching
    embedding VECTOR(1536), -- For vector similarity search
    metadata JSONB, -- Additional product data
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_client_products_client 
ON client_products(client_id);

CREATE INDEX IF NOT EXISTS idx_client_products_embedding 
ON client_products USING ivfflat (embedding vector_cosine_ops);

COMMENT ON TABLE client_products IS 'Stores client product catalog with vector embeddings for matchback';

-- =====================================================
-- 3. CLIENT SETTINGS TABLE (Brand Mention %, Reply/Post %)
-- =====================================================
CREATE TABLE IF NOT EXISTS client_settings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL UNIQUE REFERENCES clients(client_id) ON DELETE CASCADE,
    brand_mention_percentage DECIMAL(5, 2) DEFAULT 0.0, -- 0-100
    reply_percentage DECIMAL(5, 2) DEFAULT 75.0, -- 0-100
    post_percentage DECIMAL(5, 2) DEFAULT 25.0, -- 0-100
    current_phase INTEGER DEFAULT 1, -- 1-4 matching strategy timeline
    phase_start_date TIMESTAMP WITH TIME ZONE,
    auto_phase_progression BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT valid_brand_percentage CHECK (brand_mention_percentage >= 0 AND brand_mention_percentage <= 100),
    CONSTRAINT valid_reply_percentage CHECK (reply_percentage >= 0 AND reply_percentage <= 100),
    CONSTRAINT valid_post_percentage CHECK (post_percentage >= 0 AND post_percentage <= 100),
    CONSTRAINT valid_phase CHECK (current_phase >= 1 AND current_phase <= 4)
);

-- Index
CREATE INDEX IF NOT EXISTS idx_client_settings_client 
ON client_settings(client_id);

COMMENT ON TABLE client_settings IS 'Controls brand mention % and reply/post ratios per client
Phase 1: 0% brand mentions (trust building)
Phase 2: 5-10% brand mentions (soft introduction)
Phase 3: 15-20% brand mentions (product integration)
Phase 4: 20-25% brand mentions (sustained authority)';

-- =====================================================
-- 4. CONTENT GENERATION LOG TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS content_generation_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    opportunity_id UUID REFERENCES opportunities(id) ON DELETE CASCADE,
    client_id UUID NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    generated_content TEXT NOT NULL,
    content_preview TEXT,
    voice_profile_used TEXT,
    brand_mentioned BOOLEAN DEFAULT FALSE,
    product_matched TEXT,
    quality_score DECIMAL(3, 2),
    generation_metadata JSONB, -- Model, tokens, etc.
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_content_log_client 
ON content_generation_log(client_id);

CREATE INDEX IF NOT EXISTS idx_content_log_opportunity 
ON content_generation_log(opportunity_id);

CREATE INDEX IF NOT EXISTS idx_content_log_created 
ON content_generation_log(created_at DESC);

COMMENT ON TABLE content_generation_log IS 'Logs all generated content for auditing and improvement';

-- =====================================================
-- 5. VECTORIZED KNOWLEDGE BASE TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS client_knowledge_base (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    source_type TEXT NOT NULL, -- 'website', 'pdf', 'support_ticket', 'scientific_data', etc.
    source_identifier TEXT, -- URL, filename, ticket ID
    content_chunk TEXT NOT NULL,
    embedding VECTOR(1536),
    metadata JSONB, -- Original source metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_knowledge_client 
ON client_knowledge_base(client_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_source_type 
ON client_knowledge_base(source_type);

CREATE INDEX IF NOT EXISTS idx_knowledge_embedding 
ON client_knowledge_base USING ivfflat (embedding vector_cosine_ops);

COMMENT ON TABLE client_knowledge_base IS 'Stores vectorized client knowledge (website, docs, tickets, research) for content enrichment';

-- =====================================================
-- 6. SEO/GEO OPPORTUNITIES TABLE
-- =====================================================
CREATE TABLE IF NOT EXISTS seo_geo_opportunities (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id UUID NOT NULL REFERENCES clients(client_id) ON DELETE CASCADE,
    opportunity_type TEXT NOT NULL, -- 'google_ranking', 'chatgpt_citation', 'reddit_mention'
    reddit_url TEXT,
    keyword TEXT,
    search_position INTEGER,
    traffic_estimate INTEGER,
    priority_score DECIMAL(3, 2),
    metadata JSONB,
    discovered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_checked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_seo_geo_client 
ON seo_geo_opportunities(client_id);

CREATE INDEX IF NOT EXISTS idx_seo_geo_type 
ON seo_geo_opportunities(opportunity_type);

COMMENT ON TABLE seo_geo_opportunities IS 'Tracks Reddit threads ranking in Google or cited in ChatGPT (20% of discovery strategy)';

-- =====================================================
-- 7. UPDATE CLIENTS TABLE WITH NEW FIELDS
-- =====================================================
ALTER TABLE clients ADD COLUMN IF NOT EXISTS brand_voice JSONB;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS onboarding_completed BOOLEAN DEFAULT FALSE;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS voice_database_built BOOLEAN DEFAULT FALSE;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS intelligence_report_sent BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN clients.brand_voice IS 'Stores extracted brand voice patterns
Example:
{
  "tone": "girlfriend-approved, supportive",
  "signature_phrases": ["You are allowed to...", "Talk to your provider"],
  "medical_disclaimer": "We are not doctors - talk to your provider about...",
  "formality_level": "LOW",
  "avoid_patterns": ["toxic positivity", "corporate speak"]
}';

-- =====================================================
-- 8. CREATE FUNCTIONS FOR VECTOR SIMILARITY
-- =====================================================

-- Function to find similar products
CREATE OR REPLACE FUNCTION find_similar_products(
    query_embedding VECTOR(1536),
    p_client_id UUID,
    match_threshold DECIMAL DEFAULT 0.65,
    match_count INT DEFAULT 3
)
RETURNS TABLE (
    product_id UUID,
    product_name TEXT,
    similarity DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        id,
        client_products.product_name,
        1 - (client_products.embedding <=> query_embedding) AS similarity
    FROM client_products
    WHERE 
        client_products.client_id = p_client_id
        AND client_products.active = TRUE
        AND 1 - (client_products.embedding <=> query_embedding) > match_threshold
    ORDER BY client_products.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- Function to find relevant knowledge
CREATE OR REPLACE FUNCTION find_relevant_knowledge(
    query_embedding VECTOR(1536),
    p_client_id UUID,
    p_source_types TEXT[] DEFAULT NULL,
    match_threshold DECIMAL DEFAULT 0.70,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    knowledge_id UUID,
    content TEXT,
    source_type TEXT,
    similarity DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        id,
        content_chunk,
        client_knowledge_base.source_type,
        1 - (client_knowledge_base.embedding <=> query_embedding) AS similarity
    FROM client_knowledge_base
    WHERE 
        client_knowledge_base.client_id = p_client_id
        AND (p_source_types IS NULL OR client_knowledge_base.source_type = ANY(p_source_types))
        AND 1 - (client_knowledge_base.embedding <=> query_embedding) > match_threshold
    ORDER BY client_knowledge_base.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- =====================================================
-- 9. CREATE TRIGGERS FOR UPDATED_AT
-- =====================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to tables
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_voice_profiles_updated_at') THEN
        CREATE TRIGGER update_voice_profiles_updated_at
            BEFORE UPDATE ON subreddit_voice_profiles
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_client_products_updated_at') THEN
        CREATE TRIGGER update_client_products_updated_at
            BEFORE UPDATE ON client_products
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'update_client_settings_updated_at') THEN
        CREATE TRIGGER update_client_settings_updated_at
            BEFORE UPDATE ON client_settings
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

-- =====================================================
-- 10. GRANT PERMISSIONS
-- =====================================================

GRANT SELECT, INSERT, UPDATE, DELETE ON subreddit_voice_profiles TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON client_products TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON client_settings TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON content_generation_log TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON client_knowledge_base TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON seo_geo_opportunities TO authenticated;

-- =====================================================
-- SCHEMA UPDATE COMPLETE
-- =====================================================

-- Verify schema
SELECT 
    'subreddit_voice_profiles' as table_name,
    COUNT(*) as row_count
FROM subreddit_voice_profiles
UNION ALL
SELECT 'client_products', COUNT(*) FROM client_products
UNION ALL
SELECT 'client_settings', COUNT(*) FROM client_settings
UNION ALL
SELECT 'content_generation_log', COUNT(*) FROM content_generation_log
UNION ALL
SELECT 'client_knowledge_base', COUNT(*) FROM client_knowledge_base
UNION ALL
SELECT 'seo_geo_opportunities', COUNT(*) FROM seo_geo_opportunities;
