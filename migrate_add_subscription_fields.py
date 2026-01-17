"""Migration script to add subscription fields to users table"""
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from database import db

with app.app_context():
    try:
        # Add new columns to users table
        print("[RELOAD] Adding subscription_tier column...")
        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(20) DEFAULT 'free'"))
            db.session.commit()
            print("[OK] Added subscription_tier")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("[WARN] subscription_tier already exists")
            else:
                raise
        
        print("[RELOAD] Adding monthly_call_limit column...")
        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN monthly_call_limit INTEGER DEFAULT 5"))
            db.session.commit()
            print("[OK] Added monthly_call_limit")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("[WARN] monthly_call_limit already exists")
            else:
                raise
        
        print("[RELOAD] Adding monthly_used column...")
        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN monthly_used INTEGER DEFAULT 0"))
            db.session.commit()
            print("[OK] Added monthly_used")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("[WARN] monthly_used already exists")
            else:
                raise
        
        print("[RELOAD] Adding monthly_reset_date column...")
        try:
            db.session.execute(db.text("ALTER TABLE users ADD COLUMN monthly_reset_date DATETIME DEFAULT CURRENT_TIMESTAMP"))
            db.session.commit()
            print("[OK] Added monthly_reset_date")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("[WARN] monthly_reset_date already exists")
            else:
                raise
        
        print("[OK] Migration completed successfully!")
        
    except Exception as e:
        print(f"[ERROR] Migration error: {e}")
        db.session.rollback()
        raise

