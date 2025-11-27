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

def get_location_from_ip(ip_address):
    """Get detailed location from IP address using free IP geolocation API"""
    if not ip_address or ip_address == 'unknown' or ip_address.startswith('127.') or ip_address.startswith('::1'):
        return None, None, None, None
    
    try:
        import requests
        # Use ip-api.com (free, no API key required, 45 requests/minute limit)
        # Get more fields: country, city, regionName (state/province), timezone
        response = requests.get(f'http://ip-api.com/json/{ip_address}?fields=status,country,countryCode,city,regionName,timezone,lat,lon', timeout=3)
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                country = data.get('country')
                city = data.get('city')
                region = data.get('regionName')  # State/Province
                timezone = data.get('timezone')
                # Format: "City, Region, Country" for better precision
                return country, city, region, timezone
    except Exception as e:
        print(f"Error getting location from IP {ip_address}: {e}")
    
    return None, None, None, None

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
        
        # Get IP address from request or data
        ip_address = data.get('ip_address') or request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or request.remote_addr
        
        # Resolve location from IP if not provided
        country = data.get('country')
        city = data.get('city')
        region = data.get('region')  # State/Province
        if not country or not city:
            resolved_country, resolved_city, resolved_region, timezone = get_location_from_ip(ip_address)
            country = country or resolved_country
            city = city or resolved_city
            region = region or resolved_region
            # Store region in city field if we have it for better precision
            if city and region and region not in city:
                city = f"{city}, {region}"
        
        # Check if session exists
        existing_session = UserSession.query.get(session_id)
        
        if existing_session:
            # Update existing session
            existing_session.last_activity = datetime.fromisoformat(data.get('last_activity', datetime.utcnow().isoformat()).replace('Z', '+00:00')) if isinstance(data.get('last_activity'), str) else datetime.utcnow()
            existing_session.page_views = data.get('page_views', existing_session.page_views)
            existing_session.events = data.get('events', existing_session.events)
            existing_session.is_active = data.get('is_active', True)
            # Update location if not set
            if not existing_session.country and country:
                existing_session.country = country
            if not existing_session.city and city:
                existing_session.city = city
            if not existing_session.ip_address and ip_address:
                existing_session.ip_address = ip_address
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
                country=country,
                city=city,
                ip_address=ip_address,
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

@analytics_api.route('/events/list', methods=['GET'])
@require_admin
def get_events_list():
    """Get paginated list of all events with full details"""
    try:
        range_param = request.args.get('range', '24h')
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 50))
        event_type = request.args.get('event_type')  # Filter by event type
        
        # Calculate time range
        now = datetime.utcnow()
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
        
        # Build query
        query = AnalyticsEvent.query.filter(
            AnalyticsEvent.timestamp >= start_time
        )
        
        # Filter by event type if specified
        if event_type:
            query = query.filter(AnalyticsEvent.event_name == event_type)
        
        # Get total count
        total_count = query.count()
        
        # Get paginated events
        events = query.order_by(desc(AnalyticsEvent.timestamp)).offset(
            (page - 1) * per_page
        ).limit(per_page).all()
        
        # Format events with full details
        events_list = []
        for event in events:
            properties = event.properties or {}
            
            # Get page path from URL
            page_path = ""
            if event.page_url:
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(event.page_url)
                    page_path = parsed.path or "/"
                except:
                    page_path = event.page_url[:50]
            
            events_list.append({
                'id': str(event.id),
                'event_name': event.event_name,
                'event_type': event.event_type,
                'page_url': event.page_url,
                'page_path': page_path,
                'page_title': event.page_title,
                'properties': properties,
                'device_type': event.device_type,
                'browser': event.browser,
                'os': event.os,
                'timestamp': event.timestamp.isoformat() if event.timestamp else None,
                'timestamp_ms': int(event.timestamp.timestamp() * 1000) if event.timestamp else None,
                'user_id': event.user_id,
                'session_id': event.session_id,
            })
        
        # Get unique event types for filtering
        event_types = db.session.query(
            AnalyticsEvent.event_name,
            func.count(AnalyticsEvent.id).label('count')
        ).filter(
            AnalyticsEvent.timestamp >= start_time
        ).group_by(AnalyticsEvent.event_name).order_by(desc('count')).all()
        
        return jsonify({
            'events': events_list,
            'total': total_count,
            'page': page,
            'per_page': per_page,
            'total_pages': (total_count + per_page - 1) // per_page,
            'event_types': [{'name': name, 'count': count} for name, count in event_types],
            'time_range': range_param,
            'start_time': start_time.isoformat(),
        }), 200
        
    except Exception as e:
        print(f"Error getting events list: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

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
        
        # Country/Region breakdown
        country_breakdown_query = db.session.query(
            UserSession.country,
            func.count(func.distinct(UserSession.id)).label('count')
        ).filter(
            and_(
                UserSession.start_time >= start_time,
                UserSession.country.isnot(None)
            )
        ).group_by(UserSession.country).order_by(desc('count')).limit(20).all()
        
        country_breakdown = [{'country': country or 'Unknown', 'count': count} for country, count in country_breakdown_query]
        
        # City breakdown (top cities)
        city_breakdown_query = db.session.query(
            UserSession.city,
            UserSession.country,
            func.count(func.distinct(UserSession.id)).label('count')
        ).filter(
            and_(
                UserSession.start_time >= start_time,
                UserSession.city.isnot(None)
            )
        ).group_by(UserSession.city, UserSession.country).order_by(desc('count')).limit(20).all()
        
        city_breakdown = [{'city': city or 'Unknown', 'country': country or 'Unknown', 'count': count} for city, country, count in city_breakdown_query]
        
        # Recent activity (last 100 events) with detailed descriptions
        recent_events = AnalyticsEvent.query.filter(
            AnalyticsEvent.timestamp >= start_time
        ).order_by(desc(AnalyticsEvent.timestamp)).limit(100).all()
        
        recent_activity = []
        for event in recent_events:
            properties = event.properties or {}
            description = ""
            details = []
            
            # Build detailed description based on event type
            if event.event_name == "api_call":
                url = properties.get('url', '')
                method = properties.get('method', 'GET')
                status = properties.get('status', '')
                # Extract endpoint from URL
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    endpoint = parsed.path
                    if endpoint.startswith('/api/'):
                        endpoint = endpoint.replace('/api/', '')
                    description = f"API Call: {method} {endpoint}"
                    if status:
                        description += f" ({status})"
                except:
                    description = f"API Call: {method} {url[:50]}"
                    if status:
                        description += f" ({status})"
                if properties.get('duration'):
                    details.append(f"Duration: {properties.get('duration')}ms")
                    
            elif event.event_name == "page_load" or event.event_name == "pageview":
                page_url = event.page_url or properties.get('page', '')
                page_title = event.page_title or properties.get('title', '')
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(page_url)
                    path = parsed.path or "/"
                    description = f"Page Load: {path}"
                    if page_title:
                        details.append(f"Title: {page_title}")
                except:
                    description = f"Page Load: {page_url[:50]}"
                    
            elif event.event_name == "navigation_click" or event.event_name == "click":
                element = properties.get('element', '')
                location = properties.get('location', '')
                from_page = properties.get('from', '')
                to_page = properties.get('to', '')
                if from_page and to_page:
                    try:
                        from urllib.parse import urlparse
                        from_path = urlparse(from_page).path if from_page else ""
                        to_path = urlparse(to_page).path if to_page else ""
                        description = f"Navigation: {from_path} → {to_path}"
                    except:
                        description = f"Navigation: {from_page} → {to_page}"
                elif element:
                    description = f"Click: {element}"
                    if location:
                        details.append(f"Location: {location}")
                else:
                    description = f"Click on {event.page_url or 'page'}"
                    
            elif event.event_name == "user_interaction":
                interaction_type = properties.get('type', '')
                element = properties.get('element', '')
                if interaction_type and element:
                    description = f"Interaction: {interaction_type} on {element}"
                elif element:
                    description = f"Interaction: {element}"
                else:
                    description = f"User Interaction: {interaction_type or 'unknown'}"
                if properties.get('value'):
                    details.append(f"Value: {properties.get('value')}")
                    
            elif event.event_name == "api_error":
                url = properties.get('url', '')
                error = properties.get('error', 'Unknown error')
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    endpoint = parsed.path
                    description = f"API Error: {endpoint}"
                except:
                    description = f"API Error: {url[:50]}"
                details.append(f"Error: {error[:100]}")
                
            else:
                # Generic event - use event name and extract key properties
                description = event.event_name.replace('_', ' ').title()
                if properties:
                    # Add relevant properties as details
                    for key in ['url', 'method', 'element', 'location', 'from', 'to', 'page']:
                        if key in properties and properties[key]:
                            details.append(f"{key.title()}: {str(properties[key])[:50]}")
            
            # Add page context if available
            if event.page_url and event.event_name not in ["page_load", "pageview"]:
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(event.page_url)
                    page_path = parsed.path or "/"
                    if page_path not in description:
                        details.append(f"Page: {page_path}")
                except:
                    pass
            
            # Build final description with details
            if details:
                description += " • " + " • ".join(details[:3])  # Limit to 3 details
            
            recent_activity.append({
                'id': str(event.id),
                'type': event.event_type,
                'description': description,
                'event_name': event.event_name,
                'properties': properties,
                'page_url': event.page_url,
                'page_title': event.page_title,
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
            'countryBreakdown': country_breakdown,
            'cityBreakdown': city_breakdown,
            'recentActivity': recent_activity,
            'conversionRate': round(conversion_rate, 2),
            'errorRate': round(error_rate, 2)
        }), 200
        
    except Exception as e:
        print(f"Error getting analytics dashboard: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

