#!/usr/bin/env python3
"""
Sync user role from Supabase to backend database.
This script ensures that user roles in the backend database match Supabase.
"""

import os
import sys
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import psycopg2
from psycopg2.extras import RealDictCursor

# Supabase connection string (hardcoded to ensure we always use Supabase)
SUPABASE_URL = "postgresql://postgres.pqdxqvxyrahvongbhtdb:Kopenikus0218!@aws-1-eu-west-1.pooler.supabase.com:6543/postgres"

def get_backend_db_url():
    """Get the backend database URL from environment or use Supabase"""
    database_url = os.getenv('DATABASE_URL')
    
    # Check if Railway is auto-provisioning a database
    is_railway_db = database_url and ('railway.app' in database_url or 'railway.internal' in database_url or 'containers-us-west' in database_url)
    
    # If Railway DB detected, prefer explicit Supabase URL from environment
    if is_railway_db:
        print("[WARN] [SYNC] Railway auto-provisioned database detected!")
        supabase_url = os.getenv('SUPABASE_DATABASE_URL')
        if supabase_url:
            print("[OK] [SYNC] Using explicit Supabase URL from SUPABASE_DATABASE_URL")
            database_url = supabase_url
        else:
            # Use hardcoded Supabase connection as fallback
            print("[WARN] [SYNC] No explicit Supabase URL found, using hardcoded Supabase connection")
            database_url = SUPABASE_URL
    
    if not database_url:
        # Fallback to SQLite for local development
        database_url = 'sqlite:///trevnoctilla_api.db'
        print("[WARN] [SYNC] DATABASE_URL not set - using SQLite fallback")
    
    # Handle PostgreSQL URL format for SQLAlchemy
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
    
    return database_url

def sync_user_role(email=None):
    """
    Sync user role from Supabase to backend database.
    If email is provided, sync only that user. Otherwise, sync all users.
    """
    try:
        # Connect to Supabase
        print(f" Connecting to Supabase...")
        supabase_conn = psycopg2.connect(SUPABASE_URL, sslmode='require')
        supabase_cursor = supabase_conn.cursor(cursor_factory=RealDictCursor)
        
        # Get backend database URL
        backend_db_url = get_backend_db_url()
        print(f" Connecting to backend database...")
        print(f"   Backend DB: {backend_db_url.split('@')[-1] if '@' in backend_db_url else backend_db_url}")
        
        # Connect to backend database
        backend_engine = create_engine(backend_db_url)
        backend_session = sessionmaker(bind=backend_engine)()
        
        # Query Supabase for users
        if email:
            print(f"[FETCH] Fetching user '{email}' from Supabase...")
            supabase_cursor.execute(
                "SELECT id, email, role, is_active FROM users WHERE email = %s",
                (email.lower(),)
            )
        else:
            print(f"[FETCH] Fetching all users from Supabase...")
            supabase_cursor.execute(
                "SELECT id, email, role, is_active FROM users ORDER BY email"
            )
        
        supabase_users = supabase_cursor.fetchall()
        
        if not supabase_users:
            print(f"[ERROR] No users found in Supabase" + (f" with email '{email}'" if email else ""))
            return
        
        print(f"[OK] Found {len(supabase_users)} user(s) in Supabase\n")
        
        # Sync each user
        synced_count = 0
        updated_count = 0
        not_found_count = 0
        
        for supabase_user in supabase_users:
            user_email = supabase_user['email']
            supabase_role = supabase_user['role']
            supabase_id = supabase_user['id']
            supabase_is_active = supabase_user['is_active']
            
            print(f"[RELOAD] Syncing user: {user_email}")
            print(f"   Supabase Role: {supabase_role}")
            print(f"   Supabase ID: {supabase_id}")
            print(f"   Supabase Active: {supabase_is_active}")
            
            # Check if user exists in backend database
            if backend_db_url.startswith('sqlite'):
                # SQLite
                result = backend_session.execute(
                    text("SELECT id, email, role, is_active FROM users WHERE email = :email"),
                    {"email": user_email.lower()}
                )
            else:
                # PostgreSQL
                result = backend_session.execute(
                    text("SELECT id, email, role, is_active FROM users WHERE email = :email"),
                    {"email": user_email.lower()}
                )
            
            backend_user = result.fetchone()
            
            if not backend_user:
                print(f"   [WARN]  User not found in backend database - skipping")
                not_found_count += 1
                continue
            
            backend_role = backend_user.role if hasattr(backend_user, 'role') else backend_user[2]
            backend_id = backend_user.id if hasattr(backend_user, 'id') else backend_user[0]
            
            print(f"   Backend Role: {backend_role}")
            print(f"   Backend ID: {backend_id}")
            
            # Check if roles match
            if backend_role == supabase_role:
                print(f"   [OK] Roles match - no update needed")
                synced_count += 1
            else:
                print(f"   [RELOAD] Roles differ - updating backend role from '{backend_role}' to '{supabase_role}'")
                
                # Update role in backend database
                if backend_db_url.startswith('sqlite'):
                    # SQLite
                    backend_session.execute(
                        text("UPDATE users SET role = :role, is_active = :is_active WHERE email = :email"),
                        {
                            "role": supabase_role,
                            "is_active": supabase_is_active,
                            "email": user_email.lower()
                        }
                    )
                else:
                    # PostgreSQL
                    backend_session.execute(
                        text("UPDATE users SET role = :role, is_active = :is_active WHERE email = :email"),
                        {
                            "role": supabase_role,
                            "is_active": supabase_is_active,
                            "email": user_email.lower()
                        }
                    )
                
                backend_session.commit()
                print(f"   [OK] Updated backend role to '{supabase_role}'")
                updated_count += 1
            
            print()
        
        # Summary
        print("=" * 80)
        print("[INFO] SYNC SUMMARY")
        print("=" * 80)
        print(f"Total users in Supabase: {len(supabase_users)}")
        print(f"Already synced (no changes): {synced_count}")
        print(f"Updated: {updated_count}")
        print(f"Not found in backend: {not_found_count}")
        print("=" * 80)
        
        # Close connections
        supabase_cursor.close()
        supabase_conn.close()
        backend_session.close()
        backend_engine.dispose()
        
        print("\n[OK] Sync completed successfully!")
        
    except Exception as e:
        print(f"\n[ERROR] Error during sync: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Sync user roles from Supabase to backend database")
    parser.add_argument("--email", type=str, help="Sync only this specific user email")
    
    args = parser.parse_args()
    
    if args.email:
        sync_user_role(email=args.email)
    else:
        print("[WARN]  Syncing ALL users from Supabase to backend database...")
        print("   Use --email <email> to sync a specific user\n")
        sync_user_role()

