from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
from datetime import datetime

db = SQLAlchemy()
migrate = Migrate()

def restore_users_from_supabase(db_session):
    """
    Restore users from Supabase to primary database if primary DB is empty.
    This is a safety net to prevent data loss when Railway database gets wiped.
    """
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        print("[WARN] [RESTORE] psycopg2 not installed, cannot restore from Supabase")
        return
    
    # Get Supabase connection string
    supabase_url = "postgresql://postgres.pqdxqvxyrahvongbhtdb:Kopenikus0218!@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    
    try:
        # Connect to Supabase
        conn = psycopg2.connect(supabase_url, sslmode='require')
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get all users from Supabase
        cursor.execute("""
            SELECT email, password_hash, role, is_active, subscription_tier,
                   monthly_call_limit, monthly_used, monthly_reset_date,
                   created_at, last_login
            FROM users
            ORDER BY created_at ASC
        """)
        supabase_users = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        if not supabase_users:
            print("[INFO] [RESTORE] No users found in Supabase to restore")
            return
        
        print(f"[FETCH] [RESTORE] Found {len(supabase_users)} users in Supabase - restoring to primary database...")
        
        from models import User
        restored_count = 0
        skipped_count = 0
        
        for supabase_user in supabase_users:
            email = supabase_user['email']
            
            # Check if user already exists in primary DB (shouldn't happen if count was 0, but double-check)
            existing = User.query.filter_by(email=email).first()
            if existing:
                skipped_count += 1
                continue
            
            # Create user in primary database
            user = User(
                email=email,
                password_hash=supabase_user['password_hash'],
                role=supabase_user.get('role', 'user'),
                is_active=supabase_user.get('is_active', True),
                subscription_tier=supabase_user.get('subscription_tier', 'free'),
                monthly_call_limit=supabase_user.get('monthly_call_limit', 5),
                monthly_used=supabase_user.get('monthly_used', 0),
                monthly_reset_date=supabase_user.get('monthly_reset_date') or datetime.utcnow(),
                created_at=supabase_user.get('created_at') or datetime.utcnow(),
                last_login=supabase_user.get('last_login')
            )
            
            db_session.add(user)
            restored_count += 1
        
        db_session.commit()
        print(f"[OK] [RESTORE] Successfully restored {restored_count} users from Supabase")
        if skipped_count > 0:
            print(f"   (Skipped {skipped_count} users that already existed)")
        
    except Exception as e:
        print(f"[ERROR] [RESTORE] Error restoring users from Supabase: {e}")
        import traceback
        traceback.print_exc()
        db_session.rollback()
        raise

def init_db(app):
    """Initialize database with the Flask app"""
    # Database configuration
    # CRITICAL: Prefer Supabase connection string to prevent Railway auto-provisioned DB override
    database_url = os.getenv('DATABASE_URL')
    
    # Check if Railway is auto-provisioning a database (Railway's DB URLs contain 'railway.app' or 'railway.internal')
    is_railway_db = database_url and ('railway.app' in database_url or 'railway.internal' in database_url or 'containers-us-west' in database_url)
    
    # If Railway DB detected, prefer explicit Supabase URL from environment
    if is_railway_db:
        print("[WARN] [DATABASE] Railway auto-provisioned database detected!")
        print(f"   Railway DB URL: {database_url[:50]}...")
        # Check for explicit Supabase URL in environment (Railway might set both)
        supabase_url = os.getenv('SUPABASE_DATABASE_URL') or os.getenv('SUPABASE_URL')
        if supabase_url:
            print("[OK] [DATABASE] Using explicit Supabase URL from SUPABASE_DATABASE_URL")
            database_url = supabase_url
        else:
            # Use hardcoded Supabase connection as fallback
            print("[WARN] [DATABASE] No explicit Supabase URL found, using hardcoded Supabase connection")
            database_url = "postgresql://postgres.pqdxqvxyrahvongbhtdb:Kopenikus0218!@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"
    
    if not database_url:
        # Fallback to SQLite for local development
        database_url = 'sqlite:///trevnoctilla_api.db'
        print("[WARN] [DATABASE] DATABASE_URL not set - using SQLite fallback")
    
    # Detect Supabase connection
    is_supabase = 'supabase.com' in database_url or 'supabase.co' in database_url
    is_sqlite = database_url.startswith('sqlite')
    
    # Log database type
    if is_supabase:
        # Mask password in logs
        masked_url = database_url.split('@')[1] if '@' in database_url else database_url
        print(f"[OK] [DATABASE] Using Supabase PostgreSQL: ...@{masked_url}")
    elif is_sqlite:
        print(f"[WARN] [DATABASE] Using SQLite: {database_url}")
    else:
        # Mask password in logs
        masked_url = database_url.split('@')[1] if '@' in database_url else database_url
        print(f"[INFO] [DATABASE] Using PostgreSQL: ...@{masked_url}")
    
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
                
                # Create missing tables (notifications, analytics tables, campaigns tables, etc.)
                missing_tables = []
                required_tables = ['notifications', 'analytics_events', 'page_views', 'user_sessions', 'campaigns', 'companies', 'submission_logs']
                
                for table_name in required_tables:
                    if table_name not in tables:
                        missing_tables.append(table_name)
                
                if missing_tables:
                    print(f"[LOAD] Creating missing tables: {', '.join(missing_tables)}...")
                    # Ensure all models are imported before creating tables
                    try:
                        from models import Notification, AnalyticsEvent, PageView, UserSession, Campaign, Company, SubmissionLog
                        db.create_all()  # This will create all missing tables
                        print(f"[OK] Created missing tables: {', '.join(missing_tables)}")
                    except Exception as e:
                        print(f"[WARN] Warning: Could not create missing tables: {e}")
                        import traceback
                        traceback.print_exc()
                        # Continue anyway - tables might be created later
            finally:
                # Cancel alarm if it was set
                if hasattr(signal, 'SIGALRM'):
                    signal.alarm(0)
            
            if 'users' in tables:
                # Table exists - check and add missing columns
                print("[RELOAD] Checking for missing columns...")
                columns = [col['name'] for col in inspector.get_columns('users')]
                
                if 'subscription_tier' not in columns:
                    print("[RELOAD] Migrating: Adding subscription_tier column...")
                    db.session.execute(text("ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(20) DEFAULT 'free'"))
                    db.session.commit()
                    print("[OK] Added subscription_tier")
                
                if 'monthly_call_limit' not in columns:
                    print("[RELOAD] Migrating: Adding monthly_call_limit column...")
                    db.session.execute(text("ALTER TABLE users ADD COLUMN monthly_call_limit INTEGER DEFAULT 5"))
                    db.session.commit()
                    print("[OK] Added monthly_call_limit")
                
                if 'monthly_used' not in columns:
                    print("[RELOAD] Migrating: Adding monthly_used column...")
                    db.session.execute(text("ALTER TABLE users ADD COLUMN monthly_used INTEGER DEFAULT 0"))
                    db.session.commit()
                    print("[OK] Added monthly_used")
                
                if 'monthly_reset_date' not in columns:
                    print("[RELOAD] Migrating: Adding monthly_reset_date column...")
                    # SQLite doesn't allow CURRENT_TIMESTAMP in ALTER TABLE, so add without default then update
                    db.session.execute(text("ALTER TABLE users ADD COLUMN monthly_reset_date DATETIME"))
                    # Update existing rows with current timestamp
                    from datetime import datetime
                    db.session.execute(text("UPDATE users SET monthly_reset_date = :now WHERE monthly_reset_date IS NULL"), {"now": datetime.utcnow()})
                    db.session.commit()
                    print("[OK] Added monthly_reset_date")
            
            # Check and migrate api_keys table for free tier fields
            if 'api_keys' in tables:
                print("[RELOAD] Checking api_keys table for missing free tier columns...")
                api_keys_columns = [col['name'] for col in inspector.get_columns('api_keys')]
                
                if 'is_free_tier' not in api_keys_columns:
                    print("[RELOAD] Migrating: Adding is_free_tier column to api_keys...")
                    # PostgreSQL uses BOOLEAN, SQLite uses INTEGER
                    if is_supabase or not is_sqlite:
                        db.session.execute(text("ALTER TABLE api_keys ADD COLUMN is_free_tier BOOLEAN DEFAULT FALSE"))
                    else:
                        db.session.execute(text("ALTER TABLE api_keys ADD COLUMN is_free_tier INTEGER DEFAULT 0"))
                    db.session.commit()
                    print("[OK] Added is_free_tier to api_keys")
                
                if 'free_tier_type' not in api_keys_columns:
                    print("[RELOAD] Migrating: Adding free_tier_type column to api_keys...")
                    db.session.execute(text("ALTER TABLE api_keys ADD COLUMN free_tier_type VARCHAR(50)"))
                    db.session.commit()
                    print("[OK] Added free_tier_type to api_keys")
                
                if 'granted_by' not in api_keys_columns:
                    print("[RELOAD] Migrating: Adding granted_by column to api_keys...")
                    db.session.execute(text("ALTER TABLE api_keys ADD COLUMN granted_by INTEGER"))
                    db.session.commit()
                    print("[OK] Added granted_by to api_keys")
                
                if 'granted_at' not in api_keys_columns:
                    print("[RELOAD] Migrating: Adding granted_at column to api_keys...")
                    db.session.execute(text("ALTER TABLE api_keys ADD COLUMN granted_at TIMESTAMP"))
                    db.session.commit()
                    print("[OK] Added granted_at to api_keys")
                
                if 'notes' not in api_keys_columns:
                    print("[RELOAD] Migrating: Adding notes column to api_keys...")
                    # PostgreSQL uses TEXT, SQLite uses TEXT
                    db.session.execute(text("ALTER TABLE api_keys ADD COLUMN notes TEXT"))
                    db.session.commit()
                    print("[OK] Added notes to api_keys")
            
            # Check and migrate usage_logs table for free tier field
            if 'usage_logs' in tables:
                print("[RELOAD] Checking usage_logs table for missing free tier column...")
                usage_logs_columns = [col['name'] for col in inspector.get_columns('usage_logs')]
                
                if 'is_free_tier' not in usage_logs_columns:
                    print("[RELOAD] Migrating: Adding is_free_tier column to usage_logs...")
                    # PostgreSQL uses BOOLEAN, SQLite uses INTEGER
                    if is_supabase or not is_sqlite:
                        db.session.execute(text("ALTER TABLE usage_logs ADD COLUMN is_free_tier BOOLEAN DEFAULT FALSE"))
                    else:
                        db.session.execute(text("ALTER TABLE usage_logs ADD COLUMN is_free_tier INTEGER DEFAULT 0"))
                    db.session.commit()
                    print("[OK] Added is_free_tier to usage_logs")
            
            # If users table doesn't exist, create all tables
            if 'users' not in tables:
                # Table doesn't exist - create all tables
                print("[LOAD] Creating database tables...")
                db.create_all()
                print("[OK] Database tables created successfully")
            
            # CRITICAL: Startup sync - restore users from Supabase if primary DB is empty
            # This prevents data loss when Railway database gets wiped on redeploy
            from models import User
            user_count = User.query.count()
            
            if user_count == 0:
                print("[WARN] [DATABASE] Primary database is empty - checking Supabase for users to restore...")
                try:
                    restore_users_from_supabase(db.session)
                except Exception as e:
                    print(f"[WARN] [DATABASE] Failed to restore users from Supabase: {e}")
                    import traceback
                    traceback.print_exc()
                    # Continue anyway - users can still register fresh
            
            # Ensure super admin users exist and have correct role
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
                    print(f"[OK] Created super_admin user: {email}")
                else:
                    # Update existing user to super_admin if not already
                    if user.role != 'super_admin':
                        user.role = 'super_admin'
                        db.session.commit()
                        print(f"[OK] Upgraded {email} to super_admin role")
                    else:
                        print(f"[OK] {email} already has super_admin role")
                
        except Exception as e:
            print(f"[ERROR] Error creating database tables: {e}")
            import traceback
            traceback.print_exc()
            # Don't raise - allow app to start even if database init fails
            # Database can be initialized later or healthcheck will show it's not ready
            print("[WARN] Continuing without database initialization - app will start but database features may not work")
    
    return db

def create_tables():
    """Create all database tables"""
    with db.app.app_context():
        db.create_all()
