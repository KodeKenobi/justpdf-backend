from app import app
from database import db
from models import User
from auth import login_user

def test_email_case():
    with app.app_context():
        # Test different email cases
        test_cases = [
            'kodekenobi@gmail.com',
            'Kodekenobi@gmail.com', 
            'KODEKENOBI@GMAIL.COM',
            'kodekenobi@GMAIL.COM'
        ]
        
        password = 'Kopenikus0218!'
        
        for email in test_cases:
            print(f"\n🔍 Testing email: {email}")
            result, message = login_user(email, password)
            
            if result:
                print(f"✅ Login successful!")
                print(f"   Message: {message}")
            else:
                print(f"❌ Login failed: {message}")

if __name__ == '__main__':
    test_email_case()
