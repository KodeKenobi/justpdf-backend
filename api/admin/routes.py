from flask import Blueprint, request, jsonify, g
from sqlalchemy import func, desc, or_
from datetime import datetime, timedelta
from api_auth import require_api_key, get_user_stats

# Create Blueprint
admin_api = Blueprint('admin_api', __name__, url_prefix='/api/admin')

def require_admin(f):
    """Decorator to require admin role"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'current_user') or (g.current_user.role != 'admin' and g.current_user.role != 'super_admin'):
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

@admin_api.before_request
def load_user():
    """Set g.current_user from JWT token or API key"""
    # Skip authentication for OPTIONS requests (CORS preflight)
    if request.method == 'OPTIONS':
        return jsonify({}), 200
    
    # Try JWT authentication first (for frontend)
    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        from models import User
        
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
        if user_id:
            if isinstance(user_id, str):
                user_id = int(user_id)
            g.current_user = User.query.get(user_id)
            if g.current_user:
                return  # JWT auth successful
    except Exception:
        pass  # JWT auth failed, try API key
    
    # Fallback to API key authentication
    try:
        from api_auth import verify_api_key
        api_key = request.headers.get('X-API-Key') or request.headers.get('Authorization', '').replace('Bearer ', '')
        if api_key:
            user = verify_api_key(api_key)
            if user:
                g.current_user = user
                from models import APIKey
                g.current_api_key = APIKey.query.filter_by(key=api_key).first()
                return  # API key auth successful
    except Exception:
        pass
    
    # If neither worked, return error
    if not hasattr(g, 'current_user') or not g.current_user:
        return jsonify({'error': 'Authentication required'}), 401

@admin_api.route('/users', methods=['GET'])
@require_admin
def list_users():
    """List all users with pagination and filtering"""
    try:
        from models import User
        
        page = request.args.get('page', 1, type=int)
        requested_per_page = request.args.get('per_page', 20, type=int)
        
        # Super admins can get up to 10000 users per page, regular admins limited to 100
        if hasattr(g, 'current_user') and g.current_user and g.current_user.role == 'super_admin':
            per_page = min(requested_per_page, 10000)
        else:
            per_page = min(requested_per_page, 100)
        
        search = request.args.get('search', '')
        roles = request.args.getlist('role')  # Get multiple role values
        is_active = request.args.get('is_active', '')
        subscription_tiers = request.args.getlist('subscription_tier')  # Get multiple tier values
        
        # Build query
        query = User.query
        
        if search:
            query = query.filter(User.email.contains(search))
        if roles:
            # Use OR logic for multiple roles
            query = query.filter(or_(*[User.role == role for role in roles]))
        if is_active:
            query = query.filter(User.is_active == (is_active.lower() == 'true'))
        if subscription_tiers:
            # Use OR logic for multiple tiers
            query = query.filter(or_(*[User.subscription_tier == tier for tier in subscription_tiers]))
        
        # Order by creation date
        query = query.order_by(desc(User.created_at))
        
        # For super admin with no filters, return all users without pagination
        if (hasattr(g, 'current_user') and g.current_user and g.current_user.role == 'super_admin' 
            and not search and not roles and not is_active and not subscription_tiers):
            # Return all users without pagination
            all_users = query.all()
            print(f"🔍 Super Admin list_users - Total users in DB: {User.query.count()}")
            print(f"🔍 Super Admin list_users - Returning ALL {len(all_users)} users (no pagination)")
            return jsonify({
                'users': [user.to_dict() for user in all_users],
                'pagination': {
                    'page': 1,
                    'per_page': len(all_users),
                    'total': len(all_users),
                    'pages': 1,
                    'has_next': False,
                    'has_prev': False
                }
            }), 200
        
        # Paginate for filtered queries or regular admins
        users = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        # Debug logging
        print(f"🔍 Admin list_users - Total users in DB: {User.query.count()}")
        print(f"🔍 Admin list_users - Query result count: {users.total}")
        print(f"🔍 Admin list_users - Current user: {g.current_user.email if hasattr(g, 'current_user') and g.current_user else 'None'}")
        print(f"🔍 Admin list_users - Current user role: {g.current_user.role if hasattr(g, 'current_user') and g.current_user else 'None'}")
        print(f"🔍 Admin list_users - Per page: {per_page}, Requested: {requested_per_page}")
        print(f"🔍 Admin list_users - Returning {len(users.items)} users")
        
        return jsonify({
            'users': [user.to_dict() for user in users.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': users.total,
                'pages': users.pages,
                'has_next': users.has_next,
                'has_prev': users.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_api.route('/users/<int:user_id>', methods=['GET'])
@require_admin
def get_user(user_id):
    """Get detailed user information"""
    try:
        from models import User, APIKey, Job
        
        user = User.query.get_or_404(user_id)
        
        # Get user stats
        stats = get_user_stats(user_id)
        
        # Get API keys
        api_keys = APIKey.query.filter_by(user_id=user_id).all()
        
        # Get recent jobs
        recent_jobs = Job.query.filter_by(user_id=user_id)\
            .order_by(desc(Job.created_at))\
            .limit(10).all()
        
        user_data = user.to_dict()
        user_data.update({
            'stats': stats,
            'api_keys': [key.to_dict() for key in api_keys],
            'recent_jobs': [job.to_dict() for job in recent_jobs]
        })
        
        return jsonify(user_data), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_api.route('/users/<int:user_id>/api-keys', methods=['POST'])
@require_admin
def create_api_key(user_id):
    """Create API key for a user"""
    try:
        from database import db
        from models import User, APIKey
        
        user = User.query.get_or_404(user_id)
        
        data = request.get_json()
        name = data.get('name', f'API Key {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}')
        rate_limit = data.get('rate_limit', 1000)
        
        # Generate API key
        api_key = APIKey(
            key=APIKey.generate_key(),
            name=name,
            user_id=user_id,
            rate_limit=rate_limit
        )
        
        db.session.add(api_key)
        db.session.commit()
        
        return jsonify(api_key.to_dict(include_key=True)), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/api-keys/<int:key_id>', methods=['DELETE'])
@require_admin
def revoke_api_key(key_id):
    """Revoke an API key"""
    try:
        from database import db
        from models import APIKey
        
        api_key = APIKey.query.get_or_404(key_id)
        api_key.is_active = False
        db.session.commit()
        
        return jsonify({'message': 'API key revoked successfully'}), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/api-keys/<int:key_id>', methods=['PUT'])
@require_admin
def update_api_key(key_id):
    """Update API key settings"""
    try:
        from database import db
        from models import APIKey
        
        api_key = APIKey.query.get_or_404(key_id)
        
        data = request.get_json()
        if 'name' in data:
            api_key.name = data['name']
        if 'rate_limit' in data:
            api_key.rate_limit = data['rate_limit']
        if 'is_active' in data:
            api_key.is_active = data['is_active']
        
        db.session.commit()
        
        return jsonify(api_key.to_dict()), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/usage/stats', methods=['GET'])
@require_admin
def get_usage_stats():
    """Get system-wide usage statistics"""
    try:
        from database import db
        from models import User, UsageLog
        
        # Time range
        days = request.args.get('days', 30, type=int)
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Total users
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        
        # Total API calls
        total_calls = UsageLog.query.filter(UsageLog.timestamp >= start_date).count()
        
        # Calls by status
        success_calls = UsageLog.query.filter(
            UsageLog.timestamp >= start_date,
            UsageLog.status_code.between(200, 299)
        ).count()
        
        error_calls = UsageLog.query.filter(
            UsageLog.timestamp >= start_date,
            UsageLog.status_code >= 400
        ).count()
        
        # Popular endpoints
        popular_endpoints = db.session.query(
            UsageLog.endpoint,
            func.count(UsageLog.id).label('count')
        ).filter(
            UsageLog.timestamp >= start_date
        ).group_by(
            UsageLog.endpoint
        ).order_by(
            func.count(UsageLog.id).desc()
        ).limit(10).all()
        
        # Daily usage (last 30 days)
        daily_usage = db.session.query(
            func.date(UsageLog.timestamp).label('date'),
            func.count(UsageLog.id).label('count')
        ).filter(
            UsageLog.timestamp >= start_date
        ).group_by(
            func.date(UsageLog.timestamp)
        ).order_by(
            func.date(UsageLog.timestamp)
        ).all()
        
        # Top users by usage
        top_users = db.session.query(
            User.email,
            func.count(UsageLog.id).label('count')
        ).join(
            UsageLog, User.id == UsageLog.user_id
        ).filter(
            UsageLog.timestamp >= start_date
        ).group_by(
            User.id, User.email
        ).order_by(
            func.count(UsageLog.id).desc()
        ).limit(10).all()
        
        # Users by tier with monthly usage
        users_usage = []
        all_users = User.query.all()
        for user in all_users:
            # Get monthly usage from UsageLog
            month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            monthly_calls = UsageLog.query.filter(
                UsageLog.user_id == user.id,
                UsageLog.timestamp >= month_start
            ).count()
            
            users_usage.append({
                'id': user.id,
                'email': user.email,
                'subscription_tier': user.subscription_tier or 'free',
                'monthly_used': user.monthly_used,
                'monthly_limit': user.monthly_call_limit,
                'monthly_remaining': user.monthly_call_limit - user.monthly_used if user.monthly_call_limit != -1 else -1,
                'has_exceeded': user.monthly_used >= user.monthly_call_limit if user.monthly_call_limit != -1 else False,
                'actual_monthly_calls': monthly_calls
            })
        
        # Summary by tier
        users_by_tier = {}
        monthly_calls = 0
        for user in all_users:
            tier = user.subscription_tier or 'free'
            if tier not in users_by_tier:
                users_by_tier[tier] = 0
            users_by_tier[tier] += 1
            monthly_calls += user.monthly_used
        
        return jsonify({
            'summary': {
                'total_users': total_users,
                'active_users': active_users,
                'total_calls': total_calls,
                'success_calls': success_calls,
                'error_calls': error_calls,
                'success_rate': (success_calls / total_calls * 100) if total_calls > 0 else 0,
                'monthly_calls': monthly_calls,
                'users_by_tier': users_by_tier
            },
            'popular_endpoints': [
                {'endpoint': ep, 'count': count} 
                for ep, count in popular_endpoints
            ],
            'daily_usage': [
                {'date': str(date), 'count': count} 
                for date, count in daily_usage
            ],
            'top_users': [
                {'email': email, 'count': count} 
                for email, count in top_users
            ],
            'users_usage': users_usage
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_api.route('/jobs', methods=['GET'])
@require_admin
def list_jobs():
    """List all jobs with filtering"""
    try:
        from models import Job
        
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        status = request.args.get('status', '')
        user_id = request.args.get('user_id', type=int)
        
        # Build query
        query = Job.query
        
        if status:
            query = query.filter(Job.status == status)
        if user_id:
            query = query.filter(Job.user_id == user_id)
        
        # Order by creation date
        query = query.order_by(desc(Job.created_at))
        
        # Paginate
        jobs = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
        return jsonify({
            'jobs': [job.to_dict() for job in jobs.items],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': jobs.total,
                'pages': jobs.pages,
                'has_next': jobs.has_next,
                'has_prev': jobs.has_prev
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_api.route('/system/health', methods=['GET'])
@require_admin
def system_health():
    """Get system health information"""
    try:
        from database import db
        from models import UsageLog
        
        # Database health
        db_healthy = True
        try:
            db.session.execute('SELECT 1')
        except:
            db_healthy = False
        
        # Recent error rate
        last_hour = datetime.utcnow() - timedelta(hours=1)
        recent_calls = UsageLog.query.filter(UsageLog.timestamp >= last_hour).count()
        recent_errors = UsageLog.query.filter(
            UsageLog.timestamp >= last_hour,
            UsageLog.status_code >= 400
        ).count()
        
        error_rate = (recent_errors / recent_calls * 100) if recent_calls > 0 else 0
        
        return jsonify({
            'database': 'healthy' if db_healthy else 'unhealthy',
            'recent_calls': recent_calls,
            'recent_errors': recent_errors,
            'error_rate': round(error_rate, 2),
            'timestamp': datetime.utcnow().isoformat()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_api.route('/users/by-tier', methods=['GET'])
@require_admin
def get_users_by_tier():
    """Get users grouped by subscription tier"""
    try:
        from models import User
        from sqlalchemy import func
        
        tier = request.args.get('tier', '')  # Optional tier filter
        
        # Build query
        query = User.query
        if tier:
            query = query.filter(User.subscription_tier == tier)
        
        users = query.all()
        
        # Group by tier
        users_by_tier = {}
        for user in users:
            tier_name = user.subscription_tier or 'free'
            if tier_name not in users_by_tier:
                users_by_tier[tier_name] = []
            users_by_tier[tier_name].append(user.to_dict())
        
        # Get stats by tier
        tier_stats = {}
        for tier_name in ['free', 'premium', 'enterprise', 'client']:
            tier_users = [u for u in users if (u.subscription_tier or 'free') == tier_name]
            total_calls = sum(u.monthly_used for u in tier_users)
            tier_stats[tier_name] = {
                'count': len(tier_users),
                'total_calls_used': total_calls,
                'users': [u.to_dict() for u in tier_users]
            }
        
        return jsonify({
            'users_by_tier': users_by_tier,
            'tier_stats': tier_stats
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_api.route('/users/<int:user_id>/reset-calls', methods=['POST'])
@require_admin
def reset_user_calls(user_id):
    """Reset a user's API call count"""
    try:
        from database import db
        from models import User, ResetHistory
        
        user = User.query.get_or_404(user_id)
        admin_user = g.current_user
        
        data = request.get_json() or {}
        reason = data.get('reason', '')
        
        # Record reset history
        calls_before = user.monthly_used
        reset_history = ResetHistory(
            user_id=user_id,
            reset_by=admin_user.id,
            calls_before=calls_before,
            calls_after=0,
            reset_reason=reason
        )
        
        # Reset user's monthly_used
        user.monthly_used = 0
        user.monthly_reset_date = datetime.utcnow()
        
        db.session.add(reset_history)
        db.session.commit()
        
        return jsonify({
            'message': 'User API calls reset successfully',
            'user': user.to_dict(),
            'reset_history': reset_history.to_dict()
        }), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/users/<int:user_id>/toggle-status', methods=['POST'])
@require_admin
def toggle_user_status(user_id):
    """Toggle user active status (activate/deactivate)"""
    try:
        from database import db
        from models import User
        
        user = User.query.get_or_404(user_id)
        
        # Prevent deactivating yourself
        if user.id == g.current_user.id:
            return jsonify({'error': 'Cannot deactivate your own account'}), 400
        
        # Toggle status
        user.is_active = not user.is_active
        db.session.commit()
        
        status = "activated" if user.is_active else "deactivated"
        print(f"✅ User {user.email} {status} by admin {g.current_user.email}")
        
        return jsonify({
            'message': f'User {status} successfully',
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/users/<int:user_id>/reset-history', methods=['GET'])
@require_admin
def get_user_reset_history(user_id):
    """Get reset history for a user"""
    try:
        from models import User, ResetHistory
        
        user = User.query.get_or_404(user_id)
        history = ResetHistory.query.filter_by(user_id=user_id)\
            .order_by(desc(ResetHistory.reset_at))\
            .all()
        
        return jsonify({
            'user_id': user_id,
            'user_email': user.email,
            'reset_history': [h.to_dict() for h in history]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_api.route('/notifications', methods=['GET'])
@require_admin
def list_notifications():
    """List all notifications with filters"""
    try:
        from models import Notification
        
        # Filters
        category = request.args.get('category', '')
        notification_type = request.args.get('type', '')
        is_read = request.args.get('is_read', '')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        query = Notification.query
        
        if category:
            query = query.filter(Notification.category == category)
        if notification_type:
            query = query.filter(Notification.type == notification_type)
        if is_read.lower() == 'true':
            query = query.filter(Notification.is_read == True)
        elif is_read.lower() == 'false':
            query = query.filter(Notification.is_read == False)
        
        # Get total count before pagination
        total = query.count()
        
        # Order by newest first and paginate
        notifications = query.order_by(desc(Notification.created_at))\
            .limit(limit)\
            .offset(offset)\
            .all()
        
        return jsonify({
            'notifications': [n.to_dict() for n in notifications],
            'total': total,
            'limit': limit,
            'offset': offset
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_api.route('/notifications/<int:notification_id>/read', methods=['POST'])
@require_admin
def mark_notification_read(notification_id):
    """Mark a notification as read"""
    try:
        from database import db
        from models import Notification
        
        notification = Notification.query.get_or_404(notification_id)
        
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = datetime.utcnow()
            notification.read_by = g.current_user.id
            db.session.commit()
        
        return jsonify({
            'message': 'Notification marked as read',
            'notification': notification.to_dict()
        }), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/notifications/<int:notification_id>', methods=['DELETE'])
@require_admin
def delete_notification(notification_id):
    """Delete a notification"""
    try:
        from database import db
        from models import Notification
        
        notification = Notification.query.get_or_404(notification_id)
        db.session.delete(notification)
        db.session.commit()
        
        return jsonify({'message': 'Notification deleted successfully'}), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/notifications/read-all', methods=['POST'])
@require_admin
def mark_all_notifications_read():
    """Mark all notifications as read"""
    try:
        from database import db
        from models import Notification
        
        unread_count = Notification.query.filter_by(is_read=False).count()
        
        if unread_count > 0:
            Notification.query.filter_by(is_read=False).update({
                'is_read': True,
                'read_at': datetime.utcnow(),
                'read_by': g.current_user.id
            })
            db.session.commit()
        
        return jsonify({
            'message': f'Marked {unread_count} notifications as read'
        }), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/notifications/stats', methods=['GET'])
@require_admin
def get_notification_stats():
    """Get notification statistics"""
    try:
        from models import Notification
        
        total = Notification.query.count()
        unread = Notification.query.filter_by(is_read=False).count()
        
        # Count by type
        by_type = {}
        for ntype in ['info', 'warning', 'error', 'success', 'payment', 'subscription']:
            by_type[ntype] = Notification.query.filter_by(type=ntype).count()
        
        # Count by category
        by_category = {}
        for category in ['system', 'payment', 'subscription', 'user', 'api']:
            by_category[category] = Notification.query.filter_by(category=category).count()
        
        return jsonify({
            'total': total,
            'unread': unread,
            'read': total - unread,
            'by_type': by_type,
            'by_category': by_category
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# FREE TIER API KEY MANAGEMENT ENDPOINTS
# ============================================================================

@admin_api.route('/free-tier-keys', methods=['GET'])
@require_admin
def list_free_tier_keys():
    """List all free tier API keys"""
    try:
        from models import APIKey, User
        from database import db
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        search = request.args.get('search', '')
        free_tier_type = request.args.get('free_tier_type', '')
        is_active = request.args.get('is_active', '')
        
        # Build query - only free tier keys
        query = APIKey.query.filter_by(is_free_tier=True)
        
        if search:
            query = query.filter(
                or_(
                    APIKey.name.contains(search),
                    APIKey.key.contains(search),
                    APIKey.notes.contains(search)
                )
            )
        if free_tier_type:
            query = query.filter_by(free_tier_type=free_tier_type)
        if is_active:
            query = query.filter_by(is_active=(is_active.lower() == 'true'))
        
        # Order by creation date (newest first)
        query = query.order_by(desc(APIKey.created_at))
        
        # Paginate
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        keys = pagination.items
        
        # Get usage stats for each key
        from models import UsageLog
        from sqlalchemy import func
        
        result = []
        for key in keys:
            # Get usage stats
            total_usage = UsageLog.query.filter_by(api_key_id=key.id).count()
            recent_usage = UsageLog.query.filter(
                UsageLog.api_key_id == key.id,
                UsageLog.timestamp >= datetime.utcnow() - timedelta(days=30)
            ).count()
            
            key_dict = key.to_dict(include_key=False)
            key_dict['usage'] = {
                'total': total_usage,
                'last_30_days': recent_usage
            }
            
            # Add granted by user email if available
            if key.granted_by:
                granted_by_user = User.query.get(key.granted_by)
                if granted_by_user:
                    key_dict['granted_by_email'] = granted_by_user.email
            
            result.append(key_dict)
        
        return jsonify({
            'keys': result,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': pagination.total,
                'pages': pagination.pages
            }
        }), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/free-tier-keys', methods=['POST'])
@require_admin
def create_free_tier_key():
    """Create a new free tier API key"""
    try:
        from models import APIKey, User
        from database import db
        from api_auth import generate_api_key
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Required fields
        name = data.get('name')
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        
        # Optional fields
        free_tier_type = data.get('free_tier_type', 'educational')  # Default to educational
        rate_limit = data.get('rate_limit', 10000)  # High default rate limit for free tier
        notes = data.get('notes', '')
        expires_at = data.get('expires_at')  # Optional expiration date
        
        # Parse expiration date if provided
        expiration_date = None
        if expires_at:
            try:
                expiration_date = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            except:
                return jsonify({'error': 'Invalid expiration date format'}), 400
        
        # Create a system user for free tier keys (or use a dedicated user)
        # For now, we'll create keys associated with the admin user who creates them
        # In production, you might want a dedicated system user
        system_user = User.query.filter_by(role='super_admin').first()
        if not system_user:
            system_user = g.current_user
        
        # Generate API key
        key_string = generate_api_key()
        
        # Create the API key
        api_key = APIKey(
            key=key_string,
            name=name,
            user_id=system_user.id,
            is_active=True,
            rate_limit=rate_limit,
            is_free_tier=True,
            free_tier_type=free_tier_type,
            granted_by=g.current_user.id,
            granted_at=datetime.utcnow(),
            notes=notes,
            expires_at=expiration_date
        )
        
        db.session.add(api_key)
        db.session.commit()
        
        # Return the key with the actual key string (only shown once)
        result = api_key.to_dict(include_key=True)
        result['granted_by_email'] = g.current_user.email
        
        return jsonify({
            'message': 'Free tier API key created successfully',
            'key': result
        }), 201
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/free-tier-keys/<int:key_id>', methods=['GET'])
@require_admin
def get_free_tier_key(key_id):
    """Get details of a specific free tier API key"""
    try:
        from models import APIKey, User, UsageLog
        from database import db
        from sqlalchemy import func
        
        api_key = APIKey.query.filter_by(id=key_id, is_free_tier=True).first()
        if not api_key:
            return jsonify({'error': 'Free tier API key not found'}), 404
        
        # Get detailed usage stats
        total_usage = UsageLog.query.filter_by(api_key_id=api_key.id).count()
        recent_usage = UsageLog.query.filter(
            UsageLog.api_key_id == api_key.id,
            UsageLog.timestamp >= datetime.utcnow() - timedelta(days=30)
        ).count()
        
        # Get usage by endpoint
        usage_by_endpoint = db.session.query(
            UsageLog.endpoint,
            func.count(UsageLog.id).label('count')
        ).filter(
            UsageLog.api_key_id == api_key.id
        ).group_by(
            UsageLog.endpoint
        ).order_by(
            func.count(UsageLog.id).desc()
        ).limit(10).all()
        
        result = api_key.to_dict(include_key=False)
        result['usage'] = {
            'total': total_usage,
            'last_30_days': recent_usage,
            'by_endpoint': [{'endpoint': ep, 'count': count} for ep, count in usage_by_endpoint]
        }
        
        # Add granted by user email if available
        if api_key.granted_by:
            granted_by_user = User.query.get(api_key.granted_by)
            if granted_by_user:
                result['granted_by_email'] = granted_by_user.email
        
        return jsonify(result), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/free-tier-keys/<int:key_id>', methods=['PUT'])
@require_admin
def update_free_tier_key(key_id):
    """Update a free tier API key"""
    try:
        from models import APIKey
        from database import db
        
        api_key = APIKey.query.filter_by(id=key_id, is_free_tier=True).first()
        if not api_key:
            return jsonify({'error': 'Free tier API key not found'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Update allowed fields
        if 'name' in data:
            api_key.name = data['name']
        if 'free_tier_type' in data:
            api_key.free_tier_type = data['free_tier_type']
        if 'rate_limit' in data:
            api_key.rate_limit = data['rate_limit']
        if 'notes' in data:
            api_key.notes = data['notes']
        if 'is_active' in data:
            api_key.is_active = data['is_active']
        if 'expires_at' in data:
            if data['expires_at']:
                try:
                    api_key.expires_at = datetime.fromisoformat(data['expires_at'].replace('Z', '+00:00'))
                except:
                    return jsonify({'error': 'Invalid expiration date format'}), 400
            else:
                api_key.expires_at = None
        
        db.session.commit()
        
        return jsonify({
            'message': 'Free tier API key updated successfully',
            'key': api_key.to_dict(include_key=False)
        }), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/free-tier-keys/<int:key_id>', methods=['DELETE'])
@require_admin
def revoke_free_tier_key(key_id):
    """Revoke (deactivate) a free tier API key"""
    try:
        from models import APIKey
        from database import db
        
        api_key = APIKey.query.filter_by(id=key_id, is_free_tier=True).first()
        if not api_key:
            return jsonify({'error': 'Free tier API key not found'}), 404
        
        # Deactivate the key instead of deleting (preserves history)
        api_key.is_active = False
        db.session.commit()
        
        return jsonify({
            'message': 'Free tier API key revoked successfully'
        }), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/free-tier-keys/stats', methods=['GET'])
@require_admin
def get_free_tier_stats():
    """Get statistics about free tier API key usage"""
    try:
        from models import APIKey, UsageLog
        from database import db
        from sqlalchemy import func
        
        # Total free tier keys
        total_keys = APIKey.query.filter_by(is_free_tier=True).count()
        active_keys = APIKey.query.filter_by(is_free_tier=True, is_active=True).count()
        
        # Total usage by free tier keys
        total_usage = db.session.query(func.count(UsageLog.id)).join(
            APIKey, UsageLog.api_key_id == APIKey.id
        ).filter(
            APIKey.is_free_tier == True
        ).scalar() or 0
        
        # Usage in last 30 days
        recent_usage = db.session.query(func.count(UsageLog.id)).join(
            APIKey, UsageLog.api_key_id == APIKey.id
        ).filter(
            APIKey.is_free_tier == True,
            UsageLog.timestamp >= datetime.utcnow() - timedelta(days=30)
        ).scalar() or 0
        
        # Usage by free tier type
        usage_by_type = db.session.query(
            APIKey.free_tier_type,
            func.count(UsageLog.id).label('count')
        ).join(
            UsageLog, APIKey.id == UsageLog.api_key_id
        ).filter(
            APIKey.is_free_tier == True
        ).group_by(
            APIKey.free_tier_type
        ).all()
        
        return jsonify({
            'total_keys': total_keys,
            'active_keys': active_keys,
            'inactive_keys': total_keys - active_keys,
            'total_usage': total_usage,
            'usage_last_30_days': recent_usage,
            'usage_by_type': {t: c for t, c in usage_by_type}
        }), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/test-supabase-users', methods=['GET'])
@require_admin
def test_supabase_users():
    """
    Retrieve all users from Supabase and return them, along with summary statistics.
    Requires admin or super_admin role.
    """
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from urllib.parse import urlparse, quote_plus

        # Use the hardcoded Supabase connection string from database.py or supabase_sync.py
        # This ensures we are always querying the actual Supabase DB
        supabase_url = "postgresql://postgres.pqdxqvxyrahvongbhtdb:Kopenikus0218!@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"

        conn = psycopg2.connect(supabase_url, sslmode='require')
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        cursor.execute("""
            SELECT id, email, role, is_active, subscription_tier,
                   monthly_call_limit, monthly_used, created_at, last_login
            FROM users
            ORDER BY id ASC
        """)
        supabase_users = cursor.fetchall()

        cursor.close()
        conn.close()

        # Calculate statistics
        total_users = len(supabase_users)
        super_admins = sum(1 for u in supabase_users if u['role'] == 'super_admin')
        regular_admins = sum(1 for u in supabase_users if u['role'] == 'admin')
        regular_users = sum(1 for u in supabase_users if u['role'] == 'user')
        active_users = sum(1 for u in supabase_users if u['is_active'])
        inactive_users = total_users - active_users

        users_by_tier = {}
        for user_data in supabase_users:
            tier = user_data.get('subscription_tier', 'unknown')
            users_by_tier[tier] = users_by_tier.get(tier, 0) + 1

        stats = {
            "totalUsers": total_users,
            "superAdmins": super_admins,
            "regularAdmins": regular_admins,
            "regularUsers": regular_users,
            "activeUsers": active_users,
            "inactiveUsers": inactive_users,
            "usersByTier": users_by_tier,
        }

        return jsonify({"users": supabase_users, "stats": stats}), 200

    except Exception as e:
        print(f"ERROR in test_supabase_users: {str(e)}")
        return jsonify({"message": f"Error fetching Supabase users: {str(e)}"}), 500

@admin_api.route('/sync-user-role-from-supabase', methods=['POST'])
@require_admin
def sync_user_role_from_supabase():
    """
    Sync user role from Supabase to backend database.
    Requires admin or super_admin role.
    
    Body: { "email": "user@example.com" } or empty to sync all users
    """
    try:
        from models import User
        from database import db
        import psycopg2
        from psycopg2.extras import RealDictCursor

        data = request.get_json() or {}
        email = data.get('email', '').strip().lower() if data.get('email') else None

        # Use the hardcoded Supabase connection string
        supabase_url = "postgresql://postgres.pqdxqvxyrahvongbhtdb:Kopenikus0218!@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"

        conn = psycopg2.connect(supabase_url, sslmode='require')
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # Query Supabase for users
        if email:
            cursor.execute(
                "SELECT id, email, role, is_active FROM users WHERE email = %s",
                (email,)
            )
        else:
            cursor.execute(
                "SELECT id, email, role, is_active FROM users ORDER BY email"
            )

        supabase_users = cursor.fetchall()
        cursor.close()
        conn.close()

        if not supabase_users:
            return jsonify({
                'message': f'No users found in Supabase' + (f' with email {email}' if email else ''),
                'synced': 0,
                'updated': 0,
                'not_found': 0
            }), 200

        # Sync each user
        synced_count = 0
        updated_count = 0
        not_found_count = 0
        updates = []

        for supabase_user in supabase_users:
            user_email = supabase_user['email']
            supabase_role = supabase_user['role']
            supabase_is_active = supabase_user['is_active']

            # Check if user exists in backend database
            backend_user = User.query.filter_by(email=user_email).first()

            if not backend_user:
                not_found_count += 1
                continue

            # Check if roles match
            if backend_user.role == supabase_role and backend_user.is_active == supabase_is_active:
                synced_count += 1
            else:
                old_role = backend_user.role
                old_active = backend_user.is_active
                
                # Update role and active status in backend database
                backend_user.role = supabase_role
                backend_user.is_active = supabase_is_active
                
                updates.append({
                    'email': user_email,
                    'old_role': old_role,
                    'new_role': supabase_role,
                    'old_active': old_active,
                    'new_active': supabase_is_active
                })
                updated_count += 1

        # Commit all updates
        if updated_count > 0:
            db.session.commit()

        return jsonify({
            'message': 'Sync completed successfully',
            'total_in_supabase': len(supabase_users),
            'synced': synced_count,
            'updated': updated_count,
            'not_found_in_backend': not_found_count,
            'updates': updates
        }), 200

    except Exception as e:
        from database import db
        db.session.rollback()
        print(f"ERROR in sync_user_role_from_supabase: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({"message": f"Error syncing user roles: {str(e)}"}), 500

