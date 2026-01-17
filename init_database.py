#!/usr/bin/env python3
"""
Initialize the database with all tables
"""

from app import app
from database import db

def init_database():
    """Create all database tables"""
    with app.app_context():
        try:
            db.create_all()
            print("[OK] Database tables created successfully!")
            print("[INFO] Tables created:")
            print("   - users")
            print("   - api_keys") 
            print("   - usage_logs")
            print("   - rate_limits")
            print("   - jobs")
            print("   - webhooks")
        except Exception as e:
            print(f"[ERROR] Error creating database tables: {e}")

if __name__ == "__main__":
    init_database()
