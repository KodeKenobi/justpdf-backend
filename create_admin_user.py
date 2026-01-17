#!/usr/bin/env python3
"""
Create admin user for local testing
"""
import sys
import os

# Set encoding to UTF-8 to avoid Unicode errors
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from database import db, init_db
from models import User

def create_admin_user():
    """Create admin user with known credentials"""
    # Create Flask app context manually
    from flask import Flask
    app = Flask(__name__)
    
    # Initialize database
    init_db(app)
    
    with app.app_context():
        try:
            # Ensure tables are created
            db.create_all()
            
            email = 'admin@trevnoctilla.com'
            password = 'admin123'
            
            # Check if user already exists
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                print(f"User already exists: {email}")
                print(f"   Role: {existing_user.role}")
                print(f"   Active: {existing_user.is_active}")
                
                # Update password and role if needed
                existing_user.set_password(password)
                existing_user.role = 'super_admin'
                existing_user.is_active = True
                db.session.commit()
                print(f"Updated user password and role to super_admin")
                print(f"   Email: {email}")
                print(f"   Password: {password}")
                return existing_user
            
            # Create new user
            user = User(
                email=email,
                role='super_admin',
                is_active=True
            )
            user.set_password(password)
            
            db.session.add(user)
            db.session.commit()
            
            print("Admin user created successfully!")
            print(f"   Email: {user.email}")
            print(f"   Password: {password}")
            print(f"   Role: {user.role}")
            print(f"   ID: {user.id}")
            
            return user
            
        except Exception as e:
            db.session.rollback()
            print(f"Error creating admin user: {e}")
            import traceback
            traceback.print_exc()
            return None

if __name__ == '__main__':
    create_admin_user()
