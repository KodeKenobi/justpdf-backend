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
        from datetime import datetime
        
        data = request.get_json() or {}
        recipient = data.get('email', 'kodekenobi@gmail.com')
        tier = data.get('tier', 'free')
        amount = data.get('amount', 0.0)
        
        # Use current date as payment date for invoice generation
        payment_date = datetime.now()
        
        print(f"📧 Sending test welcome email to {recipient} (tier: {tier}, amount: {amount})")
        print(f"📧 Payment date for invoice: {payment_date}")
        
        success = send_welcome_email(recipient, tier, amount=amount, payment_id="", payment_date=payment_date)
        
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
    """Delete a user by email (admin/test endpoint) - COMPLETE DELETION WITH NO CACHE"""
    try:
        from database import db
        from models import User, APIKey, UsageLog, ResetHistory, Notification
        from sqlalchemy import text
        
        data = request.get_json() or {}
        email = data.get('email', '').strip().lower()
        
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'}), 400
        
        print(f"🗑️ Attempting COMPLETE deletion of user: {email}")
        print(f"   This will delete user from database and ensure no cache remains")
        
        # Try multiple lookup methods to find user
        user = User.query.filter_by(email=email).first()
        if not user:
            # Try case-insensitive lookup
            all_users = User.query.all()
            for u in all_users:
                if u.email.lower().strip() == email.lower().strip():
                    user = u
                    break
        
        if not user:
            print(f"❌ User not found: {email}")
            return jsonify({'success': False, 'error': f'User not found: {email}'}), 404
        
        user_id = user.id
        user_email = user.email
        print(f"📊 Found user: {user_email} (ID: {user_id})")
        
        # Delete ALL related data first (cascade delete)
        print(f"   Step 1: Deleting all related data...")
        
        # Delete API keys
        api_keys_deleted = APIKey.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        print(f"      ✅ Deleted {api_keys_deleted} API keys")
        
        # Delete usage logs
        usage_logs_deleted = UsageLog.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        print(f"      ✅ Deleted {usage_logs_deleted} usage logs")
        
        # Delete reset history
        reset_history_deleted = ResetHistory.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        print(f"      ✅ Deleted {reset_history_deleted} reset history records")
        
        # Update notifications to remove user references
        notifications_updated = Notification.query.filter_by(read_by=user_id).update({'read_by': None}, synchronize_session=False)
        print(f"      ✅ Updated {notifications_updated} notification references")
        
        # Force flush to ensure all deletes are processed
        db.session.flush()
        print(f"   Step 2: Flushed session to ensure all deletes are processed")
        
        # Delete user
        print(f"   Step 3: Deleting user from database...")
        db.session.delete(user)
        db.session.commit()
        print(f"      ✅ User deleted and committed to database")
        
        # Force another flush and commit to ensure no cache
        db.session.flush()
        db.session.commit()
        print(f"   Step 4: Forced additional flush/commit to clear any cache")
        
        # Multiple verification checks to ensure complete deletion
        print(f"   Step 5: Verifying complete deletion (multiple checks)...")
        
        # Check 1: Query by email
        verify_user_email = User.query.filter_by(email=email).first()
        if verify_user_email:
            print(f"      ❌ ERROR: User still exists when querying by email!")
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': 'User deletion failed - user still exists (email query)',
                'message': f'Failed to delete user {user_email}'
            }), 500
        
        # Check 2: Query by ID
        verify_user_id = User.query.get(user_id)
        if verify_user_id:
            print(f"      ❌ ERROR: User still exists when querying by ID!")
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': 'User deletion failed - user still exists (ID query)',
                'message': f'Failed to delete user {user_email}'
            }), 500
        
        # Check 3: Raw SQL query to bypass any ORM cache
        try:
            result = db.session.execute(text("SELECT id, email FROM users WHERE id = :user_id OR LOWER(email) = :email"), 
                                      {"user_id": user_id, "email": email.lower()})
            raw_user = result.fetchone()
            if raw_user:
                print(f"      ❌ ERROR: User still exists in raw SQL query!")
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'error': 'User deletion failed - user still exists (raw SQL)',
                    'message': f'Failed to delete user {user_email}'
                }), 500
        except Exception as sql_error:
            print(f"      ⚠️  Could not perform raw SQL check (non-critical): {sql_error}")
        
        # Check 4: Verify no API keys remain
        remaining_keys = APIKey.query.filter_by(user_id=user_id).count()
        if remaining_keys > 0:
            print(f"      ⚠️  WARNING: {remaining_keys} API keys still exist for deleted user")
            # Force delete them
            APIKey.query.filter_by(user_id=user_id).delete(synchronize_session=False)
            db.session.commit()
            print(f"      ✅ Force deleted remaining API keys")
        
        # Check 5: Verify no usage logs remain
        remaining_logs = UsageLog.query.filter_by(user_id=user_id).count()
        if remaining_logs > 0:
            print(f"      ⚠️  WARNING: {remaining_logs} usage logs still exist for deleted user")
            # Force delete them
            UsageLog.query.filter_by(user_id=user_id).delete(synchronize_session=False)
            db.session.commit()
            print(f"      ✅ Force deleted remaining usage logs")
        
        # Final verification - refresh the session to clear any cache
        db.session.expire_all()
        print(f"   Step 6: Expired all sessions to clear ORM cache")
        
        # Final check
        final_check = User.query.filter_by(email=email).first()
        if final_check:
            print(f"      ❌ ERROR: User still exists after cache expiration!")
            db.session.rollback()
            return jsonify({
                'success': False,
                'error': 'User deletion failed - user still exists after cache clear',
                'message': f'Failed to delete user {user_email}'
            }), 500
        
        print(f"✅ User {user_email} (ID: {user_id}) COMPLETELY DELETED from database")
        print(f"   ✅ All related data deleted")
        print(f"   ✅ All caches cleared")
        print(f"   ✅ User will be immediately invalid - dashboard will reject access")
        
        return jsonify({
            'success': True,
            'message': f'User {user_email} completely deleted from system and database',
            'deleted_id': user_id,
            'deleted_email': user_email,
            'cache_cleared': True,
            'verification_passed': True,
            'note': 'User is now completely removed. Any existing sessions/tokens will be invalid. Dashboard will immediately reject access.'
        }), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        error_msg = str(e)
        print(f"❌ Error deleting user: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': error_msg, 'type': type(e).__name__, 'message': f'Error: {error_msg}'}), 500

def check_user_in_supabase(email):
    """Check if a user exists in Supabase"""
    try:
        import os
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        # Use hardcoded Supabase connection string (pooler format)
        # This ensures we always check Supabase regardless of DATABASE_URL setting
        database_url = "postgresql://postgres:Kopenikus0218!@db.pqdxqvxyrahvongbhtdb.supabase.co:5432/postgres"
        
        # Convert to pooler format (works better from local machines and Railway)
        if database_url and "db." in database_url and ".supabase.co" in database_url:
            import re
            match = re.match(r'postgresql?://([^:]+):([^@]+)@db\.([^.]+)\.supabase\.co:(\d+)/(.+)', database_url)
            if match:
                user_part, password, project_ref, port, database = match.groups()
                # Use pooler format without query parameters (psycopg2 doesn't support pgbouncer param)
                database_url = f"postgresql://postgres.{project_ref}:{password}@aws-1-eu-west-1.pooler.supabase.com:6543/{database}"
        
        # Connect to Supabase
        conn = psycopg2.connect(database_url, sslmode='require')
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Check if user exists
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        existing = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return existing is not None
    except Exception as e:
        print(f"Error checking Supabase for {email}: {e}")
        return False

@test_bp.route('/view-database', methods=['GET'])
def view_database():
    """View database contents (read-only)"""
    try:
        from database import db
        from models import User, APIKey, UsageLog, Notification
        from sqlalchemy import inspect
        
        # Check if we can access the engine (this will fail if db not initialized)
        try:
            inspector = inspect(db.engine)
            tables = inspector.get_table_names()
        except Exception as db_error:
            error_msg = str(db_error)
            if 'not registered' in error_msg.lower():
                return jsonify({
                    'success': False,
                    'error': 'Database is not initialized. Please wait a moment and try again.',
                    'message': 'Database is still initializing. Please try again in a few seconds.'
                }), 503
            elif 'already been registered' in error_msg.lower():
                # Database is already initialized, try to proceed
                try:
                    inspector = inspect(db.engine)
                    tables = inspector.get_table_names()
                except Exception as e2:
                    return jsonify({
                        'success': False,
                        'error': f'Database access error: {str(e2)}',
                        'message': f'Database access error: {str(e2)}'
                    }), 500
            else:
                return jsonify({
                    'success': False,
                    'error': f'Database error: {error_msg}',
                    'message': f'Database error: {error_msg}'
                }), 503
        
        result = {
            'database_url': str(db.engine.url).split('@')[-1] if '@' in str(db.engine.url) else 'sqlite',
            'tables': tables,
            'users': [],
            'api_keys': [],
            'usage_logs': [],
            'notifications': []
        }
        
        # Get users with Supabase sync status
        users = User.query.all()
        for user in users:
            synced_to_supabase = check_user_in_supabase(user.email)
            result['users'].append({
                'id': user.id,
                'email': user.email,
                'role': user.role,
                'is_active': user.is_active,
                'subscription_tier': user.subscription_tier,
                'created_at': user.created_at.isoformat() if user.created_at else None,
                'synced_to_supabase': synced_to_supabase
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
                'method': log.method if hasattr(log, 'method') else None,
                'status_code': log.status_code if hasattr(log, 'status_code') else None,
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
        error_type = type(e).__name__
        print(f"❌ Error viewing database: {e}")
        import traceback
        traceback.print_exc()
        
        # Provide more helpful error messages
        if 'not registered' in error_msg.lower() or 'init_app' in error_msg.lower():
            error_msg = "Database is not initialized. Please wait a moment and try again."
        elif 'already been registered' in error_msg.lower():
            error_msg = "Database is already initialized. This should not happen - please contact support."
        elif 'no such table' in error_msg.lower():
            error_msg = "Database tables do not exist. Database may need to be initialized."
        
        return jsonify({
            'success': False, 
            'error': error_msg, 
            'type': error_type, 
            'message': f'Error: {error_msg}'
        }), 500

@test_bp.route('/sync-all-to-supabase', methods=['POST'])
def sync_all_to_supabase():
    """Sync all users to Supabase"""
    try:
        from database import db
        from models import User
        from supabase_sync import sync_user_to_supabase
        
        # Get all users
        users = User.query.all()
        
        if not users:
            return jsonify({
                'success': True,
                'message': 'No users to sync',
                'synced': 0,
                'total': 0
            }), 200
        
        # Sync each user (non-blocking, in background threads)
        synced_count = 0
        for user in users:
            try:
                sync_user_to_supabase(user)
                synced_count += 1
            except Exception as e:
                print(f"Error syncing user {user.email}: {e}")
        
        return jsonify({
            'success': True,
            'message': f'Queued {synced_count} users for sync to Supabase',
            'synced': synced_count,
            'total': len(users)
        }), 200
        
    except Exception as e:
        error_msg = str(e)
        print(f"Error syncing all users to Supabase: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': error_msg, 'type': type(e).__name__, 'message': f'Error: {error_msg}'}), 500

@test_bp.route('/migrate-all-users', methods=['POST'])
def migrate_all_users():
    """Run migration script to migrate all users from SQLite to Supabase"""
    try:
        from migrate_users_to_supabase import migrate_users
        
        # Run migration (this will execute on Railway and access the SQLite database)
        migrate_users()
        
        return jsonify({
            'success': True,
            'message': 'Migration completed. Check server logs for details.'
        }), 200
        
    except Exception as e:
        error_msg = str(e)
        print(f"Error running migration: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': error_msg, 'type': type(e).__name__, 'message': f'Error: {error_msg}'}), 500