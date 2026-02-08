from app import app
from database import db
from models import Campaign
import secrets
from sqlalchemy import text, inspect

def migrate_public_ids():
    with app.app_context():
        # Ensure column exists first
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('campaigns')]
        
        if 'public_id' not in columns:
            print("Adding public_id column to campaigns table...")
            db.session.execute(text("ALTER TABLE campaigns ADD COLUMN public_id VARCHAR(20)"))
            db.session.commit()
            print("Column added.")

        # Populate IDs
        campaigns = Campaign.query.filter(Campaign.public_id == None).all()
        print(f"Found {len(campaigns)} campaigns needing public_id")
        
        for c in campaigns:
            c.public_id = secrets.token_urlsafe(8)[:8]
            print(f"Assigned {c.public_id} to campaign {c.id}")
        
        db.session.commit()
        print("Migration complete!")

if __name__ == "__main__":
    migrate_public_ids()
