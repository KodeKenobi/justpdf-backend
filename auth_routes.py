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
            # Sync user to Supabase synchronously to ensure it completes
            try:
                import psycopg2
                from psycopg2.extras import RealDictCursor
                from datetime import datetime
                
                # Use hardcoded Supabase connection string
                database_url = "postgresql://postgres:Kopenikus0218!@db.pqdxqvxyrahvongbhtdb.supabase.co:5432/postgres"
                
                # Convert to pooler format
                if database_url and "db." in database_url and ".supabase.co" in database_url:
                    import re
                    match = re.match(r'postgresql?://([^:]+):([^@]+)@db\.([^.]+)\.supabase\.co:(\d+)/(.+)', database_url)
                    if match:
                        user_part, password, project_ref, port, database = match.groups()
                        database_url = f"postgresql://postgres.{project_ref}:{password}@aws-1-eu-west-1.pooler.supabase.com:6543/{database}"
                
                # Connect and sync
                conn = psycopg2.connect(database_url, sslmode='require')
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                
                # Check if user exists
                cursor.execute("SELECT id FROM users WHERE email = %s", (user.email,))
                existing = cursor.fetchone()
                
                if existing:
                    # Update
                    cursor.execute("""
                        UPDATE users SET
                            password_hash = %s, role = %s, is_active = %s,
                            subscription_tier = %s, monthly_call_limit = %s,
                            monthly_used = %s, monthly_reset_date = %s, last_login = %s
                        WHERE email = %s
                    """, (
                        user.password_hash, user.role, user.is_active,
                        user.subscription_tier or 'free', user.monthly_call_limit or 5,
                        user.monthly_used or 0,
                        user.monthly_reset_date if user.monthly_reset_date else datetime.utcnow(),
                        user.last_login if user.last_login else None, user.email
                    ))
                    print(f"✅ [REGISTRATION] Updated user in Supabase: {user.email}")
                else:
                    # Insert
                    cursor.execute("""
                        INSERT INTO users (email, password_hash, role, is_active, subscription_tier,
                                         monthly_call_limit, monthly_used, monthly_reset_date,
                                         created_at, last_login)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        user.email, user.password_hash, user.role, user.is_active,
                        user.subscription_tier or 'free', user.monthly_call_limit or 5,
                        user.monthly_used or 0,
                        user.monthly_reset_date if user.monthly_reset_date else datetime.utcnow(),
                        user.created_at if user.created_at else datetime.utcnow(),
                        user.last_login if user.last_login else None
                    ))
                    print(f"✅ [REGISTRATION] Added user to Supabase: {user.email}")
                
                conn.commit()
                cursor.close()
                conn.close()
                
            except Exception as e:
                print(f"⚠️ [REGISTRATION] Failed to sync to Supabase: {e}")
                import traceback
                traceback.print_exc()
                # Don't fail registration if sync fails
            
            # Send welcome email asynchronously (non-blocking) to speed up registration
            try:
                import threading
                from email_service import send_welcome_email
                from datetime import datetime
                
                # Get subscription tier from user
                tier = user.subscription_tier or 'free'
                registration_date = datetime.now()
                
                def send_email_async():
                    """Send welcome email in background thread"""
                    try:
                        print(f"📧 [REGISTRATION] Background: Sending welcome email to {user.email} (tier: {tier})")
                        success = send_welcome_email(user.email, tier, amount=0.0, payment_id="", payment_date=registration_date)
                        if success:
                            print(f"✅ [REGISTRATION] Background: Welcome email sent successfully to {user.email}")
                        else:
                            print(f"❌ [REGISTRATION] Background: Failed to send welcome email to {user.email}")
                            print(f"   Check email_service.py logs for details")
                    except Exception as e:
                        print(f"❌ [REGISTRATION] Background: Exception sending welcome email to {user.email}: {e}")
                        import traceback
                        traceback.print_exc()
                
                # Start email sending in background thread (non-blocking)
                email_thread = threading.Thread(target=send_email_async, daemon=True)
                email_thread.start()
                print(f"📧 [REGISTRATION] Welcome email queued for background sending to {user.email}")
            except Exception as e:
                print(f"⚠️ [REGISTRATION] Failed to queue welcome email: {e}")
                # Don't fail registration if email queueing fails
            
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

@auth_bp.route('/get-token-from-session', methods=['POST'])
def get_token_from_session():
    """Get backend JWT token from NextAuth session - auto-creates/updates user if needed"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        role = data.get('role', 'user')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        from models import User
        from database import db
        from flask_jwt_extended import create_access_token
        from datetime import timedelta
        
        # CRITICAL: Robust user lookup to prevent duplicate creation
        # First try exact match (case-sensitive)
        user = User.query.filter_by(email=email).first()
        
        # If not found, try case-insensitive lookup (defensive check)
        if not user:
            # Check all users with case-insensitive email match
            all_users = User.query.all()
            for u in all_users:
                if u.email.lower().strip() == email.lower().strip():
                    print(f"⚠️ [AUTH] Found user with different email casing: '{u.email}' (requested: '{email}')")
                    print(f"   Using existing user ID: {u.id}, tier: {u.subscription_tier}")
                    user = u
                    break
        
        # If still not found, user has been deleted - DO NOT auto-create
        # This prevents "resurrection" of deleted users
        if not user:
            existing_emails = [u.email for u in User.query.all()]
            print(f"❌ [AUTH] USER NOT FOUND: {email}")
            print(f"   Existing users in database: {existing_emails}")
            print(f"   User may have been deleted - returning 404 to prevent resurrection")
            return jsonify({
                'error': 'User not found',
                'code': 'USER_NOT_FOUND'
            }), 404
        else:
            # User exists - update password to match NextAuth
            # CRITICAL: Preserve subscription_tier - do NOT reset it
            old_tier = user.subscription_tier
            old_id = user.id
            user.set_password(password)
            user.is_active = True
            if role and user.role != role:
                user.role = role
            # Only update subscription_tier if explicitly provided AND different
            # This prevents accidental resets
            if 'subscription_tier' in data and data.get('subscription_tier') != old_tier:
                print(f"⚠️ [AUTH] Subscription tier change requested for {email}: {old_tier} -> {data.get('subscription_tier')}")
                print(f"   This should only happen through payment webhooks, not session sync")
                print(f"   PRESERVING existing tier: {old_tier}")
                # Don't update - preserve existing tier
            db.session.commit()
            print(f"✅ [AUTH] Updated existing user: {email} (ID: {old_id}, preserved tier: {old_tier})")
        
        # Generate JWT token
        expires = timedelta(hours=24)
        access_token = create_access_token(
            identity=str(user.id),
            expires_delta=expires
        )
        
        return jsonify({
            'access_token': access_token,
            'user': user.to_dict(),
            'expires_in': int(expires.total_seconds())
        }), 200
            
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500