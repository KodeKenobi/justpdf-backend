from app import app
from database import db
from models import User

def debug_user():
    with app.app_context():
        # Ensure tables are created
        db.create_all()

        email = 'kodekenobi@gmail.com'
        password = 'Kopenikus0218!'

        # Find user
        user = User.query.filter_by(email=email).first()
        if not user:
            print(f"[ERROR] User not found: {email}")
            return

        print(f"[OK] User found: {email}")
        print(f"   ID: {user.id}")
        print(f"   Role: {user.role}")
        print(f"   Active: {user.is_active}")
        print(f"   Password hash: {user.password_hash[:20]}...")
        
        # Test password check
        password_check = user.check_password(password)
        print(f"   Password check: {password_check}")
        
        # Test with different password
        wrong_password_check = user.check_password("wrongpassword")
        print(f"   Wrong password check: {wrong_password_check}")

if __name__ == '__main__':
    debug_user()
