from flask import Blueprint, request, jsonify, render_template

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

@test_bp.route('/database-admin', methods=['GET'])
def database_admin():
    """HTML interface for database administration"""
    return render_template('database_admin.html')

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
        error_msg = f'Import error: {str(e)}'
        print(f"❌ Import error in send_test_welcome_email: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': error_msg, 'message': error_msg}), 500
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error in send_test_welcome_email: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': error_msg, 'type': type(e).__name__, 'message': f'Error: {error_msg}'}), 500

@test_bp.route('/delete-user', methods=['POST'])
def delete_user():
    """Delete a user by email (admin/test endpoint)"""
    try:
        from database import db
        from models import User, APIKey, UsageLog, ResetHistory, Notification
        
        data = request.get_json() or {}
        email = data.get('email', '').strip().lower()
        
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        print(f"🗑️ Attempting to delete user: {email}")
        
        user = User.query.filter_by(email=email).first()
        
        if not user:
            print(f"❌ User not found: {email}")
            return jsonify({'success': False, 'error': f'User not found: {email}'}), 404
        
        user_id = user.id
        user_email = user.email
        print(f"📊 Found user: {user_email} (ID: {user_id})")
        
        # Delete related data first
        api_keys_deleted = APIKey.query.filter_by(user_id=user_id).delete()
        print(f"   Deleted {api_keys_deleted} API keys")
        
        usage_logs_deleted = UsageLog.query.filter_by(user_id=user_id).delete()
        print(f"   Deleted {usage_logs_deleted} usage logs")
        
        reset_history_deleted = ResetHistory.query.filter_by(user_id=user_id).delete()
        print(f"   Deleted {reset_history_deleted} reset history records")
        
        notifications_updated = Notification.query.filter_by(read_by=user_id).update({'read_by': None})
        print(f"   Updated {notifications_updated} notification references")
        
        # Delete user
        db.session.delete(user)
        db.session.flush()  # Ensure deletion is processed
        db.session.commit()
        
        # Verify deletion
        db.session.expire_all()  # Clear session cache
        verify_user = User.query.filter_by(email=email).first()
        if verify_user:
            print(f"❌ ERROR: User still exists after deletion!")
            return jsonify({
                'success': False,
                'error': 'User deletion failed - user still exists',
                'message': f'Failed to delete user {user_email}'
            }), 500
        
        print(f"✅ User {user_email} deleted successfully and verified")
        return jsonify({
            'success': True,
            'message': f'User {user_email} deleted successfully',
            'deleted_id': user_id
        }), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        error_msg = str(e)
        print(f"❌ Error deleting user: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': error_msg, 'type': type(e).__name__, 'message': f'Error: {error_msg}'}), 500

@test_bp.route('/delete-all-users', methods=['POST'])
def delete_all_users():
    """Delete all users from the database (admin/test endpoint)"""
    try:
        from database import db
        from models import User, APIKey, UsageLog, ResetHistory, Notification
        
        # Get count before deletion
        user_count = User.query.count()
        print(f"🗑️ Attempting to delete all {user_count} users")
        
        if user_count == 0:
            return jsonify({
                'success': True,
                'message': 'No users to delete',
                'deleted_count': 0
            }), 200
        
        # Delete related data first
        notification_count = Notification.query.count()
        Notification.query.delete()
        print(f"   Deleted {notification_count} notifications")
        
        usage_log_count = UsageLog.query.count()
        UsageLog.query.delete()
        print(f"   Deleted {usage_log_count} usage logs")
        
        reset_history_count = ResetHistory.query.count()
        ResetHistory.query.delete()
        print(f"   Deleted {reset_history_count} reset history records")
        
        api_key_count = APIKey.query.count()
        APIKey.query.delete()
        print(f"   Deleted {api_key_count} API keys")
        
        # Delete all users
        deleted_count = User.query.delete()
        db.session.flush()
        db.session.commit()
        
        # Verify deletion
        db.session.expire_all()
        remaining_count = User.query.count()
        
        print(f"✅ Deleted {deleted_count} users. Remaining: {remaining_count}")
        
        return jsonify({
            'success': True,
            'message': f'Successfully deleted {deleted_count} users and all related data',
            'deleted_count': deleted_count,
            'remaining_count': remaining_count
        }), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        error_msg = str(e)
        print(f"❌ Error deleting all users: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': error_msg, 'type': type(e).__name__, 'message': f'Error: {error_msg}'}), 500

@test_bp.route('/create-user', methods=['POST'])
def create_user():
    """Create a new user with email, password, role, and tier"""
    try:
        from database import db
        from models import User
        from auth import register_user, validate_password
        from email_service import send_welcome_email
        import os
        
        data = request.get_json() or {}
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        confirm_password = data.get('confirm_password', '')
        role = data.get('role', 'user').lower()
        subscription_tier = data.get('subscription_tier', 'free').lower()
        
        # Validate inputs
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required'}), 400
        
        if password != confirm_password:
            return jsonify({'success': False, 'error': 'Passwords do not match'}), 400
        
        # Validate password strength
        is_valid, message = validate_password(password)
        if not is_valid:
            return jsonify({'success': False, 'error': message}), 400
        
        # Validate role
        valid_roles = ['user', 'admin', 'super_admin']
        if role not in valid_roles:
            return jsonify({'success': False, 'error': f'Invalid role. Must be one of: {", ".join(valid_roles)}'}), 400
        
        # Validate subscription tier
        valid_tiers = ['free', 'premium', 'enterprise', 'client']
        if subscription_tier not in valid_tiers:
            return jsonify({'success': False, 'error': f'Invalid tier. Must be one of: {", ".join(valid_tiers)}'}), 400
        
        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return jsonify({'success': False, 'error': 'User with this email already exists'}), 400
        
        # Create user
        user, message = register_user(email, password, role=role)
        
        if not user:
            return jsonify({'success': False, 'error': message}), 400
        
        # Set subscription tier and limits
        tier_limits = {
            'free': 5,
            'premium': 5000,
            'enterprise': -1,  # unlimited
            'client': 10000
        }
        user.subscription_tier = subscription_tier
        user.monthly_call_limit = tier_limits.get(subscription_tier, 5)
        db.session.commit()
        
        print(f"✅ [ADMIN] Created user: {email} (role: {role}, tier: {subscription_tier})")
        
        # Send welcome email based on tier
        try:
            resend_key = os.getenv('RESEND_API_KEY')
            if resend_key:
                # Determine email tier (use subscription_tier, but map roles if needed)
                email_tier = subscription_tier
                if role in ['admin', 'super_admin']:
                    # For admin roles, use enterprise tier for email content
                    email_tier = 'enterprise'
                
                success = send_welcome_email(user.email, email_tier)
                if success:
                    print(f"✅ [ADMIN] Welcome email sent to {user.email} (tier: {email_tier})")
                else:
                    print(f"❌ [ADMIN] Failed to send welcome email to {user.email}")
            else:
                print(f"⚠️ [ADMIN] RESEND_API_KEY not set - email not sent")
        except Exception as e:
            print(f"❌ [ADMIN] Exception sending welcome email: {e}")
            import traceback
            traceback.print_exc()
            # Don't fail user creation if email fails
        
        return jsonify({
            'success': True,
            'message': f'User created successfully',
            'user': user.to_dict()
        }), 201
        
    except Exception as e:
        from database import db
        db.session.rollback()
        error_msg = str(e)
        print(f"❌ Error creating user: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': error_msg, 'type': type(e).__name__, 'message': f'Error: {error_msg}'}), 500

@test_bp.route('/view-database', methods=['GET'])
def view_database():
    """View database contents (read-only)"""
    try:
        from database import db
        from models import User, APIKey, UsageLog, Notification
        from sqlalchemy import inspect
        
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        result = {
            'database_url': str(db.engine.url).split('@')[-1] if '@' in str(db.engine.url) else 'sqlite',
            'tables': tables,
            'users': [],
            'api_keys': [],
            'usage_logs': [],
            'notifications': []
        }
        
        # Get users
        users = User.query.all()
        for user in users:
            result['users'].append({
                'id': user.id,
                'email': user.email,
                'role': user.role,
                'is_active': user.is_active,
                'subscription_tier': user.subscription_tier,
                'created_at': user.created_at.isoformat() if user.created_at else None
            })
        
        # Get API keys (limited)
        api_keys = APIKey.query.limit(50).all()
        for key in api_keys:
            result['api_keys'].append({
                'id': key.id,
                'user_id': key.user_id,
                'key_prefix': key.key[:20] + '...' if key.key else None,
                'created_at': key.created_at.isoformat() if key.created_at else None
            })
        
        # Get usage logs (limited)
        usage_logs = UsageLog.query.limit(50).all()
        for log in usage_logs:
            result['usage_logs'].append({
                'id': log.id,
                'user_id': log.user_id,
                'endpoint': log.endpoint,
                'created_at': log.created_at.isoformat() if log.created_at else None
            })
        
        # Get notifications (limited)
        notifications = Notification.query.limit(50).all()
        for notif in notifications:
            result['notifications'].append({
                'id': notif.id,
                'title': notif.title,
                'type': notif.type,
                'is_read': notif.is_read,
                'created_at': notif.created_at.isoformat() if notif.created_at else None
            })
        
        result['counts'] = {
            'users': len(result['users']),
            'api_keys': APIKey.query.count(),
            'usage_logs': UsageLog.query.count(),
            'notifications': Notification.query.count()
        }
        
        return jsonify(result), 200
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Error viewing database: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': error_msg, 'type': type(e).__name__, 'message': f'Error: {error_msg}'}), 500