#!/usr/bin/env python3
"""
Script to delete all users from the database
WARNING: This will permanently delete ALL users and their related data!

Usage:
    Local: python delete_all_users.py
    Production: Set DATABASE_URL environment variable and run
"""

from app import app
from database import db
from models import User, APIKey, UsageLog, ResetHistory, Notification
from sqlalchemy import text

def delete_all_users():
    """Delete all users and their related data"""
    with app.app_context():
        try:
            # Get count before deletion
            user_count = User.query.count()
            print(f"[INFO] Found {user_count} users in database")
            
            if user_count == 0:
                print("[OK] No users to delete")
                return
            
            # Confirm deletion
            print("\n[WARN]  WARNING: This will permanently delete ALL users!")
            print(f"   - {user_count} users")
            print(f"   - All API keys")
            print(f"   - All usage logs")
            print(f"   - All reset history")
            print(f"   - All notifications")
            
            response = input("\n❓ Are you sure you want to continue? (type 'DELETE ALL' to confirm): ")
            
            if response != 'DELETE ALL':
                print("[ERROR] Deletion cancelled")
                return
            
            print("\n️  Starting deletion...")
            
            # Delete related data first (though cascade should handle APIKey)
            # Delete notifications
            notification_count = Notification.query.count()
            if notification_count > 0:
                Notification.query.delete()
                print(f"   [OK] Deleted {notification_count} notifications")
            
            # Delete usage logs
            usage_log_count = UsageLog.query.count()
            if usage_log_count > 0:
                UsageLog.query.delete()
                print(f"   [OK] Deleted {usage_log_count} usage logs")
            
            # Delete reset history
            reset_history_count = ResetHistory.query.count()
            if reset_history_count > 0:
                ResetHistory.query.delete()
                print(f"   [OK] Deleted {reset_history_count} reset history records")
            
            # Delete API keys (cascade should handle this, but being explicit)
            api_key_count = APIKey.query.count()
            if api_key_count > 0:
                APIKey.query.delete()
                print(f"   [OK] Deleted {api_key_count} API keys")
            
            # Delete all users
            deleted_count = User.query.delete()
            db.session.commit()
            
            print(f"\n[OK] Successfully deleted {deleted_count} users and all related data")
            print(f"   Total users remaining: {User.query.count()}")
            
        except Exception as e:
            db.session.rollback()
            print(f"\n[ERROR] Error deleting users: {e}")
            import traceback
            traceback.print_exc()
            raise

if __name__ == '__main__':
    import sys
    
    # Check if running in production (has DATABASE_URL)
    is_production = bool(app.config.get('DATABASE_URL') or 
                        app.config.get('SQLALCHEMY_DATABASE_URI'))
    
    env = "PRODUCTION" if is_production else "LOCAL"
    print(f" Environment: {env}")
    
    if is_production:
        print("[WARN]  PRODUCTION MODE DETECTED!")
        print("   Make sure you have the correct DATABASE_URL set")
        response = input("   Continue with production database? (yes/no): ")
        if response.lower() != 'yes':
            print("[ERROR] Cancelled")
            sys.exit(0)
    
    delete_all_users()

