from app import app
from database import db
from models import Campaign
import secrets
from sqlalchemy import text, inspect

def run():
    with app.app_context():
        # Column already added by database.py init_db logic
        campaigns = Campaign.query.filter(Campaign.public_id == None).all()
        print(f"Assigning IDs to {len(campaigns)} campaigns...")
        for c in campaigns:
            c.public_id = secrets.token_urlsafe(8)[:8]
        db.session.commit()
        print("Done!")

if __name__ == "__main__":
    run()
