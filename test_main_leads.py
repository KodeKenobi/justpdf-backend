import csv
import os
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# Add the current directory to sys.path to import local modules
sys.path.append(os.getcwd())

from app import app
from database import db
from models import Campaign, Company
from campaign_sequential import process_campaign_sequential

CSV_PATH = "../main-leads.csv"
CAMPAIGN_NAME = f"Full Scale Test - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}"
MESSAGE_TEMPLATE = "Hello, I am interested in your services. Please contact me."

def create_campaign_from_csv():
    print(f"Reading {CSV_PATH}...")
    companies_data = []
    with open(CSV_PATH, mode='r', encoding='utf-8') as f:
        reader = csv.reader(f)
        # Skip header if it exists (check first row for column names)
        first_row = next(reader)
        if "Company Name" in first_row or "Website" in first_row:
            print("Skipping header...")
        else:
            # Re-process first row as data
            companies_data.append(first_row)
            
        for row in reader:
            if not row or len(row) < 2:
                continue
            companies_data.append(row)

    print(f"Found {len(companies_data)} companies.")

    with app.app_context():
        db.session.rollback()
        # Create campaign
        campaign = Campaign(
            name=CAMPAIGN_NAME,
            message_template=MESSAGE_TEMPLATE,
            status='queued',
            total_companies=len(companies_data),
            spreadsheet_filename=os.path.basename(CSV_PATH)
        )
        db.session.add(campaign)
        db.session.commit()
        db.session.refresh(campaign)

        print(f"Created campaign: {campaign.id} - {campaign.name}")

        # Add companies in batches to be efficient
        batch_size = 100
        for i in range(0, len(companies_data), batch_size):
            batch = companies_data[i:i+batch_size]
            for row in batch:
                # Mapping:
                # 0: Company Name, 1: Website, 2: First Name, 3: Last Name, 5: Email, 6: Phone
                name = row[0]
                website = row[1]
                if not website.startswith('http'):
                    website = f"https://{website}"
                
                first_name = row[2] if len(row) > 2 else ""
                last_name = row[3] if len(row) > 3 else ""
                email = row[5] if len(row) > 5 else ""
                phone = row[6] if len(row) > 6 else ""
                
                company = Company(
                    campaign_id=campaign.id,
                    company_name=name,
                    website_url=website,
                    contact_person=f"{first_name} {last_name}".strip(),
                    contact_email=email,
                    phone=phone,
                    status='pending',
                    additional_data={
                        "title": row[4] if len(row) > 4 else "",
                        "industry": row[10] if len(row) > 10 else "",
                        "city": row[14] if len(row) > 14 else "",
                        "country": row[16] if len(row) > 16 else ""
                    }
                )
                db.session.add(company)
            db.session.commit()
            print(f"Added {min(i+batch_size, len(companies_data))}/{len(companies_data)} companies...")

        return campaign.id

def run_test(campaign_id):
    print(f"Starting processing for campaign {campaign_id}...")
    start_time = time.time()
    
    # Run the orchestrator
    # We call it directly within the app context to avoid subprocess overhead for the orchestrator itself
    with app.app_context():
        process_campaign_sequential(campaign_id)
        
    end_time = time.time()
    duration = end_time - start_time
    print(f"\nFinal Results for Campaign {campaign_id}:")
    print(f"Total Time: {duration:.2f} seconds ({duration/60:.2f} minutes)")

    with app.app_context():
        campaign = Campaign.query.get(campaign_id)
        print(f"Status: {campaign.status}")
        print(f"Total: {campaign.total_companies}")
        print(f"Processed: {campaign.processed_count}")
        print(f"Success: {campaign.success_count}")
        print(f"Failed: {campaign.failed_count}")
        print(f"Captcha: {campaign.captcha_count}")

if __name__ == "__main__":
    campaign_id = create_campaign_from_csv()
    run_test(campaign_id)
