from flask import Blueprint, request, jsonify
from auth import login_user

# Create Blueprint
debug_bp = Blueprint('debug', __name__, url_prefix='/debug')

@debug_bp.route('/login-test', methods=['POST'])
def login_test():
    """Debug login endpoint"""
    try:
        data = request.get_json()
        
        print(f"🔍 Debug login - Raw request data: {data}")
        print(f"🔍 Debug login - Data type: {type(data)}")
        
        if not data:
            return jsonify({'error': 'No data provided', 'debug': 'data is None'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        print(f"🔍 Debug login - Email: '{email}' (type: {type(email)})")
        print(f"🔍 Debug login - Password: '{password}' (type: {type(password)})")
        print(f"🔍 Debug login - Email length: {len(email)}")
        print(f"🔍 Debug login - Password length: {len(password)}")
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required', 'debug': f'email: {bool(email)}, password: {bool(password)}'}), 400
        
        print(f"🔍 Debug login - Calling login_user...")
        result, message = login_user(email, password)
        
        print(f"🔍 Debug login - Result: {result is not None}")
        print(f"🔍 Debug login - Message: {message}")
        
        if result:
            return jsonify({
                'message': message,
                'debug': 'login successful',
                **result
            }), 200
        else:
            return jsonify({'error': message, 'debug': 'login failed'}), 401
            
    except Exception as e:
        print(f"🔍 Debug login - Exception: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'debug': 'exception occurred'}), 500
