"""
Migration script to add session_id column to campaigns table
This allows guest users to have their campaigns filtered by browser session
"""

import os
from database import db
from models import Campaign
from sqlalchemy import text

def migrate():
    """Add session_id column to campaigns table"""
    try:
        # Check if column already exists
        with db.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='campaigns' AND column_name='session_id'
            """))
            
            if result.fetchone():
                print("[OK] session_id column already exists in campaigns table")
                return True
        
        # Add session_id column
        print("[MIGRATE] Adding session_id column to campaigns table...")
        with db.engine.connect() as conn:
            conn.execute(text("""
                ALTER TABLE campaigns 
                ADD COLUMN session_id VARCHAR(100)
            """))
            conn.commit()
            
        # Create index for performance
        print("[MIGRATE] Creating index on session_id...")
        with db.engine.connect() as conn:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_campaigns_session_id 
                ON campaigns(session_id)
            """))
            conn.commit()
            
        print("[SUCCESS] Migration completed successfully")
        print("  - Added session_id column to campaigns table")
        print("  - Created index on session_id for performance")
        return True
        
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Campaign Session ID Migration")
    print("=" * 60)
    
    # Initialize Flask app context
    from app import app
    with app.app_context():
        success = migrate()
        
    if success:
        print("\n✅ Migration completed successfully!")
        print("\nGuest users will now have their campaigns isolated by browser session.")
    else:
        print("\n❌ Migration failed. Please check the error messages above.")
