import os
import sys

# Add the current directory to sys.path to import local modules
sys.path.append(os.getcwd())

from app import app
from database import db
from models import Campaign, Company
from sqlalchemy import func

def check_progress():
    with app.app_context():
        # Get the latest campaign (likely our test campaign)
        campaign = Campaign.query.order_by(Campaign.created_at.desc()).first()
        
        if not campaign:
            print("No campaigns found.")
            return

        print("=" * 60)
        print(f"CAMPAIGN PROGRESS: {campaign.name}")
        print("=" * 60)
        print(f"ID: {campaign.id}")
        print(f"Status: {campaign.status}")
        print(f"Total Companies: {campaign.total_companies}")
        print(f"Processed: {campaign.processed_count}")
        
        # Breakdown by status
        stats = db.session.query(
            Company.status, func.count(Company.id)
        ).filter(Company.campaign_id == campaign.id).group_by(Company.status).all()
        
        print("\nBreakdown by Status:")
        for status, count in stats:
            print(f"  {status:15}: {count}")
            
        if campaign.total_companies > 0:
            pct = (campaign.processed_count / campaign.total_companies) * 100
            print(f"\nOverall Progress: {pct:.2f}%")
        
        print(f"\nStarted At: {campaign.started_at}")
        print(f"Last Heartbeat: {campaign.last_heartbeat_at}")
        print("=" * 60)

if __name__ == "__main__":
    check_progress()
