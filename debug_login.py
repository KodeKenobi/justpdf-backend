from app import app
from database import db
from models import User
from auth import login_user

def debug_login():
    with app.app_context():
        # Ensure tables are created
        db.create_all()

        email = 'kodekenobi@gmail.com'
        password = 'Kopenikus0218!'

        print(f" Testing login for: {email}")
        
        # Test the login_user function directly
        result, message = login_user(email, password)
        
        if result:
            print(f"[OK] Login successful!")
            print(f"   Message: {message}")
            print(f"   User ID: {result['user']['id']}")
            print(f"   User Email: {result['user']['email']}")
            print(f"   User Role: {result['user']['role']}")
            print(f"   Token exists: {'access_token' in result}")
        else:
            print(f"[ERROR] Login failed!")
            print(f"   Message: {message}")

if __name__ == '__main__':
    debug_login()
