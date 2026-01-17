from app import app
from database import db
from models import User
from auth import register_user

def create_test_user():
    with app.app_context():
        # Ensure tables are created
        db.create_all()

        email = 'kodekenobi@gmail.com'
        password = 'Kopenikus0218!' # User-specified password

        # Delete existing user first
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            print(f"️ Deleting existing user: {email}")
            db.session.delete(existing_user)
            db.session.commit()

        # Create new user
        user, message = register_user(email, password, role='admin')
        if user:
            print(f"[OK] User created successfully: {email}")
            print(f"   Password: {password}")
            print(f"   Role: {user.role}")
            print(f"   Active: {user.is_active}")
            print(f"   ID: {user.id}")
        else:
            print(f"[ERROR] Error creating user: {message}")

if __name__ == '__main__':
    create_test_user()
