#!/usr/bin/env python3
"""
Create a test user for login testing
"""

from app import app
from database import db
from models import User

def create_test_user():
    """Create a test user"""
    with app.app_context():
        try:
            # Check if user already exists
            existing_user = User.query.filter_by(email='kodekenobi@gmail.com').first()
            if existing_user:
                print(f"✅ User already exists: {existing_user.email}")
                print(f"   Role: {existing_user.role}")
                print(f"   Active: {existing_user.is_active}")
                print(f"   Created: {existing_user.created_at}")
                return existing_user
            
            # Create new user
            user = User(
                email='kodekenobi@gmail.com',
                role='admin',
                is_active=True
            )
            user.set_password('TestPassword123!')
            
            db.session.add(user)
            db.session.commit()
            
            print("✅ Test user created successfully!")
            print(f"   Email: {user.email}")
            print(f"   Password: TestPassword123!")
            print(f"   Role: {user.role}")
            print(f"   ID: {user.id}")
            
            return user
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error creating test user: {e}")
            return None

if __name__ == "__main__":
    create_test_user()
