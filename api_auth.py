from functools import wraps
from flask import request, jsonify, g
from datetime import datetime, timedelta
import time

def generate_api_key():
    """Generate a secure API key"""
    from models import APIKey
    return APIKey.generate_key()

def verify_api_key(api_key_string):
    """Verify API key and return associated user"""
    if not api_key_string:
        return None
    
    from database import db
    from models import APIKey
    
    # Find API key
    api_key = APIKey.query.filter_by(key=api_key_string, is_active=True).first()
    if not api_key:
        return None
    
    # Check if key is expired
    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        return None
    
    # Update last used timestamp
    api_key.last_used = datetime.utcnow()
    db.session.commit()
    
    return api_key.user

def verify_api_key_with_key(api_key_string):
    """Verify API key and return both user and API key object"""
    if not api_key_string:
        return None, None
    
    from database import db
    from models import APIKey
    
    # Find API key
    api_key = APIKey.query.filter_by(key=api_key_string, is_active=True).first()
    if not api_key:
        return None, None
    
    # Check if key is expired
    if api_key.expires_at and api_key.expires_at < datetime.utcnow():
        return None, None
    
    # Update last used timestamp
    api_key.last_used = datetime.utcnow()
    db.session.commit()
    
    return api_key.user, api_key

def require_api_key(f):
    """Decorator to require valid API key"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Skip authentication for OPTIONS requests (CORS preflight)
        # Flask-CORS will handle the OPTIONS response automatically
        if request.method == 'OPTIONS':
            response = jsonify({})
            response.status_code = 200
            return response
        
        # Get API key from header
        api_key = request.headers.get('X-API-Key') or request.headers.get('Authorization', '').replace('Bearer ', '')
        
        if not api_key:
            return jsonify({'error': 'API key required'}), 401
        
        # Verify API key and get both user and key object
        user, api_key_obj = verify_api_key_with_key(api_key)
        if not user or not api_key_obj:
            return jsonify({'error': 'Invalid API key'}), 401
        
        # Store user and API key in g for use in route
        g.current_user = user
        g.current_api_key = api_key_obj
        g.is_free_tier = api_key_obj.is_free_tier  # Store free tier status for easy access
        
        return f(*args, **kwargs)
    return decorated_function

def log_api_usage(endpoint, method, status_code, file_size=None, processing_time=None, error_message=None):
    """Log API usage for analytics and billing"""
    if not hasattr(g, 'current_api_key') or not g.current_api_key:
        return
    
    try:
        from database import db
        from models import UsageLog
        
        # Check if this is a free tier request
        is_free_tier = getattr(g, 'is_free_tier', False) or (g.current_api_key.is_free_tier if g.current_api_key else False)
        
        usage_log = UsageLog(
            api_key_id=g.current_api_key.id,
            user_id=g.current_user.id,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            file_size=file_size,
            processing_time=processing_time,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent', ''),
            error_message=error_message,
            is_free_tier=is_free_tier
        )
        
        db.session.add(usage_log)
        db.session.commit()
    except Exception as e:
        # Don't let logging errors break the API
        print(f"Error logging API usage: {e}")

def check_rate_limit(api_key_id):
    """Check if API key has exceeded rate limit"""
    try:
        from database import db
        from models import RateLimit
        
        # Get or create rate limit record for current hour
        now = datetime.utcnow()
        window_start = now.replace(minute=0, second=0, microsecond=0)
        
        rate_limit = RateLimit.query.filter_by(
            api_key_id=api_key_id,
            window_start=window_start
        ).first()
        
        if not rate_limit:
            # Create new rate limit record
            rate_limit = RateLimit(
                api_key_id=api_key_id,
                window_start=window_start
            )
            db.session.add(rate_limit)
        
        # Check if limit exceeded
        if rate_limit.is_exceeded():
            return False, rate_limit.api_key.rate_limit
        
        # Increment counter
        rate_limit.increment()
        db.session.commit()
        
        return True, rate_limit.api_key.rate_limit - rate_limit.requests_count
    
    except Exception as e:
        print(f"Error checking rate limit: {e}")
        # Allow request if rate limiting fails
        return True, 0

def require_rate_limit(f):
    """Decorator to enforce rate limiting"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'current_api_key'):
            return f(*args, **kwargs)
        
        # Free tier keys bypass rate limiting (they can have very high limits set)
        is_free_tier = getattr(g, 'is_free_tier', False) or (g.current_api_key.is_free_tier if g.current_api_key else False)
        
        if not is_free_tier:
            # Check rate limit for non-free tier keys
            allowed, remaining = check_rate_limit(g.current_api_key.id)
            if not allowed:
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'limit': g.current_api_key.rate_limit,
                    'reset_time': datetime.utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                }), 429
            
            # Add rate limit info to response headers
            response = f(*args, **kwargs)
            if hasattr(response, 'headers'):
                response.headers['X-RateLimit-Limit'] = str(g.current_api_key.rate_limit)
                response.headers['X-RateLimit-Remaining'] = str(remaining)
                response.headers['X-RateLimit-Reset'] = str(int((datetime.utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).timestamp()))
            
            return response
        else:
            # Free tier: still check rate limit but use the key's rate_limit value
            # This allows setting very high limits (like 100000) for free tier keys
            allowed, remaining = check_rate_limit(g.current_api_key.id)
            if not allowed:
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'limit': g.current_api_key.rate_limit,
                    'reset_time': datetime.utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
                }), 429
            
            response = f(*args, **kwargs)
            if hasattr(response, 'headers'):
                response.headers['X-RateLimit-Limit'] = str(g.current_api_key.rate_limit)
                response.headers['X-RateLimit-Remaining'] = str(remaining)
                response.headers['X-RateLimit-Reset'] = str(int((datetime.utcnow().replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).timestamp()))
                response.headers['X-Free-Tier'] = 'true'
            
            return response
    return decorated_function

def should_bypass_monthly_limit():
    """Check if the current request should bypass monthly call limits"""
    if not hasattr(g, 'current_api_key'):
        return False
    return getattr(g, 'is_free_tier', False) or (g.current_api_key.is_free_tier if g.current_api_key else False)

def increment_monthly_usage():
    """Increment monthly_used counter for the current user (skip for free tier keys)"""
    if should_bypass_monthly_limit():
        return  # Don't increment for free tier keys
    
    if not hasattr(g, 'current_user') or not g.current_user:
        return
    
    try:
        from database import db
        from models import User
        
        # Refresh user from database
        user = User.query.get(g.current_user.id)
        if not user:
            return
        
        # Only increment if not unlimited
        if user.monthly_call_limit != -1:
            user.monthly_used += 1
            db.session.commit()
    except Exception as e:
        # Don't let usage tracking errors break the API
        print(f"Error incrementing monthly usage: {e}")

def get_user_stats(user_id):
    """Get usage statistics for a user"""
    try:
        from database import db
        from models import UsageLog
        from sqlalchemy import func
        
        # Get total API calls
        total_calls = UsageLog.query.filter_by(user_id=user_id).count()
        
        # Get calls in last 24 hours
        yesterday = datetime.utcnow() - timedelta(days=1)
        recent_calls = UsageLog.query.filter(
            UsageLog.user_id == user_id,
            UsageLog.timestamp >= yesterday
        ).count()
        
        # Get calls by status
        success_calls = UsageLog.query.filter(
            UsageLog.user_id == user_id,
            UsageLog.status_code.between(200, 299)
        ).count()
        
        error_calls = UsageLog.query.filter(
            UsageLog.user_id == user_id,
            UsageLog.status_code >= 400
        ).count()
        
        # Get most used endpoints
        popular_endpoints = db.session.query(
            UsageLog.endpoint,
            func.count(UsageLog.id).label('count')
        ).filter(
            UsageLog.user_id == user_id
        ).group_by(
            UsageLog.endpoint
        ).order_by(
            func.count(UsageLog.id).desc()
        ).limit(10).all()
        
        return {
            'total_calls': total_calls,
            'recent_calls': recent_calls,
            'success_calls': success_calls,
            'error_calls': error_calls,
            'success_rate': (success_calls / total_calls * 100) if total_calls > 0 else 0,
            'popular_endpoints': [{'endpoint': ep, 'count': count} for ep, count in popular_endpoints]
        }
    except Exception as e:
        print(f"Error getting user stats: {e}")
        return {
            'total_calls': 0,
            'recent_calls': 0,
            'success_calls': 0,
            'error_calls': 0,
            'success_rate': 0,
            'popular_endpoints': []
        }
