from flask import Blueprint, request, jsonify, current_app, g
from auth import register_user, login_user, reset_password, change_password, require_auth

# Create Blueprint
auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new user"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        user, message = register_user(email, password)
        
        if user:
            return jsonify({
                'message': message,
                'user': user.to_dict()
            }), 201
        else:
            return jsonify({'error': message}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/login', methods=['POST'])
def login():
    """Login user"""
    try:
        data = request.get_json()
        
        print(f"🔍 LOGIN DEBUG - Raw data: {data}")
        
        if not data:
            print("🔍 LOGIN DEBUG - No data provided")
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        print(f"🔍 LOGIN DEBUG - Email: '{email}' (len: {len(email)})")
        print(f"🔍 LOGIN DEBUG - Password: '{password}' (len: {len(password)})")
        
        if not email or not password:
            print("🔍 LOGIN DEBUG - Missing email or password")
            return jsonify({'error': 'Email and password are required'}), 400
        
        print(f"🔍 LOGIN DEBUG - Calling login_user...")
        result, message = login_user(email, password)
        
        print(f"🔍 LOGIN DEBUG - Result: {result is not None}")
        print(f"🔍 LOGIN DEBUG - Message: {message}")
        
        if result:
            print("🔍 LOGIN DEBUG - Login successful, returning token")
            return jsonify({
                'message': message,
                **result
            }), 200
        else:
            print("🔍 LOGIN DEBUG - Login failed, returning error")
            return jsonify({'error': message}), 401
            
    except Exception as e:
        print(f"🔍 LOGIN DEBUG - Exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/reset-password', methods=['POST'])
def reset_password_endpoint():
    """Request password reset"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email', '').strip().lower()
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        success, message = reset_password(email)
        
        if success:
            return jsonify({'message': message}), 200
        else:
            return jsonify({'error': message}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/change-password', methods=['POST'])
@require_auth
def change_password_endpoint():
    """Change user password"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        old_password = data.get('old_password', '')
        new_password = data.get('new_password', '')
        
        if not old_password or not new_password:
            return jsonify({'error': 'Old and new passwords are required'}), 400
        
        from flask_jwt_extended import get_jwt_identity
        user_id = get_jwt_identity()
        success, message = change_password(user_id, old_password, new_password)
        
        if success:
            return jsonify({'message': message}), 200
        else:
            return jsonify({'error': message}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/profile', methods=['GET'])
def get_profile():
    """Get user profile"""
    import jwt
    from flask import request
    
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'No token provided'}), 401
        
        token = auth_header.split(' ')[1]
        
        # Decode JWT token manually
        try:
            payload = jwt.decode(token, current_app.config['JWT_SECRET_KEY'], algorithms=['HS256'])
            user_id = payload.get('sub')
            print(f"Profile request - User ID: {user_id}, Type: {type(user_id)}")
            
            # Convert to int if it's a string
            if isinstance(user_id, str):
                user_id = int(user_id)
            
            # Get user from database
            from models import User
            user = User.query.get(user_id)
            if not user:
                return jsonify({'error': 'User not found'}), 404
            
            return jsonify(user.to_dict())
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
            
    except Exception as e:
        print(f"Profile error: {e}")
        return jsonify({'error': 'Failed to get profile'}), 500

@auth_bp.route('/profile', methods=['PUT'])
@require_auth
def update_profile():
    """Update user profile"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        from flask_jwt_extended import get_jwt_identity
        from database import db
        from models import User
        
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Only allow updating certain fields
        if 'email' in data:
            new_email = data['email'].strip().lower()
            if not new_email:
                return jsonify({'error': 'Email cannot be empty'}), 400
            
            # Check if email is already taken
            existing_user = User.query.filter_by(email=new_email).first()
            if existing_user and existing_user.id != user.id:
                return jsonify({'error': 'Email already taken'}), 400
            
            user.email = new_email
        
        db.session.commit()
        
        return jsonify({
            'message': 'Profile updated successfully',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/admin/update-password', methods=['POST'])
def admin_update_password():
    """Admin endpoint to update any user's password (for setup purposes)"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email', '').strip().lower()
        new_password = data.get('password', '')
        new_role = data.get('role', '')
        
        if not email or not new_password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        from models import User
        from database import db
        
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Update password
        user.set_password(new_password)
        
        # Update role if provided
        if new_role:
            user.role = new_role
        
        db.session.commit()
        
        return jsonify({
            'message': f'User updated successfully for {email}',
            'user': user.to_dict()
        }), 200
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500