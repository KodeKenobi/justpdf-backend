"""
Supabase Sync Module
Syncs users to Supabase database after registration (non-blocking)
"""
import os
import threading
from datetime import datetime

def sync_user_to_supabase(user):
    """
    Sync user to Supabase database in background thread
    This is non-blocking and won't break registration if it fails
    """
    def sync_async():
        """Background thread function to sync user"""
        try:
            # Use hardcoded Supabase connection string (pooler format)
            # This ensures we always sync to Supabase regardless of DATABASE_URL setting
            database_url = "postgresql://postgres:Kopenikus0218!@db.pqdxqvxyrahvongbhtdb.supabase.co:5432/postgres"
            
            # Convert to pooler format (works better from local machines and Railway)
            if database_url and "db." in database_url and ".supabase.co" in database_url:
                import re
                match = re.match(r'postgresql?://([^:]+):([^@]+)@db\.([^.]+)\.supabase\.co:(\d+)/(.+)', database_url)
                if match:
                    user_part, password, project_ref, port, database = match.groups()
                    # Use pooler format without query parameters (psycopg2 doesn't support pgbouncer param)
                    database_url = f"postgresql://postgres.{project_ref}:{password}@aws-1-eu-west-1.pooler.supabase.com:6543/{database}"
            
            # Use psycopg2 for PostgreSQL connection
            try:
                import psycopg2
                from psycopg2.extras import RealDictCursor
            except ImportError:
                print("⚠️ [SUPABASE SYNC] psycopg2 not installed, skipping sync")
                return
            
            # Connect to Supabase
            conn = psycopg2.connect(database_url, sslmode='require')
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            
            # Check if user already exists in Supabase
            cursor.execute("""
                SELECT id FROM users WHERE email = %s
            """, (user.email,))
            existing = cursor.fetchone()
            
            if existing:
                # Update existing user (include password_hash so user can login after DB reset)
                cursor.execute("""
                    UPDATE users SET
                        password_hash = %s,
                        role = %s,
                        is_active = %s,
                        subscription_tier = %s,
                        monthly_call_limit = %s,
                        monthly_used = %s,
                        monthly_reset_date = %s,
                        last_login = %s
                    WHERE email = %s
                """, (
                    user.password_hash,  # Sync password hash so user can login
                    user.role,
                    user.is_active,
                    user.subscription_tier or 'free',
                    user.monthly_call_limit or 5,
                    user.monthly_used or 0,
                    user.monthly_reset_date if user.monthly_reset_date else datetime.utcnow(),
                    user.last_login if user.last_login else None,
                    user.email
                ))
                print(f"✅ [SUPABASE SYNC] Updated user in Supabase: {user.email}")
            else:
                # Insert new user (include password_hash so user can login after DB reset)
                cursor.execute("""
                    INSERT INTO users (email, password_hash, role, is_active, subscription_tier, 
                                     monthly_call_limit, monthly_used, monthly_reset_date, 
                                     created_at, last_login)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    user.email,
                    user.password_hash,  # Sync password hash so user can login
                    user.role,
                    user.is_active,
                    user.subscription_tier or 'free',
                    user.monthly_call_limit or 5,
                    user.monthly_used or 0,
                    user.monthly_reset_date if user.monthly_reset_date else datetime.utcnow(),
                    user.created_at if user.created_at else datetime.utcnow(),
                    user.last_login if user.last_login else None
                ))
                print(f"✅ [SUPABASE SYNC] Added user to Supabase: {user.email}")
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            # Don't break registration if sync fails
            print(f"⚠️ [SUPABASE SYNC] Failed to sync user {user.email} to Supabase: {e}")
            import traceback
            traceback.print_exc()
    
    # Start sync in background thread (non-daemon so it completes even if main thread ends)
    sync_thread = threading.Thread(target=sync_async, daemon=False)
    sync_thread.start()
    print(f"🔄 [SUPABASE SYNC] Started sync thread for user: {user.email}")

