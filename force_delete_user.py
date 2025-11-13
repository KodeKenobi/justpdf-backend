#!/usr/bin/env python3
"""
Force delete a user - more aggressive deletion
"""
import os
from app import app
from database import db
from models import User, APIKey, UsageLog, ResetHistory, Notification
from sqlalchemy import text

def force_delete_user(email):
    """Force delete a user using raw SQL if needed"""
    with app.app_context():
        try:
            email = email.strip().lower()
            
            # First try ORM approach
            user = User.query.filter_by(email=email).first()
            
            if not user:
                print(f"❌ User not found: {email}")
                return False
            
            user_id = user.id
            print(f"📊 Found user: {email} (ID: {user_id})")
            
            # Delete using raw SQL to ensure it works
            try:
                # Delete related data
                db.session.execute(text("DELETE FROM api_keys WHERE user_id = :user_id"), {"user_id": user_id})
                db.session.execute(text("DELETE FROM usage_logs WHERE user_id = :user_id"), {"user_id": user_id})
                db.session.execute(text("DELETE FROM reset_history WHERE user_id = :user_id"), {"user_id": user_id})
                db.session.execute(text("UPDATE notifications SET read_by = NULL WHERE read_by = :user_id"), {"user_id": user_id})
                
                # Delete user
                db.session.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": user_id})
                db.session.commit()
                
                # Verify
                verify = db.session.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).fetchone()
                if verify:
                    print(f"❌ User still exists after SQL delete!")
                    return False
                
                print(f"✅ User {email} force deleted successfully")
                return True
                
            except Exception as e:
                db.session.rollback()
                print(f"❌ SQL delete error: {e}")
                raise
                
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python force_delete_user.py <email>")
        sys.exit(1)
    
    email = sys.argv[1]
    force_delete_user(email)

