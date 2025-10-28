from flask import Blueprint, request, jsonify, g
from sqlalchemy import desc
from datetime import datetime, timedelta
from api_auth import get_user_stats
from flask_jwt_extended import jwt_required, get_jwt_identity

# Create Blueprint
client_api = Blueprint('client_api', __name__, url_prefix='/api/client')

def get_authenticated_user():
    """Get authenticated user from JWT token"""
    try:
        from models import User
        user_id = get_jwt_identity()
        return User.query.get(user_id)
    except Exception as e:
        print(f"Error getting authenticated user: {e}")
        return None

@client_api.route('/keys', methods=['GET'])
@jwt_required()
def get_api_keys():
    """Get user's API keys"""
    try:
        from models import APIKey, User
        
        user = get_authenticated_user()
        if not user:
            return jsonify({'error': 'User not found'}), 401
        
        api_keys = APIKey.query.filter_by(
            user_id=user.id,
            is_active=True
        ).order_by(desc(APIKey.created_at)).all()
        
        return jsonify([key.to_dict(include_key=True) for key in api_keys]), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@client_api.route('/keys', methods=['POST'])
@jwt_required()
def create_api_key():
    """Create new API key for user"""
    try:
        from database import db
        from models import APIKey, User
        
        user = get_authenticated_user()
        if not user:
            return jsonify({'error': 'User not found'}), 401
        
        data = request.get_json()
        name = data.get('name', f'API Key {datetime.utcnow().strftime("%Y-%m-%d %H:%M")}')
        rate_limit = data.get('rate_limit', 1000)
        
        # Check if user has reached max keys limit (e.g., 5 keys per user)
        existing_keys = APIKey.query.filter_by(user_id=user.id, is_active=True).count()
        if existing_keys >= 5:
            return jsonify({'error': 'Maximum number of API keys reached'}), 400
        
        # Generate API key
        api_key = APIKey(
            key=APIKey.generate_key(),
            name=name,
            user_id=user.id,
            rate_limit=rate_limit
        )
        
        db.session.add(api_key)
        db.session.commit()
        
        return jsonify(api_key.to_dict(include_key=True)), 201
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@client_api.route('/keys/<int:key_id>', methods=['PUT'])
@jwt_required()
def update_api_key(key_id):
    """Update API key settings"""
    try:
        from database import db
        from models import APIKey, User
        
        user = get_authenticated_user()
        if not user:
            return jsonify({'error': 'User not found'}), 401
        
        api_key = APIKey.query.filter_by(
            id=key_id,
            user_id=user.id
        ).first()
        
        if not api_key:
            return jsonify({'error': 'API key not found'}), 404
        
        data = request.get_json()
        if 'name' in data:
            api_key.name = data['name']
        if 'rate_limit' in data:
            api_key.rate_limit = data['rate_limit']
        
        db.session.commit()
        
        return jsonify(api_key.to_dict(include_key=True)), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@client_api.route('/keys/<int:key_id>', methods=['DELETE'])
@jwt_required()
def delete_api_key(key_id):
    """Delete API key"""
    try:
        from database import db
        from models import APIKey, User
        
        user = get_authenticated_user()
        if not user:
            return jsonify({'error': 'User not found'}), 401
        
        api_key = APIKey.query.filter_by(
            id=key_id,
            user_id=user.id
        ).first()
        
        if not api_key:
            return jsonify({'error': 'API key not found'}), 404
        
        # Soft delete - deactivate instead of hard delete
        api_key.is_active = False
        db.session.commit()
        
        return jsonify({'message': 'API key deleted successfully'}), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@client_api.route('/usage', methods=['GET'])
@jwt_required()
def get_usage_stats():
    """Get user's usage statistics"""
    try:
        from database import db
        from models import UsageLog, User
        
        user = get_authenticated_user()
        if not user:
            return jsonify({'error': 'User not found'}), 401
        
        # Time range
        days = request.args.get('days', 30, type=int)
        start_date = datetime.utcnow() - timedelta(days=days)
        
        # Get usage stats
        stats = get_user_stats(user.id)
        
        # Get recent usage logs
        recent_logs = UsageLog.query.filter(
            UsageLog.user_id == user.id,
            UsageLog.timestamp >= start_date
        ).order_by(desc(UsageLog.timestamp)).limit(100).all()
        
        # Get usage by day
        daily_usage = db.session.query(
            db.func.date(UsageLog.timestamp).label('date'),
            db.func.count(UsageLog.id).label('count')
        ).filter(
            UsageLog.user_id == user.id,
            UsageLog.timestamp >= start_date
        ).group_by(
            db.func.date(UsageLog.timestamp)
        ).order_by(
            db.func.date(UsageLog.timestamp)
        ).all()
        
        # Get usage by endpoint
        endpoint_usage = db.session.query(
            UsageLog.endpoint,
            db.func.count(UsageLog.id).label('count')
        ).filter(
            UsageLog.user_id == user.id,
            UsageLog.timestamp >= start_date
        ).group_by(
            UsageLog.endpoint
        ).order_by(
            db.func.count(UsageLog.id).desc()
        ).all()
        
        return jsonify({
            'summary': stats,
            'recent_logs': [log.to_dict() for log in recent_logs],
            'daily_usage': [
                {'date': str(date), 'count': count} 
                for date, count in daily_usage
            ],
            'endpoint_usage': [
                {'endpoint': ep, 'count': count} 
                for ep, count in endpoint_usage
            ]
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@client_api.route('/jobs', methods=['GET'])
@jwt_required()
def get_user_jobs():
    """Get user's jobs"""
    try:
        from models import Job, User
        
        user = get_authenticated_user()
        if not user:
            return jsonify({'error': 'User not found'}), 401
        
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 20, type=int), 100)
        status = request.args.get('status', '')
        
        # Build query
        query = Job.query.filter_by(user_id=user.id)
        
        if status:
            query = query.filter(Job.status == status)
        
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

@client_api.route('/profile', methods=['GET'])
@jwt_required()
def get_profile():
    """Get user profile information"""
    try:
        user = get_authenticated_user()
        if not user:
            return jsonify({'error': 'User not found'}), 401
        return jsonify(user.to_dict()), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@client_api.route('/profile', methods=['PUT'])
@jwt_required()
def update_profile():
    """Update user profile"""
    try:
        from database import db
        from models import User
        
        user = get_authenticated_user()
        if not user:
            return jsonify({'error': 'User not found'}), 401
        
        data = request.get_json()
        
        # Only allow updating certain fields
        if 'email' in data:
            # Check if email is already taken
            existing_user = User.query.filter_by(email=data['email']).first()
            if existing_user and existing_user.id != user.id:
                return jsonify({'error': 'Email already taken'}), 400
            user.email = data['email']
        
        db.session.commit()
        
        return jsonify(user.to_dict()), 200
        
    except Exception as e:
        from database import db
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
