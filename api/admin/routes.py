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

