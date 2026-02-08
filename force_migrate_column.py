from app import app
from database import db
from sqlalchemy import text, inspect
import time

def force_migrate():
    with app.app_context():
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('campaigns')]
        
        if 'public_id' not in columns:
            print("Attempting to force add 'public_id' column...")
            try:
                # Try to kill anything blocking us (careful!)
                # But first just try to add with a longer timeout
                db.session.execute(text("SET STATEMENT_TIMEOUT TO '30s'"))
                db.session.execute(text("ALTER TABLE campaigns ADD COLUMN public_id VARCHAR(36)"))
                db.session.commit()
                print("Successfully added 'public_id' column!")
            except Exception as e:
                print(f"Error adding column: {e}")
                db.session.rollback()
                
                # If it's a lock wait timeout, we might need to try harder
                if "timeout" in str(e).lower() or "lock" in str(e).lower():
                    print("Migration is blocked by another process. Please stop any running campaigns and try again.")
        else:
            print("'public_id' column already exists.")

if __name__ == "__main__":
    force_migrate()
