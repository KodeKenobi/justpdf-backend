#!/usr/bin/env python3
"""
Script to delete a specific user by email
"""

from app import app
from database import db
from models import User, APIKey, UsageLog, ResetHistory, Notification

def delete_user_by_email(email):
    """Delete a specific user by email"""
    with app.app_context():
        try:
            email = email.strip().lower()
            user = User.query.filter_by(email=email).first()
            
            if not user:
                print(f"[ERROR] User not found: {email}")
                return False
            
            print(f"[INFO] Found user: {email} (ID: {user.id})")
            print(f"   Role: {user.role}")
            print(f"   Active: {user.is_active}")
            print(f"   Created: {user.created_at}")
            
            # Delete related data
            api_keys = APIKey.query.filter_by(user_id=user.id).all()
            if api_keys:
                for key in api_keys:
                    db.session.delete(key)
                print(f"   [OK] Deleted {len(api_keys)} API keys")
            
            usage_logs = UsageLog.query.filter_by(user_id=user.id).all()
            if usage_logs:
                for log in usage_logs:
                    db.session.delete(log)
                print(f"   [OK] Deleted {len(usage_logs)} usage logs")
            
            reset_history = ResetHistory.query.filter_by(user_id=user.id).all()
            if reset_history:
                for history in reset_history:
                    db.session.delete(history)
                print(f"   [OK] Deleted {len(reset_history)} reset history records")
            
            notifications = Notification.query.filter_by(read_by=user.id).all()
            if notifications:
                for notif in notifications:
                    notif.read_by = None
                print(f"   [OK] Cleared {len(notifications)} notification references")
            
            # Delete user
            db.session.delete(user)
            db.session.commit()
            
            print(f"\n[OK] Successfully deleted user: {email}")
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"\n[ERROR] Error deleting user: {e}")
            import traceback
            traceback.print_exc()
            return False

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python delete_user.py <email>")
        sys.exit(1)
    
    email = sys.argv[1]
    delete_user_by_email(email)

