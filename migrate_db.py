"""Standalone migration script to add subscription fields"""
import sqlite3
import os

# Find the database file - check multiple locations
possible_paths = [
    os.path.join(os.path.dirname(__file__), 'instance', 'trevnoctilla_api.db'),
    os.path.join(os.path.dirname(__file__), 'trevnoctilla_api.db'),
    os.path.join(os.path.dirname(__file__), 'local.db'),
    os.path.join(os.path.dirname(__file__), 'instance', 'local.db'),
]

db_path = None
for path in possible_paths:
    if os.path.exists(path):
        db_path = path
        break

if not db_path:
    print(f"❌ Database not found. Checked:")
    for path in possible_paths:
        print(f"   - {path}")
    # Create the instance directory and use default path
    instance_dir = os.path.join(os.path.dirname(__file__), 'instance')
    os.makedirs(instance_dir, exist_ok=True)
    db_path = os.path.join(instance_dir, 'trevnoctilla_api.db')
    print(f"📝 Will create database at: {db_path}")

print(f"📂 Found database at: {db_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

try:
    # Check if columns exist
    cursor.execute("PRAGMA table_info(users)")
    columns = [row[1] for row in cursor.fetchall()]
    print(f"📋 Existing columns: {columns}")
    
    # Add subscription_tier
    if 'subscription_tier' not in columns:
        print("🔄 Adding subscription_tier column...")
        cursor.execute("ALTER TABLE users ADD COLUMN subscription_tier VARCHAR(20) DEFAULT 'free'")
        print("✅ Added subscription_tier")
    else:
        print("⚠️ subscription_tier already exists")
    
    # Add monthly_call_limit
    if 'monthly_call_limit' not in columns:
        print("🔄 Adding monthly_call_limit column...")
        cursor.execute("ALTER TABLE users ADD COLUMN monthly_call_limit INTEGER DEFAULT 5")
        print("✅ Added monthly_call_limit")
    else:
        print("⚠️ monthly_call_limit already exists")
    
    # Add monthly_used
    if 'monthly_used' not in columns:
        print("🔄 Adding monthly_used column...")
        cursor.execute("ALTER TABLE users ADD COLUMN monthly_used INTEGER DEFAULT 0")
        print("✅ Added monthly_used")
    else:
        print("⚠️ monthly_used already exists")
    
    # Add monthly_reset_date
    if 'monthly_reset_date' not in columns:
        print("🔄 Adding monthly_reset_date column...")
        cursor.execute("ALTER TABLE users ADD COLUMN monthly_reset_date DATETIME DEFAULT CURRENT_TIMESTAMP")
        print("✅ Added monthly_reset_date")
    else:
        print("⚠️ monthly_reset_date already exists")
    
    conn.commit()
    print("✅ Migration completed successfully!")
    
    # Verify
    cursor.execute("PRAGMA table_info(users)")
    columns_after = [row[1] for row in cursor.fetchall()]
    print(f"📋 Columns after migration: {columns_after}")
    
except Exception as e:
    print(f"❌ Migration error: {e}")
    conn.rollback()
    raise
finally:
    conn.close()

