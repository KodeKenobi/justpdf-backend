import psutil
import time
import logging
from datetime import datetime, timedelta
from flask import jsonify
from models import UsageLog, Job, db
from database import db as database
from sqlalchemy import func, desc

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_system_health():
    """Get system health metrics"""
    try:
        # CPU usage
        cpu_percent = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_available = memory.available / (1024**3)  # GB
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        disk_free = disk.free / (1024**3)  # GB
        
        # Database health
        db_healthy = True
        try:
            database.session.execute('SELECT 1')
        except Exception as e:
            db_healthy = False
            logger.error(f"Database health check failed: {e}")

        # Recent error rate
        last_hour = datetime.utcnow() - timedelta(hours=1)
        recent_calls = UsageLog.query.filter(UsageLog.timestamp >= last_hour).count()
        recent_errors = UsageLog.query.filter(
            UsageLog.timestamp >= last_hour,
            UsageLog.status_code >= 400
        ).count()
        
        error_rate = (recent_errors / recent_calls * 100) if recent_calls > 0 else 0

        # Active jobs
        active_jobs = Job.query.filter(Job.status == 'processing').count()
        
        # Queue length (if using Redis)
        queue_length = 0
        try:
            import redis
            redis_client = redis.from_url('redis://localhost:6379/0')
            queue_length = redis_client.llen('celery')
        except:
            pass

        return {
            'status': 'healthy' if all([
                cpu_percent < 80,
                memory_percent < 80,
                disk_percent < 90,
                db_healthy,
                error_rate < 10
            ]) else 'unhealthy',
            'timestamp': datetime.utcnow().isoformat(),
            'metrics': {
                'cpu_percent': round(cpu_percent, 2),
                'memory_percent': round(memory_percent, 2),
                'memory_available_gb': round(memory_available, 2),
                'disk_percent': round(disk_percent, 2),
                'disk_free_gb': round(disk_free, 2),
                'database_healthy': db_healthy,
                'recent_calls': recent_calls,
                'recent_errors': recent_errors,
                'error_rate': round(error_rate, 2),
                'active_jobs': active_jobs,
                'queue_length': queue_length
            }
        }

    except Exception as e:
        logger.error(f"Error getting system health: {e}")
        return {
            'status': 'error',
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e)
        }

def get_performance_metrics(hours=24):
    """Get performance metrics for the last N hours"""
    try:
        start_time = datetime.utcnow() - timedelta(hours=hours)
        
        # Total requests
        total_requests = UsageLog.query.filter(UsageLog.timestamp >= start_time).count()
        
        # Success rate
        successful_requests = UsageLog.query.filter(
            UsageLog.timestamp >= start_time,
            UsageLog.status_code.between(200, 299)
        ).count()
        
        success_rate = (successful_requests / total_requests * 100) if total_requests > 0 else 0
        
        # Average response time
        avg_response_time = database.session.query(
            func.avg(UsageLog.processing_time)
        ).filter(
            UsageLog.timestamp >= start_time,
            UsageLog.processing_time.isnot(None)
        ).scalar() or 0
        
        # Requests by hour
        hourly_requests = database.session.query(
            func.date_trunc('hour', UsageLog.timestamp).label('hour'),
            func.count(UsageLog.id).label('count')
        ).filter(
            UsageLog.timestamp >= start_time
        ).group_by(
            func.date_trunc('hour', UsageLog.timestamp)
        ).order_by('hour').all()
        
        # Top endpoints
        top_endpoints = database.session.query(
            UsageLog.endpoint,
            func.count(UsageLog.id).label('count')
        ).filter(
            UsageLog.timestamp >= start_time
        ).group_by(
            UsageLog.endpoint
        ).order_by(
            func.count(UsageLog.id).desc()
        ).limit(10).all()
        
        # Error breakdown
        error_breakdown = database.session.query(
            UsageLog.status_code,
            func.count(UsageLog.id).label('count')
        ).filter(
            UsageLog.timestamp >= start_time,
            UsageLog.status_code >= 400
        ).group_by(
            UsageLog.status_code
        ).order_by(
            func.count(UsageLog.id).desc()
        ).all()
        
        return {
            'period_hours': hours,
            'total_requests': total_requests,
            'success_rate': round(success_rate, 2),
            'average_response_time': round(avg_response_time, 2),
            'hourly_requests': [
                {'hour': str(hour), 'count': count} 
                for hour, count in hourly_requests
            ],
            'top_endpoints': [
                {'endpoint': endpoint, 'count': count} 
                for endpoint, count in top_endpoints
            ],
            'error_breakdown': [
                {'status_code': status_code, 'count': count} 
                for status_code, count in error_breakdown
            ]
        }

    except Exception as e:
        logger.error(f"Error getting performance metrics: {e}")
        return {
            'error': str(e),
            'period_hours': hours
        }

def get_user_metrics():
    """Get user-related metrics"""
    try:
        # Total users
        from models import User
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        
        # New users in last 30 days
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        new_users = User.query.filter(User.created_at >= thirty_days_ago).count()
        
        # Users by role
        from models import User
        users_by_role = database.session.query(
            User.role,
            func.count(User.id).label('count')
        ).group_by(User.role).all()
        
        # API key usage
        from models import APIKey
        total_api_keys = APIKey.query.count()
        active_api_keys = APIKey.query.filter_by(is_active=True).count()
        
        return {
            'total_users': total_users,
            'active_users': active_users,
            'new_users_30_days': new_users,
            'users_by_role': [
                {'role': role, 'count': count} 
                for role, count in users_by_role
            ],
            'total_api_keys': total_api_keys,
            'active_api_keys': active_api_keys
        }

    except Exception as e:
        logger.error(f"Error getting user metrics: {e}")
        return {'error': str(e)}

def get_job_metrics():
    """Get job processing metrics"""
    try:
        # Job status distribution
        job_status = database.session.query(
            Job.status,
            func.count(Job.id).label('count')
        ).group_by(Job.status).all()
        
        # Average processing time by endpoint
        avg_processing_time = database.session.query(
            Job.endpoint,
            func.avg(Job.processing_time).label('avg_time')
        ).filter(
            Job.processing_time.isnot(None)
        ).group_by(Job.endpoint).all()
        
        # Jobs by day (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        jobs_by_day = database.session.query(
            func.date(Job.created_at).label('date'),
            func.count(Job.id).label('count')
        ).filter(
            Job.created_at >= thirty_days_ago
        ).group_by(
            func.date(Job.created_at)
        ).order_by('date').all()
        
        return {
            'job_status': [
                {'status': status, 'count': count} 
                for status, count in job_status
            ],
            'avg_processing_time': [
                {'endpoint': endpoint, 'avg_time': round(avg_time, 2)} 
                for endpoint, avg_time in avg_processing_time
            ],
            'jobs_by_day': [
                {'date': str(date), 'count': count} 
                for date, count in jobs_by_day
            ]
        }

    except Exception as e:
        logger.error(f"Error getting job metrics: {e}")
        return {'error': str(e)}

def check_alerts():
    """Check for alert conditions"""
    alerts = []
    
    try:
        health = get_system_health()
        
        # CPU alert
        if health['metrics']['cpu_percent'] > 80:
            alerts.append({
                'type': 'cpu',
                'severity': 'warning',
                'message': f"High CPU usage: {health['metrics']['cpu_percent']}%"
            })
        
        # Memory alert
        if health['metrics']['memory_percent'] > 80:
            alerts.append({
                'type': 'memory',
                'severity': 'warning',
                'message': f"High memory usage: {health['metrics']['memory_percent']}%"
            })
        
        # Disk alert
        if health['metrics']['disk_percent'] > 90:
            alerts.append({
                'type': 'disk',
                'severity': 'critical',
                'message': f"Low disk space: {health['metrics']['disk_percent']}% used"
            })
        
        # Error rate alert
        if health['metrics']['error_rate'] > 10:
            alerts.append({
                'type': 'error_rate',
                'severity': 'warning',
                'message': f"High error rate: {health['metrics']['error_rate']}%"
            })
        
        # Database alert
        if not health['metrics']['database_healthy']:
            alerts.append({
                'type': 'database',
                'severity': 'critical',
                'message': "Database connection failed"
            })
        
        return alerts

    except Exception as e:
        logger.error(f"Error checking alerts: {e}")
        return [{
            'type': 'system',
            'severity': 'critical',
            'message': f"Alert system error: {str(e)}"
        }]

def get_dashboard_metrics():
    """Get comprehensive dashboard metrics"""
    try:
        return {
            'health': get_system_health(),
            'performance': get_performance_metrics(24),
            'users': get_user_metrics(),
            'jobs': get_job_metrics(),
            'alerts': check_alerts(),
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting dashboard metrics: {e}")
        return {
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }
