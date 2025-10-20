from app import app
from database import db
from models import User

def check_user_exists():
    with app.app_context():
        # Ensure tables are created
        db.create_all()

        email = 'kodekenobi@gmail.com'
        
        # Check all users
        all_users = User.query.all()
        print(f"📊 Total users in database: {len(all_users)}")
        
        for user in all_users:
            print(f"   User: {user.email} (ID: {user.id}, Active: {user.is_active}, Role: {user.role})")
        
        # Find specific user
        user = User.query.filter_by(email=email).first()
        if user:
            print(f"\n✅ Found user: {email}")
            print(f"   ID: {user.id}")
            print(f"   Role: {user.role}")
            print(f"   Active: {user.is_active}")
            print(f"   Created: {user.created_at}")
            print(f"   Password hash: {user.password_hash[:30]}...")
        else:
            print(f"\n❌ User not found: {email}")
            
        # Test case-insensitive search
        user_lower = User.query.filter(User.email.ilike(email)).first()
        if user_lower:
            print(f"✅ Found user (case-insensitive): {user_lower.email}")
        else:
            print(f"❌ User not found (case-insensitive)")

if __name__ == '__main__':
    check_user_exists()
