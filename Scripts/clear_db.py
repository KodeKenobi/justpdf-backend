import os
import sys

# Add the parent directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from database import db
from models import Campaign, Company, ScrapingSession, AnalyticsEvent, PageView, UserSession, SubmissionLog

def clear_campaign_data():
    with app.app_context():
        print("--- DATABASE CLEAN SLATE ---")
        try:
            # 1. Delete Scraping Sessions
            print("Cleaning up Scraping Sessions...")
            num_sessions = ScrapingSession.query.delete()
            print(f"Deleted {num_sessions} scraping sessions.")

            # 2. Delete Submission Logs
            print("Cleaning up Submission Logs...")
            num_logs = SubmissionLog.query.delete()
            print(f"Deleted {num_logs} submission logs.")

            # 3. Delete Companies
            print("Cleaning up Companies...")
            num_companies = Company.query.delete()
            print(f"Deleted {num_companies} companies.")

            # 4. Delete Campaigns
            print("Cleaning up Campaigns...")
            num_campaigns = Campaign.query.delete()
            print(f"Deleted {num_campaigns} campaigns.")

            # 5. Clear general analytics
            print("Cleaning up Analytics & Sessions...")
            num_events = AnalyticsEvent.query.delete()
            num_pvs = PageView.query.delete()
            num_sess = UserSession.query.delete()
            print(f"Deleted {num_events} analytics events, {num_pvs} page views, and {num_sess} user sessions.")

            db.session.commit()
            print("--- SUCCESS: All campaign data cleared from Supabase ---")
        except Exception as e:
            db.session.rollback()
            print(f"--- ERROR: Cleanup failed: {e} ---")

if __name__ == "__main__":
    clear_campaign_data()
