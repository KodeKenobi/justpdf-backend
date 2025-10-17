from flask import Blueprint, request, jsonify, g
from sqlalchemy import func, desc
from datetime import datetime, timedelta
from models import User, APIKey, UsageLog, Job, db
from api_auth import require_api_key, get_user_stats

# Create Blueprint
admin_api = Blueprint('admin_api', __name__, url_prefix='/api/admin')

def require_admin(f):
    """Decorator to require admin role"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'current_user') or g.current_user.role != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

@admin_api.route('/users', methods=['GET'])
@require_api_key
@require_admin
def list_users():
    """List all users with pagination and filtering"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        search = request.args.get('search', '')
        role = request.args.get('role', '')
        is_active = request.args.get('is_active', '')
        
        # Build query
        query = User.query
        
        if search:
            query = query.filter(User.email.contains(search))
        if role:
            query = query.filter(User.role == role)
        if is_active:
            query = query.filter(User.is_active == (is_active.lower() == 'true'))
        
        # Order by creation date
        query = query.order_by(desc(User.created_at))
        
        # Paginate
        users = query.paginate(
            page=page, 
            per_page=per_page, 
            error_out=False
        )
        
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
@require_api_key
@require_admin
def get_user(user_id):
    """Get detailed user information"""
    try:
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
@require_api_key
@require_admin
def create_api_key(user_id):
    """Create API key for a user"""
    try:
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
@require_api_key
@require_admin
def revoke_api_key(key_id):
    """Revoke an API key"""
    try:
        api_key = APIKey.query.get_or_404(key_id)
        api_key.is_active = False
        db.session.commit()
        
        return jsonify({'message': 'API key revoked successfully'}), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/api-keys/<int:key_id>', methods=['PUT'])
@require_api_key
@require_admin
def update_api_key(key_id):
    """Update API key settings"""
    try:
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
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@admin_api.route('/usage/stats', methods=['GET'])
@require_api_key
@require_admin
def get_usage_stats():
    """Get system-wide usage statistics"""
    try:
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
        
        return jsonify({
            'summary': {
                'total_users': total_users,
                'active_users': active_users,
                'total_calls': total_calls,
                'success_calls': success_calls,
                'error_calls': error_calls,
                'success_rate': (success_calls / total_calls * 100) if total_calls > 0 else 0
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
            ]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@admin_api.route('/jobs', methods=['GET'])
@require_api_key
@require_admin
def list_jobs():
    """List all jobs with filtering"""
    try:
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
@require_api_key
@require_admin
def system_health():
    """Get system health information"""
    try:
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
