-- Create analytics tables for real analytics tracking
-- Run this SQL script on your database to create the analytics tables

-- Analytics Events Table
CREATE TABLE IF NOT EXISTS analytics_events (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  event_type VARCHAR(50) NOT NULL,
  event_name VARCHAR(100) NOT NULL,
  properties JSONB,
  session_id VARCHAR(100) NOT NULL,
  page_url TEXT NOT NULL,
  page_title TEXT,
  timestamp TIMESTAMP NOT NULL,
  user_agent TEXT,
  device_type VARCHAR(20),
  browser VARCHAR(50),
  os VARCHAR(50),
  referrer TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Page Views Table
CREATE TABLE IF NOT EXISTS page_views (
  id SERIAL PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  session_id VARCHAR(100) NOT NULL,
  page_url TEXT NOT NULL,
  page_title TEXT,
  timestamp TIMESTAMP NOT NULL,
  duration INTEGER,
  referrer TEXT,
  user_agent TEXT,
  device_type VARCHAR(20),
  browser VARCHAR(50),
  os VARCHAR(50),
  created_at TIMESTAMP DEFAULT NOW()
);

-- User Sessions Table
CREATE TABLE IF NOT EXISTS user_sessions (
  id VARCHAR(100) PRIMARY KEY,
  user_id INTEGER REFERENCES users(id),
  start_time TIMESTAMP NOT NULL,
  last_activity TIMESTAMP NOT NULL,
  page_views INTEGER DEFAULT 0,
  events INTEGER DEFAULT 0,
  device_type VARCHAR(20),
  browser VARCHAR(50),
  os VARCHAR(50),
  country VARCHAR(50),
  city VARCHAR(50),
  ip_address VARCHAR(45),
  user_agent TEXT,
  referrer TEXT,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_analytics_events_user_id ON analytics_events(user_id);
CREATE INDEX IF NOT EXISTS idx_analytics_events_timestamp ON analytics_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_analytics_events_event_name ON analytics_events(event_name);
CREATE INDEX IF NOT EXISTS idx_analytics_events_session_id ON analytics_events(session_id);
CREATE INDEX IF NOT EXISTS idx_page_views_user_id ON page_views(user_id);
CREATE INDEX IF NOT EXISTS idx_page_views_timestamp ON page_views(timestamp);
CREATE INDEX IF NOT EXISTS idx_page_views_session_id ON page_views(session_id);
CREATE INDEX IF NOT EXISTS idx_page_views_page_url ON page_views(page_url);
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sessions_start_time ON user_sessions(start_time);

