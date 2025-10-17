from flask import request, jsonify, g
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from models import User, db
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
        # Validate email
        if not validate_email(email):
            return None, "Invalid email format"
        
        # Validate password
        is_valid, message = validate_password(password)
        if not is_valid:
            return None, message
        
        # Check if user already exists
        if User.query.filter_by(email=email).first():
            return None, "Email already registered"
        
        # Create user
        user = User(email=email, role=role)
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        return user, "User registered successfully"
        
    except Exception as e:
        db.session.rollback()
        return None, str(e)

def login_user(email, password):
    """Login user and return JWT token"""
    try:
        # Find user
        user = User.query.filter_by(email=email, is_active=True).first()
        if not user:
            return None, "Invalid credentials"
        
        # Check password
        if not user.check_password(password):
            return None, "Invalid credentials"
        
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
        db.session.rollback()
        return False, str(e)

@jwt.user_identity_loader
def user_identity_lookup(user_id):
    """Load user identity from JWT token"""
    return user_id

@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    """Load user from JWT token"""
    identity = jwt_data["sub"]
    # Handle both string and integer identity
    try:
        user_id = int(identity) if isinstance(identity, str) else identity
        return User.query.get(user_id)
    except (ValueError, TypeError) as e:
        print(f"Error in user lookup: {e}, identity: {identity}, type: {type(identity)}")
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
        user = User.query.get(get_jwt_identity())
        if not user or user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function
