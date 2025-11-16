from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os

db = SQLAlchemy()
migrate = Migrate()

def init_db(app):
    """Initialize database with the Flask app"""
    # Database configuration
    database_url = os.getenv('DATABASE_URL', 'sqlite:///trevnoctilla_api.db')
    
    # Handle PostgreSQL URL format for SQLAlchemy
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    
    # Create tables (with timeout protection for Railway)
    with app.app_context():
        try:
            # First, check if users table exists and migrate if needed
            from sqlalchemy import inspect, text
            import signal
            
            # Set a timeout for database operations (30 seconds)
            def timeout_handler(signum, frame):
                raise TimeoutError("Database initialization timed out")
            
            # Only set timeout on Unix systems (not available on Windows)
            if hasattr(signal, 'SIGALRM'):
                signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(30)  # 30 second timeout
            
            try:
                inspector = inspect(db.engine)
                
                # Check if users table exists
                tables = inspector.get_table_names()
                
                # Create missing tables (notifications, analytics tables, etc.)
                missing_tables = []
                required_tables = ['notifications', 'analytics_events', 'page_views', 'user_sessions']
                
                for table_name in required_tables:
                    if table_name not in tables:
                        missing_tables.append(table_name)
                
                if missing_tables:
                    print(f"📦 Creating missing tables: {', '.join(missing_tables)}...")
                    # Ensure all models are imported before creating tables
                    try:
                        from models import Notification, AnalyticsEvent, PageView, UserSession
                        db.create_all()  # This will create all missing tables
                        print(f"✅ Created missing tables: {', '.join(missing_tables)}")
                    except Exception as e:
                        print(f"⚠️ Warning: Could not create missing tables: {e}")
                        import traceback
                        traceback.print_exc()
                        # Continue anyway - tables might be created later
            finally:
                # Cancel alarm if it was set
                if hasattr(signal, 'SIGALRM'):
                    signal.alarm(0)
            
            if 'users' in tables:
                # Table exists - check and add missing columns
                print("🔄 Checking for missing columns...")
                columns = [col['name'] for col in inspector.get_columns('users')]
                
                if 'subscription_tier' not in columns:
                    print("🔄 Migrating: Adding subscription_tier column...")
                    db.session.execute(text("ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(20) DEFAULT 'free'"))
                    db.session.commit()
                    print("✅ Added subscription_tier")
                
                if 'monthly_call_limit' not in columns:
                    print("🔄 Migrating: Adding monthly_call_limit column...")
                    db.session.execute(text("ALTER TABLE users ADD COLUMN monthly_call_limit INTEGER DEFAULT 5"))
                    db.session.commit()
                    print("✅ Added monthly_call_limit")
                
                if 'monthly_used' not in columns:
                    print("🔄 Migrating: Adding monthly_used column...")
                    db.session.execute(text("ALTER TABLE users ADD COLUMN monthly_used INTEGER DEFAULT 0"))
                    db.session.commit()
                    print("✅ Added monthly_used")
                
                if 'monthly_reset_date' not in columns:
                    print("🔄 Migrating: Adding monthly_reset_date column...")
                    # SQLite doesn't allow CURRENT_TIMESTAMP in ALTER TABLE, so add without default then update
                    db.session.execute(text("ALTER TABLE users ADD COLUMN monthly_reset_date DATETIME"))
                    # Update existing rows with current timestamp
                    from datetime import datetime
                    db.session.execute(text("UPDATE users SET monthly_reset_date = :now WHERE monthly_reset_date IS NULL"), {"now": datetime.utcnow()})
                    db.session.commit()
                    print("✅ Added monthly_reset_date")
            else:
                # Table doesn't exist - create all tables
                print("📦 Creating database tables...")
                db.create_all()
                print("✅ Database tables created successfully")
            
            # Ensure super admin users exist and have correct role
            from models import User
            super_admin_emails = [
                'admin@trevnoctilla.com',
                'admin@gmail.com',
                'kodekenobi@gmail.com'
            ]
            
            for email in super_admin_emails:
                user = User.query.filter_by(email=email).first()
                if not user:
                    # Create new super admin user
                    user = User(
                        email=email,
                        role='super_admin',
                        is_active=True
                    )
                    # Set default password only for admin@trevnoctilla.com
                    if email == 'admin@trevnoctilla.com':
                        user.set_password('admin123')  # Default password
                    else:
                        # For other emails, set a random password (user must reset via forgot password)
                        import secrets
                        user.set_password(secrets.token_urlsafe(32))
                    db.session.add(user)
                    db.session.commit()
                    print(f"✅ Created super_admin user: {email}")
                else:
                    # Update existing user to super_admin if not already
                    if user.role != 'super_admin':
                        user.role = 'super_admin'
                        db.session.commit()
                        print(f"✅ Upgraded {email} to super_admin role")
                    else:
                        print(f"✅ {email} already has super_admin role")
                
        except Exception as e:
            print(f"❌ Error creating database tables: {e}")
            import traceback
            traceback.print_exc()
            # Don't raise - allow app to start even if database init fails
            # Database can be initialized later or healthcheck will show it's not ready
            print("⚠️ Continuing without database initialization - app will start but database features may not work")
    
    return db

def create_tables():
    """Create all database tables"""
    with db.app.app_context():
        db.create_all()
