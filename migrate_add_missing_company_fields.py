"""
Migration script to add missing fields to the companies table.
"""

from database import db
from sqlalchemy import text

def migrate():
    """Add missing fields to the companies table"""
    try:
        fields = [
            ('contact_method', 'VARCHAR(100)'),
            ('emails_found', 'JSON'),
            ('emails_sent', 'JSON'),
            ('email_sent_at', 'DATETIME'),
            ('form_structure', 'JSON'),
            ('field_mappings', 'JSON'),
            ('form_complexity', 'VARCHAR(50)'),
            ('pattern_learned', 'BOOLEAN DEFAULT FALSE')
        ]
        
        with db.engine.connect() as conn:
            for field_name, field_type in fields:
                # Check if column already exists
                result = conn.execute(text(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name='companies' AND column_name='{field_name}'
                """))
                
                if result.fetchone():
                    print(f"[OK] {field_name} column already exists in companies table")
                else:
                    print(f"[MIGRATE] Adding {field_name} column to companies table...")
                    conn.execute(text(f"ALTER TABLE companies ADD COLUMN {field_name} {field_type}"))
                    conn.commit()
            
        print("[SUCCESS] Migration completed successfully")
        return True
        
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        return False

if __name__ == "__main__":
    from app import app
    with app.app_context():
        migrate()
