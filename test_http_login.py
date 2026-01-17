from app import app
from database import db
from models import User
from auth import login_user
import json

def test_http_login():
    with app.app_context():
        # Simulate the exact HTTP request
        email = 'kodekenobi@gmail.com'
        password = 'Kopenikus0218!'
        
        print(f" Testing HTTP login simulation")
        print(f"   Email: {email}")
        print(f"   Password: {password}")
        print(f"   Email type: {type(email)}")
        print(f"   Password type: {type(password)}")
        
        # Test the login_user function
        result, message = login_user(email, password)
        
        if result:
            print(f"[OK] Login successful!")
            print(f"   Message: {message}")
            print(f"   User ID: {result['user']['id']}")
            print(f"   User Email: {result['user']['email']}")
            print(f"   User Role: {result['user']['role']}")
            print(f"   Token length: {len(result['access_token'])}")
        else:
            print(f"[ERROR] Login failed!")
            print(f"   Message: {message}")
            
        # Test with JSON serialization (like HTTP request)
        request_data = {'email': email, 'password': password}
        json_data = json.dumps(request_data)
        parsed_data = json.loads(json_data)
        
        print(f"\n Testing with JSON serialization")
        print(f"   Parsed email: {parsed_data['email']}")
        print(f"   Parsed password: {parsed_data['password']}")
        
        result2, message2 = login_user(parsed_data['email'], parsed_data['password'])
        
        if result2:
            print(f"[OK] JSON login successful!")
        else:
            print(f"[ERROR] JSON login failed: {message2}")

if __name__ == '__main__':
    test_http_login()
