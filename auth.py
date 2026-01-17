from flask import request, jsonify, g
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from datetime import datetime, timedelta
import re

# Initialize JWT manager (will be initialized in app.py)
jwt = JWTManager()

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    
    return True, "Password is valid"

def register_user(email, password, role='user'):
    """Register a new user"""
    try:
        from database import db
        from models import User
        
        # Validate email
        if not validate_email(email):
            return None, "Invalid email format"
        
        # Validate password
        is_valid, message = validate_password(password)
        if not is_valid:
            return None, message
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        
        if existing_user:
            # If user exists and is active, reject registration
            if existing_user.is_active:
                return None, "Email already registered"
            # If user exists but is deactivated, reactivate them with new password
            else:
                existing_user.set_password(password)
                existing_user.is_active = True
                existing_user.created_at = datetime.utcnow()  # Reset creation date
                db.session.commit()
                print(f"[OK] Reactivated deactivated user: {email}")
                return existing_user, "Account reactivated successfully"
        
        # Create new user
        user = User(email=email, role=role)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        return user, "User registered successfully"
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return None, str(e)

def login_user(email, password):
    """Login user and return JWT token"""
    try:
        from database import db
        from models import User
        
        # Find user
        user = User.query.filter_by(email=email, is_active=True).first()
        if not user:
            return None, "Invalid credentials"
        
        # Check password
        if not user.check_password(password):
            return None, "Invalid credentials"
        
        # CRITICAL: Sync role from Supabase if available
        # This ensures the backend always has the correct role from Supabase
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
            
            # Use hardcoded Supabase connection string
            supabase_url = "postgresql://postgres.pqdxqvxyrahvongbhtdb:Kopenikus0218!@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
            
            conn = psycopg2.connect(supabase_url, sslmode='require')
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            cursor.execute(
                "SELECT role, is_active FROM users WHERE email = %s",
                (email.lower(),)
            )
            supabase_user = cursor.fetchone()
            
            cursor.close()
            conn.close()
            
            # If user exists in Supabase and role differs, sync it
            if supabase_user:
                supabase_role = supabase_user['role']
                supabase_is_active = supabase_user['is_active']
                
                if user.role != supabase_role or user.is_active != supabase_is_active:
                    print(f"[RELOAD] [LOGIN] Syncing role from Supabase for {email}: {user.role} -> {supabase_role}")
                    user.role = supabase_role
                    user.is_active = supabase_is_active
                    db.session.commit()
                    print(f"[OK] [LOGIN] Role synced from Supabase: {email} now has role {supabase_role}")
        except Exception as sync_error:
            # Don't fail login if Supabase sync fails
            print(f"[WARN] [LOGIN] Failed to sync role from Supabase: {sync_error}")
        
        # Update last login
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        # Create JWT token
        expires = timedelta(hours=24)
        access_token = create_access_token(
            identity=str(user.id),
            expires_delta=expires
        )
        
        return {
            'user': user.to_dict(),
            'access_token': access_token,
            'expires_in': int(expires.total_seconds())
        }, "Login successful"
        
    except Exception as e:
        return None, str(e)

def reset_password(email):
    """Initiate password reset (placeholder for email sending)"""
    try:
        from models import User
        
        user = User.query.filter_by(email=email, is_active=True).first()
        if not user:
            # Don't reveal if email exists
            return True, "If the email exists, a reset link has been sent"
        
        # In a real implementation, you would:
        # 1. Generate a secure reset token
        # 2. Store it in the database with expiration
        # 3. Send email with reset link
        
        # For now, just return success
        return True, "If the email exists, a reset link has been sent"
        
    except Exception as e:
        return False, str(e)

def change_password(user_id, old_password, new_password):
    """Change user password"""
    try:
        from database import db
        from models import User
        
        user = User.query.get(user_id)
        if not user:
            return False, "User not found"
        
        # Verify old password
        if not user.check_password(old_password):
            return False, "Current password is incorrect"
        
        # Validate new password
        is_valid, message = validate_password(new_password)
        if not is_valid:
            return False, message
        
        # Set new password
        user.set_password(new_password)
        db.session.commit()
        
        return True, "Password changed successfully"
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return False, str(e)

@jwt.user_identity_loader
def user_identity_lookup(user_id):
    """Load user identity from JWT token"""
    return user_id

@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    """Load user from JWT token"""
    try:
        from models import User
        
        identity = jwt_data["sub"]
        # Handle both string and integer identity
        try:
            user_id = int(identity) if isinstance(identity, str) else identity
            return User.query.get(user_id)
        except (ValueError, TypeError) as e:
            print(f"Error in user lookup: {e}, identity: {identity}, type: {type(identity)}")
            return None
    except Exception as e:
        print(f"Error importing User model: {e}")
        return None

def require_auth(f):
    """Decorator to require JWT authentication"""
    from functools import wraps
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        # User is automatically loaded by user_lookup_callback
        g.current_user = get_jwt_identity()
        return f(*args, **kwargs)
    return decorated_function

def require_admin(f):
    """Decorator to require admin role"""
    from functools import wraps
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        from models import User
        
        user = User.query.get(get_jwt_identity())
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function
