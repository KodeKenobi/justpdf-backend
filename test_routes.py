from flask import Blueprint, request, jsonify

# Create Blueprint
test_bp = Blueprint('test', __name__, url_prefix='/test')

@test_bp.route('/debug', methods=['POST'])
def debug():
    """Debug endpoint to test request data"""
    try:
        data = request.get_json()
        
        return jsonify({
            'received_data': data,
            'email': data.get('email') if data else None,
            'password': data.get('password') if data else None,
            'email_type': type(data.get('email')) if data else None,
            'password_type': type(data.get('password')) if data else None,
            'email_length': len(data.get('email', '')) if data else 0,
            'password_length': len(data.get('password', '')) if data else 0
        }), 200
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500
