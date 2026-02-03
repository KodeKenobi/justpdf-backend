-- Self-learning brain storage (Supabase). No domains stored — pattern-only intelligence.
-- Run this in Supabase SQL Editor to create tables.

-- Aggregated pattern strength (pattern_type + pattern_value = one row, we upsert and increment)
CREATE TABLE IF NOT EXISTS brain_patterns (
  id BIGSERIAL PRIMARY KEY,
  pattern_type TEXT NOT NULL,
  pattern_value TEXT NOT NULL,
  success_count INT NOT NULL DEFAULT 0,
  use_count INT NOT NULL DEFAULT 0,
  last_used_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(pattern_type, pattern_value)
);

CREATE INDEX IF NOT EXISTS idx_brain_patterns_type ON brain_patterns(pattern_type);
CREATE INDEX IF NOT EXISTS idx_brain_patterns_success ON brain_patterns(pattern_type, success_count DESC);

-- Raw learning events for admin visibility (what happened, when; no domain)
CREATE TABLE IF NOT EXISTS brain_events (
  id BIGSERIAL PRIMARY KEY,
  event_type TEXT NOT NULL,
  pattern_value TEXT,
  outcome TEXT NOT NULL,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_brain_events_created ON brain_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_brain_events_type ON brain_events(event_type);

COMMENT ON TABLE brain_patterns IS 'Aggregated learned patterns (no domains). pattern_type: contact_keyword, cookie_selector, submit_selector, etc.';
COMMENT ON TABLE brain_events IS 'Recent learning events for admin dashboard; no domain stored.';
