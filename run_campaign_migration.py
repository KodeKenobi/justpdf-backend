#!/usr/bin/env python3
"""
Migration script to make campaigns table public (user_id nullable)
"""
import os
import sys

def run_migration():
    """Run the database migration to make user_id nullable"""
    try:
        # Try psycopg2 first (production)
        import psycopg2
        
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            print("ERROR: DATABASE_URL environment variable not set")
            print("For Supabase, get the connection string from:")
            print("  Supabase Dashboard > Project Settings > Database > Connection String")
            sys.exit(1)
        
        print(f"Connecting to database...")
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        print("Running migration: Making user_id nullable in campaigns table...")
        
        # Make user_id nullable
        cursor.execute("""
            ALTER TABLE campaigns 
            ALTER COLUMN user_id DROP NOT NULL;
        """)
        
        # Add comments
        cursor.execute("""
            COMMENT ON TABLE campaigns IS 'Contact automation campaigns - Public, no user authentication required';
        """)
        
        cursor.execute("""
            COMMENT ON COLUMN campaigns.user_id IS 'Optional user ID - NULL for public campaigns';
        """)
        
        conn.commit()
        print("SUCCESS: Migration completed successfully!")
        print("- user_id column in campaigns table is now nullable")
        print("- Campaigns can now be created without authentication")
        
        cursor.close()
        conn.close()
        
    except ImportError:
        print("ERROR: psycopg2 not installed")
        print("Install it with: pip install psycopg2-binary")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    print("=" * 60)
    print("Campaign Table Migration - Make Public")
    print("=" * 60)
    print()
    run_migration()
