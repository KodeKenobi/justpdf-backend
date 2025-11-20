#!/usr/bin/env python3
"""
Create test user for login flow testing
Uses the same credentials as test-login-flow.js
"""

from app import app
from database import db
from models import User
from auth import register_user

def create_login_test_user():
    with app.app_context():
        # Ensure tables are created
        db.create_all()

        email = 'tshepomtshali89@gmail.com'
        password = 'Kopenikus0218!'  # Same password as test script

        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            print(f"✅ User already exists: {email}")
            print(f"   ID: {existing_user.id}")
            print(f"   Role: {existing_user.role}")
            print(f"   Active: {existing_user.is_active}")
            
            # Update password to ensure it matches
            existing_user.set_password(password)
            db.session.commit()
            print(f"   ✅ Password updated to match test script")
            return existing_user

        # Create new user
        print(f"📝 Creating test user: {email}")
        user, message = register_user(email, password, role='user')
        if user:
            print(f"✅ User created successfully!")
            print(f"   Email: {email}")
            print(f"   Password: {password}")
            print(f"   Role: {user.role}")
            print(f"   Active: {user.is_active}")
            print(f"   ID: {user.id}")
            return user
        else:
            print(f"❌ Error creating user: {message}")
            return None

if __name__ == '__main__':
    create_login_test_user()

