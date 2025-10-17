from database import db
from datetime import datetime
import secrets
import string
import bcrypt

class User(db.Model):
    """User model for authentication and API access"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default='user', nullable=False)  # 'user', 'admin'
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime)
    
    # Relationships
    api_keys = db.relationship('APIKey', backref='user', lazy=True, cascade='all, delete-orphan')
    usage_logs = db.relationship('UsageLog', backref='user', lazy=True)
    
    def set_password(self, password):
        """Hash and set password"""
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def check_password(self, password):
        """Check password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'email': self.email,
            'role': self.role,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'api_keys_count': len(self.api_keys)
        }

class APIKey(db.Model):
    """API Key model for authentication"""
    __tablename__ = 'api_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)  # User-friendly name
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    rate_limit = db.Column(db.Integer, default=1000, nullable=False)  # Requests per hour
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_used = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)  # Optional expiration
    
    # Relationships
    usage_logs = db.relationship('UsageLog', backref='api_key', lazy=True)
    rate_limits = db.relationship('RateLimit', backref='api_key', lazy=True)
    
    @staticmethod
    def generate_key():
        """Generate a secure API key"""
        # Generate 32 random bytes and encode as base64
        return secrets.token_urlsafe(32)
    
    def to_dict(self, include_key=False):
        """Convert to dictionary for JSON serialization"""
        data = {
            'id': self.id,
            'name': self.name,
            'user_id': self.user_id,
            'is_active': self.is_active,
            'rate_limit': self.rate_limit,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None
        }
        if include_key:
            data['key'] = self.key
        return data

class UsageLog(db.Model):
    """Usage log for tracking API calls"""
    __tablename__ = 'usage_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    api_key_id = db.Column(db.Integer, db.ForeignKey('api_keys.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    endpoint = db.Column(db.String(200), nullable=False)
    method = db.Column(db.String(10), nullable=False)
    status_code = db.Column(db.Integer, nullable=False)
    file_size = db.Column(db.BigInteger)  # Size of uploaded file in bytes
    processing_time = db.Column(db.Float)  # Processing time in seconds
    ip_address = db.Column(db.String(45))  # IPv4 or IPv6
    user_agent = db.Column(db.String(500))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    error_message = db.Column(db.Text)  # Error details if any
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'api_key_id': self.api_key_id,
            'user_id': self.user_id,
            'endpoint': self.endpoint,
            'method': self.method,
            'status_code': self.status_code,
            'file_size': self.file_size,
            'processing_time': self.processing_time,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'error_message': self.error_message
        }

class RateLimit(db.Model):
    """Rate limiting tracking"""
    __tablename__ = 'rate_limits'
    
    id = db.Column(db.Integer, primary_key=True)
    api_key_id = db.Column(db.Integer, db.ForeignKey('api_keys.id'), nullable=False)
    requests_count = db.Column(db.Integer, default=0, nullable=False)
    window_start = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    window_duration = db.Column(db.Integer, default=3600, nullable=False)  # Seconds (1 hour)
    
    def is_exceeded(self):
        """Check if rate limit is exceeded"""
        return self.requests_count >= self.api_key.rate_limit
    
    def reset_window(self):
        """Reset the rate limit window"""
        self.requests_count = 0
        self.window_start = datetime.utcnow()
    
    def increment(self):
        """Increment request count"""
        self.requests_count += 1

class Job(db.Model):
    """Job tracking for async processing"""
    __tablename__ = 'jobs'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    api_key_id = db.Column(db.Integer, db.ForeignKey('api_keys.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    endpoint = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='pending', nullable=False)  # pending, processing, completed, failed
    input_file_path = db.Column(db.String(500))
    output_file_path = db.Column(db.String(500))
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    processing_time = db.Column(db.Float)
    
    # Relationships
    api_key = db.relationship('APIKey', backref='jobs')
    user = db.relationship('User', backref='jobs')
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'job_id': self.job_id,
            'status': self.status,
            'endpoint': self.endpoint,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'processing_time': self.processing_time,
            'error_message': self.error_message,
            'download_url': f'/api/v1/jobs/{self.job_id}/download' if self.status == 'completed' and self.output_file_path else None
        }

class Webhook(db.Model):
    """Webhook configuration for job notifications"""
    __tablename__ = 'webhooks'
    
    id = db.Column(db.Integer, primary_key=True)
    api_key_id = db.Column(db.Integer, db.ForeignKey('api_keys.id'), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    events = db.Column(db.JSON)  # List of events to trigger webhook
    secret = db.Column(db.String(64))  # Webhook secret for verification
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_triggered = db.Column(db.DateTime)
    failure_count = db.Column(db.Integer, default=0, nullable=False)
    
    # Relationships
    api_key = db.relationship('APIKey', backref='webhooks')
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'url': self.url,
            'events': self.events,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_triggered': self.last_triggered.isoformat() if self.last_triggered else None,
            'failure_count': self.failure_count
        }
