-- Migration: Make campaigns table public (user_id nullable)
-- This allows campaigns to be created without authentication

-- Make user_id nullable in campaigns table
ALTER TABLE campaigns 
ALTER COLUMN user_id DROP NOT NULL;

-- Add comment to explain this is a public table
COMMENT ON TABLE campaigns IS 'Contact automation campaigns - Public, no user authentication required';
COMMENT ON COLUMN campaigns.user_id IS 'Optional user ID - NULL for public campaigns';
