#!/usr/bin/env python3
"""
Script to view database contents
"""
from app import app
from database import db
from models import User, APIKey, UsageLog, ResetHistory, Notification
from sqlalchemy import inspect, text

def view_database():
    """View all database contents"""
    with app.app_context():
        try:
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
            
            print("=" * 60)
            print("DATABASE CONTENTS")
            print("=" * 60)
            print(f"\n📊 Database: {db.engine.url}")
            print(f"📋 Tables: {', '.join(tables)}\n")
            
            # View Users
            if 'users' in tables:
                users = User.query.all()
                print(f"\n👥 USERS ({len(users)} total):")
                print("-" * 60)
                for user in users:
                    print(f"  ID: {user.id}")
                    print(f"  Email: {user.email}")
                    print(f"  Role: {user.role}")
                    print(f"  Active: {user.is_active}")
                    print(f"  Tier: {user.subscription_tier}")
                    print(f"  Created: {user.created_at}")
                    print()
            
            # View API Keys
            if 'api_keys' in tables:
                api_keys = APIKey.query.all()
                print(f"\n🔑 API KEYS ({len(api_keys)} total):")
                print("-" * 60)
                for key in api_keys:
                    print(f"  ID: {key.id}")
                    print(f"  User ID: {key.user_id}")
                    print(f"  Key: {key.key[:20]}...")
                    print(f"  Created: {key.created_at}")
                    print()
            
            # View Usage Logs
            if 'usage_logs' in tables:
                usage_logs = UsageLog.query.limit(10).all()
                print(f"\n📝 USAGE LOGS (showing first 10 of {UsageLog.query.count()} total):")
                print("-" * 60)
                for log in usage_logs:
                    print(f"  ID: {log.id}")
                    print(f"  User ID: {log.user_id}")
                    print(f"  Endpoint: {log.endpoint}")
                    print(f"  Created: {log.created_at}")
                    print()
            
            # View Notifications
            if 'notifications' in tables:
                notifications = Notification.query.limit(10).all()
                print(f"\n🔔 NOTIFICATIONS (showing first 10 of {Notification.query.count()} total):")
                print("-" * 60)
                for notif in notifications:
                    print(f"  ID: {notif.id}")
                    print(f"  Title: {notif.title}")
                    print(f"  Type: {notif.type}")
                    print(f"  Read: {notif.is_read}")
                    print(f"  Created: {notif.created_at}")
                    print()
            
            print("=" * 60)
            
        except Exception as e:
            print(f"❌ Error viewing database: {e}")
            import traceback
            traceback.print_exc()

if __name__ == '__main__':
    view_database()

