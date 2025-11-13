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

@test_bp.route('/ping', methods=['GET'])
def ping():
    """Simple ping endpoint to test route accessibility"""
    return jsonify({'status': 'ok', 'message': 'Test route is accessible'}), 200

@test_bp.route('/send-welcome-email', methods=['POST'])
def send_test_welcome_email():
    """Test endpoint to send welcome email"""
    try:
        print(f"📧 Received request to send welcome email")
        print(f"📧 Request data: {request.get_json()}")
        
        from email_service import send_welcome_email
        
        data = request.get_json() or {}
        recipient = data.get('email', 'kodekenobi@gmail.com')
        tier = data.get('tier', 'free')
        
        print(f"📧 Sending test welcome email to {recipient} (tier: {tier})")
        
        success = send_welcome_email(recipient, tier)
        
        print(f"📧 Email send result: {success}")
        
        if success:
            return jsonify({
                'success': True,
                'message': f'Welcome email sent successfully to {recipient}',
                'recipient': recipient,
                'tier': tier
            }), 200
        else:
            return jsonify({
                'success': False,
                'message': f'Failed to send welcome email to {recipient}',
                'recipient': recipient,
                'tier': tier
            }), 500
            
    except ImportError as e:
        print(f"❌ Import error in send_test_welcome_email: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Import error: {str(e)}'}), 500
    except Exception as e:
        print(f"❌ Error in send_test_welcome_email: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'type': type(e).__name__}), 500