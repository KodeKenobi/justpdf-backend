#!/usr/bin/env python3
"""
Reset password for kodekenobi@gmail.com
"""

from app import app
from database import db
from models import User

def reset_user_password():
    """Reset password for kodekenobi@gmail.com"""
    with app.app_context():
        try:
            # Find the user
            user = User.query.filter_by(email='kodekenobi@gmail.com').first()
            if not user:
                print("[ERROR] User not found: kodekenobi@gmail.com")
                return False
            
            # Set new password
            new_password = 'Kopenikus0218!'
            user.set_password(new_password)
            user.is_active = True
            
            db.session.commit()
            
            print("[OK] Password reset successfully!")
            print(f"   Email: {user.email}")
            print(f"   Password: {new_password}")
            print(f"   Role: {user.role}")
            print(f"   Active: {user.is_active}")
            print(f"   ID: {user.id}")
            
            return True
            
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Error resetting password: {e}")
            return False

if __name__ == "__main__":
    reset_user_password()
