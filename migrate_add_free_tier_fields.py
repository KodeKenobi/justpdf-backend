"""Migration script to add free tier fields to api_keys and usage_logs tables"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from database import db

with app.app_context():
    try:
        # Add new columns to api_keys table
        print("🔄 Adding is_free_tier column to api_keys...")
        try:
            # PostgreSQL uses BOOLEAN with FALSE, not 0
            db.session.execute(db.text("ALTER TABLE api_keys ADD COLUMN is_free_tier BOOLEAN DEFAULT FALSE"))
            db.session.commit()
            print("✅ Added is_free_tier")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠️ is_free_tier already exists")
            else:
                raise
        
        print("🔄 Adding free_tier_type column to api_keys...")
        try:
            db.session.execute(db.text("ALTER TABLE api_keys ADD COLUMN free_tier_type VARCHAR(50)"))
            db.session.commit()
            print("✅ Added free_tier_type")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠️ free_tier_type already exists")
            else:
                raise
        
        print("🔄 Adding granted_by column to api_keys...")
        try:
            db.session.execute(db.text("ALTER TABLE api_keys ADD COLUMN granted_by INTEGER"))
            db.session.commit()
            print("✅ Added granted_by")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠️ granted_by already exists")
            else:
                raise
        
        print("🔄 Adding granted_at column to api_keys...")
        try:
            # PostgreSQL uses TIMESTAMP, not DATETIME
            db.session.execute(db.text("ALTER TABLE api_keys ADD COLUMN granted_at TIMESTAMP"))
            db.session.commit()
            print("✅ Added granted_at")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠️ granted_at already exists")
            else:
                raise
        
        print("🔄 Adding notes column to api_keys...")
        try:
            db.session.execute(db.text("ALTER TABLE api_keys ADD COLUMN notes TEXT"))
            db.session.commit()
            print("✅ Added notes")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠️ notes already exists")
            else:
                raise
        
        # Add new column to usage_logs table
        print("🔄 Adding is_free_tier column to usage_logs...")
        try:
            # PostgreSQL uses BOOLEAN with FALSE, not 0
            db.session.execute(db.text("ALTER TABLE usage_logs ADD COLUMN is_free_tier BOOLEAN DEFAULT FALSE"))
            db.session.commit()
            print("✅ Added is_free_tier to usage_logs")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("⚠️ is_free_tier already exists in usage_logs")
            else:
                raise
        
        # Add foreign key constraint for granted_by if it doesn't exist
        print("🔄 Checking foreign key constraint for granted_by...")
        try:
            # Check if foreign key already exists (this is database-specific)
            # For SQLite, we'll skip this as it doesn't support adding foreign keys after table creation
            # For PostgreSQL/MySQL, you might want to add the constraint
            print("⚠️ Foreign key constraint check skipped (add manually if needed)")
        except Exception as e:
            print(f"⚠️ Foreign key constraint error (non-critical): {e}")
        
        print("✅ Migration completed successfully!")
        
    except Exception as e:
        print(f"❌ Migration error: {e}")
        db.session.rollback()
        raise

