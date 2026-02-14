from database import db
from datetime import datetime
import secrets
import string
import bcrypt
import uuid

class User(db.Model):
    """User model for authentication and API access"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), default='user', nullable=False)  # 'user', 'admin', 'super_admin'
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime)
    
    # Subscription fields
    subscription_tier = db.Column(db.String(20), default='free', nullable=False)  # 'free', 'premium', 'enterprise', 'client'
    monthly_call_limit = db.Column(db.Integer, default=5, nullable=False)  # -1 for unlimited
    monthly_used = db.Column(db.Integer, default=0, nullable=False)
    monthly_reset_date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)  # Last reset date
    
    # Relationships
    api_keys = db.relationship('APIKey', foreign_keys='APIKey.user_id', backref='user', lazy=True, cascade='all, delete-orphan')
    usage_logs = db.relationship('UsageLog', backref='user', lazy=True)
    reset_history = db.relationship('ResetHistory', foreign_keys='ResetHistory.user_id', backref='user', lazy=True)
    
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
            'api_keys_count': len(self.api_keys),
            'subscription_tier': self.subscription_tier,
            'monthly_call_limit': self.monthly_call_limit,
            'monthly_used': self.monthly_used,
            'monthly_remaining': self.monthly_call_limit - self.monthly_used if self.monthly_call_limit != -1 else -1,
            'monthly_reset_date': self.monthly_reset_date.isoformat() if self.monthly_reset_date else None
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
    
    # Free tier fields
    is_free_tier = db.Column(db.Boolean, default=False, nullable=False)  # Special free tier key
    free_tier_type = db.Column(db.String(50))  # 'educational', 'nonprofit', 'partner', etc.
    granted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Admin who granted it
    granted_at = db.Column(db.DateTime)  # When it was granted
    notes = db.Column(db.Text)  # Optional notes about why it was granted
    
    # Relationships
    usage_logs = db.relationship('UsageLog', backref='api_key', lazy=True)
    rate_limits = db.relationship('RateLimit', backref='api_key', lazy=True)
    granted_by_user = db.relationship('User', foreign_keys=[granted_by], backref='granted_free_tier_keys')
    
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
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_free_tier': self.is_free_tier,
            'free_tier_type': self.free_tier_type,
            'granted_by': self.granted_by,
            'granted_at': self.granted_at.isoformat() if self.granted_at else None,
            'notes': self.notes
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
    is_free_tier = db.Column(db.Boolean, default=False, nullable=False)  # Track if this was a free tier request
    
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
            'error_message': self.error_message,
            'is_free_tier': self.is_free_tier
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

class ResetHistory(db.Model):
    """History of API call resets by admins"""
    __tablename__ = 'reset_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reset_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # Admin who reset
    calls_before = db.Column(db.Integer, nullable=False)  # Calls used before reset
    calls_after = db.Column(db.Integer, default=0, nullable=False)  # Calls after reset (should be 0)
    reset_reason = db.Column(db.String(500))  # Optional reason
    reset_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    reset_by_user = db.relationship('User', foreign_keys=[reset_by], backref='resets_performed')
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'reset_by': self.reset_by,
            'reset_by_email': self.reset_by_user.email if self.reset_by_user else None,
            'calls_before': self.calls_before,
            'calls_after': self.calls_after,
            'reset_reason': self.reset_reason,
            'reset_at': self.reset_at.isoformat() if self.reset_at else None
        }

class Notification(db.Model):
    """System-wide notifications for admins"""
    __tablename__ = 'notifications'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), default='info', nullable=False)  # 'info', 'warning', 'error', 'success', 'payment', 'subscription'
    category = db.Column(db.String(50), default='system', nullable=False)  # 'system', 'payment', 'subscription', 'user', 'api'
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    read_at = db.Column(db.DateTime)
    read_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Admin who read it
    notification_metadata = db.Column(db.JSON)  # Additional data (user_id, payment_id, etc.)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    read_by_user = db.relationship('User', foreign_keys=[read_by], backref='notifications_read')
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'title': self.title,
            'message': self.message,
            'type': self.type,
            'category': self.category,
            'is_read': self.is_read,
            'read_at': self.read_at.isoformat() if self.read_at else None,
            'read_by': self.read_by,
            'read_by_email': self.read_by_user.email if self.read_by_user else None,
            'metadata': self.notification_metadata,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class AnalyticsEvent(db.Model):
    """Analytics events tracking"""
    __tablename__ = 'analytics_events'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    event_type = db.Column(db.String(50), nullable=False)
    event_name = db.Column(db.String(100), nullable=False, index=True)
    properties = db.Column(db.JSON)  # Additional event properties
    session_id = db.Column(db.String(100), nullable=False, index=True)
    page_url = db.Column(db.Text, nullable=False)
    page_title = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    user_agent = db.Column(db.Text)
    device_type = db.Column(db.String(20))  # desktop, mobile, tablet
    browser = db.Column(db.String(50))
    os = db.Column(db.String(50))
    referrer = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = db.relationship('User', backref='analytics_events')
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'event_type': self.event_type,
            'event_name': self.event_name,
            'properties': self.properties,
            'session_id': self.session_id,
            'page_url': self.page_url,
            'page_title': self.page_title,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'user_agent': self.user_agent,
            'device_type': self.device_type,
            'browser': self.browser,
            'os': self.os,
            'referrer': self.referrer,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class PageView(db.Model):
    """Page views tracking"""
    __tablename__ = 'page_views'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    session_id = db.Column(db.String(100), nullable=False, index=True)
    page_url = db.Column(db.Text, nullable=False, index=True)
    page_title = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    duration = db.Column(db.Integer)  # Duration in seconds
    referrer = db.Column(db.Text)
    user_agent = db.Column(db.Text)
    device_type = db.Column(db.String(20))
    browser = db.Column(db.String(50))
    os = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = db.relationship('User', backref='page_views')
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'page_url': self.page_url,
            'page_title': self.page_title,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'duration': self.duration,
            'referrer': self.referrer,
            'user_agent': self.user_agent,
            'device_type': self.device_type,
            'browser': self.browser,
            'os': self.os,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class UserSession(db.Model):
    """User sessions tracking"""
    __tablename__ = 'user_sessions'
    
    id = db.Column(db.String(100), primary_key=True)  # session_id
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    start_time = db.Column(db.DateTime, nullable=False, index=True)
    last_activity = db.Column(db.DateTime, nullable=False)
    page_views = db.Column(db.Integer, default=0)
    events = db.Column(db.Integer, default=0)
    device_type = db.Column(db.String(20))
    browser = db.Column(db.String(50))
    os = db.Column(db.String(50))
    country = db.Column(db.String(50))
    city = db.Column(db.String(50))
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.Text)
    referrer = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = db.relationship('User', backref='user_sessions')
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'last_activity': self.last_activity.isoformat() if self.last_activity else None,
            'page_views': self.page_views,
            'events': self.events,
            'device_type': self.device_type,
            'browser': self.browser,
            'os': self.os,
            'country': self.country,
            'city': self.city,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'referrer': self.referrer,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Campaign(db.Model):
    """Contact automation campaign - Public, no user required"""
    __tablename__ = 'campaigns'
    
    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(20), unique=True, nullable=False, index=True, default=lambda: secrets.token_urlsafe(8)[:8])
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)  # Optional - for public campaigns
    session_id = db.Column(db.String(100), nullable=True, index=True)  # For guest users - browser session identifier
    name = db.Column(db.String(200), nullable=False)
    message_template = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='draft', nullable=False)  # draft, queued, processing, completed, paused, failed
    spreadsheet_filename = db.Column(db.String(500))
    spreadsheet_path = db.Column(db.String(500))  # Stored in Supabase Storage
    
    # Statistics
    total_companies = db.Column(db.Integer, default=0, nullable=False)
    processed_count = db.Column(db.Integer, default=0, nullable=False)
    success_count = db.Column(db.Integer, default=0, nullable=False)
    failed_count = db.Column(db.Integer, default=0, nullable=False)
    captcha_count = db.Column(db.Integer, default=0, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    last_heartbeat_at = db.Column(db.DateTime)
    
    # Relationships
    user = db.relationship('User', backref='campaigns')
    companies = db.relationship('Company', backref='campaign', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self, include_companies=False):
        """Convert to dictionary for JSON serialization"""
        data = {
            'id': self.id,
            'public_id': self.public_id,
            'user_id': self.user_id,
            'name': self.name,
            'message_template': self.message_template,
            'status': self.status,
            'spreadsheet_filename': self.spreadsheet_filename,
            'total_companies': self.total_companies,
            'processed_count': self.processed_count,
            'success_count': self.success_count,
            'failed_count': self.failed_count,
            'captcha_count': self.captcha_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'last_heartbeat_at': self.last_heartbeat_at.isoformat() if self.last_heartbeat_at else None,
            'progress_percentage': round((self.processed_count / self.total_companies * 100) if self.total_companies > 0 else 0, 2)
        }
        if include_companies:
            data['companies'] = [company.to_dict() for company in self.companies]
        return data

class Company(db.Model):
    """Company in a campaign"""
    __tablename__ = 'companies'
    
    id = db.Column(db.Integer, primary_key=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'), nullable=False, index=True)
    company_name = db.Column(db.String(300), nullable=False)
    website_url = db.Column(db.String(500), nullable=False)
    contact_email = db.Column(db.String(200))  # Optional from spreadsheet
    contact_person = db.Column(db.String(200))  # Optional from spreadsheet
    phone = db.Column(db.String(50))  # Optional from spreadsheet
    additional_data = db.Column(db.JSON)  # Any other columns from spreadsheet
    
    # Processing status
    status = db.Column(db.String(20), default='pending', nullable=False, index=True)  # pending, processing, success, failed, captcha, skipped
    error_message = db.Column(db.Text)
    
    # Contact page detection
    contact_page_url = db.Column(db.String(500))
    contact_page_found = db.Column(db.Boolean, default=False)
    form_found = db.Column(db.Boolean, default=False)
    
    # Submission details
    submitted_at = db.Column(db.DateTime)
    screenshot_url = db.Column(db.String(500))  # Screenshot stored in Supabase Storage
    contact_method = db.Column(db.String(100))
    emails_found = db.Column(db.JSON)
    emails_sent = db.Column(db.JSON)
    email_sent_at = db.Column(db.DateTime)
    form_structure = db.Column(db.JSON)
    field_mappings = db.Column(db.JSON)
    form_complexity = db.Column(db.String(50))
    pattern_learned = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    processed_at = db.Column(db.DateTime)
    
    # Relationships
    submission_logs = db.relationship('SubmissionLog', backref='company', lazy=True, cascade='all, delete-orphan')
    
    def to_dict(self, include_logs=False):
        """Convert to dictionary for JSON serialization"""
        data = {
            'id': self.id,
            'campaign_id': self.campaign_id,
            'company_name': self.company_name,
            'website_url': self.website_url,
            'contact_email': self.contact_email,
            'contact_person': self.contact_person,
            'phone': self.phone,
            'additional_data': self.additional_data,
            'status': self.status,
            'error_message': self.error_message,
            'contact_page_url': self.contact_page_url,
            'contact_page_found': self.contact_page_found,
            'form_found': self.form_found,
            'submitted_at': self.submitted_at.isoformat() if self.submitted_at else None,
            'screenshot_url': self.screenshot_url,
            'contact_method': self.contact_method,
            'emails_found': self.emails_found,
            'emails_sent': self.emails_sent,
            'email_sent_at': self.email_sent_at.isoformat() if self.email_sent_at else None,
            'form_structure': self.form_structure,
            'field_mappings': self.field_mappings,
            'form_complexity': self.form_complexity,
            'pattern_learned': self.pattern_learned,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None
        }
        if include_logs:
            data['logs'] = [log.to_dict() for log in self.submission_logs]
        return data

class SubmissionLog(db.Model):
    """Detailed log of each submission attempt"""
    __tablename__ = 'submission_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    
    # Attempt details
    attempt_number = db.Column(db.Integer, default=1, nullable=False)
    action = db.Column(db.String(100), nullable=False)  # 'visited_homepage', 'found_contact_page', 'detected_form', 'filled_form', 'submitted_form', 'captcha_detected', 'error'
    status = db.Column(db.String(20), nullable=False)  # 'success', 'failed', 'warning'
    message = db.Column(db.Text)
    details = db.Column(db.JSON)  # Additional technical details
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'company_id': self.company_id,
            'attempt_number': self.attempt_number,
            'action': self.action,
            'status': self.status,
            'message': self.message,
            'details': self.details,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class ScrapingRule(db.Model):
    """Custom scraping rules for specific domains or global"""
    __tablename__ = 'scraping_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)  # NULL for global rules
    
    # Rule definition
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    domain = db.Column(db.String(500))  # NULL for global rules, specific domain otherwise
    rule_type = db.Column(db.String(50), nullable=False)  # 'cookie', 'contact_page', 'form_field', 'submit_button', 'captcha'
    
    # Matching criteria
    selector = db.Column(db.String(500))  # CSS selector
    xpath = db.Column(db.String(500))  # XPath selector
    text_pattern = db.Column(db.String(500))  # Text regex pattern
    url_pattern = db.Column(db.String(500))  # URL pattern
    
    # Action
    action = db.Column(db.String(50), nullable=False)  # 'click', 'fill', 'wait', 'navigate'
    action_value = db.Column(db.String(500))  # Value to fill or wait time
    
    # Priority and conditions
    priority = db.Column(db.Integer, default=100, nullable=False)  # Lower = higher priority
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    language = db.Column(db.String(10))  # ISO code, NULL for all languages
    
    # Metadata
    success_count = db.Column(db.Integer, default=0, nullable=False)
    failure_count = db.Column(db.Integer, default=0, nullable=False)
    last_used_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    user = db.relationship('User', backref='scraping_rules')
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'description': self.description,
            'domain': self.domain,
            'rule_type': self.rule_type,
            'selector': self.selector,
            'xpath': self.xpath,
            'text_pattern': self.text_pattern,
            'url_pattern': self.url_pattern,
            'action': self.action,
            'action_value': self.action_value,
            'priority': self.priority,
            'enabled': self.enabled,
            'language': self.language,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

class ScrapingSession(db.Model):
    """Live scraping session for monitoring"""
    __tablename__ = 'scraping_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    campaign_id = db.Column(db.Integer, db.ForeignKey('campaigns.id'), nullable=False, index=True)
    
    # Session state
    status = db.Column(db.String(20), default='active', nullable=False)  # 'active', 'completed', 'failed', 'stopped'
    current_step = db.Column(db.String(200))
    progress_percentage = db.Column(db.Integer, default=0, nullable=False)
    
    # Detected information
    detected_language = db.Column(db.String(10))
    contact_page_url = db.Column(db.String(500))
    contact_page_found = db.Column(db.Boolean, default=False)
    cookie_modal_handled = db.Column(db.Boolean, default=False)
    captcha_detected = db.Column(db.Boolean, default=False)
    form_found = db.Column(db.Boolean, default=False)
    
    # Live monitoring data
    current_url = db.Column(db.String(500))
    current_screenshot_url = db.Column(db.String(500))
    video_recording_url = db.Column(db.String(500))
    
    # Timestamps
    started_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    completed_at = db.Column(db.DateTime)
    last_update_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    company = db.relationship('Company', backref='scraping_sessions')
    campaign = db.relationship('Campaign', backref='scraping_sessions')
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'company_id': self.company_id,
            'campaign_id': self.campaign_id,
            'status': self.status,
            'current_step': self.current_step,
            'progress_percentage': self.progress_percentage,
            'detected_language': self.detected_language,
            'contact_page_url': self.contact_page_url,
            'contact_page_found': self.contact_page_found,
            'cookie_modal_handled': self.cookie_modal_handled,
            'captcha_detected': self.captcha_detected,
            'form_found': self.form_found,
            'current_url': self.current_url,
            'current_screenshot_url': self.current_screenshot_url,
            'video_recording_url': self.video_recording_url,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'last_update_at': self.last_update_at.isoformat() if self.last_update_at else None,
        }

class SystemSetting(db.Model):
    """Global system settings and state"""
    __tablename__ = 'system_settings'
    
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)
    description = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @staticmethod
    def get(key, default=None):
        setting = SystemSetting.query.get(key)
        return setting.value if setting else default

    @staticmethod
    def set(key, value, description=None):
        setting = SystemSetting.query.get(key)
        if setting:
            setting.value = str(value)
            if description:
                setting.description = description
        else:
            setting = SystemSetting(key=key, value=str(value), description=description)
            db.session.add(setting)
        db.session.commit()
        return value
