from flask import Blueprint, request, jsonify, g
from sqlalchemy import func, desc, and_, or_
from datetime import datetime, timedelta
from database import db
from models import AnalyticsEvent, PageView, UserSession, User

# Create Blueprint
analytics_api = Blueprint('analytics_api', __name__, url_prefix='/api/analytics')

@analytics_api.before_request
def load_user():
    """Set g.current_user from JWT token or API key (optional for tracking)"""
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
        pass  # JWT auth failed, try API key or allow anonymous
    
    # Fallback to API key authentication (optional)
    try:
        from api_auth import verify_api_key
        api_key = request.headers.get('X-API-Key') or request.headers.get('Authorization', '').replace('Bearer ', '')
        if api_key:
            user = verify_api_key(api_key)
            if user:
                g.current_user = user
                return
    except Exception:
        pass  # API key auth failed, allow anonymous tracking
    
    # Allow anonymous tracking - g.current_user will be None

@analytics_api.route('/events', methods=['POST'])
def track_event():
    """Track analytics events"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        events = data.get('events', [])
        if not isinstance(events, list):
            return jsonify({'error': 'Events must be an array'}), 400
        
        # Get user_id from session if available (optional for anonymous tracking)
        user_id = None
        if hasattr(g, 'current_user') and g.current_user:
            user_id = g.current_user.id
        
        # Process each event
        for event_data in events:
            event = AnalyticsEvent(
                user_id=user_id,
                event_type=event_data.get('event_type', 'custom'),
                event_name=event_data.get('event_name', 'unknown'),
                properties=event_data.get('properties'),
                session_id=event_data.get('session_id', ''),
                page_url=event_data.get('page_url', ''),
                page_title=event_data.get('page_title'),
                timestamp=datetime.fromisoformat(event_data.get('timestamp', datetime.utcnow().isoformat()).replace('Z', '+00:00')) if isinstance(event_data.get('timestamp'), str) else datetime.utcnow(),
                user_agent=event_data.get('user_agent'),
                device_type=event_data.get('device_type'),
                browser=event_data.get('browser'),
                os=event_data.get('os'),
                referrer=event_data.get('referrer')
            )
            db.session.add(event)
        
        db.session.commit()
        return jsonify({'success': True, 'processed': len(events)}), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Error tracking analytics event: {e}")
        return jsonify({'error': str(e)}), 500

@analytics_api.route('/pageview', methods=['POST'])
def track_pageview():
    """Track page views"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Get user_id from session if available (optional for anonymous tracking)
        user_id = None
        if hasattr(g, 'current_user') and g.current_user:
            user_id = g.current_user.id
        
        pageview = PageView(
            user_id=user_id,
            session_id=data.get('session_id', ''),
            page_url=data.get('page_url', ''),
            page_title=data.get('page_title'),
            timestamp=datetime.fromisoformat(data.get('timestamp', datetime.utcnow().isoformat()).replace('Z', '+00:00')) if isinstance(data.get('timestamp'), str) else datetime.utcnow(),
            duration=data.get('duration'),
            referrer=data.get('referrer'),
            user_agent=data.get('user_agent'),
            device_type=data.get('device_type'),
            browser=data.get('browser'),
            os=data.get('os')
        )
        db.session.add(pageview)
        db.session.commit()
        
        return jsonify({'success': True}), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Error tracking pageview: {e}")
        return jsonify({'error': str(e)}), 500

@analytics_api.route('/session', methods=['POST'])
def track_session():
    """Track user sessions"""
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        session_id = data.get('id') or data.get('session_id', '')
        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400
        
        # Get user_id from session if available (optional for anonymous tracking)
        user_id = None
        if hasattr(g, 'current_user') and g.current_user:
            user_id = g.current_user.id
        
        # Check if session exists
        existing_session = UserSession.query.get(session_id)
        
        if existing_session:
            # Update existing session
            existing_session.last_activity = datetime.fromisoformat(data.get('last_activity', datetime.utcnow().isoformat()).replace('Z', '+00:00')) if isinstance(data.get('last_activity'), str) else datetime.utcnow()
            existing_session.page_views = data.get('page_views', existing_session.page_views)
            existing_session.events = data.get('events', existing_session.events)
            existing_session.is_active = data.get('is_active', True)
        else:
            # Create new session
            new_session = UserSession(
                id=session_id,
                user_id=user_id,
                start_time=datetime.fromisoformat(data.get('start_time', datetime.utcnow().isoformat()).replace('Z', '+00:00')) if isinstance(data.get('start_time'), str) else datetime.utcnow(),
                last_activity=datetime.fromisoformat(data.get('last_activity', datetime.utcnow().isoformat()).replace('Z', '+00:00')) if isinstance(data.get('last_activity'), str) else datetime.utcnow(),
                page_views=data.get('page_views', 0),
                events=data.get('events', 0),
                device_type=data.get('device_type'),
                browser=data.get('browser'),
                os=data.get('os'),
                country=data.get('country'),
                city=data.get('city'),
                ip_address=data.get('ip_address'),
                user_agent=data.get('user_agent'),
                referrer=data.get('referrer'),
                is_active=data.get('is_active', True)
            )
            db.session.add(new_session)
        
        db.session.commit()
        return jsonify({'success': True}), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"Error tracking session: {e}")
        return jsonify({'error': str(e)}), 500

def require_admin(f):
    """Decorator to require admin role"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not hasattr(g, 'current_user') or not g.current_user:
            return jsonify({'error': 'Authentication required'}), 401
        if g.current_user.role != 'admin' and g.current_user.role != 'super_admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

@analytics_api.route('/dashboard', methods=['GET'])
@require_admin
def get_dashboard():
    """Get analytics dashboard data"""
    try:
        range_param = request.args.get('range', '24h')
        start_time_param = request.args.get('start_time')
        
        # Calculate time range
        now = datetime.utcnow()
        if start_time_param:
            try:
                start_time = datetime.fromisoformat(start_time_param.replace('Z', '+00:00'))
            except:
                start_time = now - timedelta(hours=24)
        else:
            # Default ranges
            if range_param == '1h':
                start_time = now - timedelta(hours=1)
            elif range_param == '24h':
                start_time = now - timedelta(hours=24)
            elif range_param == '7d':
                start_time = now - timedelta(days=7)
            elif range_param == '30d':
                start_time = now - timedelta(days=30)
            elif range_param == '90d':
                start_time = now - timedelta(days=90)
            else:
                start_time = now - timedelta(hours=24)
        
        # Total unique users (distinct user_ids, including null for anonymous)
        total_users = db.session.query(func.count(func.distinct(UserSession.user_id))).filter(
            UserSession.start_time >= start_time
        ).scalar() or 0
        
        # Total sessions
        total_sessions = UserSession.query.filter(
            UserSession.start_time >= start_time
        ).count()
        
        # Total page views
        total_page_views = PageView.query.filter(
            PageView.timestamp >= start_time
        ).count()
        
        # Total events
        total_events = AnalyticsEvent.query.filter(
            AnalyticsEvent.timestamp >= start_time
        ).count()
        
        # Average session duration (in seconds)
        sessions_with_duration = UserSession.query.filter(
            and_(
                UserSession.start_time >= start_time,
                UserSession.last_activity.isnot(None)
            )
        ).all()
        
        avg_duration = 0
        if sessions_with_duration:
            total_duration = sum(
                (s.last_activity - s.start_time).total_seconds() 
                for s in sessions_with_duration 
                if s.last_activity and s.start_time
            )
            avg_duration = int(total_duration / len(sessions_with_duration)) if sessions_with_duration else 0
        
        # Top pages
        top_pages_query = db.session.query(
            PageView.page_url,
            func.count(PageView.id).label('views')
        ).filter(
            PageView.timestamp >= start_time
        ).group_by(PageView.page_url).order_by(desc('views')).limit(10).all()
        
        top_pages = [{'page': page, 'views': views} for page, views in top_pages_query]
        
        # Top events
        top_events_query = db.session.query(
            AnalyticsEvent.event_name,
            func.count(AnalyticsEvent.id).label('count')
        ).filter(
            AnalyticsEvent.timestamp >= start_time
        ).group_by(AnalyticsEvent.event_name).order_by(desc('count')).limit(10).all()
        
        top_events = [{'event': event, 'count': count} for event, count in top_events_query]
        
        # Device breakdown
        device_breakdown_query = db.session.query(
            UserSession.device_type,
            func.count(func.distinct(UserSession.id)).label('count')
        ).filter(
            and_(
                UserSession.start_time >= start_time,
                UserSession.device_type.isnot(None)
            )
        ).group_by(UserSession.device_type).all()
        
        device_breakdown = [{'device': device or 'unknown', 'count': count} for device, count in device_breakdown_query]
        
        # Browser breakdown
        browser_breakdown_query = db.session.query(
            UserSession.browser,
            func.count(func.distinct(UserSession.id)).label('count')
        ).filter(
            and_(
                UserSession.start_time >= start_time,
                UserSession.browser.isnot(None)
            )
        ).group_by(UserSession.browser).all()
        
        browser_breakdown = [{'browser': browser or 'unknown', 'count': count} for browser, count in browser_breakdown_query]
        
        # OS breakdown
        os_breakdown_query = db.session.query(
            UserSession.os,
            func.count(func.distinct(UserSession.id)).label('count')
        ).filter(
            and_(
                UserSession.start_time >= start_time,
                UserSession.os.isnot(None)
            )
        ).group_by(UserSession.os).all()
        
        os_breakdown = [{'os': os_name or 'unknown', 'count': count} for os_name, count in os_breakdown_query]
        
        # Recent activity (last 20 events)
        recent_events = AnalyticsEvent.query.filter(
            AnalyticsEvent.timestamp >= start_time
        ).order_by(desc(AnalyticsEvent.timestamp)).limit(20).all()
        
        recent_activity = []
        for event in recent_events:
            description = f"{event.event_name}"
            if event.page_title:
                description += f" on {event.page_title}"
            recent_activity.append({
                'id': str(event.id),
                'type': event.event_type,
                'description': description,
                'timestamp': int(event.timestamp.timestamp() * 1000) if event.timestamp else int(datetime.utcnow().timestamp() * 1000)
            })
        
        # Error rate (events with error in name or type)
        error_events = AnalyticsEvent.query.filter(
            and_(
                AnalyticsEvent.timestamp >= start_time,
                or_(
                    AnalyticsEvent.event_name.ilike('%error%'),
                    AnalyticsEvent.event_type.ilike('%error%')
                )
            )
        ).count()
        
        error_rate = (error_events / total_events * 100) if total_events > 0 else 0
        
        # Conversion rate (events with conversion in name)
        conversion_events = AnalyticsEvent.query.filter(
            and_(
                AnalyticsEvent.timestamp >= start_time,
                AnalyticsEvent.event_name.ilike('%conversion%')
            )
        ).count()
        
        conversion_rate = (conversion_events / total_events * 100) if total_events > 0 else 0
        
        return jsonify({
            'totalUsers': total_users,
            'totalSessions': total_sessions,
            'totalPageViews': total_page_views,
            'totalEvents': total_events,
            'averageSessionDuration': avg_duration,
            'topPages': top_pages,
            'topEvents': top_events,
            'deviceBreakdown': device_breakdown,
            'browserBreakdown': browser_breakdown,
            'osBreakdown': os_breakdown,
            'recentActivity': recent_activity,
            'conversionRate': round(conversion_rate, 2),
            'errorRate': round(error_rate, 2)
        }), 200
        
    except Exception as e:
        print(f"Error getting analytics dashboard: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

